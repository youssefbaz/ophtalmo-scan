"""
Shared Flask extensions — imported by app.py and route blueprints.
Initialized lazily via .init_app(app) to avoid circular imports.
"""
import logging
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

logger = logging.getLogger(__name__)

csrf = CSRFProtect()

# Set RATELIMIT_ENABLED=0 in environment to disable (used in tests)
_limiter_enabled = os.environ.get("RATELIMIT_ENABLED", "1") != "0"

# Rate-limit storage: in a multi-worker deployment the default memory:// backend
# is per-process, so each worker tracks its own counters and the real effective
# limit is Nx what's configured. Set RATELIMIT_STORAGE_URI (e.g.
# redis://host:6379/0) in production so all workers share the same counters.
_storage_uri = os.environ.get("RATELIMIT_STORAGE_URI", "").strip() or "memory://"

if _storage_uri == "memory://" and os.environ.get("FLASK_ENV") == "production":
    logger.warning(
        "RATELIMIT_STORAGE_URI not set — using in-memory limiter. "
        "In a multi-worker deployment, per-IP limits will NOT be enforced "
        "globally. Set RATELIMIT_STORAGE_URI to a Redis URL in production."
    )

limiter = Limiter(
    key_func=get_remote_address,
    # Global safety net: 600 req/hour per IP across all API routes.
    # Tight limits on expensive endpoints are applied per-route below.
    default_limits=["600 per hour", "60 per minute"],
    storage_uri=_storage_uri,
    enabled=_limiter_enabled,
)
