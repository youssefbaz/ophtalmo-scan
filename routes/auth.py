import uuid
from flask import Blueprint, request, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db, current_user

bp = Blueprint('auth', __name__)


@bp.route('/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row and check_password_hash(row['password_hash'], password):
        session['username'] = username
        return jsonify({
            "ok": True,
            "role": row['role'],
            "nom": row['nom'],
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
        "role": u['role'],
        "nom": u['nom'],
        "prenom": u['prenom'] or ''
    }
    if u['role'] == 'patient':
        info['patient_id'] = u.get('patient_id')
    return jsonify(info)


@bp.route('/api/register', methods=['POST'])
def register():
    """Créer un compte utilisateur (médecin, assistant ou patient).
    Réservé aux médecins connectés."""
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
    if role not in ('medecin', 'assistant', 'patient'):
        return jsonify({"error": "Rôle invalide (medecin | assistant | patient)"}), 400

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
