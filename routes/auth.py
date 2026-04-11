import uuid
import secrets
import datetime
from flask import Blueprint, request, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db, current_user
from extensions import limiter

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute; 50 per hour")
def login():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row and check_password_hash(row['password_hash'], password):
        status = row['status'] if row['status'] else 'active'
        if status == 'pending':
            return jsonify({"ok": False, "error": "Votre compte est en attente de validation par l'administrateur."}), 403
        if status == 'rejected':
            return jsonify({"ok": False, "error": "Votre demande de compte a été refusée. Contactez l'administrateur."}), 403
        session.permanent = True
        session['username'] = username
        return jsonify({
            "ok": True,
            "id":    row['id'],
            "role":  row['role'],
            "nom":   row['nom'],
            "prenom": row['prenom'] or ''
        })
    return jsonify({"ok": False, "error": "Identifiants incorrects"}), 401


@bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.route('/me', methods=['GET'])
def me():
    u = current_user()
    if not u:
        return jsonify({"authenticated": False}), 401
    info = {
        "authenticated": True,
        "id":    u['id'],
        "role":  u['role'],
        "nom":   u['nom'],
        "prenom": u['prenom'] or ''
    }
    if u['role'] == 'patient':
        info['patient_id'] = u.get('patient_id')
    return jsonify(info)


@bp.route('/api/medecins', methods=['GET'])
def get_medecins():
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify([]), 403
    db = get_db()
    rows = db.execute(
        "SELECT id, nom, prenom, username FROM users WHERE role='medecin' ORDER BY nom"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/change-password', methods=['POST'])
def change_password():
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    data       = request.json or {}
    current_pw = data.get('current_password', '')
    new_pw     = data.get('new_password', '').strip()
    if not new_pw or len(new_pw) < 8:
        return jsonify({"error": "Le nouveau mot de passe doit faire au moins 8 caractères"}), 400
    db  = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (u['id'],)).fetchone()
    if not row or not check_password_hash(row['password_hash'], current_pw):
        return jsonify({"error": "Mot de passe actuel incorrect"}), 401
    db.execute("UPDATE users SET password_hash=? WHERE id=?",
               (generate_password_hash(new_pw), u['id']))
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/register', methods=['POST'])
def register():
    """Create a user account (doctor or patient). Reserved for logged-in doctors."""
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé — seul un médecin peut créer des comptes"}), 403

    data = request.json or {}
    username   = data.get('username', '').strip()
    password   = data.get('password', '').strip()
    role       = data.get('role', '').strip()
    nom        = data.get('nom', '').strip()
    prenom     = data.get('prenom', '').strip()
    patient_id = data.get('patient_id')

    if not all([username, password, role, nom]):
        return jsonify({"error": "Champs requis : username, password, role, nom"}), 400
    if role not in ('medecin', 'patient'):
        return jsonify({"error": "Rôle invalide (medecin | patient)"}), 400

    db = get_db()
    if db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
        return jsonify({"error": "Nom d'utilisateur déjà pris"}), 409

    uid = str(uuid.uuid4())[:8].upper()
    db.execute(
        "INSERT INTO users (id, username, password_hash, role, nom, prenom, patient_id) "
        "VALUES (?,?,?,?,?,?,?)",
        (uid, username, generate_password_hash(password), role, nom, prenom, patient_id)
    )
    db.commit()
    return jsonify({"ok": True, "id": uid, "username": username, "role": role}), 201


# ─── PUBLIC: PATIENT SELF-REGISTRATION ────────────────────────────────────────

@bp.route('/api/patient-register', methods=['POST'])
@limiter.limit("5 per hour")
def patient_register():
    """Patient self-registration using their patient ID as an invitation code."""
    data       = request.json or {}
    patient_id = data.get('patient_id', '').strip().upper()
    username   = data.get('username', '').strip()
    password   = data.get('password', '')

    if not all([patient_id, username, password]):
        return jsonify({"error": "Tous les champs sont requis"}), 400
    if len(username) < 3:
        return jsonify({"error": "L'identifiant doit contenir au moins 3 caractères"}), 400
    if len(password) < 8:
        return jsonify({"error": "Le mot de passe doit contenir au moins 8 caractères"}), 400

    db = get_db()
    p = db.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
    if not p:
        return jsonify({"error": "Code patient invalide. Vérifiez auprès de votre médecin."}), 400

    if db.execute("SELECT id FROM users WHERE patient_id=?", (patient_id,)).fetchone():
        return jsonify({"error": "Un compte existe déjà pour ce patient."}), 409

    if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        return jsonify({"error": "Cet identifiant est déjà pris, choisissez-en un autre."}), 409

    uid = "U" + str(uuid.uuid4())[:6].upper()
    db.execute(
        "INSERT INTO users (id, username, password_hash, role, nom, prenom, patient_id) "
        "VALUES (?,?,?,?,?,?,?)",
        (uid, username, generate_password_hash(password), 'patient',
         p['nom'], p['prenom'], patient_id)
    )
    db.commit()
    return jsonify({"ok": True}), 201


# ─── PUBLIC: FORGOT PASSWORD ───────────────────────────────────────────────────

