"""
database package — backward-compatible re-export of all public symbols.

All existing imports of the form:
    from database import get_db, current_user, log_audit, ...
continue to work without modification.

Sub-modules:
  connection    — DB_PATH, get_db, close_db, PostgreSQL adapter
  session       — current_user, require_role, next_medecin_code
  audit         — log_audit, audit_read
  notifications — add_notif
  lockout       — record_login_attempt, is_account_locked, MAX_ATTEMPTS
  migrations    — init_db (and internal _create_tables, _migrate, _seed_data)
"""

# Re-export everything that was previously importable from the flat database.py
from database.connection    import (get_db, close_db, DB_PATH, DATABASE,
                                     _USE_PG, _open_pg)
from database.session       import (current_user, require_role, next_medecin_code)
from database.audit         import (log_audit, audit_read)
from database.notifications import (add_notif,)
from database.lockout       import (record_login_attempt, is_account_locked,
                                     MAX_ATTEMPTS, LOCKOUT_MINUTES)
from database.migrations    import (init_db,)

__all__ = [
    "get_db", "close_db", "DB_PATH", "DATABASE",
    "current_user", "require_role", "next_medecin_code",
    "log_audit", "audit_read",
    "add_notif",
    "record_login_attempt", "is_account_locked", "MAX_ATTEMPTS", "LOCKOUT_MINUTES",
    "init_db",
]
