import uuid
import secrets
import hashlib
import datetime
from flask import Blueprint, request, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db, current_user, log_audit, record_login_attempt, is_account_locked, add_notif, next_medecin_code
from extensions import limiter
from security_utils import validate_password, sanitize, get_client_ip, get_user_agent, decrypt_patient, encrypt_patient_fields, decrypt_field

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['POST'])
@limiter.limit("10 per minute; 50 per hour")
def login():
    data     = request.json or {}
    username = sanitize(data.get('username', ''), max_len=150)
    password = data.get('password', '')
    ip       = get_client_ip()
    ua       = get_user_agent()

    db  = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

    if not row:
        # Still record attempt against a dummy id to avoid timing oracle
        return jsonify({"ok": False, "error": "Identifiants incorrects"}), 401

    # ── Account lockout check (Step 3) ─────────────────────────────────────────
    locked, unlock_time = is_account_locked(row)
    if locked:
        return jsonify({
            "ok": False,
            "error": f"Compte temporairement verrouillé suite à plusieurs tentatives échouées. "
                     f"Réessayez après {unlock_time}."
        }), 423

    # ── Password verification ──────────────────────────────────────────────────
    if not check_password_hash(row['password_hash'], password):
        record_login_attempt(db, row['id'], ip, success=False)
        db.commit()
        log_audit(db, 'login_failed', 'users', row['id'], user_id=row['id'], detail=f"ip={ip}", ip_address=ip, user_agent=ua)
        db.commit()
        return jsonify({"ok": False, "error": "Identifiants incorrects"}), 401

    # ── Account status ─────────────────────────────────────────────────────────
    status = row['status'] if row['status'] else 'active'
    if status == 'pending':
        return jsonify({"ok": False, "error": "Votre compte est en attente de validation par l'administrateur."}), 403
    if status in ('rejected', 'inactive'):
        return jsonify({"ok": False, "error": "Votre compte a été désactivé. Contactez l'administrateur."}), 403

    # ── Role tab check — ensure account role matches the selected login tab ────
    selected_role = sanitize(data.get('role', ''), max_len=20)
    if selected_role:
        actual_role = row['role']
        if selected_role == 'patient' and actual_role != 'patient':
            return jsonify({"ok": False, "error": "Ce compte n'est pas un compte patient. Veuillez sélectionner l'onglet Médecin."}), 403
        if selected_role == 'medecin' and actual_role == 'patient':
            return jsonify({"ok": False, "error": "Ce compte n'est pas un compte médecin. Veuillez sélectionner l'onglet Patient."}), 403

    # ── 2FA check (Step 3) ─────────────────────────────────────────────────────
    totp_enabled = row['totp_enabled'] if row['totp_enabled'] else 0
    if totp_enabled:
        totp_token = data.get('totp_token', '').strip()
        if not totp_token:
            # Signal client that TOTP is required without granting session
            return jsonify({"ok": False, "totp_required": True, "error": "Code 2FA requis"}), 200

        import pyotp
        totp = pyotp.TOTP(row['totp_secret'])
        if not totp.verify(totp_token, valid_window=1):
            # Try backup code as fallback (strip dashes, uppercase)
            code_clean = totp_token.replace('-', '').upper()
            code_hash  = hashlib.sha256(code_clean.encode()).hexdigest()
            backup = db.execute(
                "SELECT id FROM totp_backup_codes WHERE user_id=? AND code_hash=? AND used=0",
                (row['id'], code_hash)
            ).fetchone()
            if not backup:
                record_login_attempt(db, row['id'], ip, success=False)
                db.commit()
                log_audit(db, 'login_totp_failed', 'users', row['id'], user_id=row['id'],
                          detail=f"ip={ip}", ip_address=ip, user_agent=ua)
                db.commit()
                return jsonify({"ok": False, "error": "Code 2FA invalide ou expiré"}), 401
            # Valid backup code — mark it as used (single-use)
            db.execute(
                "UPDATE totp_backup_codes SET used=1, used_at=? WHERE id=?",
                (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), backup['id'])
            )
            log_audit(db, 'login_backup_code_used', 'users', row['id'], user_id=row['id'],
                      detail=f"ip={ip}", ip_address=ip, user_agent=ua)
            db.commit()

    # ── Success ────────────────────────────────────────────────────────────────
    record_login_attempt(db, row['id'], ip, success=True)
    db.commit()
    log_audit(db, 'login', 'users', row['id'], user_id=row['id'], detail=f"ip={ip}", ip_address=ip, user_agent=ua)
    db.commit()

    session.permanent = True
    session['username'] = username
    return jsonify({
        "ok":                   True,
        "id":                   row['id'],
        "role":                 row['role'],
        "nom":                  row['nom'],
        "prenom":               row['prenom'] or '',
        "force_password_change": bool(row['force_password_change']) if row['force_password_change'] else False,
    })


