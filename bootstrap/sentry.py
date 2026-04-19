"""Sentry error monitoring initialisation — opt-in via SENTRY_DSN."""
import os
import logging

logger = logging.getLogger(__name__)


def init_sentry() -> bool:
    """Initialise Sentry if SENTRY_DSN is set. Returns True when active."""
    dsn = os.environ.get('SENTRY_DSN', '').strip()
    if not dsn:
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        sentry_sdk.init(
            dsn=dsn,
            integrations=[FlaskIntegration()],
            traces_sample_rate=float(os.environ.get('SENTRY_TRACES_RATE', '0.05')),
            send_default_pii=False,
            environment=os.environ.get('SENTRY_ENVIRONMENT', 'production'),
            release=os.environ.get('SENTRY_RELEASE', ''),
        )
        logger.info("Sentry error monitoring initialised")
        return True
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed. "
            "Run: pip install sentry-sdk[flask]"
        )
        return False
