import logging
import traceback

from django.db import connections
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.utils import OperationalError

logger = logging.getLogger(__name__)


def log_db_diagnostics_on_failure(alias='default'):
    """
    Log diagnostic information when a database connection fails.

    This includes:
      - The DB connection parameters (host, port, user, name).
      - Connection usage statistics, if the connection is valid enough to run queries.

    Intended to help diagnose OperationalError exceptions, especially timeouts or connection refusals.
    """
    try:
        settings_dict = connections[alias].settings_dict
        logger.error("Database settings used:")
        logger.error(f"  NAME: {settings_dict.get('NAME')}")
        logger.error(f"  USER: {settings_dict.get('USER')}")
        logger.error(f"  HOST: {settings_dict.get('HOST')}")
        logger.error(f"  PORT: {settings_dict.get('PORT')}")
    except Exception as e:
        logger.warning(f"Could not retrieve DB settings: {e}")

    # Attempt to log pg_stat_activity connection info if we're connected far enough to run a query
    try:
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
        # This will often fail if the DB is completely unreachable
        logger.warning(f"[DB Stats] Could not retrieve connection stats: {stats_exc}")


def patch_connect_with_diagnostics():
    """
    Monkey-patch the BaseDatabaseWrapper.connect() method to inject diagnostics on failure.

    Why patch connect() instead of ensure_connection():
      - Some libraries like django-dbconn-retry override ensure_connection() early in startup.
      - Those wrappers eventually call connect(), so patching connect() ensures we capture all final failures.
      - This gives us visibility even if ensure_connection() is retried multiple times upstream.

    On OperationalError:
      - Log a formatted traceback.
      - Log database connection settings.
      - Attempt to log connection stats (active/idle/total).
    """
    original_connect = BaseDatabaseWrapper.connect

    def wrapped_connect(self, *args, **kwargs):
        try:
            return original_connect(self, *args, **kwargs)
        except OperationalError as e:
            logger.error(f"[DB ERROR] connect() failed for alias '{self.alias}': {e}")
            logger.error("Traceback:\n" + "".join(traceback.format_exc()))
            log_db_diagnostics_on_failure(self.alias)
            raise

    BaseDatabaseWrapper.connect = wrapped_connect