@bp.route('/logout', methods=['POST'])
def logout():
    u  = current_user()
    ip = get_client_ip()
    ua = get_user_agent()
    if u:
        db = get_db()
        log_audit(db, 'logout', 'users', u['id'], user_id=u['id'], detail=f"ip={ip}", ip_address=ip, user_agent=ua)
        db.commit()
    session.clear()
    return jsonify({"ok": True})


@bp.route('/me', methods=['GET'])
def me():
    u = current_user()
    if not u:
        return jsonify({"authenticated": False}), 401
    # Patient nom/prenom are stored encrypted in the users table — decrypt before returning
    nom    = decrypt_field(u['nom']    or '') if u['role'] == 'patient' else (u['nom']    or '')
    prenom = decrypt_field(u['prenom'] or '') if u['role'] == 'patient' else (u['prenom'] or '')
    info = {
        "authenticated":         True,
        "id":                    u['id'],
        "role":                  u['role'],
        "nom":                   nom,
        "prenom":                prenom,
        "totp_enabled":          bool(u['totp_enabled']) if u['totp_enabled'] else False,
        "force_password_change": bool(u['force_password_change']) if u['force_password_change'] else False,
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


@bp.route('/api/my-doctors', methods=['GET'])
def my_doctors():
    """Return the list of doctors linked to the current patient, with last-RDV date.
    Sorted by last RDV descending so the most recent is first.
    """
    u = current_user()
    if not u or u['role'] != 'patient':
        return jsonify([]), 403
    pid = u.get('patient_id')
    if not pid:
        return jsonify([]), 200
    db = get_db()

    # Collect all doctor IDs linked to this patient (primary + junction table)
    primary_row = db.execute("SELECT medecin_id FROM patients WHERE id=?", (pid,)).fetchone()
    primary_id  = primary_row['medecin_id'] if primary_row else ''

    linked_rows = db.execute(
        "SELECT medecin_id FROM patient_doctors WHERE patient_id=?", (pid,)
    ).fetchall()
    linked_ids = {r['medecin_id'] for r in linked_rows}
    if primary_id:
        linked_ids.add(primary_id)

    if not linked_ids:
        return jsonify([]), 200

    result = []
    for mid in linked_ids:
        doc = db.execute(
            "SELECT id, nom, prenom, organisation FROM users WHERE id=? AND role='medecin' AND status='active'",
            (mid,)
        ).fetchone()
        if not doc:
            continue
        # Last confirmed/completed RDV with this doctor
        last_rdv = db.execute(
            "SELECT date FROM rdv WHERE patient_id=? AND medecin_id=? AND statut NOT IN ('annule','refusé') ORDER BY date DESC LIMIT 1",
            (pid, mid)
        ).fetchone()
        result.append({
            "id":           doc['id'],
            "nom":          doc['nom'],
            "prenom":       doc['prenom'],
            "organisation": doc['organisation'] or '',
            "last_rdv":     last_rdv['date'] if last_rdv else '',
            "is_primary":   mid == primary_id,
        })

    # Sort: most recent RDV first; those with no RDV go last
    result.sort(key=lambda d: d['last_rdv'] or '0000-00-00', reverse=True)
    return jsonify(result)


@bp.route('/api/change-password', methods=['POST'])
@limiter.limit("5 per hour")
def change_password():
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    data       = request.json or {}
    current_pw = data.get('current_password', '')
    new_pw     = data.get('new_password', '').strip()

    # ── Password policy (Step 3) ───────────────────────────────────────────────
    ok, err = validate_password(new_pw)
    if not ok:
        return jsonify({"error": err}), 400

    db  = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (u['id'],)).fetchone()
    if not row or not check_password_hash(row['password_hash'], current_pw):
        return jsonify({"error": "Mot de passe actuel incorrect"}), 401

    db.execute(
        "UPDATE users SET password_hash=?, force_password_change=0 WHERE id=?",
        (generate_password_hash(new_pw), u['id'])
    )
    log_audit(db, 'password_changed', 'users', u['id'], user_id=u['id'], ip_address=get_client_ip(), user_agent=get_user_agent())
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/register', methods=['POST'])
def register():
    """Create a user account (doctor or patient). Reserved for logged-in doctors."""
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé — seul un médecin peut créer des comptes"}), 403

    data       = request.json or {}
    username   = sanitize(data.get('username', ''), max_len=100)
    password   = data.get('password', '').strip()
    role       = sanitize(data.get('role', ''), max_len=20)
    nom        = sanitize(data.get('nom', ''), max_len=100)
    prenom     = sanitize(data.get('prenom', ''), max_len=100)
    patient_id = data.get('patient_id')

    if not all([username, password, role, nom]):
        return jsonify({"error": "Champs requis : username, password, role, nom"}), 400
    if role not in ('medecin', 'patient'):
        return jsonify({"error": "Rôle invalide (medecin | patient)"}), 400

    # Enforce password policy for new accounts
    ok, err = validate_password(password)
    if not ok:
        return jsonify({"error": err}), 400

    db = get_db()
    if db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
        return jsonify({"error": "Nom d'utilisateur déjà pris"}), 409

    uid = str(uuid.uuid4())[:8].upper()
    db.execute(
        "INSERT INTO users (id, username, password_hash, role, nom, prenom, patient_id) "
        "VALUES (?,?,?,?,?,?,?)",
        (uid, username, generate_password_hash(password), role, nom, prenom, patient_id)
    )
    log_audit(db, 'user_created', 'users', uid, user_id=u['id'], detail=f"new_user={uid} role={role}",
              ip_address=get_client_ip(), user_agent=get_user_agent())
    db.commit()
    return jsonify({"ok": True, "id": uid, "username": username, "role": role}), 201