@bp.route('/api/forgot-password', methods=['POST'])
@limiter.limit("5 per hour")
def forgot_password():
    data     = request.json or {}
    username = data.get('username', '').strip()

    # Always return the same message to prevent user enumeration
    _safe_msg = "Si un compte existe avec cet identifiant et qu'un email est associé, vous recevrez un lien de réinitialisation."

    if not username:
        return jsonify({"ok": True, "message": _safe_msg})

    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not user:
        return jsonify({"ok": True, "message": _safe_msg})

    # Resolve email: from users.email or via patient record
    email = user['email'] if user['email'] else None
    if not email and user['patient_id']:
        row = db.execute(
            "SELECT email FROM patients WHERE id=?", (user['patient_id'],)
        ).fetchone()
        if row and row['email']:
            email = row['email']

    # Invalidate any previous unused tokens for this user
    db.execute("DELETE FROM password_resets WHERE user_id=? AND used=0", (user['id'],))
    # Generate reset token (valid 2 hours)
    token      = secrets.token_urlsafe(32)
    expires_at = (datetime.datetime.now() + datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO password_resets (token, user_id, expires_at, used) VALUES (?,?,?,0)",
        (token, user['id'], expires_at)
    )
    db.commit()

    if email:
        try:
            from email_notif import send_email
            host     = request.host_url.rstrip('/')
            reset_url = f"{host}/?token={token}"
            body = f"""
<html><body style="font-family:Arial,sans-serif;color:#222;background:#f5f5f5;padding:24px">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
  <div style="background:#0e7a76;padding:22px 28px">
    <div style="font-size:22px;font-weight:bold;color:#fff">👁 OphtalmoScan</div>
  </div>
  <div style="padding:28px">
    <h2 style="color:#0e7a76;margin-top:0">Réinitialisation de mot de passe</h2>
    <p>Bonjour,</p>
    <p>Vous avez demandé la réinitialisation de votre mot de passe. Cliquez sur le bouton ci-dessous :</p>
    <div style="text-align:center;margin:24px 0">
      <a href="{reset_url}" style="background:#0e7a76;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block">
        Réinitialiser mon mot de passe
      </a>
    </div>
    <p style="color:#6b7280;font-size:13px">Ce lien expire dans 2 heures. Si vous n'avez pas fait cette demande, ignorez cet email.</p>
    <hr style="border:none;border-top:1px solid #e5e7eb;margin:20px 0">
    <p style="color:#9ca3af;font-size:11px;margin:0">— OphtalmoScan · Ce message est généré automatiquement</p>
  </div>
</div>
</body></html>"""
            send_email(email, "Réinitialisation de votre mot de passe — OphtalmoScan", body)
        except Exception:
            pass  # email failure is silent; token still valid for admin use

    return jsonify({"ok": True, "message": _safe_msg})


# ─── PUBLIC: RESET PASSWORD ────────────────────────────────────────────────────

@bp.route('/api/reset-password', methods=['POST'])
@limiter.limit("10 per hour")
def reset_password_public():
    data         = request.json or {}
    token        = data.get('token', '').strip()
    new_password = data.get('new_password', '')

    if not token or not new_password:
        return jsonify({"error": "Token et mot de passe requis"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "Le mot de passe doit contenir au moins 8 caractères"}), 400

    db  = get_db()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = db.execute(
        "SELECT * FROM password_resets WHERE token=? AND used=0 AND expires_at > ?",
        (token, now)
    ).fetchone()
    if not row:
        return jsonify({"error": "Lien invalide ou expiré. Faites une nouvelle demande."}), 400

    db.execute("UPDATE users SET password_hash=? WHERE id=?",
               (generate_password_hash(new_password), row['user_id']))
    db.execute("UPDATE password_resets SET used=1 WHERE token=?", (token,))
    db.commit()
    return jsonify({"ok": True})


# ─── PUBLIC: MÉDECIN SELF-REGISTRATION ────────────────────────────────────────

@bp.route('/api/register-medecin', methods=['POST'])
@limiter.limit("5 per hour")
def register_medecin():
    """Public endpoint for doctors to request an account (status=pending)."""
    data           = request.json or {}
    username       = data.get('username',       '').strip()
    password       = data.get('password',       '')
    nom            = data.get('nom',            '').strip()
    prenom         = data.get('prenom',         '').strip()
    email          = data.get('email',          '').strip()
    organisation   = data.get('organisation',   '').strip()
    date_naissance = data.get('date_naissance', '').strip()

    if not all([username, password, nom, prenom]):
        return jsonify({"error": "Champs requis : identifiant, mot de passe, nom, prénom"}), 400
    if len(username) < 3:
        return jsonify({"error": "L'identifiant doit contenir au moins 3 caractères"}), 400
    if len(password) < 8:
        return jsonify({"error": "Le mot de passe doit contenir au moins 8 caractères"}), 400

    db = get_db()
    if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        return jsonify({"error": "Cet identifiant est déjà pris, choisissez-en un autre."}), 409

    uid = "U" + str(uuid.uuid4())[:6].upper()
    db.execute(
        "INSERT INTO users (id,username,password_hash,role,nom,prenom,email,organisation,date_naissance,status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (uid, username, generate_password_hash(password),
         'medecin', nom, prenom, email, organisation, date_naissance, 'pending')
    )
    db.commit()
    return jsonify({"ok": True, "message": "Votre demande a été envoyée. Un administrateur validera votre compte sous peu."}), 201
