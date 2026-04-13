import uuid, json
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash
from database import get_db, current_user, add_notif, next_medecin_code, log_audit
from extensions import limiter
from security_utils import validate_password, encrypt_patient_fields, sanitize, decrypt_field, get_client_ip, get_user_agent


def _decrypt_user_row(r: dict) -> dict:
    """Decrypt nom/prenom for patient accounts (stored encrypted in users table)."""
    if r.get('role') == 'patient':
        r['nom']    = decrypt_field(r.get('nom')    or '')
        r['prenom'] = decrypt_field(r.get('prenom') or '')
    return r

bp = Blueprint('admin', __name__)


def _require_admin():
    u = current_user()
    if not u or u['role'] != 'admin':
        return None, (jsonify({"error": "Accès refusé — administrateur requis"}), 403)
    return u, None


# ─── STATS ────────────────────────────────────────────────────────────────────

@bp.route('/api/admin/stats', methods=['GET'])
def admin_stats():
    _, err = _require_admin()
    if err: return err
    db = get_db()
    pending  = db.execute("SELECT COUNT(*) FROM users WHERE status='pending'").fetchone()[0]
    medecins = db.execute("SELECT COUNT(*) FROM users WHERE role='medecin' AND status='active'").fetchone()[0]
    patients = db.execute("SELECT COUNT(*) FROM users WHERE role='patient'").fetchone()[0]
    inactive = db.execute("SELECT COUNT(*) FROM users WHERE status='inactive'").fetchone()[0]
    return jsonify({
        "pending": pending,
        "medecins": medecins,
        "patients": patients,
        "inactive": inactive,
    })


# ─── LIST ALL USERS ───────────────────────────────────────────────────────────

@bp.route('/api/admin/users', methods=['GET'])
def admin_get_users():
    _, err = _require_admin()
    if err: return err
    db   = get_db()
    role = request.args.get('role')          # optional filter
    status = request.args.get('status')
    sql  = "SELECT id,username,role,nom,prenom,email,organisation,date_naissance,status,medecin_code,created_at FROM users WHERE role != 'admin'"
    params = []
    if role:
        sql += " AND role=?";   params.append(role)
    if status:
        sql += " AND status=?"; params.append(status)
    sql += " ORDER BY created_at DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify([_decrypt_user_row(dict(r)) for r in rows])


# ─── PENDING ACCOUNTS ─────────────────────────────────────────────────────────

@bp.route('/api/admin/users/pending', methods=['GET'])
def admin_get_pending():
    _, err = _require_admin()
    if err: return err
    db   = get_db()
    rows = db.execute(
        "SELECT id,username,role,nom,prenom,email,organisation,date_naissance,status,medecin_code,created_at "
        "FROM users WHERE status='pending' ORDER BY created_at DESC"
    ).fetchall()
    return jsonify([_decrypt_user_row(dict(r)) for r in rows])


# ─── VALIDATE ─────────────────────────────────────────────────────────────────

@bp.route('/api/admin/users/<uid>/validate', methods=['POST'])
def admin_validate(uid):
    admin, err = _require_admin()
    if err: return err
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    u_nom    = decrypt_field(row['nom']    or '') if row['role'] == 'patient' else (row['nom']    or '')
    u_prenom = decrypt_field(row['prenom'] or '') if row['role'] == 'patient' else (row['prenom'] or '')
    db.execute("UPDATE users SET status='active' WHERE id=?", (uid,))
    log_audit(db, 'admin_account_validated', 'users', uid,
              user_id=admin['id'], detail=f"target={uid} username={row['username']}",
              ip_address=get_client_ip(), user_agent=get_user_agent())
    add_notif(db, "compte_valide",
              f"✅ Compte validé : {u_prenom} {u_nom} ({row['username']})",
              "admin")
    db.commit()

    # Send validation email if the user has an email address
    email = (row['email'] or '').strip()
    if email:
        try:
            from email_notif import send_account_validated_email
            send_account_validated_email(
                email,
                u_prenom, u_nom, row['username'],
                app_host=request.host_url.rstrip('/')
            )
        except Exception:
            pass  # email failure is silent; account is already activated

    return jsonify({"ok": True})


