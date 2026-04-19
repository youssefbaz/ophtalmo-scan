"""APScheduler setup — daily email reminders, post-op gap check, encrypted backup.

Multi-worker safety: under gunicorn every worker imports the app and would
start its own scheduler → cron jobs fire N times. Require an explicit opt-in
(ENABLE_SCHEDULER=1) on exactly one worker or a dedicated singleton process.
"""
import os
import atexit
import logging

logger = logging.getLogger('apscheduler.startup')


def _should_run(debug: bool) -> bool:
    raw = os.environ.get('ENABLE_SCHEDULER', '').strip()
    if raw == '1':
        return True
    if raw == '0':
        return False
    if debug:
        return os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    logger.warning(
        "APScheduler not started — set ENABLE_SCHEDULER=1 on exactly one "
        "worker or a dedicated singleton process to enable scheduled jobs."
    )
    return False


def start_scheduler(app) -> object | None:
    """Start the scheduler when appropriate. Returns the scheduler or None."""
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    if not _should_run(debug):
        return None
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("APScheduler not installed — scheduled jobs disabled.")
        return None

    from routes.agenda import check_postop_gaps

    scheduler = BackgroundScheduler()

    scheduler.add_job(
        func=lambda: __import__('email_notif').send_rdv_email_reminders(app),
        trigger='cron', hour=8, minute=5,
        id='email_reminders', replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Scheduled job registered: email_reminders (daily 08:05)")

    scheduler.add_job(
        func=lambda: check_postop_gaps(app),
        trigger='cron', hour=7, minute=30,
        id='postop_gaps', replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Scheduled job registered: postop_gaps (daily 07:30)")

    def _run_backup():
        try:
            import backup as _bk
            path = _bk.run_backup()
            logger.info("Scheduled backup completed: %s", path)
        except Exception as e:
            logger.error("Scheduled backup failed: %s", e)

    scheduler.add_job(
        func=_run_backup,
        trigger='cron', hour=2, minute=0,
        id='daily_backup', replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info("Scheduled job registered: daily_backup (daily 02:00)")

    scheduler.start()
    logger.info(
        "APScheduler started — %d job(s): %s",
        len(scheduler.get_jobs()),
        [j.id for j in scheduler.get_jobs()]
    )

    def _shutdown():
        import logging as _logging
        prev = _logging.raiseExceptions
        _logging.raiseExceptions = False
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        finally:
            _logging.raiseExceptions = prev
    atexit.register(_shutdown)

    return scheduler
