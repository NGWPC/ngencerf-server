import logging
import traceback
import re
import time
import threading

from django.db import connections
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.utils import OperationalError as DjangoOperationalError
from psycopg import Error as PostgresDriverError  # psycopg3 always available

logger = logging.getLogger(__name__)

# ---- Rate limiting for retries ------------------------------------------------
# Keep diagnostics from spamming logs during retry loops (e.g., django-dbconn-retry).
# We log at most once per RATE_LIMIT_SECONDS for a given (alias, error signature).
RATE_LIMIT_SECONDS: float = 60.0
_last_diag_log: dict[tuple[str, str, str], float] = {}
_rl_lock = threading.Lock()

# ---- Patch guard (idempotency) -----------------------------------------------
_PATCHED = False


def _should_log(alias: str, exc: Exception) -> bool:
    """
    Decide whether to emit diagnostics for this failure based on a simple
    time-based rate limit keyed by alias + error signature.
    """
    err_type = f"{type(exc).__module__}.{type(exc).__name__}"
    # Use a short signature of the message to avoid massive keys; keeps identical
    # failures (like repeated timeouts) grouped.
    err_sig = str(exc)
    if len(err_sig) > 200:
        err_sig = err_sig[:200]  # trim to avoid long keys

    key = (alias, err_type, err_sig)
    now = time.monotonic()
    with _rl_lock:
        last = _last_diag_log.get(key, 0.0)
        if (now - last) >= RATE_LIMIT_SECONDS:
            _last_diag_log[key] = now
            return True

    # We still want to show *some* evidence that we suppressed a duplicate:
    logger.debug(
        f"[DB Diagnostics] Suppressing repeated diagnostics for alias='{alias}', "
        f"error={err_type} (last logged {now - last:.1f}s ago; threshold {RATE_LIMIT_SECONDS:.0f}s)."
    )
    return False


def _parse_statement_timeout(options_str: str | None) -> str | None:
    """
    Parse 'statement_timeout' from a PostgreSQL options string such as:
      '-c statement_timeout=10000ms -c search_path=public'
    Returns the value as a string (e.g., '10000ms') or None if not present.
    """
    if not options_str:
        return None
    # Look for 'statement_timeout=<value>' anywhere in the string.
    m = re.search(r"statement_timeout\s*=\s*(\S+)", options_str)
    return m.group(1) if m else None


def log_db_diagnostics_on_failure(alias: str = 'default', settings_dict: dict | None = None) -> None:
    """
    Log diagnostic information when a database connection fails.

    This includes:
      - The DB connection parameters (host, port, user, name).
      - Timeout-related config: CONN_MAX_AGE, OPTIONS.connect_timeout, OPTIONS.options (parsed for statement_timeout).
      - Connection usage statistics, IF we can get a cursor (often not possible on hard failures).

    Intended to help diagnose OperationalError / psycopg errors (timeouts, auth failures, etc.).
    """
    # 1) Connection parameters and timeouts (safe; do not require a live connection).
    try:
        if not settings_dict:
            settings_dict = connections[alias].settings_dict

        logger.error("Database settings used:")
        logger.error(f"  NAME: {settings_dict.get('NAME')}")
        logger.error(f"  USER: {settings_dict.get('USER')}")
        logger.error(f"  HOST: {settings_dict.get('HOST')}")
        logger.error(f"  PORT: {settings_dict.get('PORT')}")

        # Timeouts and related options
        opts = (settings_dict or {}).get('OPTIONS', {}) or {}
        conn_max_age = settings_dict.get('CONN_MAX_AGE')
        connect_timeout = opts.get('connect_timeout')
        options_raw = opts.get('options')

        stmt_timeout = _parse_statement_timeout(options_raw)

        logger.error("Timeout-related settings:")
        logger.error(f"  CONN_MAX_AGE: {conn_max_age!r}")
        logger.error(f"  OPTIONS.connect_timeout: {connect_timeout!r}")
        logger.error(f"  OPTIONS.options: {options_raw!r}")
        logger.error(f"  Parsed statement_timeout: {stmt_timeout!r}")
    except Exception as e:
        logger.error(f"[DB Diagnostics] Could not retrieve DB settings: {e}")

    # 2) Try to collect pg_stat_activity stats (best-effort; will usually fail on hard failures/timeouts).
    try:
        # If the failing alias can still give us a cursor, great; if not, this will raise.
        with connections[alias].cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FILTER (WHERE state = 'active') AS active,
                       COUNT(*) FILTER (WHERE state = 'idle')   AS idle,
                       COUNT(*)                                 AS total
                FROM pg_stat_activity
                WHERE datname = current_database();
            """)
            active, idle, total = cursor.fetchone()

            cursor.execute("SHOW max_connections;")
            max_conn = int(cursor.fetchone()[0])

            logger.error(
                f"[DB Stats on Failure] total={total}, active={active}, idle={idle}, "
                f"max={max_conn}, usage={total}/{max_conn} ({(total / max_conn) * 100:.1f}%)"
            )
    except Exception as stats_exc:
        # This is expected if the DB is completely unreachable or authentication failed.
        logger.error(f"[DB Stats] Could not retrieve connection stats: {stats_exc}")


def patch_connect_with_diagnostics() -> None:
    """
    Patch BaseDatabaseWrapper.connect() to log diagnostics on failures from either:
      - Django's OperationalError, or
      - psycopg3 driver errors (including timeouts, auth failures, etc.).

    Why patch connect() (not ensure_connection()):
      - Libraries like django-dbconn-retry wrap ensure_connection(), which eventually calls connect().
      - Catching at connect() ensures we see the *actual* driver error (e.g., psycopg.errors.ConnectionTimeout).

    Rate limiting:
      - To avoid logging identical diagnostics for every retry attempt, we log at most once per
        RATE_LIMIT_SECONDS per (alias, error signature).
    """
    global _PATCHED
    if _PATCHED:
        return  # idempotent: do not patch twice

    original_connect = BaseDatabaseWrapper.connect

    def wrapped_connect(self):
        try:
            return original_connect(self)
        except (DjangoOperationalError, PostgresDriverError) as e:
            if _should_log(self.alias, e):
                err_type = f"{type(e).__module__}.{type(e).__name__}"
                logger.error(f"[DB ERROR] connect() failed for alias '{self.alias}': {err_type}: {e}")
                logger.error("Traceback:\n" + "".join(traceback.format_exc()))
                # Use the wrapper’s settings_dict to avoid any state issues
                log_db_diagnostics_on_failure(self.alias, settings_dict=getattr(self, "settings_dict", None))
            # Always re-raise so normal retry/error handling continues.
            raise

    BaseDatabaseWrapper.connect = wrapped_connect
    _PATCHED = True
