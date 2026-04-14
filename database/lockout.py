import uuid, datetime, logging

logger = logging.getLogger(__name__)


# ─── ACCOUNT LOCKOUT HELPERS (Step 3) ────────────────────────────────────────

MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 30


def record_login_attempt(db, user_id: str, ip: str, success: bool):
    db.execute(
        "INSERT INTO login_attempts (id,user_id,ip_address,success,created_at) "
        "VALUES (?,?,?,?,?)",
        (str(uuid.uuid4())[:12], user_id, ip, 1 if success else 0,
         datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    if not success:
        # Check if lockout threshold reached
        cutoff = (datetime.datetime.now() - datetime.timedelta(minutes=LOCKOUT_MINUTES)
                  ).strftime("%Y-%m-%d %H:%M:%S")
        row = db.execute(
            "SELECT COUNT(*) FROM login_attempts "
            "WHERE user_id=? AND success=0 AND created_at >= ?",
            (user_id, cutoff)
        ).fetchone()
        if row and row[0] >= MAX_ATTEMPTS:
            locked_until = (
                datetime.datetime.now() + datetime.timedelta(minutes=LOCKOUT_MINUTES)
            ).strftime("%Y-%m-%d %H:%M:%S")
            db.execute(
                "UPDATE users SET locked_until=? WHERE id=?", (locked_until, user_id)
            )
    db.commit()


def is_account_locked(user_row) -> tuple[bool, str]:
    """Returns (is_locked, unlock_time_str). Accepts sqlite3.Row or dict."""
    if user_row is None:
        return False, ""
    # sqlite3.Row supports key access but not .get(); convert safely
    try:
        locked_until = user_row["locked_until"]
    except (KeyError, IndexError):
        locked_until = None
    if not locked_until:
        return False, ""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if locked_until > now:
        return True, locked_until
    return False, ""


