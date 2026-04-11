"""
Shared Flask extensions — imported by app.py and route blueprints.
Initialized lazily via .init_app(app) to avoid circular imports.
"""
import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()

# Set RATELIMIT_ENABLED=0 in environment to disable (used in tests)
_limiter_enabled = os.environ.get("RATELIMIT_ENABLED", "1") != "0"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],          # no global limit — set per-route
    storage_uri="memory://",
    enabled=_limiter_enabled,
)