# ─── DEACTIVATE / ACTIVATE ────────────────────────────────────────────────────

@bp.route('/api/admin/users/<uid>/deactivate', methods=['POST'])
def admin_deactivate(uid):
    admin, err = _require_admin()
    if err: return err
    db  = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    if row['role'] == 'admin':
        return jsonify({"error": "Impossible de désactiver le compte administrateur"}), 400
    u_nom    = decrypt_field(row['nom']    or '') if row['role'] == 'patient' else (row['nom']    or '')
    u_prenom = decrypt_field(row['prenom'] or '') if row['role'] == 'patient' else (row['prenom'] or '')
    db.execute("UPDATE users SET status='inactive' WHERE id=?", (uid,))
    log_audit(db, 'admin_account_deactivated', 'users', uid,
              user_id=admin['id'], detail=f"target={uid} username={row['username']}",
              ip_address=get_client_ip(), user_agent=get_user_agent())
    db.commit()
    add_notif(db, "compte_desactive",
              f"🔒 Compte désactivé : {u_prenom} {u_nom} ({row['username']})",
              "admin")
    return jsonify({"ok": True})


@bp.route('/api/admin/users/<uid>/activate', methods=['POST'])
def admin_activate(uid):
    admin, err = _require_admin()
    if err: return err
    db  = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    u_nom    = decrypt_field(row['nom']    or '') if row['role'] == 'patient' else (row['nom']    or '')
    u_prenom = decrypt_field(row['prenom'] or '') if row['role'] == 'patient' else (row['prenom'] or '')
    db.execute("UPDATE users SET status='active' WHERE id=?", (uid,))
    log_audit(db, 'admin_account_activated', 'users', uid,
              user_id=admin['id'], detail=f"target={uid} username={row['username']}",
              ip_address=get_client_ip(), user_agent=get_user_agent())
    db.commit()
    add_notif(db, "compte_active",
              f"🔓 Compte activé : {u_prenom} {u_nom} ({row['username']})",
              "admin")
    return jsonify({"ok": True})


# ─── DELETE USER ─────────────────────────────────────────────────────────────

@bp.route('/api/admin/users/<uid>', methods=['DELETE'])
def admin_delete_user(uid):
    admin, err = _require_admin()
    if err: return err
    db  = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    if row['role'] == 'admin':
        return jsonify({"error": "Impossible de supprimer le compte administrateur"}), 400
    u_nom    = decrypt_field(row['nom']    or '') if row['role'] == 'patient' else (row['nom']    or '')
    u_prenom = decrypt_field(row['prenom'] or '') if row['role'] == 'patient' else (row['prenom'] or '')
    log_audit(db, 'admin_user_deleted', 'users', uid,
              user_id=admin['id'], detail=f"target={uid} username={row['username']} role={row['role']}",
              ip_address=get_client_ip(), user_agent=get_user_agent())
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    add_notif(db, "compte_supprime",
              f"🗑️ Compte supprimé : {u_prenom} {u_nom} ({row['username']})",
              "admin")
    return jsonify({"ok": True})


# ─── GET SINGLE USER ──────────────────────────────────────────────────────────

