"""
routes/patients.py — Core patient CRUD endpoints.

History, surgery/suivi, account management, import/export, and search have been
extracted into separate modules:
  - patients_history.py  — historique + trends
  - patients_surgery.py  — chirurgie + suivi post-op
  - patients_account.py  — account creation, invitations, claims
  - patients_import.py   — CSV import/export, search, audit, post-op gaps
"""
import os, json, datetime, logging
from flask import Blueprint, request, jsonify
from database import get_db, current_user, add_notif, require_role, log_audit, audit_read
from security_utils import decrypt_patient, encrypt_patient_fields, sanitize
from routes.patients_helpers import _assert_owns_patient, _build_patient, _auto_create_account, _next_patient_id
from extensions import limiter

logger = logging.getLogger(__name__)

bp = Blueprint('patients', __name__)


# ─── LIST ──────────────────────────────────────────────────────────────────────

# Only the columns actually used for the list view — avoids fetching (and decrypting)
# telephone, email, allergies, and other fields that the list endpoint never returns.
_LIST_COLS = (
    "p.id, p.nom, p.prenom, p.ddn, p.sexe, p.medecin_id, p.antecedents, p.birth_year, "
    "COUNT(CASE WHEN r.urgent=1 AND r.statut='en_attente' THEN 1 END) AS nb_rdv_urgent, "
    "(SELECT MAX(h.date) FROM historique h "
    " WHERE h.patient_id = p.id AND (h.deleted IS NULL OR h.deleted=0)) AS last_consult"
)
_LIST_JOIN = "LEFT JOIN rdv r ON r.patient_id = p.id AND (r.deleted IS NULL OR r.deleted=0)"
_LIST_ORDER = "GROUP BY p.id ORDER BY p.nom, p.prenom"


def _row_to_patient(row, linked_ids, mid, _df):
    """Decrypt only the fields needed for the list response."""
    nom       = _df(row['nom']    or '')
    prenom    = _df(row['prenom'] or '')
    ddn       = _df(row['ddn']    or '')
    row_mid   = row['medecin_id'] or ''
    is_linked = row['id'] in linked_ids and row_mid != mid
    return {
        "id":            row['id'],
        "nom":           nom,
        "prenom":        prenom,
        "ddn":           ddn,
        "antecedents":   json.loads(row['antecedents'] or '[]')[:2],
        "nb_rdv_urgent": row['nb_rdv_urgent'],
        "medecin_id":    row_mid,
        "linked":        is_linked,
        "last_consult":  row['last_consult'] or '',
    }


