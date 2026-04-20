import uuid, datetime, json, logging, threading, base64, io, os
from flask import Blueprint, request, jsonify, current_app
from database import get_db, current_user, add_notif, require_role, audit_read, medecin_can_access_patient
from llm import call_llm, LLMUnavailableError, SYSTEM_OPHTHALMO, SYSTEM_IMAGE_ANALYSIS
from security_utils import decrypt_patient, encrypt_field, decrypt_field, decrypt_clinical
from extensions import limiter

logger = logging.getLogger(__name__)

bp = Blueprint('documents', __name__)

# Directory for encrypted image files — keeps images out of SQLite
_DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'uploads', 'documents')


def _save_image_file(doc_id: str, image_b64: str) -> str:
    """Fernet-encrypt image_b64 and save to disk. Returns the absolute file path."""
    os.makedirs(_DOCS_DIR, exist_ok=True)
    path = os.path.join(_DOCS_DIR, f"{doc_id}.enc")
    encrypted = encrypt_field(image_b64)
    with open(path, 'w', encoding='ascii') as f:
        f.write(encrypted)
    return path


def _load_image_b64(doc: dict) -> str:
    """Return the image as a base64 string, reading from file when available.

    Backward-compatible: falls back to the legacy image_b64 DB column so
    documents uploaded before this change continue to work.
    """
    image_path = (doc.get('image_path') or '').strip()
    if image_path and os.path.exists(image_path):
        try:
            with open(image_path, 'r', encoding='ascii') as f:
                return decrypt_field(f.read().strip())
        except Exception as e:
            logger.warning("Failed to load image from %s: %s", image_path, e)
    return doc.get('image_b64') or ''


