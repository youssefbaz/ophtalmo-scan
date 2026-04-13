import uuid, datetime, json, logging, threading, base64, io
from flask import Blueprint, request, jsonify, current_app
from database import get_db, current_user, add_notif, require_role
from llm import call_llm, SYSTEM_OPHTHALMO
from security_utils import decrypt_patient
from extensions import limiter

logger = logging.getLogger(__name__)

bp = Blueprint('documents', __name__)


def _compress_image(image_b64: str, max_dim: int = 1600, quality: int = 78) -> str:
    """Resize and JPEG-compress a base64 image to reduce database storage.

    Falls back to the original if compression fails or produces a larger result.
    """
    if not image_b64:
        return image_b64
    try:
        from PIL import Image
        raw = base64.b64decode(image_b64)
        img = Image.open(io.BytesIO(raw))
        # Flatten transparency to white background for JPEG
        if img.mode in ('RGBA', 'P', 'LA'):
            bg = Image.new('RGB', img.size, (255, 255, 255))
            src = img.convert('RGBA') if img.mode == 'P' else img
            mask = src.split()[3] if src.mode in ('RGBA', 'LA') else None
            bg.paste(src.convert('RGB'), mask=mask)
            img = bg
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        # Resize only when necessary (maintain aspect ratio)
        if img.width > max_dim or img.height > max_dim:
            img.thumbnail((max_dim, max_dim), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality, optimize=True)
        compressed = base64.b64encode(buf.getvalue()).decode('ascii')
        # Only keep the compressed version when it's actually smaller
        return compressed if len(compressed) < len(image_b64) else image_b64
    except Exception as e:
        logger.warning(f"Image compression failed: {e}")
        return image_b64


def _analyze_in_background(app, doc_id: str, prompt: str, image_b64):
    """Run the LLM analysis in a background thread and persist the result."""
    with app.app_context():
        from database import get_db as _get_db
        db = _get_db()
        try:
            analysis = call_llm(prompt, SYSTEM_OPHTHALMO, image_b64=image_b64, max_tokens=800)
            db.execute(
                "UPDATE documents SET analyse_ia=?, valide=1, analysis_status='done' WHERE id=?",
                (analysis, doc_id)
            )
            db.commit()
            logger.info(f"Background analysis done for document {doc_id}")
        except Exception as e:
            logger.error(f"Background LLM analysis failed for doc {doc_id}: {e}")
            db.execute(
                "UPDATE documents SET analysis_status='failed' WHERE id=?", (doc_id,)
            )
            db.commit()


@bp.route('/api/patients/<pid>/upload', methods=['POST'])
@limiter.limit("30 per hour; 5 per minute")
def upload_document(pid):
    u = current_user()
    if not u:
        return jsonify({}), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    _p = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not _p:
        return jsonify({"error": "Patient non trouvé"}), 404
    p = decrypt_patient(dict(_p))

    data       = request.json or {}
    doc_id     = "DOC" + str(uuid.uuid4())[:6].upper()
    doc_type   = data.get('type', 'Document')
    source     = 'imagerie' if u['role'] != 'patient' else 'document'
    target_mid = data.get('medecin_id', '') or ''  # doctor this upload is directed to

    # For doctor uploads, always set medecin_id to themselves
    if u['role'] == 'medecin':
        target_mid = u['id']

    # Compress image before storing to reduce DB size
    raw_image = data.get('image', '') or ''
    stored_image = _compress_image(raw_image) if raw_image else ''

    db.execute(
        "INSERT INTO documents (id,patient_id,type,date,description,uploaded_by,valide,image_b64,source,medecin_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (doc_id, pid, doc_type,
         datetime.datetime.now().strftime("%Y-%m-%d"),
         data.get('description',''), u['role'],
         1 if u['role'] == 'medecin' else 0,
         stored_image, source, target_mid)
    )
    db.commit()

    if u['role'] == 'patient':
        add_notif(db, "document_uploaded",
                  f"📎 {p['prenom']} {p['nom']} a uploadé : {doc_type}",
                  "patient", pid, {"doc_id": doc_id},
                  medecin_id=target_mid or None)

    return jsonify({"ok": True, "id": doc_id})


