"""Flask-Talisman security-headers initialisation."""
import logging

logger = logging.getLogger(__name__)


def init_talisman(app) -> None:
    """Apply CSP, HSTS, and related headers. HTTPS enforcement follows SESSION_COOKIE_SECURE."""
    try:
        from flask_talisman import Talisman
    except ImportError:
        logger.warning(
            "flask-talisman not installed — security headers not applied. "
            "Run: pip install flask-talisman"
        )
        return

    force_https = app.config.get('SESSION_COOKIE_SECURE', False)
    Talisman(
        app,
        force_https=force_https,
        strict_transport_security=force_https,
        strict_transport_security_max_age=31536000,
        content_security_policy={
            'default-src': ["'self'"],
            'script-src':  ["'self'", "'unsafe-inline'",
                            'cdn.jsdelivr.net', 'cdnjs.cloudflare.com'],
            'style-src':   ["'self'", "'unsafe-inline'",
                            'cdn.jsdelivr.net', 'fonts.googleapis.com'],
            'font-src':    ["'self'", 'fonts.gstatic.com', 'data:'],
            'img-src':     ["'self'", 'data:', 'blob:'],
            'connect-src': ["'self'"],
            'frame-ancestors': ["'none'"],
        },
        referrer_policy='strict-origin-when-cross-origin',
        feature_policy={
            'geolocation': "'none'",
            'camera':      "'none'",
            'microphone':  "'none'",
        },
        session_cookie_secure=force_https,
    )
    logger.info("Talisman initialised (force_https=%s)", force_https)