_ALLOWED_UPLOAD_MAGIC: list[tuple[bytes, str]] = [
    (b'\xff\xd8\xff',      'image/jpeg'),
    (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (b'GIF87a',            'image/gif'),
    (b'GIF89a',            'image/gif'),
    (b'%PDF-',             'application/pdf'),
    (b'RIFF',              'image/webp'),   # WebP starts with RIFF....WEBP
]


def _detect_upload_mime(image_b64: str) -> str | None:
    """Return the detected MIME type, or None if the payload isn't an allowed type."""
    if not image_b64:
        return None
    try:
        raw = base64.b64decode(image_b64[:64])
        for magic, mime in _ALLOWED_UPLOAD_MAGIC:
            if raw.startswith(magic):
                # WebP needs an extra check for the WEBP tag at offset 8
                if mime == 'image/webp' and raw[8:12] != b'WEBP':
                    continue
                return mime
        return None
    except Exception:
        return None


def _validate_image_mime(image_b64: str) -> bool:
    """Backward-compat wrapper — True when the payload is an accepted upload."""
    if not image_b64:
        return True
    return _detect_upload_mime(image_b64) is not None


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


# Retry config for background LLM analysis — exponential backoff for transient errors.
# Total worst case: 0 + 2 + 6 = 8s of sleep before giving up on a temporary failure.
_ANALYSIS_MAX_ATTEMPTS = 3
_ANALYSIS_BACKOFF_BASE = 2.0


def _analyze_in_background(app, doc_id: str, prompt: str, image_b64):
    """Run the LLM analysis in a background thread and persist the result.

    Retries up to _ANALYSIS_MAX_ATTEMPTS on temporary errors with exponential
    backoff. Permanent errors (invalid API key, etc.) fail fast. This replaces
    the previous 'doctor has to click retry by hand' flow for transient glitches.
    """
    import time as _time
    with app.app_context():
        from database import get_db as _get_db
        db = _get_db()

        last_err: Exception | None = None
        for attempt in range(1, _ANALYSIS_MAX_ATTEMPTS + 1):
            try:
                analysis = call_llm(prompt, SYSTEM_IMAGE_ANALYSIS if image_b64 else SYSTEM_OPHTHALMO,
                                    image_b64=image_b64, max_tokens=1200)
                db.execute(
                    "UPDATE documents SET analyse_ia=?, valide=1, analysis_status='done' WHERE id=?",
                    (analysis, doc_id)
                )
                db.commit()
                logger.info("Background analysis done for document %s (attempt %d)", doc_id, attempt)
                return
            except LLMUnavailableError as e:
                last_err = e
                if not e.temporary:
                    # Permanent failure — no point retrying.
                    logger.error("Background LLM analysis permanent failure for doc %s: %s", doc_id, e)
                    db.execute(
                        "UPDATE documents SET analysis_status=?, analyse_ia=? WHERE id=?",
                        ('failed_perm',
                         "⚠️ Analyse échouée (vérifiez vos clés API).",
                         doc_id)
                    )
                    db.commit()
                    return
                logger.warning(
                    "Background LLM analysis temporary failure for doc %s (attempt %d/%d): %s",
                    doc_id, attempt, _ANALYSIS_MAX_ATTEMPTS, e
                )
                if attempt < _ANALYSIS_MAX_ATTEMPTS:
                    _time.sleep(_ANALYSIS_BACKOFF_BASE * (3 ** (attempt - 1)))
                    continue
            except Exception as e:
                last_err = e
                logger.warning(
                    "Background LLM analysis error for doc %s (attempt %d/%d): %s",
                    doc_id, attempt, _ANALYSIS_MAX_ATTEMPTS, e
                )
                if attempt < _ANALYSIS_MAX_ATTEMPTS:
                    _time.sleep(_ANALYSIS_BACKOFF_BASE * (3 ** (attempt - 1)))
                    continue

        # All attempts exhausted — persist a final failure state.
        logger.error("Background LLM analysis exhausted retries for doc %s: %s", doc_id, last_err)
        if isinstance(last_err, LLMUnavailableError):
            db.execute(
                "UPDATE documents SET analysis_status='failed_temp', analyse_ia=? WHERE id=?",
                ("⚠️ Analyse échouée après plusieurs tentatives — réessayez plus tard.", doc_id)
            )
        else:
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
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403
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

    # Validate and compress image before storing
    raw_image = data.get('image', '') or ''
    mime = _detect_upload_mime(raw_image) if raw_image else None
    if raw_image and mime is None:
        return jsonify({"error": "Type de fichier non autorisé. Formats acceptés : JPEG, PNG, GIF, WebP, PDF."}), 400

    # Patients must direct the upload to one of their doctors, otherwise the
    # document would be orphaned and no médecin would ever see it.
    if u['role'] == 'patient' and not target_mid:
        fallback = db.execute(
            "SELECT medecin_id FROM patients WHERE id=?", (pid,)
        ).fetchone()
        target_mid = (fallback['medecin_id'] if fallback else '') or ''
        if not target_mid:
            linked = db.execute(
                "SELECT medecin_id FROM patient_doctors WHERE patient_id=? LIMIT 1", (pid,)
            ).fetchone()
            target_mid = linked['medecin_id'] if linked else ''
    if u['role'] == 'patient' and not target_mid:
        return jsonify({
            "error": "Aucun médecin associé à votre compte. Prenez d'abord un rendez-vous pour pouvoir envoyer un document."
        }), 400

    # Save file to encrypted storage on disk (images compressed, PDFs stored as-is)
    stored_image_path = ''
    if raw_image:
        payload = raw_image if mime == 'application/pdf' else _compress_image(raw_image)
        try:
            stored_image_path = _save_image_file(doc_id, payload)
        except Exception as _ie:
            logger.error("Upload file save failed for %s: %s", doc_id, _ie)
            return jsonify({"error": "Erreur lors de l'enregistrement du fichier"}), 500

    db.execute(
        "INSERT INTO documents (id,patient_id,type,date,description,uploaded_by,valide,image_b64,image_path,source,medecin_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (doc_id, pid, doc_type,
         datetime.datetime.now().strftime("%Y-%m-%d"),
         data.get('description',''), u['role'],
         1 if u['role'] == 'medecin' else 0,
         '', stored_image_path, source, target_mid)
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
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403

    _has_image_expr = (
        "(CASE WHEN (image_b64 != '' AND image_b64 IS NOT NULL) "
        "OR (image_path != '' AND image_path IS NOT NULL) THEN 1 ELSE 0 END) AS has_image"
    )
    if u['role'] == 'medecin':
        # Show documents explicitly directed to this doctor, plus legacy docs with no medecin_id
        rows = db.execute(
            f"SELECT id,patient_id,type,date,description,uploaded_by,valide,notes,analyse_ia,source,deleted,deleted_at,medecin_id,"
            f"{_has_image_expr} "
            "FROM documents WHERE patient_id=? AND source='document' AND deleted=0 "
            "AND (medecin_id=? OR medecin_id='' OR medecin_id IS NULL) "
            "ORDER BY date DESC",
            (pid, u['id'])
        ).fetchall()
    else:
        rows = db.execute(
            f"SELECT id,patient_id,type,date,description,uploaded_by,valide,notes,analyse_ia,source,deleted,deleted_at,medecin_id,"
            f"{_has_image_expr} "
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
    if not medecin_can_access_patient(db, u['id'], pid):
        return jsonify([]), 403
    rows = db.execute(
        "SELECT id,patient_id,type,date,description,uploaded_by,valide,notes,analyse_ia,source,deleted,deleted_at,"
        "(CASE WHEN (image_b64 != '' AND image_b64 IS NOT NULL) "
        "OR (image_path != '' AND image_path IS NOT NULL) THEN 1 ELSE 0 END) AS has_image "
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
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403
    row = db.execute(
        "SELECT * FROM documents WHERE id=? AND patient_id=?", (doc_id, pid)
    ).fetchone()
    if not row:
        return jsonify({}), 404
    result = dict(row)
    # Load image from encrypted file when available (backward-compatible with legacy image_b64)
    result['image_b64'] = _load_image_b64(result)
    audit_read(db, 'documents', doc_id, pid)
    return jsonify(result)


@bp.route('/api/patients/<pid>/documents/<doc_id>/analyze', methods=['POST'])
@limiter.limit("20 per hour")
def analyze_document(pid, doc_id):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    if not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403
    p_row = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    doc   = db.execute("SELECT * FROM documents WHERE id=? AND patient_id=?", (doc_id, pid)).fetchone()
    if not p_row or not doc:
        return jsonify({}), 404
    p = decrypt_patient(dict(p_row))

    # Check ai_analysis consent before proceeding
    consent_row = db.execute(
        "SELECT granted FROM patient_consents "
        "WHERE patient_id=? AND consent_type='ai_analysis' "
        "ORDER BY created_at DESC LIMIT 1",
        (pid,)
    ).fetchone()
    if not consent_row or not consent_row['granted']:
        return jsonify({
            "error": "Consentement IA requis. Veuillez enregistrer le consentement du patient pour l'analyse IA avant de continuer.",
            "consent_required": True
        }), 403

    # If already processing, return current status
    current_status = doc['analysis_status'] if 'analysis_status' in doc.keys() else ''
    if current_status == 'pending':
        return jsonify({"ok": True, "status": "pending", "message": "Analyse déjà en cours…"})

    def _safe_llm(val, max_len=200):
        """Strip prompt-injection markers from free-text fields before inserting into LLM prompt."""
        if val is None:
            return ''
        return (str(val)
                .replace('```', '')
                .replace('<|', '')
                .replace('|>', '')
                .replace('[INST]', '')
                .replace('[/INST]', '')
                .replace('###', ''))[:max_len]

    antecedents = json.loads(p.get('antecedents') or '[]')
    age = datetime.datetime.now().year - int(p['ddn'][:4]) if (p.get('ddn') and p['ddn'][:4].isdigit()) else 0
    safe_antecedents = ', '.join(_safe_llm(a, 80) for a in antecedents) or 'aucun renseigné'
    context = (f"Patient : {_safe_llm(p.get('prenom'), 60)} {_safe_llm(p.get('nom'), 60)}, {age} ans. "
               f"Antécédents : {safe_antecedents}")
    uploader = "le patient" if doc['uploaded_by'] == 'patient' else "le médecin"

    safe_type = _safe_llm(doc['type'])

    image_b64 = _load_image_b64(dict(doc)) or None
    # PDFs are stored like images but vision LLMs can't read them — fall back
    # to contextual text analysis rather than feeding PDF bytes to the model.
    if image_b64 and _detect_upload_mime(image_b64) == 'application/pdf':
        image_b64 = None
    system_prompt = SYSTEM_IMAGE_ANALYSIS if image_b64 else SYSTEM_OPHTHALMO
    doc_description = _safe_llm(doc.get('description') if hasattr(doc, 'get') else '', max_len=300) \
        or _safe_llm(dict(doc).get('description', ''), max_len=300)
    if image_b64:
        prompt = (
            f"[EXAMEN À ANALYSER]\n"
            f"Type déclaré : {safe_type}\n"
            f"Uploadé par : {uploader}\n"
            f"Description fournie : {doc_description or 'aucune'}\n\n"
            f"[CONTEXTE PATIENT]\n{context}\n\n"
            f"[CONSIGNE]\n"
            f"Analyse cette image en suivant strictement le format de sortie imposé par le système "
            f"(6 sections markdown). Sois précis sur la latéralité (OD/OG) quand elle est identifiable "
            f"et sur la localisation des anomalies. Rattache les signes observés au contexte clinique "
            f"du patient (âge, antécédents) lorsque c'est pertinent."
        )
    else:
        prompt = (
            f"{uploader.capitalize()} a uploadé un document de type '{safe_type}' (non-image).\n"
            f"Description : {doc_description or 'aucune'}\n\n"
            f"[CONTEXTE PATIENT]\n{context}\n\n"
            f"Donne au médecin : (1) les points de vigilance clinique pour ce type de document, "
            f"(2) les questions à poser au patient, (3) les examens complémentaires à prévoir, "
            f"(4) les signes d'alerte nécessitant une prise en charge urgente."
        )

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
    if not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403
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
    elif u['role'] == 'medecin':
        if not medecin_can_access_patient(db, u['id'], pid):
            return jsonify({"error": "Accès refusé"}), 403
    else:
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
    if not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403
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
    u = current_user()
    if not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403
    p_row = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    if not p_row:
        return jsonify({"error": "Patient non trouvé"}), 404
    p = decrypt_patient(dict(p_row))

    # Enforce AI consent before sending patient data to third-party LLM
    consent_row = db.execute(
        "SELECT granted FROM patient_consents "
        "WHERE patient_id=? AND consent_type='ai_analysis' "
        "ORDER BY created_at DESC LIMIT 1",
        (pid,)
    ).fetchone()
    if not consent_row or not consent_row['granted']:
        return jsonify({
            "error": "Consentement IA requis. Veuillez enregistrer le consentement du patient avant de générer un résumé.",
            "consent_required": True
        }), 403

    data = request.json or {}
    hid  = data.get('historique_id')

    if hid:
        h_row = db.execute(
            "SELECT * FROM historique WHERE id=? AND patient_id=? AND (deleted IS NULL OR deleted=0)",
            (hid, pid)
        ).fetchone()
    else:
        h_row = db.execute(
            "SELECT * FROM historique WHERE patient_id=? AND (deleted IS NULL OR deleted=0) "
            "ORDER BY date DESC LIMIT 1", (pid,)
        ).fetchone()

    if not h_row:
        return jsonify({"error": "Aucune consultation disponible"}), 404

    h = decrypt_clinical(dict(h_row))

    antecedents = json.loads(p.get('antecedents') or '[]')
    allergies   = json.loads(p.get('allergies')   or '[]')
    age = datetime.datetime.now().year - int(p['ddn'][:4]) if (p.get('ddn') and p['ddn'][:4].isdigit()) else 0

    def _safe(val, max_len=500):
        """Strip prompt-injection markers and cap length for free-text DB fields."""
        if val is None:
            return ''
        return (str(val)
                .replace('```', '')
                .replace('<|', '')
                .replace('|>', '')
                .replace('[INST]', '')
                .replace('[/INST]', '')
                .replace('###', ''))[:max_len]

    safe_antecedents = ', '.join(_safe(a, 80) for a in antecedents) or 'aucun renseigné'
    safe_allergies   = ', '.join(_safe(a, 80) for a in allergies) if allergies else 'Aucune'
    prompt = (
        "Génère un compte-rendu de consultation ophtalmologique structuré et professionnel "
        "à partir des données cliniques suivantes (données issues du dossier médical) :\n\n"
        f"[DONNÉES PATIENT]\n"
        f"Nom : {_safe(p.get('prenom'), 60)} {_safe(p.get('nom'), 60)}\n"
        f"Age : {age} ans\n"
        f"Sexe : {_safe(p.get('sexe'), 20)}\n"
        f"Antécédents : {safe_antecedents}\n"
        f"Allergies : {safe_allergies}\n\n"
        f"[DONNÉES CONSULTATION]\n"
        f"Date : {_safe(h.get('date'), 20)}\n"
        f"Motif : {_safe(h['motif'])}\n"
        f"Acuité OD : {_safe(h['acuite_od'], 50)} | OG : {_safe(h['acuite_og'], 50)}\n"
        f"Tonus OD : {_safe(h['tension_od'], 20)} mmHg | OG : {_safe(h['tension_og'], 20)} mmHg\n"
        f"Réfraction OD : S {_safe(h['refraction_od_sph'], 20)} C {_safe(h['refraction_od_cyl'], 20)} Axe {_safe(h['refraction_od_axe'], 20)}\n"
        f"Réfraction OG : S {_safe(h['refraction_og_sph'], 20)} C {_safe(h['refraction_og_cyl'], 20)} Axe {_safe(h['refraction_og_axe'], 20)}\n"
        f"Segment antérieur : {_safe(h['segment_ant']) or 'non renseigné'}\n"
        f"Diagnostic : {_safe(h['diagnostic'])}\n"
        f"Traitement : {_safe(h['traitement'])}\n"
        f"Notes : {_safe(h['notes']) or 'aucune'}\n\n"
        "[FIN DES DONNÉES]\n\n"
        "Rédige un compte-rendu complet, clair et structuré en français, prêt à être transmis ou archivé."
    )

    try:
        summary = call_llm(prompt, SYSTEM_OPHTHALMO, max_tokens=1000)
    except LLMUnavailableError as e:
        logger.error(f"LLM summary failed: {e}")
        msg = ("Service IA temporairement indisponible — réessayez dans quelques minutes."
               if e.temporary else
               "Service IA non configuré — vérifiez les clés API dans les paramètres.")
        return jsonify({"error": msg, "temporary": e.temporary}), 503
    except Exception as e:
        logger.error(f"LLM summary unexpected error: {e}")
        return jsonify({"error": "Erreur inattendue du service IA.", "temporary": True}), 503

    return jsonify({"ok": True, "summary": summary})