@bp.route('/api/patients/<pid>/documents', methods=['GET'])
def get_documents(pid):
    u = current_user()
    if not u:
        return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()

    if u['role'] == 'medecin':
        # Show documents explicitly directed to this doctor, plus legacy docs with no medecin_id
        rows = db.execute(
            "SELECT id,patient_id,type,date,description,uploaded_by,valide,notes,analyse_ia,source,deleted,deleted_at,medecin_id,"
            "(CASE WHEN image_b64 != '' AND image_b64 IS NOT NULL THEN 1 ELSE 0 END) AS has_image "
            "FROM documents WHERE patient_id=? AND source='document' AND deleted=0 "
            "AND (medecin_id=? OR medecin_id='' OR medecin_id IS NULL) "
            "ORDER BY date DESC",
            (pid, u['id'])
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT id,patient_id,type,date,description,uploaded_by,valide,notes,analyse_ia,source,deleted,deleted_at,medecin_id,"
            "(CASE WHEN image_b64 != '' AND image_b64 IS NOT NULL THEN 1 ELSE 0 END) AS has_image "
            "FROM documents WHERE patient_id=? AND source='document' AND deleted=0 ORDER BY date DESC",
            (pid,)
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/patients/<pid>/documents/deleted', methods=['GET'])
def get_deleted_documents(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify([]), 403
    db = get_db()
    rows = db.execute(
        "SELECT id,patient_id,type,date,description,uploaded_by,valide,notes,analyse_ia,source,deleted,deleted_at,"
        "(CASE WHEN image_b64 != '' AND image_b64 IS NOT NULL THEN 1 ELSE 0 END) AS has_image "
        "FROM documents WHERE patient_id=? AND deleted=1 ORDER BY deleted_at DESC",
        (pid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/patients/<pid>/documents/<doc_id>', methods=['GET'])
def get_document(pid, doc_id):
    u = current_user()
    if not u:
        return jsonify({}), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    row = db.execute(
        "SELECT * FROM documents WHERE id=? AND patient_id=?", (doc_id, pid)
    ).fetchone()
    if not row:
        return jsonify({}), 404
    return jsonify(dict(row))


@bp.route('/api/patients/<pid>/documents/<doc_id>/analyze', methods=['POST'])
@limiter.limit("20 per hour")
def analyze_document(pid, doc_id):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    p   = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    doc = db.execute("SELECT * FROM documents WHERE id=? AND patient_id=?", (doc_id, pid)).fetchone()
    if not p or not doc:
        return jsonify({}), 404

    # If already processing, return current status
    current_status = doc['analysis_status'] if 'analysis_status' in doc.keys() else ''
    if current_status == 'pending':
        return jsonify({"ok": True, "status": "pending", "message": "Analyse déjà en cours…"})

    antecedents = json.loads(p['antecedents'] or '[]')
    age = datetime.datetime.now().year - int(p['ddn'][:4]) if p['ddn'] else 0
    context = (f"Patient : {p['prenom']} {p['nom']}, {age} ans. "
               f"Antécédents : {', '.join(antecedents) or 'aucun renseigné'}")
    uploader = "le patient" if doc['uploaded_by'] == 'patient' else "le médecin"

    image_b64 = doc['image_b64'] or None
    if image_b64:
        prompt = (f"Analysez cette image ophtalmologique de type '{doc['type']}' uploadée par {uploader}. "
                  f"Contexte : {context}. "
                  f"Décrivez précisément les éléments cliniques visibles (structure, anomalies, lésions), "
                  f"formulez une impression diagnostique et des recommandations thérapeutiques.")
    else:
        prompt = (f"{uploader.capitalize()} a uploadé un document de type '{doc['type']}'. "
                  f"Contexte : {context}. "
                  f"Donnez les points de vigilance clinique et les recommandations générales.")

    # Mark as pending and fire background thread — return immediately
    db.execute("UPDATE documents SET analysis_status='pending' WHERE id=?", (doc_id,))
    db.commit()

    app_ref = current_app._get_current_object()
    threading.Thread(
        target=_analyze_in_background,
        args=(app_ref, doc_id, prompt, image_b64),
        daemon=True
    ).start()

    return jsonify({"ok": True, "status": "pending",
                    "message": "Analyse IA lancée — vérifiez le résultat dans quelques secondes."})


@bp.route('/api/patients/<pid>/documents/<doc_id>/validate', methods=['POST'])
def validate_document(pid, doc_id):
    """Mark a patient-uploaded document as reviewed/validated by the doctor."""
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    if not db.execute("SELECT id FROM documents WHERE id=? AND patient_id=?", (doc_id, pid)).fetchone():
        return jsonify({"error": "Non trouvé"}), 404
    db.execute("UPDATE documents SET valide=1 WHERE id=?", (doc_id,))
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/documents/<doc_id>', methods=['DELETE'])
def delete_document(pid, doc_id):
    """Soft-delete: marks as deleted, keeps image_b64 in storage."""
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    db = get_db()
    row = db.execute("SELECT * FROM documents WHERE id=? AND patient_id=?", (doc_id, pid)).fetchone()
    if not row:
        return jsonify({"error": "Non trouvé"}), 404
    # Patients can only delete documents they uploaded themselves
    if u['role'] == 'patient':
        if u.get('patient_id') != pid or row['uploaded_by'] != 'patient':
            return jsonify({"error": "Accès refusé"}), 403
    elif u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db.execute(
        "UPDATE documents SET deleted=1, deleted_at=? WHERE id=?",
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), doc_id)
    )
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/patients/<pid>/documents/<doc_id>/restore', methods=['POST'])
def restore_document(pid, doc_id):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    db.execute(
        "UPDATE documents SET deleted=0, deleted_at='' WHERE id=? AND patient_id=?",
        (doc_id, pid)
    )
    db.commit()
    return jsonify({"ok": True})


# ─── AI CONSULTATION SUMMARY ──────────────────────────────────────────────────

@bp.route('/api/patients/<pid>/consultation-summary', methods=['POST'])
@require_role('medecin')
def consultation_summary(pid):
    """Generate an AI-written clinical summary from the latest consultation."""
    db = get_db()
    p = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not p:
        return jsonify({"error": "Patient non trouvé"}), 404

    data = request.json or {}
    hid  = data.get('historique_id')

    if hid:
        h = db.execute(
            "SELECT * FROM historique WHERE id=? AND patient_id=? AND (deleted IS NULL OR deleted=0)",
            (hid, pid)
        ).fetchone()
    else:
        h = db.execute(
            "SELECT * FROM historique WHERE patient_id=? AND (deleted IS NULL OR deleted=0) "
            "ORDER BY date DESC LIMIT 1", (pid,)
        ).fetchone()

    if not h:
        return jsonify({"error": "Aucune consultation disponible"}), 404

    antecedents = json.loads(p['antecedents'] or '[]')
    allergies   = json.loads(p['allergies']   or '[]')
    age = datetime.datetime.now().year - int(p['ddn'][:4]) if p.get('ddn') else 0

    def _safe(val):
        """Strip prompt-injection attempts from free-text DB fields."""
        if val is None:
            return ''
        return str(val).replace('```', '').replace('<|', '').replace('|>', '')

    prompt = (
        "Génère un compte-rendu de consultation ophtalmologique structuré et professionnel "
        "à partir des données cliniques suivantes (données issues du dossier médical) :\n\n"
        f"[DONNÉES PATIENT]\n"
        f"Nom : {p['prenom']} {p['nom']}\n"
        f"Age : {age} ans\n"
        f"Sexe : {p['sexe']}\n"
        f"Antécédents : {', '.join(antecedents) or 'aucun renseigné'}\n"
        f"Allergies : {', '.join(allergies) if allergies else 'Aucune'}\n\n"
        f"[DONNÉES CONSULTATION]\n"
        f"Date : {h['date']}\n"
        f"Motif : {_safe(h['motif'])}\n"
        f"Acuité OD : {_safe(h['acuite_od'])} | OG : {_safe(h['acuite_og'])}\n"
        f"Tonus OD : {_safe(h['tension_od'])} mmHg | OG : {_safe(h['tension_og'])} mmHg\n"
        f"Réfraction OD : S {_safe(h['refraction_od_sph'])} C {_safe(h['refraction_od_cyl'])} Axe {_safe(h['refraction_od_axe'])}\n"
        f"Réfraction OG : S {_safe(h['refraction_og_sph'])} C {_safe(h['refraction_og_cyl'])} Axe {_safe(h['refraction_og_axe'])}\n"
        f"Segment antérieur : {_safe(h['segment_ant']) or 'non renseigné'}\n"
        f"Diagnostic : {_safe(h['diagnostic'])}\n"
        f"Traitement : {_safe(h['traitement'])}\n"
        f"Notes : {_safe(h['notes']) or 'aucune'}\n\n"
        "[FIN DES DONNÉES]\n\n"
        "Rédige un compte-rendu complet, clair et structuré en français, prêt à être transmis ou archivé."
    )

    try:
        summary = call_llm(prompt, SYSTEM_OPHTHALMO, max_tokens=1000)
    except Exception as e:
        logger.error(f"LLM summary failed: {e}")
        return jsonify({"error": "Service IA indisponible, réessayez dans quelques minutes."}), 503

    return jsonify({"ok": True, "summary": summary})