# ─── PUBLIC: VALIDATE INVITATION TOKEN ────────────────────────────────────────

@bp.route('/api/invite/<token>', methods=['GET'])
def check_invite(token):
    """Validate an invitation token and return the patient's first name for display."""
    db  = get_db()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = db.execute(
        "SELECT * FROM patient_invitations WHERE token=? AND used=0 AND expires_at > ?",
        (token, now)
    ).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Lien invalide ou expiré."}), 400
    p = db.execute("SELECT nom, prenom FROM patients WHERE id=?", (row['patient_id'],)).fetchone()
    if not p:
        return jsonify({"ok": False, "error": "Patient introuvable."}), 400
    patient = decrypt_patient(dict(p))
    return jsonify({"ok": True, "prenom": patient['prenom'], "nom": patient['nom']})


# ─── PUBLIC: DOCTOR SEARCH (for patient registration) ─────────────────────────

@bp.route('/api/doctors/search', methods=['GET'])
@limiter.limit("30 per minute")
def search_doctors():
    """Search active doctors by name for patient self-registration."""
    q = sanitize(request.args.get('q', ''), max_len=100).strip().lower()
    if len(q) < 2:
        return jsonify([])
    db   = get_db()
    rows = db.execute(
        "SELECT id, nom, prenom, medecin_code FROM users "
        "WHERE role='medecin' AND status='active' ORDER BY nom",
    ).fetchall()
    results = []
    for r in rows:
        if q in (r['nom'] or '').lower() or q in (r['prenom'] or '').lower():
            results.append({"id": r['id'], "nom": r['nom'], "prenom": r['prenom'],
                            "medecin_code": r['medecin_code'] or ''})
    return jsonify(results[:10])


# ─── PUBLIC: PATIENT SELF-REGISTRATION ────────────────────────────────────────

