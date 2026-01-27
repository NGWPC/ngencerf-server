import logging
import os
import platform
import signal
import threading
import time

# =====================================================================
# IMPORTANT — READ THIS FIRST
# =====================================================================
#
# This Gunicorn config EXPECTS that Gunicorn is started with:
#
#       --preload
#
# Without --preload:
#   • Django is NOT loaded in the master process
#   • settings are unavailable
#   • when_ready() cannot safely access Django APIs
#
# With --preload:
#   • Django loads ONCE in the MASTER
#   • Workers fork from an initialized Django state
#
# runCerf.sh script already uses --preload.
#
# =====================================================================

# ============================================================
# Gunicorn native logging settings (Option A — disable noise)
# ============================================================

# Disable access logs entirely
accesslog = None

# Disable Gunicorn's own stderr logging format
# (Django logging already handles everything cleanly)
errorlog = None

# Gunicorn logging controls
# Set to "debug" (or pass --log-level debug) to get more Gunicorn arbiter/worker lifecycle logs.
loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")
capture_output = False

# IMPORTANT:
# Leave this False to avoid globally disabling pre-existing loggers created during --preload.
# (Django's LOGGING already controls noise.)
disable_existing_loggers = False


def _env_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


# Enable extra diagnostics only when explicitly requested
_DIAG = _env_bool("GUNICORN_DIAGNOSTICS", False)
_DIAG_POLL_SECONDS = int(os.getenv("GUNICORN_DIAGNOSTICS_POLL_SECONDS", "10"))


# =====================================================================
# 1. Hook: Configure Gunicorn loggers to use Django handlers
# =====================================================================

def _configure_logging(worker=None):
    """
    Route Gunicorn (and Uvicorn) logs through Django's handlers so they land in ngencerf.log,
    without globally disabling loggers.

    Notes:
    - Attach Django root handlers to gunicorn.* and uvicorn.* loggers.
    - Set propagate=False so records don't bubble up and get handled twice.
    - De-dupe by handler object id to avoid re-attaching on reload/respawn.
    """
    try:
        # Django logging handlers should already be installed because --preload loads
        # the app in the master before when_ready(), and workers inherit that state at fork.
        django_root = logging.getLogger()
        django_handlers = django_root.handlers

        level_name = loglevel.upper()
        level = getattr(logging, level_name, logging.INFO)

        for name in (
            "gunicorn.error",
            "gunicorn.access",
            "uvicorn",
            "uvicorn.error",
            "uvicorn.access",
            "uvicorn.asgi",
        ):
            glog = logging.getLogger(name)
            glog.setLevel(level)
            glog.propagate = False

            existing = {id(h) for h in glog.handlers}
            for h in django_handlers:
                if id(h) not in existing:
                    glog.addHandler(h)

    except Exception as e:
        # Early import failures are expected before Django initializes.
        print(f"[gunicorn_conf] Logging hook failed (safe to ignore early): {e}")


def _log_signal_handlers(logger: logging.Logger, where: str) -> None:
    """Log current signal handlers (master only)."""

    def _h(sig_name: str) -> str:
        sig = getattr(signal, sig_name, None)
        if sig is None:
            return "<missing>"
        try:
            return repr(signal.getsignal(sig))
        except Exception as e:
            return f"<error: {e}>"

    logger.info(
        "[gunicorn_conf] %s signal handlers: SIGCHLD=%s SIGTERM=%s SIGINT=%s SIGHUP=%s SIGQUIT=%s SIGUSR1=%s SIGUSR2=%s",
        where,
        _h("SIGCHLD"),
        _h("SIGTERM"),
        _h("SIGINT"),
        _h("SIGHUP"),
        _h("SIGQUIT"),
        _h("SIGUSR1"),
        _h("SIGUSR2"),
    )


def _start_sigchld_monitor(logger: logging.Logger) -> None:
    """
    Very low-risk diagnostic: periodically check SIGCHLD handler in the master
    and log ONLY if it changes.
    """
    try:
        last = signal.getsignal(signal.SIGCHLD)
    except Exception as e:
        logger.warning("[gunicorn_conf] SIGCHLD monitor could not read handler: %s", e)
        return

    def _run():
        nonlocal last
        while True:
            time.sleep(_DIAG_POLL_SECONDS)
            try:
                cur = signal.getsignal(signal.SIGCHLD)
            except Exception:
                continue
            if cur != last:
                logger.warning("[gunicorn_conf] SIGCHLD handler changed: %r -> %r", last, cur)
                last = cur

    t = threading.Thread(target=_run, name="sigchld-monitor", daemon=True)
    t.start()


# =====================================================================
# 2. Hook: Master is starting (Django not yet loaded here)
# =====================================================================

def on_starting(_server):
    logging.getLogger("gunicorn.error").info("[gunicorn_conf] Master starting up (PID=%s)", os.getpid())


# =====================================================================
# 3. Hook: Master is ready AFTER preload (Django loaded HERE)
# =====================================================================

def when_ready(_server):
    """
    Runs once in the master AFTER Django is loaded.
    Just configure logging + optional diagnostics.
    """
    _configure_logging()

    logger = logging.getLogger("gunicorn.error")
    logger.info("[gunicorn_conf] Master ready (PID=%s)", os.getpid())

    try:
        import gunicorn  # type: ignore
        logger.info("[gunicorn_conf] gunicorn=%s", getattr(gunicorn, "__version__", "<unknown>"))
    except Exception:
        pass
    try:
        import uvicorn  # type: ignore
        logger.info("[gunicorn_conf] uvicorn=%s", getattr(uvicorn, "__version__", "<unknown>"))
    except Exception:
        pass

    _log_signal_handlers(logger, "when_ready(master)")

    # Background diagnostic thread: periodically checks the master's SIGCHLD handler
    # and logs only if it changes, to detect external code or libraries interfering
    # with Gunicorn's child-process signal handling.
    if _DIAG:
        logger.info(
            "[gunicorn_conf] DIAGNOSTICS enabled. python=%s platform=%s",
            platform.python_version(),
            platform.platform(),
        )
        _start_sigchld_monitor(logger)


def pre_fork(_server, worker):
    """
    Runs in the master just before forking a worker.
    Useful to confirm the master is attempting respawns.
    """
    if _DIAG:
        logging.getLogger("gunicorn.error").info(
            "[gunicorn_conf] pre_fork: about to fork worker (worker_tmp=%s)",
            getattr(worker, "tmp", None)
        )


# =====================================================================
# 4. Hook: Worker initialization (per worker)
# =====================================================================

def post_fork(_server, worker):
    """
    Runs once for each worker (initial and respawned).
    Configure logging and enforce umask per worker.
    """

    # Ensure the worker does not reuse any DB connections inherited from the master.
    try:
        from django.db import connections
        connections.close_all()
    except Exception:
        # If Django isn't ready for any reason, don't break worker boot.
        pass

    _configure_logging(worker)

    # Enforce umask per-worker
    os.umask(0o022)

    worker.log.info("[gunicorn_conf] post_fork: Worker started PID=%s with umask=022", worker.pid)


# =====================================================================
# 5. Hook: Worker exiting
# =====================================================================

def worker_exit(_server, worker):
    logging.getLogger("gunicorn.error").warning("[gunicorn_conf] worker_exit: Worker PID=%s exiting", worker.pid)


# =====================================================================
# 6. Optional debugging hooks
# =====================================================================

def worker_int(worker):
    worker.log.warning("[gunicorn_conf] worker_int: Worker %s got SIGINT", worker.pid)


def worker_abort(worker):
    worker.log.error("[gunicorn_conf] worker_abort: Worker %s aborted", worker.pid)
