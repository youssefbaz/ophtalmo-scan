"""
routes/patients_history.py — Consultation history and clinical trends endpoints.
"""
import uuid, datetime, logging
from flask import Blueprint, request, jsonify
from database import get_db, current_user, log_audit
from routes.patients_helpers import _assert_owns_patient
from security_utils import encrypt_clinical, valid_date

logger = logging.getLogger(__name__)

bp = Blueprint('patients_history', __name__)


@bp.route('/api/patients/<pid>/historique', methods=['POST'])
def add_historique(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    _assert_owns_patient(db, u, pid)
    if not db.execute(
        "SELECT id FROM patients WHERE id=? AND (deleted IS NULL OR deleted=0)", (pid,)
    ).fetchone():
        return jsonify({"error": "Patient non trouvé"}), 404
    entry_date = data.get('date', datetime.date.today().isoformat())
    if not valid_date(entry_date):
        return jsonify({"error": "Format de date invalide (YYYY-MM-DD attendu)."}), 400

    # Length caps on free-text clinical fields to prevent oversized payloads
    _CAP = {
        'motif': 1000, 'diagnostic': 2000, 'traitement': 2000,
        'segment_ant': 2000, 'notes': 3000,
    }
    for field, maxlen in _CAP.items():
        val = data.get(field, '')
        if isinstance(val, str) and len(val) > maxlen:
            return jsonify({"error": f"Le champ '{field}' dépasse la limite de {maxlen} caractères."}), 400

    hid = "H" + str(uuid.uuid4())[:6].upper()
    enc = encrypt_clinical(data)
    try:
        db.execute(
            "INSERT INTO historique (id,patient_id,date,motif,diagnostic,traitement,"
            "tension_od,tension_og,acuite_od,acuite_og,"
            "refraction_od_sph,refraction_od_cyl,refraction_od_axe,"
            "refraction_og_sph,refraction_og_cyl,refraction_og_axe,"
            "segment_ant,notes,medecin) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (hid, pid, entry_date,
             enc.get('motif',''), enc.get('diagnostic',''), enc.get('traitement',''),
             data.get('tension_od',''), data.get('tension_og',''),
             data.get('acuite_od',''), data.get('acuite_og',''),
             data.get('refraction_od_sph',''), data.get('refraction_od_cyl',''), data.get('refraction_od_axe',''),
             data.get('refraction_og_sph',''), data.get('refraction_og_cyl',''), data.get('refraction_og_axe',''),
             enc.get('segment_ant',''), enc.get('notes',''),
             u['nom'])
        )
        log_audit(db, 'INSERT', 'historique', hid, u['id'], pid, data.get('motif', ''))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"add_historique failed: {exc}")
        return jsonify({"error": "Erreur lors de la création de la consultation."}), 500
    return jsonify({"ok": True, "id": hid}), 201


@bp.route('/api/patients/<pid>/historique/<hid>', methods=['PUT'])
def update_historique(pid, hid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    _assert_owns_patient(db, u, pid)
    if not db.execute(
        "SELECT id FROM historique WHERE id=? AND patient_id=? AND (deleted IS NULL OR deleted=0)",
        (hid, pid)
    ).fetchone():
        return jsonify({"error": "Consultation non trouvée"}), 404
    upd_date = data.get('date', '')
    if upd_date and not valid_date(upd_date):
        return jsonify({"error": "Format de date invalide (YYYY-MM-DD attendu)."}), 400

    _CAP = {
        'motif': 1000, 'diagnostic': 2000, 'traitement': 2000,
        'segment_ant': 2000, 'notes': 3000,
    }
    for field, maxlen in _CAP.items():
        val = data.get(field, '')
        if isinstance(val, str) and len(val) > maxlen:
            return jsonify({"error": f"Le champ '{field}' dépasse la limite de {maxlen} caractères."}), 400

    enc = encrypt_clinical(data)
    try:
        db.execute(
            "UPDATE historique SET date=?,motif=?,diagnostic=?,traitement=?,"
            "tension_od=?,tension_og=?,acuite_od=?,acuite_og=?,"
            "refraction_od_sph=?,refraction_od_cyl=?,refraction_od_axe=?,"
            "refraction_og_sph=?,refraction_og_cyl=?,refraction_og_axe=?,"
            "segment_ant=?,notes=? WHERE id=? AND patient_id=?",
            (upd_date, enc.get('motif',''), enc.get('diagnostic',''), enc.get('traitement',''),
             data.get('tension_od',''), data.get('tension_og',''),
             data.get('acuite_od',''), data.get('acuite_og',''),
             data.get('refraction_od_sph',''), data.get('refraction_od_cyl',''), data.get('refraction_od_axe',''),
             data.get('refraction_og_sph',''), data.get('refraction_og_cyl',''), data.get('refraction_og_axe',''),
             enc.get('segment_ant',''), enc.get('notes',''),
             hid, pid)
        )
        log_audit(db, 'UPDATE', 'historique', hid, u['id'], pid, data.get('motif', ''))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"update_historique failed: {exc}")
        return jsonify({"error": "Erreur lors de la mise à jour de la consultation."}), 500
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/historique/<hid>', methods=['DELETE'])
def delete_historique(pid, hid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    _assert_owns_patient(db, u, pid)
    if not db.execute(
        "SELECT id FROM historique WHERE id=? AND patient_id=? AND (deleted IS NULL OR deleted=0)",
        (hid, pid)
    ).fetchone():
        return jsonify({"error": "Consultation non trouvée"}), 404
    try:
        db.execute(
            "UPDATE historique SET deleted=1, deleted_at=? WHERE id=? AND patient_id=?",
            (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), hid, pid)
        )
        log_audit(db, 'DELETE', 'historique', hid, u['id'], pid)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error(f"delete_historique failed: {exc}")
        return jsonify({"error": "Erreur lors de la suppression."}), 500
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/trends', methods=['GET'])
def get_trends(pid):
    u = current_user()
    if not u:
        return jsonify({}), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    rows = db.execute(
        "SELECT date, acuite_od, acuite_og, tension_od, tension_og "
        "FROM historique WHERE patient_id=? AND date!='' "
        "AND (deleted IS NULL OR deleted=0) ORDER BY date ASC",
        (pid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])