@bp.route('/api/patient-register', methods=['POST'])
@limiter.limit("5 per hour")
def patient_register():
    """Patient self-registration.
    Mode A – invite_token : links to existing patient record created by a doctor.
    Mode B – free         : creates a new patient record (medecin_id optional).
    """
    data     = request.json or {}
    username = sanitize(data.get('username', ''), max_len=100)
    password = data.get('password', '')

    if not username or not password:
        return jsonify({"error": "Identifiant et mot de passe sont requis"}), 400
    if len(username) < 3:
        return jsonify({"error": "L'identifiant doit contenir au moins 3 caractères"}), 400

    ok, err = validate_password(password)
    if not ok:
        return jsonify({"error": err}), 400

    db  = get_db()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── Mode A : invitation token → existing patient record ───────────────────
    invite_token = data.get('invite_token', '').strip()
    if invite_token:
        inv = db.execute(
            "SELECT * FROM patient_invitations WHERE token=? AND used=0 AND expires_at > ?",
            (invite_token, now)
        ).fetchone()
        if not inv:
            return jsonify({"error": "Lien d'invitation invalide ou expiré."}), 400
        patient_id = inv['patient_id']
        p = db.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
        if not p:
            return jsonify({"error": "Dossier patient introuvable."}), 400
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
        db.execute("UPDATE patient_invitations SET used=1 WHERE token=?", (invite_token,))
        log_audit(db, 'patient_self_registered', 'users', uid, user_id=uid,
                  detail=f"patient_id={patient_id} method=invite",
                  ip_address=get_client_ip(), user_agent=get_user_agent())
        db.commit()
        return jsonify({"ok": True}), 201

    # ── Mode B : free registration → create new patient record ───────────────
    nom        = sanitize(data.get('nom',    ''), max_len=100).strip()
    prenom     = sanitize(data.get('prenom', ''), max_len=100).strip()
    ddn        = sanitize(data.get('ddn',    ''), max_len=20).strip()
    email      = sanitize(data.get('email',  ''), max_len=200).strip()
    medecin_id = sanitize(data.get('medecin_id', ''), max_len=20).strip()

    if not all([nom, prenom, ddn]):
        return jsonify({"error": "Nom, prénom et date de naissance sont requis"}), 400
    if not email or '@' not in email:
        return jsonify({"error": "L'adresse email est obligatoire"}), 400

    if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        return jsonify({"error": "Cet identifiant est déjà pris, choisissez-en un autre."}), 409

    # Validate medecin_id if provided
    if medecin_id:
        doc = db.execute(
            "SELECT id FROM users WHERE id=? AND role='medecin' AND status='active'",
            (medecin_id,)
        ).fetchone()
        if not doc:
            medecin_id = ''  # silently ignore invalid doctor id

    # Generate patient id
    row_max = db.execute(
        "SELECT MAX(CAST(SUBSTR(id,2) AS INTEGER)) FROM patients WHERE id GLOB 'P[0-9]*'"
    ).fetchone()
    pid = f"P{((row_max[0] or 0) + 1):03d}"

    # Encrypt PII before storing
    try:
        birth_year = int(str(ddn).strip()[:4]) if ddn and len(str(ddn).strip()) >= 4 else 0
    except (ValueError, TypeError):
        birth_year = 0
    enc = encrypt_patient_fields({"nom": nom, "prenom": prenom, "ddn": ddn, "email": email})

    db.execute(
        "INSERT INTO patients (id, nom, prenom, ddn, email, medecin_id, birth_year) VALUES (?,?,?,?,?,?,?)",
        (pid, enc['nom'], enc['prenom'], enc['ddn'], enc['email'], medecin_id, birth_year)
    )

    uid = "U" + str(uuid.uuid4())[:6].upper()
    db.execute(
        "INSERT INTO users (id, username, password_hash, role, nom, prenom, patient_id) "
        "VALUES (?,?,?,?,?,?,?)",
        (uid, username, generate_password_hash(password), 'patient',
         enc['nom'], enc['prenom'], pid)
    )
    log_audit(db, 'patient_self_registered', 'users', uid, user_id=uid,
              detail=f"patient_id={pid} method=free medecin_id={medecin_id or 'none'}",
              ip_address=get_client_ip(), user_agent=get_user_agent())
    db.commit()
    return jsonify({"ok": True}), 201


# ─── PUBLIC: FORGOT PASSWORD ───────────────────────────────────────────────────

