import datetime, logging
from functools import wraps
from flask import g, session, jsonify
from database.connection import get_db

logger = logging.getLogger(__name__)


# ─── SESSION HELPER ───────────────────────────────────────────────────────────

def current_user():
    if "current_user" in g:
        return g.current_user
    username = session.get("username")
    if not username:
        g.current_user = None
        return None
    row = get_db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    user = dict(row) if row else None
    if user:
        # Block inactive / non-active accounts immediately
        if user.get('status') not in ('active', None):
            session.clear()
            user = None
        # Also enforce account lockout on existing sessions
        elif user.get('locked_until'):
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if str(user['locked_until']) > now:
                session.clear()
                user = None
    g.current_user = user
    return g.current_user


# ─── ROLE DECORATOR ───────────────────────────────────────────────────────────

def require_role(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            u = current_user()
            if not u or u["role"] not in roles:
                return jsonify({"error": "Accès refusé"}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ─── MEDECIN CODE HELPER ──────────────────────────────────────────────────────

def next_medecin_code(db):
    row = db.execute(
        "SELECT MAX(CAST(SUBSTR(medecin_code,2) AS INTEGER)) FROM users "
        "WHERE medecin_code GLOB 'M[0-9]*'"
    ).fetchone()
    n = (row[0] or 0) + 1
    return f"M{n:03d}"


# ─── PATIENT ACCESS CONTROL ──────────────────────────────────────────────────

def medecin_can_access_patient(db, medecin_id: str, patient_id: str) -> bool:
    """True if the doctor owns the patient (primary medecin_id) or is linked
    via the patient_doctors junction table. Used to block cross-patient IDOR."""
    if not medecin_id or not patient_id:
        return False
    row = db.execute(
        "SELECT 1 FROM patients WHERE id=? AND medecin_id=? "
        "UNION ALL "
        "SELECT 1 FROM patient_doctors WHERE patient_id=? AND medecin_id=? "
        "LIMIT 1",
        (patient_id, medecin_id, patient_id, medecin_id)
    ).fetchone()
    return row is not None


