"""
routes/patients_account.py — Patient account management, invitations, and assignment.
"""
import uuid, logging
from flask import Blueprint, request, jsonify
from database import get_db, current_user, log_audit
from security_utils import decrypt_patient

logger = logging.getLogger(__name__)

bp = Blueprint('patients_account', __name__)


@bp.route('/api/patients/<pid>/has-account', methods=['GET'])
def has_account(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"has_account": False}), 403
    db = get_db()
    row = db.execute("SELECT id, username FROM users WHERE patient_id=? AND role='patient'", (pid,)).fetchone()
    if row:
        return jsonify({"has_account": True, "username": row['username']})
    return jsonify({"has_account": False})


@bp.route('/api/patients/<pid>/create-account', methods=['POST'])
def create_patient_account(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    p = db.execute(
        "SELECT * FROM patients WHERE id=? AND (deleted IS NULL OR deleted=0)", (pid,)
    ).fetchone()
    if not p:
        return jsonify({"error": "Patient non trouvé"}), 404
    existing = db.execute("SELECT id FROM users WHERE patient_id=?", (pid,)).fetchone()
    if existing:
        return jsonify({"error": "Ce patient a déjà un compte"}), 409

    data     = request.json or {}
    username = (data.get('username') or
                f"patient.{p['prenom'].lower().replace(' ','-')}.{p['nom'].lower().replace(' ','-')}")
    password = data.get('password') or str(uuid.uuid4())[:10]

    base_username = username
    counter = 1
    while db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        username = f"{base_username}{counter}"
        counter += 1

    # Decrypt PII before use — p['email'] is stored as a Fernet token
    patient = decrypt_patient(dict(p))

    # Allow the doctor to override / update the email in the same request
    email_to_use = (data.get('email') or '').strip() or patient.get('email', '')

    # Persist updated email back to patients table if the doctor provided a new one
    if data.get('email') and data['email'].strip() and data['email'].strip() != patient.get('email', ''):
        from security_utils import encrypt_patient_fields
        new_pii = encrypt_patient_fields({"email": data['email'].strip()})
        db.execute("UPDATE patients SET email=? WHERE id=?", (new_pii['email'], pid))

    from werkzeug.security import generate_password_hash
    uid = "U" + str(uuid.uuid4())[:6].upper()
    db.execute(
        "INSERT INTO users (id, username, password_hash, role, nom, prenom, patient_id, status) VALUES (?,?,?,?,?,?,?,?)",
        (uid, username, generate_password_hash(password), 'patient', p['nom'], p['prenom'], pid, 'active')
    )
    db.commit()

    email_sent = False
    if email_to_use and '@' in email_to_use:
        try:
            from email_notif import send_credentials_email
            host = request.host_url.rstrip('/')
            email_sent = send_credentials_email(
                email_to_use, patient['prenom'], patient['nom'], username, password, host
            )
        except Exception:
            pass

    return jsonify({"ok": True, "username": username, "password": password,
                    "email_sent": email_sent, "email": email_to_use})


@bp.route('/api/patients/unassigned', methods=['GET'])
def get_unassigned_patients():
    """Return patients with no assigned doctor. Médecin only."""
    u = current_user()
    if not u or u['role'] not in ('medecin', 'admin'):
        return jsonify([]), 403
    db   = get_db()
    rows = db.execute(
        "SELECT * FROM patients WHERE (medecin_id IS NULL OR medecin_id = '') "
        "AND (deleted IS NULL OR deleted=0) ORDER BY created_at DESC"
    ).fetchall()
    result = []
    for row in rows:
        p = decrypt_patient(dict(row))
        acc = db.execute("SELECT username FROM users WHERE patient_id=?", (p['id'],)).fetchone()
        p['has_account'] = acc is not None
        p['username']    = acc['username'] if acc else None
        result.append(p)
    return jsonify(result)


@bp.route('/api/patients/<pid>/claim', methods=['POST'])
def claim_patient(pid):
    """Assign an unassigned patient to the current doctor."""
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db  = get_db()
    row = db.execute(
        "SELECT * FROM patients WHERE id=? AND (deleted IS NULL OR deleted=0)", (pid,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Patient non trouvé"}), 404
    if row['medecin_id'] and row['medecin_id'] != '':
        return jsonify({"error": "Ce patient est déjà assigné à un médecin"}), 409
    db.execute("UPDATE patients SET medecin_id=? WHERE id=?", (u['id'], pid))
    log_audit(db, 'patient_claimed', 'patients', pid, user_id=u['id'],
              detail=f"medecin_id={u['id']}")
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/send-invite', methods=['POST'])
def send_patient_invite(pid):
    """Generate a one-time registration link and send it to the patient's email."""
    import secrets as _sec, datetime as _dt
    u = current_user()
    if not u or u['role'] not in ('medecin', 'admin'):
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    p = db.execute(
        "SELECT * FROM patients WHERE id=? AND (deleted IS NULL OR deleted=0)", (pid,)
    ).fetchone()
    if not p:
        return jsonify({"error": "Patient non trouvé"}), 404

    patient = decrypt_patient(dict(p))
    email   = patient.get('email', '').strip()
    if not email or '@' not in email:
        return jsonify({"error": "Ce patient n'a pas d'adresse email enregistrée."}), 400

    existing = db.execute("SELECT id FROM users WHERE patient_id=?", (pid,)).fetchone()
    if existing:
        return jsonify({"error": "Ce patient possède déjà un compte."}), 409

    db.execute("DELETE FROM patient_invitations WHERE patient_id=? AND used=0", (pid,))
    token      = _sec.token_urlsafe(32)
    expires_at = (_dt.datetime.now() + _dt.timedelta(hours=72)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO patient_invitations (token, patient_id, expires_at, used) VALUES (?,?,?,0)",
        (token, pid, expires_at)
    )
    db.commit()

    try:
        import html as _html
        from email_notif import send_email
        host       = request.host_url.rstrip('/')
        invite_url = f"{host}/?invite={token}"
        h_prenom   = _html.escape(patient['prenom'])
        h_nom      = _html.escape(patient['nom'])
        body = f"""
<html><body style="font-family:Arial,sans-serif;color:#222;background:#f5f5f5;padding:24px">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
  <div style="background:#0e7a76;padding:22px 28px">
    <div style="font-size:22px;font-weight:bold;color:#fff">👁 OphtalmoScan</div>
    <div style="font-size:13px;color:rgba(255,255,255,.8);margin-top:4px">Votre espace patient</div>
  </div>
  <div style="padding:28px">
    <h2 style="color:#0e7a76;margin-top:0">Créez votre compte patient</h2>
    <p>Bonjour <strong>{h_prenom} {h_nom}</strong>,</p>
    <p>Votre médecin vous invite à créer votre compte sur OphtalmoScan pour accéder à votre dossier médical en ligne.</p>
    <div style="text-align:center;margin:24px 0">
      <a href="{invite_url}" style="background:#0e7a76;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block">
        Créer mon compte
      </a>
    </div>
    <p style="color:#6b7280;font-size:13px">Ce lien est valable 72 heures et ne peut être utilisé qu'une seule fois.</p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0">
    <p style="color:#9ca3af;font-size:11px;margin:0">— OphtalmoScan · Ce message est généré automatiquement</p>
  </div>
</div>
</body></html>"""
        send_email(email, "Invitation à créer votre compte OphtalmoScan", body)
    except Exception:
        pass

    return jsonify({"ok": True})
