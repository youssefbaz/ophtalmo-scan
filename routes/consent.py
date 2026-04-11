"""
routes/consent.py — Patient consent management (Step 9 — Loi 09-08 CNDP Morocco).

Endpoints:
  GET  /api/consent/status/<patient_id>  — get all consent records for a patient
  POST /api/consent/grant                — grant a consent type
  POST /api/consent/revoke               — revoke a previously granted consent
"""
import datetime
from flask import Blueprint, request, jsonify
from database import get_db, current_user, log_audit
from security_utils import sanitize, get_client_ip, get_user_agent

bp = Blueprint('consent', __name__)

# Valid consent types for Loi 09-08 compliance
CONSENT_TYPES = {
    "data_processing":    "Traitement des données personnelles à des fins médicales",
    "data_sharing":       "Partage des données avec d'autres professionnels de santé",
    "ai_analysis":        "Analyse par intelligence artificielle des données cliniques",
    "backup_storage":     "Stockage chiffré et sauvegarde des données",
    "research_anonymized":"Utilisation anonymisée à des fins de recherche",
}


@bp.route('/api/consent/status/<patient_id>', methods=['GET'])
def consent_status(patient_id):
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401

    # Patients can only see their own consent; doctors see their patients
    db = get_db()
    if u['role'] == 'patient':
        pat = db.execute("SELECT * FROM patients WHERE id=?", (patient_id,)).fetchone()
        if not pat or u.get('patient_id') != patient_id:
            return jsonify({"error": "Accès refusé"}), 403
    elif u['role'] in ('medecin', 'admin'):
        if u['role'] == 'medecin':
            pat = db.execute(
                "SELECT id FROM patients WHERE id=? AND medecin_id=?",
                (patient_id, u['id'])
            ).fetchone()
            if not pat:
                return jsonify({"error": "Patient introuvable ou hors périmètre"}), 403
    else:
        return jsonify({"error": "Accès refusé"}), 403

    rows = db.execute(
        "SELECT * FROM patient_consents WHERE patient_id=? ORDER BY created_at DESC",
        (patient_id,)
    ).fetchall()

    # Build a summary: latest state per consent type
    latest = {}
    for r in rows:
        ct = r['consent_type']
        if ct not in latest:
            latest[ct] = {
                "consent_type":  ct,
                "label":         CONSENT_TYPES.get(ct, ct),
                "granted":       bool(r['granted']),
                "granted_at":    r['granted_at'],
                "revoked_at":    r['revoked_at'],
                "ip_address":    r['ip_address'],
            }

    # Ensure all known types appear in the response (not-yet-granted = False)
    for ct, label in CONSENT_TYPES.items():
        if ct not in latest:
            latest[ct] = {
                "consent_type": ct,
                "label":        label,
                "granted":      False,
                "granted_at":   None,
                "revoked_at":   None,
                "ip_address":   None,
            }

    return jsonify({
        "patient_id":  patient_id,
        "consents":    list(latest.values()),
        "history":     [dict(r) for r in rows],
    })


@bp.route('/api/consent/grant', methods=['POST'])
def consent_grant():
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401

    data         = request.json or {}
    patient_id   = sanitize(data.get('patient_id', ''), max_len=20)
    consent_type = sanitize(data.get('consent_type', ''), max_len=50)

    if not patient_id or not consent_type:
        return jsonify({"error": "patient_id et consent_type sont requis"}), 400
    if consent_type not in CONSENT_TYPES:
        return jsonify({"error": f"Type de consentement inconnu: {consent_type}"}), 400

    db  = get_db()
    _check_consent_access(db, u, patient_id)

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip  = get_client_ip()
    db.execute(
        "INSERT INTO patient_consents (patient_id, user_id, consent_type, granted, granted_at, ip_address, created_at) "
        "VALUES (?,?,?,1,?,?,?)",
        (patient_id, u['id'], consent_type, now, ip, now)
    )
    log_audit(db, 'consent_granted', u['id'],
              f"patient_id={patient_id} type={consent_type}",
              ip_address=ip, user_agent=get_user_agent())
    db.commit()
    return jsonify({"ok": True, "consent_type": consent_type, "granted": True, "granted_at": now})


@bp.route('/api/consent/revoke', methods=['POST'])
def consent_revoke():
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401

    data         = request.json or {}
    patient_id   = sanitize(data.get('patient_id', ''), max_len=20)
    consent_type = sanitize(data.get('consent_type', ''), max_len=50)

    if not patient_id or not consent_type:
        return jsonify({"error": "patient_id et consent_type sont requis"}), 400
    if consent_type not in CONSENT_TYPES:
        return jsonify({"error": f"Type de consentement inconnu: {consent_type}"}), 400

    db  = get_db()
    _check_consent_access(db, u, patient_id)

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ip  = get_client_ip()
    db.execute(
        "INSERT INTO patient_consents (patient_id, user_id, consent_type, granted, revoked_at, ip_address, created_at) "
        "VALUES (?,?,?,0,?,?,?)",
        (patient_id, u['id'], consent_type, now, ip, now)
    )
    log_audit(db, 'consent_revoked', u['id'],
              f"patient_id={patient_id} type={consent_type}",
              ip_address=ip, user_agent=get_user_agent())
    db.commit()
    return jsonify({"ok": True, "consent_type": consent_type, "granted": False, "revoked_at": now})


@bp.route('/api/consent/types', methods=['GET'])
def consent_types():
    """Return the list of recognised consent types."""
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    return jsonify([{"key": k, "label": v} for k, v in CONSENT_TYPES.items()])


# ── Internal helper ────────────────────────────────────────────────────────────

def _check_consent_access(db, u, patient_id):
    """Raise 403 if the current user is not allowed to manage this patient's consent."""
    from flask import abort
    if u['role'] == 'patient':
        if u.get('patient_id') != patient_id:
            abort(403)
    elif u['role'] == 'medecin':
        pat = db.execute(
            "SELECT id FROM patients WHERE id=? AND medecin_id=?",
            (patient_id, u['id'])
        ).fetchone()
        if not pat:
            abort(403)
    elif u['role'] == 'admin':
        pass  # admin can manage any consent
    else:
        from flask import abort
        abort(403)
