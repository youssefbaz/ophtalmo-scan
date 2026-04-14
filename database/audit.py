import uuid, datetime, logging

logger = logging.getLogger(__name__)


# ─── ENHANCED AUDIT LOG (Step 5) ──────────────────────────────────────────────

def log_audit(db, action: str, table: str = "", record_id: str = "",
              user_id: str = "", patient_id: str = "",
              detail: str = "", ip: str = "", ua: str = "",
              # aliases used by auth.py / routes
              ip_address: str = "", user_agent: str = ""):
    """
    Append-only audit log.
    action : READ | CREATE | UPDATE | DELETE | LOGIN | LOGOUT | LOGIN_FAIL | 2FA_*
    """
    # Resolve aliases
    _ip = (ip_address or ip or "")[:45]
    _ua = (user_agent or ua or "")[:200]
    try:
        db.execute(
            "INSERT INTO audit_log "
            "(id,action,table_name,record_id,user_id,patient_id,detail,ip_address,user_agent,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4())[:12],
                action, table, record_id,
                user_id, patient_id, detail[:500],
                _ip, _ua,
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
    except Exception as exc:
        logger.warning(f"audit_log insert failed: {exc}")


def audit_read(db, table: str, record_id: str, patient_id: str = ""):
    """Convenience: log a READ access from the current Flask request context."""
    from security_utils import get_client_ip, get_user_agent
    from database.session import current_user
    u = current_user()
    log_audit(
        db, "READ", table, record_id,
        user_id=u["id"] if u else "",
        patient_id=patient_id,
        ip=get_client_ip(),
        ua=get_user_agent(),
    )


