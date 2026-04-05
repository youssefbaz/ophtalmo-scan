import uuid
from flask import Blueprint, request, jsonify
from database import get_db, current_user, add_notif

bp = Blueprint('rdv', __name__)


@bp.route('/api/rdv', methods=['GET'])
def get_rdv():
    u = current_user()
    if not u:
        return jsonify([]), 401
    db = get_db()
    if u['role'] == 'patient':
        rows = db.execute("""
            SELECT r.*, p.nom AS patient_nom, p.prenom AS patient_prenom
            FROM rdv r JOIN patients p ON r.patient_id = p.id
            WHERE r.patient_id = ?
            ORDER BY r.date, r.heure
        """, (u.get('patient_id'),)).fetchall()
    else:
        rows = db.execute("""
            SELECT r.*, p.nom AS patient_nom, p.prenom AS patient_prenom
            FROM rdv r JOIN patients p ON r.patient_id = p.id
            ORDER BY r.date, r.heure
        """).fetchall()
    result = [dict(r) for r in rows]
    for r in result:
        r['urgent'] = bool(r['urgent'])
    return jsonify(result)


@bp.route('/api/rdv', methods=['POST'])
def add_rdv():
    u = current_user()
    if not u:
        return jsonify({}), 401
    data = request.json or {}
    db = get_db()
    pid = data.get('patient_id') or u.get('patient_id')
    p = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not p:
        return jsonify({"error": "Patient non trouvé"}), 404
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403

    urgent = bool(data.get('urgent', False))
    statut = 'en_attente' if urgent or u['role'] == 'patient' else data.get('statut', 'programmé')
    rdv_id = "RDV" + str(uuid.uuid4())[:6].upper()

    db.execute(
        "INSERT INTO rdv (id,patient_id,date,heure,type,statut,medecin,notes,urgent,demande_par) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (rdv_id, pid, data.get('date',''), data.get('heure',''),
         data.get('type','Consultation'), statut,
         data.get('medecin', u['nom']), data.get('notes',''),
         1 if urgent else 0, u['role'])
    )
    db.commit()

    if urgent or u['role'] == 'patient':
        msg = f"{'🚨 RDV URGENT' if urgent else 'Nouveau RDV'} demandé par {p['prenom']} {p['nom']}"
        add_notif(db, "rdv_urgent" if urgent else "rdv_demande", msg, u['role'], pid, {"rdv_id": rdv_id})

    return jsonify({
        "ok": True,
        "rdv": {
            "id": rdv_id, "date": data.get('date',''), "heure": data.get('heure',''),
            "type": data.get('type','Consultation'), "statut": statut,
            "medecin": data.get('medecin','Dr. Martin'), "urgent": urgent
        }
    })


@bp.route('/api/rdv/<rdv_id>', methods=['DELETE'])
def delete_rdv(rdv_id):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    row = db.execute("SELECT * FROM rdv WHERE id=?", (rdv_id,)).fetchone()
    if not row:
        return jsonify({"error": "RDV non trouvé"}), 404
    db.execute("DELETE FROM rdv WHERE id=?", (rdv_id,))
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/rdv/<rdv_id>/valider', methods=['POST'])
def valider_rdv(rdv_id):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    row = db.execute(
        "SELECT r.*, p.nom, p.prenom FROM rdv r JOIN patients p ON r.patient_id=p.id WHERE r.id=?",
        (rdv_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "RDV non trouvé"}), 404

    new_statut = data.get('statut', 'confirmé')
    new_notes  = data.get('notes', row['notes'])
    new_date   = data.get('date',  row['date'])
    new_heure  = data.get('heure', row['heure'])

    db.execute(
        "UPDATE rdv SET statut=?, notes=?, date=?, heure=? WHERE id=?",
        (new_statut, new_notes, new_date, new_heure, rdv_id)
    )
    db.commit()
    add_notif(db, "rdv_validé",
              f"RDV confirmé pour {row['prenom']} {row['nom']} le {new_date}",
              u['role'], row['patient_id'])
    return jsonify({"ok": True})