@bp.route('/api/forgot-password', methods=['POST'])
@limiter.limit("5 per hour")
def forgot_password():
    data     = request.json or {}
    username = sanitize(data.get('username', ''), max_len=150)

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
            host      = request.host_url.rstrip('/')
            reset_url = f"{host}/?token={token}"
            body = f"""
<html><body style="font-family:Arial,sans-serif;color:#222;background:#f5f5f5;padding:24px">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
  <div style="background:#0e7a76;padding:22px 28px">
    <div style="font-size:22px;font-weight:bold;color:#fff">OphtalmoScan</div>
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

    # Enforce password policy
    ok, err = validate_password(new_password)
    if not ok:
        return jsonify({"error": err}), 400

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
    log_audit(db, 'password_reset', 'users', row['user_id'], user_id=row['user_id'], ip_address=get_client_ip(), user_agent=get_user_agent())
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/settings/request-pw-reset', methods=['POST'])
def settings_request_pw_reset():
    """Logged-in user requests password reset link — verifies email matches account."""
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    data  = request.json or {}
    email = sanitize(data.get('email', ''), max_len=200).lower()
    if not email or '@' not in email:
        return jsonify({"error": "Adresse email invalide"}), 400

    db = get_db()
    # Resolve user's registered email
    user_email = (u['email'] or '').strip().lower()
    if not user_email and u.get('patient_id'):
        row = db.execute("SELECT email FROM patients WHERE id=?", (u['patient_id'],)).fetchone()
        if row: user_email = (row['email'] or '').strip().lower()

    if not user_email:
        return jsonify({"error": "Aucun email enregistré sur ce compte. Contactez l'administrateur."}), 400
    if email != user_email:
        return jsonify({"error": "L'email saisi ne correspond pas à l'email enregistré sur votre compte."}), 400

    import secrets as _s, datetime as _dt
    db.execute("DELETE FROM password_resets WHERE user_id=? AND used=0", (u['id'],))
    token      = _s.token_urlsafe(32)
    expires_at = (_dt.datetime.now() + _dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO password_resets (token, user_id, expires_at, used) VALUES (?,?,?,0)",
        (token, u['id'], expires_at)
    )
    db.commit()

    try:
        import html as _html
        from email_notif import send_email as _send
        host      = request.host_url.rstrip('/')
        reset_url = f"{host}/?token={token}"
        h_prenom  = _html.escape(u['prenom'] or '')
        h_nom     = _html.escape(u['nom']    or '')
        body = f"""<html><body style="font-family:Arial,sans-serif;color:#222;background:#f5f5f5;padding:24px">
<div style="max-width:520px;margin:0 auto;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,.08)">
  <div style="background:#0e7a76;padding:22px 28px"><div style="font-size:22px;font-weight:bold;color:#fff">OphtalmoScan</div></div>
  <div style="padding:28px">
    <h2 style="color:#0e7a76;margin-top:0">Réinitialisation de mot de passe</h2>
    <p>Bonjour {h_prenom} {h_nom},</p>
    <p>Cliquez sur le bouton ci-dessous pour réinitialiser votre mot de passe :</p>
    <div style="text-align:center;margin:24px 0">
      <a href="{reset_url}" style="background:#0e7a76;color:#fff;padding:12px 28px;border-radius:8px;text-decoration:none;font-weight:bold;display:inline-block">
        Réinitialiser mon mot de passe
      </a>
    </div>
    <p style="color:#6b7280;font-size:13px">Ce lien expire dans 2 heures.</p>
  </div>
