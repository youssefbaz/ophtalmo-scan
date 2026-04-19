"""Recovery of stuck async work on app startup."""
import logging

logger = logging.getLogger(__name__)


def recover_pending_analyses(app) -> int:
    """Reset documents left in 'pending' analysis state after a previous crash/restart.

    Without this, a process crash during LLM analysis would leave documents
    stuck forever — the UI would spin and no retry would ever fire.
    """
    with app.app_context():
        try:
            from database import get_db
            db = get_db()
            stuck = db.execute(
                "UPDATE documents SET analysis_status='' WHERE analysis_status='pending'"
            ).rowcount
            if stuck:
                db.commit()
                logger.warning(
                    "Recovered %d document(s) stuck in 'pending' analysis state.", stuck
                )
            return stuck or 0
        except Exception as e:
            logger.warning("Pending analysis recovery failed: %s", e)
            return 0