@bp.route('/api/patients', methods=['GET'])
def get_patients():
    u = current_user()
    if not u:
        return jsonify([]), 401
    db = get_db()
    q        = request.args.get('q', '').lower().strip()
    page     = request.args.get('page',     type=int, default=None)
    per_page = request.args.get('per_page', type=int, default=50)
    per_page = max(1, min(per_page, 200))

    if u['role'] == 'patient':
        pid = u.get('patient_id')
        row = db.execute(
            "SELECT id, nom, prenom FROM patients WHERE id=? AND (deleted IS NULL OR deleted=0)",
            (pid,)
        ).fetchone()
        if row:
            from security_utils import decrypt_field as _df
            return jsonify([{'id': row['id'],
                             'nom':    _df(row['nom']    or ''),
                             'prenom': _df(row['prenom'] or '')}])
        return jsonify([])

    from security_utils import decrypt_field as _df

    mid = u['id'] if u['role'] == 'medecin' else None

    if mid:
        _where  = ("WHERE (p.medecin_id=? "
                   "OR p.id IN (SELECT patient_id FROM patient_doctors WHERE medecin_id=?)) "
                   "AND (p.deleted IS NULL OR p.deleted=0)")
        _params = (mid, mid)
        linked_ids = {r['patient_id'] for r in db.execute(
            "SELECT patient_id FROM patient_doctors WHERE medecin_id=?", (mid,)
        ).fetchall()}
    else:
        _where  = "WHERE (p.deleted IS NULL OR p.deleted=0)"
        _params = ()
        linked_ids = set()

    # Fast path: no search + pagination — do the count and data fetch in SQL,
    # decrypt only the page (not the entire roster).
    if not q and page is not None:
        total = db.execute(
            f"SELECT COUNT(DISTINCT p.id) FROM patients p {_LIST_JOIN} {_where}", _params
        ).fetchone()[0]
        offset = (page - 1) * per_page
        rows = db.execute(
            f"SELECT {_LIST_COLS} FROM patients p {_LIST_JOIN} {_where} "
            f"{_LIST_ORDER} LIMIT ? OFFSET ?",
            _params + (per_page, offset)
        ).fetchall()
        data = [_row_to_patient(r, linked_ids, mid, _df) for r in rows]
        return jsonify({"data": data, "total": total, "page": page,
                        "per_page": per_page,
                        "pages": max(1, (total + per_page - 1) // per_page)})

    # Standard path: fetch all scoped rows, decrypt only nom+prenom for filtering,
    # defer ddn decryption to after the filter check.
    rows = db.execute(
        f"SELECT {_LIST_COLS} FROM patients p {_LIST_JOIN} {_where} {_LIST_ORDER}", _params
    ).fetchall()

    result = []
    for row in rows:
        nom    = _df(row['nom']    or '')
        prenom = _df(row['prenom'] or '')
        if q and not (q in nom.lower() or q in prenom.lower() or q in row['id'].lower()):
            continue
        ddn       = _df(row['ddn'] or '')
        row_mid   = row['medecin_id'] or ''
        is_linked = row['id'] in linked_ids and row_mid != mid
        result.append({
            "id":            row['id'],
            "nom":           nom,
            "prenom":        prenom,
            "ddn":           ddn,
            "antecedents":   json.loads(row['antecedents'] or '[]')[:2],
            "nb_rdv_urgent": row['nb_rdv_urgent'],
            "medecin_id":    row_mid,
            "linked":        is_linked,
            "last_consult":  row['last_consult'] or '',
        })

    total = len(result)

    if page is not None:
        offset    = (page - 1) * per_page
        paginated = result[offset: offset + per_page]
        return jsonify({"data": paginated, "total": total, "page": page,
                        "per_page": per_page,
                        "pages": max(1, (total + per_page - 1) // per_page)})

    return jsonify(result)


# ─── GET ONE ───────────────────────────────────────────────────────────────────

@bp.route('/api/patients/<pid>', methods=['GET'])
def get_patient(pid):
    u = current_user()
    if not u:
        return jsonify({}), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    if u['role'] in ('medecin',):
        _assert_owns_patient(db, u, pid)
    p = _build_patient(db, pid)
    if not p:
        return jsonify({"error": "Non trouvé"}), 404
    audit_read(db, 'patients', pid, pid)

    if u['role'] == 'patient':
        patient_view = dict(p)
        patient_view['historique'] = [
            {
                "date":       h["date"],
                "motif":      h["motif"],
                "traitement": h["traitement"],
                "acuite_od":  h.get("acuite_od", ""),
                "acuite_og":  h.get("acuite_og", "")
            }
            for h in p["historique"]
        ]
        return jsonify(patient_view)

    return jsonify(p)


# ─── CREATE ────────────────────────────────────────────────────────────────────

@bp.route('/api/patients', methods=['POST'])
@require_role('medecin', 'admin')
@limiter.limit("60 per hour")
def add_patient():
    u = current_user()
    data = request.json or {}
    db = get_db()
    pid        = _next_patient_id(db)
    medecin_id = data.get("medecin_id") or (u['id'] if u['role'] == 'medecin' else '')
    send_email = data.get("send_email", True)
    email_raw = sanitize(data.get("email", ""), max_len=200).strip()
    if not email_raw or '@' not in email_raw:
        return jsonify({"error": "L'adresse email du patient est obligatoire."}), 400

    ddn_plain = sanitize(data.get("ddn", ""), max_len=20)
    try:
        birth_year = int(ddn_plain[:4]) if len(ddn_plain) >= 4 else 0
    except (ValueError, TypeError):
        birth_year = 0

    pii = encrypt_patient_fields({
        "nom":       sanitize(data.get("nom", ""),       max_len=100),
        "prenom":    sanitize(data.get("prenom", ""),    max_len=100),
        "ddn":       ddn_plain,
        "telephone": sanitize(data.get("telephone", ""), max_len=30),
        "email":     email_raw,
    })
    try:
        db.execute(
            "INSERT INTO patients (id,nom,prenom,ddn,sexe,telephone,email,antecedents,allergies,medecin_id,birth_year) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (pid,
             pii["nom"], pii["prenom"], pii["ddn"], sanitize(data.get("sexe",""), max_len=10),
             pii["telephone"], pii["email"],
             json.dumps(data.get("antecedents",[])), json.dumps(data.get("allergies",[])),
             medecin_id, birth_year)
        )
        host  = request.host_url.rstrip('/')
        email = email_raw if send_email else ''
        creds = _auto_create_account(
            db, pid,
            nom=data.get("nom",""), prenom=data.get("prenom",""),
            email=email, app_host=host
        )
        log_audit(db, 'INSERT', 'patients', pid, u['id'], pid,
                  f"{data.get('prenom','')} {data.get('nom','')}")
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"add_patient failed: {e}")
        return jsonify({"error": "Erreur lors de la création du patient"}), 500
    add_notif(db, "patient_added",
              f"Nouveau patient ajouté : {data.get('prenom','')} {data.get('nom','')}",
              u['role'], pid)
    return jsonify({"ok": True, "id": pid, "credentials": creds}), 201


# ─── UPDATE ────────────────────────────────────────────────────────────────────

@bp.route('/api/patients/<pid>', methods=['PUT'])
@limiter.limit("120 per hour")
def update_patient(pid):
    u = current_user()
    if not u or u['role'] not in ('medecin', 'admin'):
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    _assert_owns_patient(db, u, pid)
    if not db.execute(
        "SELECT id FROM patients WHERE id=? AND (deleted IS NULL OR deleted=0)", (pid,)
    ).fetchone():
        return jsonify({"error": "Non trouvé"}), 404
    data = request.json or {}
    ddn_plain = sanitize(data.get("ddn", ""), max_len=20)
    try:
        birth_year = int(ddn_plain[:4]) if len(ddn_plain) >= 4 else 0
    except (ValueError, TypeError):
        birth_year = 0
    pii = encrypt_patient_fields({
        "nom":       sanitize(data.get("nom", ""),       max_len=100),
        "prenom":    sanitize(data.get("prenom", ""),    max_len=100),
        "ddn":       ddn_plain,
        "telephone": sanitize(data.get("telephone", ""), max_len=30),
        "email":     sanitize(data.get("email", ""),     max_len=200),
    })
    db.execute(
        "UPDATE patients SET nom=?, prenom=?, ddn=?, sexe=?, telephone=?, email=?, "
        "antecedents=?, allergies=?, birth_year=? WHERE id=?",
        (pii["nom"], pii["prenom"], pii["ddn"], sanitize(data.get("sexe",""), max_len=10),
         pii["telephone"], pii["email"],
         json.dumps(data.get("antecedents",[])), json.dumps(data.get("allergies",[])),
         birth_year, pid)
    )
    db.commit()
    return jsonify({"ok": True})


# ─── SOFT DELETE ───────────────────────────────────────────────────────────────

@bp.route('/api/patients/<pid>', methods=['DELETE'])
@require_role('medecin', 'admin')
def delete_patient(pid):
    u = current_user()
    db = get_db()
    _assert_owns_patient(db, u, pid)
    patient = db.execute(
        "SELECT * FROM patients WHERE id=? AND (deleted IS NULL OR deleted=0)", (pid,)
    ).fetchone()
    if not patient:
        return jsonify({"error": "Non trouvé"}), 404
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    db.execute(
        "UPDATE patients SET deleted=1, deleted_at=? WHERE id=?", (now, pid)
    )
    # Soft-delete all future RDVs so they disappear from the médecin agenda.
    # Past RDVs (date < today) are left intact for medical history continuity.
    today = datetime.date.today().isoformat()
    db.execute(
        "UPDATE rdv SET deleted=1, deleted_at=? WHERE patient_id=? AND date >= ? AND (deleted IS NULL OR deleted=0)",
        (now, pid, today)
    )
    # GDPR scrub of nominative detail in audit trail. Patient record itself stays
    # soft-deleted (restorable); only the audit_log.detail strings are scrubbed.
    db.execute(
        "UPDATE audit_log SET detail='[données supprimées - RGPD]' WHERE patient_id=?",
        (pid,)
    )
    log_audit(db, 'patient_deleted_gdpr', 'patients', pid, u['id'], pid,
              f"patient_id={pid} deleted_by={u['id']}")
    db.commit()
    return jsonify({"ok": True})


# ─── RESTORE (undo soft-delete) ────────────────────────────────────────────────

@bp.route('/api/patients/<pid>/restore', methods=['POST'])
@require_role('medecin', 'admin')
def restore_patient(pid):
    u = current_user()
    db = get_db()
    row = db.execute(
        "SELECT id, medecin_id FROM patients WHERE id=? AND deleted=1", (pid,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Patient non supprimé ou introuvable"}), 404
    # Médecins can only restore patients they owned/were linked to
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403
    db.execute("UPDATE patients SET deleted=0, deleted_at=NULL WHERE id=?", (pid,))
    # Restore future RDVs that were soft-deleted together with the patient.
    today = datetime.date.today().isoformat()
    db.execute(
        "UPDATE rdv SET deleted=0, deleted_at=NULL WHERE patient_id=? AND date >= ? AND deleted=1",
        (pid, today)
    )
    log_audit(db, 'patient_restored', 'patients', pid, u['id'], pid,
              f"patient_id={pid} restored_by={u['id']}")
    db.commit()
    return jsonify({"ok": True})


# ─── ASSIGN DOCTOR ─────────────────────────────────────────────────────────────

@bp.route('/api/patients/<pid>/assigner', methods=['POST'])
def assigner_medecin(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    new_medecin_id = data.get('medecin_id', '').strip()
    if not new_medecin_id:
        return jsonify({"error": "medecin_id requis"}), 400
    db = get_db()
    _assert_owns_patient(db, u, pid)
    target = db.execute(
        "SELECT id FROM users WHERE id=? AND role='medecin'", (new_medecin_id,)
    ).fetchone()
    if not target:
        return jsonify({"error": "Médecin introuvable ou identifiant invalide"}), 404
    db.execute("UPDATE patients SET medecin_id=? WHERE id=?", (new_medecin_id, pid))
    db.commit()
    return jsonify({"ok": True})


# ─── GDPR HARD PURGE ───────────────────────────────────────────────────────────

@bp.route('/api/patients/<pid>/purge', methods=['DELETE'])
@require_role('admin')
def purge_patient(pid):
    """
    GDPR Art. 17 — Right to erasure (hard delete).
    Irreversibly removes all patient data from the database.
    Only callable by admins. Patient must already be soft-deleted.
    """
    u = current_user()
    db = get_db()
    patient = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not patient:
        return jsonify({"error": "Patient introuvable"}), 404
    if not patient['deleted']:
        return jsonify({
            "error": "Le patient doit d'abord être supprimé (suppression logique) avant purge définitive."
        }), 409

    # Hard-delete all linked data — order respects FK constraints
    tables = [
        ("historique",       "patient_id"),
        ("ordonnances",      "patient_id"),
        ("documents",        "patient_id"),
        ("questions",        "patient_id"),
        ("rdv",              "patient_id"),
        ("ivt",              "patient_id"),
        ("suivi_postop",     "patient_id"),
        ("patient_consents", "patient_id"),
        ("patient_doctors",  "patient_id"),
        ("users",            "patient_id"),
    ]
    for table, col in tables:
        try:
            db.execute(f"DELETE FROM {table} WHERE {col}=?", (pid,))
        except Exception:
            pass  # table may not exist in all deployments

    # Delete encrypted image files for this patient
    try:
        import glob as _glob
        doc_rows = db.execute(
            "SELECT image_path FROM documents WHERE patient_id=?", (pid,)
        ).fetchall()
        for row in doc_rows:
            path = (row['image_path'] or '').strip()
            if path and os.path.exists(path):
                os.remove(path)
    except Exception:
        pass

    db.execute("DELETE FROM patients WHERE id=?", (pid,))

    # Keep a minimal erasure record in the audit log (no PII, just IDs and timestamp)
    log_audit(db, 'GDPR_PURGE', 'patients', pid, u['id'], pid,
              f"hard_purge by admin={u['id']}")
    db.commit()
    return jsonify({"ok": True, "purged": pid})