@bp.route('/api/admin/users/<uid>', methods=['GET'])
def admin_get_user(uid):
    _, err = _require_admin()
    if err: return err
    db  = get_db()
    row = db.execute(
        "SELECT id,username,role,nom,prenom,email,organisation,date_naissance,status,medecin_code,created_at "
        "FROM users WHERE id=?", (uid,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    return jsonify(_decrypt_user_row(dict(row)))


# ─── UPDATE USER ──────────────────────────────────────────────────────────────

@bp.route('/api/admin/users/<uid>', methods=['PUT'])
def admin_update_user(uid):
    admin, err = _require_admin()
    if err: return err
    db   = get_db()
    row  = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    data = request.json or {}
    db.execute(
        "UPDATE users SET nom=?,prenom=?,email=?,organisation=?,date_naissance=?,status=? WHERE id=?",
        (
            data.get("nom",            row["nom"]),
            data.get("prenom",         row["prenom"]),
            data.get("email",          row["email"]),
            data.get("organisation",   row["organisation"]),
            data.get("date_naissance", row["date_naissance"]),
            data.get("status",         row["status"]),
            uid,
        )
    )
    log_audit(db, 'admin_user_updated', 'users', uid,
              user_id=admin['id'], detail=f"target={uid} fields={list(data.keys())}",
              ip_address=get_client_ip(), user_agent=get_user_agent())
    db.commit()
    return jsonify({"ok": True})


# ─── RESET USER PASSWORD (admin) ──────────────────────────────────────────────

@bp.route('/api/admin/users/<uid>/reset-password', methods=['POST'])
@limiter.limit("20 per hour")
def admin_reset_password(uid):
    admin, err = _require_admin()
    if err: return err
    data     = request.json or {}
    new_pw   = data.get("new_password", "")
    ok, err_msg = validate_password(new_pw)
    if not ok:
        return jsonify({"error": err_msg}), 400
    db = get_db()
    if not db.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone():
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    db.execute("UPDATE users SET password_hash=? WHERE id=?",
               (generate_password_hash(new_pw), uid))
    log_audit(db, 'admin_password_reset', 'users', uid,
              user_id=admin['id'], detail=f"target={uid}",
              ip_address=get_client_ip(), user_agent=get_user_agent())
    db.commit()
    return jsonify({"ok": True})


# ─── SMTP STATUS + TEST ───────────────────────────────────────────────────────

@bp.route('/api/admin/smtp-status', methods=['GET'])
def admin_smtp_status():
    _, err = _require_admin()
    if err: return err
    import os
    host     = os.environ.get("SMTP_HOST", "")
    port     = os.environ.get("SMTP_PORT", "587")
    user     = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    configured = bool(host and user and password)
    return jsonify({
        "configured": configured,
        "host": host,
        "port": port,
        "user": user,
        "from": os.environ.get("EMAIL_FROM", "") or user,
    })


@bp.route('/api/admin/test-email', methods=['POST'])
def admin_test_email():
    _, err = _require_admin()
    if err: return err
    data = request.json or {}
    to   = data.get("to", "").strip()
    if not to or '@' not in to:
        return jsonify({"error": "Adresse email destinataire invalide"}), 400
    try:
        import smtplib, os
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        host     = os.environ.get("SMTP_HOST", "")
        port     = int(os.environ.get("SMTP_PORT", "587"))
        user     = os.environ.get("SMTP_USER", "")
        password = os.environ.get("SMTP_PASSWORD", "")
        from_    = os.environ.get("EMAIL_FROM", "") or user
        if not all([host, user, password]):
            return jsonify({"error": "SMTP non configuré (SMTP_HOST / SMTP_USER / SMTP_PASSWORD manquants)"}), 400
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Test SMTP — OphtalmoScan"
        msg['From']    = from_
        msg['To']      = to
        body = ("<html><body style='font-family:Arial,sans-serif;padding:24px'>"
                "<h2 style='color:#0e7a76'>Test SMTP réussi ✓</h2>"
                "<p>La configuration email d'OphtalmoScan fonctionne correctement.</p>"
                "<p style='color:#6b7280;font-size:12px'>— OphtalmoScan</p>"
                "</body></html>")
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(user, password)
            server.sendmail(from_, [to], msg.as_string())
        return jsonify({"ok": True, "message": f"Email de test envoyé à {to}"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─── CREATE MÉDECIN (admin) ───────────────────────────────────────────────────

@bp.route('/api/admin/medecins', methods=['POST'])
def admin_create_medecin():
    admin, err = _require_admin()
    if err: return err
    data = request.json or {}

    username       = data.get("username",       "").strip()
    password       = data.get("password",       "").strip()
    nom            = data.get("nom",            "").strip()
    prenom         = data.get("prenom",         "").strip()
    email          = data.get("email",          "").strip()
    organisation   = data.get("organisation",   "").strip()
    date_naissance = data.get("date_naissance", "").strip()

    if not all([username, password, nom, prenom]):
        return jsonify({"error": "Champs requis : username, password, nom, prénom"}), 400
    ok, err_msg = validate_password(password)
    if not ok:
        return jsonify({"error": err_msg}), 400

    db = get_db()
    if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        return jsonify({"error": "Cet identifiant est déjà utilisé"}), 409

    uid   = "U" + str(uuid.uuid4())[:6].upper()
    mcode = next_medecin_code(db)
    db.execute(
        "INSERT INTO users(id,username,password_hash,role,nom,prenom,email,organisation,date_naissance,status,medecin_code) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (uid, username, generate_password_hash(password),
         "medecin", nom, prenom, email, organisation, date_naissance, "active", mcode)
    )
    log_audit(db, 'admin_medecin_created', 'users', uid,
              user_id=admin['id'], detail=f"new_user={uid} username={username} mcode={mcode}",
              ip_address=get_client_ip(), user_agent=get_user_agent())
    db.commit()
    add_notif(db, "medecin_cree",
              f"👨‍⚕️ Nouveau médecin créé : Dr. {prenom} {nom} ({username}) — {mcode}",
              "admin")
    return jsonify({"ok": True, "id": uid, "username": username, "medecin_code": mcode}), 201


# ─── CREATE PATIENT (admin) ───────────────────────────────────────────────────

@bp.route('/api/admin/patients', methods=['POST'])
@limiter.limit("60 per hour")
def admin_create_patient():
    _, err = _require_admin()
    if err: return err
    data = request.json or {}

    nom        = data.get("nom",        "").strip()
    prenom     = data.get("prenom",     "").strip()
    ddn        = data.get("ddn",        "").strip()
    sexe       = data.get("sexe",       "").strip()
    telephone  = data.get("telephone",  "").strip()
    email      = data.get("email",      "").strip()
    medecin_id = data.get("medecin_id", "").strip()
    send_email = data.get("send_email", True)
    antecedents = data.get("antecedents", [])
    allergies   = data.get("allergies",   [])

    if not nom or not prenom:
        return jsonify({"error": "Nom et prénom requis"}), 400
    if not email or '@' not in email:
        return jsonify({"error": "L'adresse email du patient est obligatoire."}), 400

    from routes.patients import _next_patient_id, _auto_create_account
    db  = get_db()
    pid = _next_patient_id(db)

    # If no médecin specified, assign to the first active médecin
    if not medecin_id:
        row = db.execute("SELECT id FROM users WHERE role='medecin' AND status='active' LIMIT 1").fetchone()
        medecin_id = row['id'] if row else ''

    ddn_plain = sanitize(ddn, max_len=20)
    try:
        birth_year = int(ddn_plain[:4]) if len(ddn_plain) >= 4 else 0
    except (ValueError, TypeError):
        birth_year = 0
    pii = encrypt_patient_fields({
        "nom":       sanitize(nom,       max_len=100),
        "prenom":    sanitize(prenom,    max_len=100),
        "ddn":       ddn_plain,
        "telephone": sanitize(telephone, max_len=30),
        "email":     sanitize(email,     max_len=200),
    })

    db.execute(
        "INSERT INTO patients(id,nom,prenom,ddn,sexe,telephone,email,antecedents,allergies,medecin_id,birth_year) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (pid, pii["nom"], pii["prenom"], pii["ddn"], sexe, pii["telephone"], pii["email"],
         json.dumps(antecedents), json.dumps(allergies), medecin_id, birth_year)
    )
    db.commit()

    creds = None
    if send_email or not email:
        host  = request.host_url.rstrip('/')
        creds = _auto_create_account(db, pid, nom=nom, prenom=prenom, email=email if send_email else '', app_host=host)
        if creds:
            db.commit()
    else:
        host  = request.host_url.rstrip('/')
        creds = _auto_create_account(db, pid, nom=nom, prenom=prenom, email='', app_host=host)
        if creds:
            db.commit()

    add_notif(db, "patient_added", f"Nouveau patient ajouté par admin : {prenom} {nom}", "admin", pid)
    return jsonify({"ok": True, "id": pid, "credentials": creds}), 201
