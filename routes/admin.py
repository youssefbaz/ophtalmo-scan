import uuid
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash
from database import get_db, current_user, add_notif
from extensions import limiter

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
    rejected = db.execute("SELECT COUNT(*) FROM users WHERE status='rejected'").fetchone()[0]
    return jsonify({
        "pending": pending,
        "medecins": medecins,
        "patients": patients,
        "rejected": rejected,
    })


# ─── LIST ALL USERS ───────────────────────────────────────────────────────────

@bp.route('/api/admin/users', methods=['GET'])
def admin_get_users():
    _, err = _require_admin()
    if err: return err
    db   = get_db()
    role = request.args.get('role')          # optional filter
    status = request.args.get('status')
    sql  = "SELECT id,username,role,nom,prenom,email,organisation,date_naissance,status,created_at FROM users WHERE role != 'admin'"
    params = []
    if role:
        sql += " AND role=?";   params.append(role)
    if status:
        sql += " AND status=?"; params.append(status)
    sql += " ORDER BY created_at DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify([dict(r) for r in rows])


# ─── PENDING ACCOUNTS ─────────────────────────────────────────────────────────

@bp.route('/api/admin/users/pending', methods=['GET'])
def admin_get_pending():
    _, err = _require_admin()
    if err: return err
    db   = get_db()
    rows = db.execute(
        "SELECT id,username,role,nom,prenom,email,organisation,date_naissance,status,created_at "
        "FROM users WHERE status='pending' ORDER BY created_at DESC"
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ─── VALIDATE ─────────────────────────────────────────────────────────────────

@bp.route('/api/admin/users/<uid>/validate', methods=['POST'])
def admin_validate(uid):
    _, err = _require_admin()
    if err: return err
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    db.execute("UPDATE users SET status='active' WHERE id=?", (uid,))
    db.commit()
    add_notif(db, "compte_valide",
              f"✅ Compte validé : {row['prenom']} {row['nom']} ({row['username']})",
              "admin")
    return jsonify({"ok": True})


# ─── REJECT ───────────────────────────────────────────────────────────────────

@bp.route('/api/admin/users/<uid>/reject', methods=['POST'])
def admin_reject(uid):
    _, err = _require_admin()
    if err: return err
    db  = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    db.execute("UPDATE users SET status='rejected' WHERE id=?", (uid,))
    db.commit()
    add_notif(db, "compte_rejete",
              f"❌ Compte refusé : {row['prenom']} {row['nom']} ({row['username']})",
              "admin")
    return jsonify({"ok": True})


# ─── DELETE USER ──────────────────────────────────────────────────────────────

@bp.route('/api/admin/users/<uid>', methods=['DELETE'])
def admin_delete_user(uid):
    _, err = _require_admin()
    if err: return err
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not row:
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    if row['role'] == 'admin':
        return jsonify({"error": "Impossible de supprimer le compte administrateur"}), 400
    db.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    return jsonify({"ok": True})


# ─── UPDATE USER ──────────────────────────────────────────────────────────────

@bp.route('/api/admin/users/<uid>', methods=['PUT'])
def admin_update_user(uid):
    _, err = _require_admin()
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
    db.commit()
    return jsonify({"ok": True})


# ─── RESET USER PASSWORD (admin) ──────────────────────────────────────────────

@bp.route('/api/admin/users/<uid>/reset-password', methods=['POST'])
def admin_reset_password(uid):
    _, err = _require_admin()
    if err: return err
    data     = request.json or {}
    new_pw   = data.get("new_password", "")
    if len(new_pw) < 8:
        return jsonify({"error": "Mot de passe trop court (min 8 caractères)"}), 400
    db = get_db()
    if not db.execute("SELECT id FROM users WHERE id=?", (uid,)).fetchone():
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    db.execute("UPDATE users SET password_hash=? WHERE id=?",
               (generate_password_hash(new_pw), uid))
    db.commit()
    return jsonify({"ok": True})


# ─── CREATE MÉDECIN (admin) ───────────────────────────────────────────────────

@bp.route('/api/admin/medecins', methods=['POST'])
def admin_create_medecin():
    _, err = _require_admin()
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
    if len(password) < 8:
        return jsonify({"error": "Mot de passe trop court (min 8 caractères)"}), 400

    db = get_db()
    if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        return jsonify({"error": "Cet identifiant est déjà utilisé"}), 409

    uid = "U" + str(uuid.uuid4())[:6].upper()
    db.execute(
        "INSERT INTO users(id,username,password_hash,role,nom,prenom,email,organisation,date_naissance,status) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (uid, username, generate_password_hash(password),
         "medecin", nom, prenom, email, organisation, date_naissance, "active")
    )
    db.commit()
    add_notif(db, "medecin_cree",
              f"👨‍⚕️ Nouveau médecin créé : Dr. {prenom} {nom} ({username})",
              "admin")
    return jsonify({"ok": True, "id": uid, "username": username}), 201