</div></body></html>"""
        _send(user_email, "Réinitialisation de votre mot de passe — OphtalmoScan", body)
    except Exception:
        pass  # token still valid

    return jsonify({"ok": True, "message": "Un lien de réinitialisation a été envoyé à votre adresse email."})


# ─── SETTINGS: PROFILE GET / UPDATE ──────────────────────────────────────────

@bp.route('/api/settings/profile', methods=['GET'])
def settings_get_profile():
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    db  = get_db()
    row = db.execute(
        "SELECT id,username,nom,prenom,email,organisation,medecin_code,role,totp_enabled FROM users WHERE id=?",
        (u['id'],)
    ).fetchone()
    profile = dict(row)
    if profile.get('role') == 'patient':
        profile['nom']    = decrypt_field(profile.get('nom')    or '')
        profile['prenom'] = decrypt_field(profile.get('prenom') or '')
    return jsonify(profile)


@bp.route('/api/settings/profile', methods=['PUT'])
def settings_update_profile():
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    if u['role'] not in ('medecin', 'admin'):
        return jsonify({"error": "Modification non autorisée"}), 403

    data     = request.json or {}
    nom      = sanitize(data.get('nom',      ''), max_len=100)
    prenom   = sanitize(data.get('prenom',   ''), max_len=100)
    email    = sanitize(data.get('email',    ''), max_len=200)
    username = sanitize(data.get('username', ''), max_len=100)

    if not nom or not prenom:
        return jsonify({"error": "Nom et prénom sont requis"}), 400
    if not username or len(username) < 3:
        return jsonify({"error": "L'identifiant doit contenir au moins 3 caractères"}), 400

    db = get_db()
    conflict = db.execute(
        "SELECT id FROM users WHERE username=? AND id!=?", (username, u['id'])
    ).fetchone()
    if conflict:
        return jsonify({"error": "Cet identifiant est déjà utilisé par un autre compte"}), 409

    dup_name = db.execute(
        "SELECT id,medecin_code FROM users WHERE nom=? AND prenom=? AND id!=? AND role='medecin'",
        (nom, prenom, u['id'])
    ).fetchone()

    db.execute(
        "UPDATE users SET nom=?, prenom=?, email=?, username=? WHERE id=?",
        (nom, prenom, email, username, u['id'])
    )
    log_audit(db, 'profile_updated', 'users', u['id'], user_id=u['id'], ip_address=get_client_ip(), user_agent=get_user_agent())
    db.commit()
    if username != session.get('username'):
        session['username'] = username

    result = {"ok": True}
    if dup_name:
        result["warning"] = (
            f"Un autre médecin s'appelle également {prenom} {nom} "
            f"(code {dup_name['medecin_code'] or dup_name['id']}). "
            f"Votre code médecin vous distingue."
        )
    return jsonify(result)


# ─── PUBLIC: MÉDECIN SELF-REGISTRATION ────────────────────────────────────────

@bp.route('/api/register-medecin', methods=['POST'])
@limiter.limit("5 per hour")
def register_medecin():
    """Médecin self-registration. Account is created with status='pending' until admin validates it."""
    data           = request.json or {}
    username       = sanitize(data.get('username',       ''), max_len=100)
    password       = data.get('password', '').strip()
    nom            = sanitize(data.get('nom',            ''), max_len=100)
    prenom         = sanitize(data.get('prenom',         ''), max_len=100)
    email          = sanitize(data.get('email',          ''), max_len=200)
    organisation   = sanitize(data.get('organisation',   ''), max_len=200)
    date_naissance = sanitize(data.get('date_naissance', ''), max_len=20)

    if not all([username, password, nom, prenom, email]):
        return jsonify({"error": "Champs requis : identifiant, mot de passe, nom, prénom, email"}), 400
    if '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify({"error": "Adresse email invalide"}), 400
    if len(username) < 3:
        return jsonify({"error": "L'identifiant doit contenir au moins 3 caractères"}), 400

    ok, err = validate_password(password)
    if not ok:
        return jsonify({"error": err}), 400

    db = get_db()
    if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        return jsonify({"error": "Cet identifiant est déjà utilisé, veuillez en choisir un autre."}), 409

    uid   = "U" + str(uuid.uuid4())[:6].upper()
    mcode = next_medecin_code(db)
    db.execute(
        "INSERT INTO users(id,username,password_hash,role,nom,prenom,email,organisation,date_naissance,status,medecin_code) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (uid, username, generate_password_hash(password),
         'medecin', nom, prenom, email, organisation, date_naissance, 'pending', mcode)
    )
    add_notif(db, "nouveau_medecin_en_attente",
              f"🩺 Nouvelle demande médecin : Dr. {prenom} {nom} ({username}) — en attente de validation",
              "medecin")
    log_audit(db, 'medecin_self_registered', 'users', uid, user_id=uid,
              detail=f"username={username} status=pending",
              ip_address=get_client_ip(), user_agent=get_user_agent())
    db.commit()
    return jsonify({
        "ok": True,
        "message": "Votre demande a été envoyée. Un administrateur validera votre compte avant activation."
    }), 201
