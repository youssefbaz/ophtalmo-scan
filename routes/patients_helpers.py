"""
routes/patients_helpers.py — Shared helpers used across patients_*.py modules.

Extracted from the original monolithic patients.py to allow splitting without
circular imports. All patient route modules import from here.
"""
import re, uuid, calendar, datetime, json, logging
from flask import abort
from database import get_db
from security_utils import (decrypt_patient, decrypt_field,
                             decrypt_clinical, decrypt_ordonnance_fields,
                             decrypt_question_fields)

logger = logging.getLogger(__name__)

_FERNET_RE = re.compile(r'^gAAAAA[A-Za-z0-9_\-]{40,}={0,2}$')


# ─── ACCESS CONTROL ────────────────────────────────────────────────────────────

def _assert_owns_patient(db, u, pid):
    """Abort 403 if a médecin does not own the patient. Admins pass freely."""
    if u['role'] == 'admin':
        return
    if u['role'] == 'medecin':
        row = db.execute(
            "SELECT id FROM patients WHERE id=? AND medecin_id=? AND (deleted IS NULL OR deleted=0)",
            (pid, u['id'])
        ).fetchone()
        if not row:
            # Also allow access if linked via patient_doctors (patient booked an RDV with this doctor)
            row = db.execute(
                "SELECT 1 FROM patient_doctors WHERE patient_id=? AND medecin_id=?",
                (pid, u['id'])
            ).fetchone()
        if not row:
            abort(403)
    # patients are checked separately at the route level (patient_id match)


# ─── PATIENT BUILDER ───────────────────────────────────────────────────────────

def _build_patient(db, pid, strip_images=True):
    """Assemble a full patient dict from all DB tables (PII decrypted)."""
    row = db.execute(
        "SELECT * FROM patients WHERE id=? AND (deleted IS NULL OR deleted=0)", (pid,)
    ).fetchone()
    if not row:
        return None
    p = decrypt_patient(dict(row))
    for _f in ('antecedents', 'allergies'):
        v = p.get(_f)
        if isinstance(v, list):
            continue
        if not v:
            p[_f] = []
            continue
        try:
            parsed = json.loads(v)
            p[_f] = parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            p[_f] = []

    p['historique_total'] = db.execute(
        "SELECT COUNT(*) FROM historique WHERE patient_id=? AND (deleted IS NULL OR deleted=0)",
        (pid,)
    ).fetchone()[0]
    p['historique'] = [decrypt_clinical(dict(r)) for r in
        db.execute(
            "SELECT * FROM historique WHERE patient_id=? AND (deleted IS NULL OR deleted=0) "
            "ORDER BY date DESC LIMIT 50", (pid,)
        )]

    rdvs = [dict(r) for r in
        db.execute(
            "SELECT * FROM rdv WHERE patient_id=? AND (deleted IS NULL OR deleted=0) "
            "ORDER BY date, heure", (pid,)
        )]
    for r in rdvs:
        r['urgent'] = bool(r['urgent'])
        med = r.get('medecin') or ''
        r['medecin'] = '' if (med and _FERNET_RE.match(med.strip())) else med
    p['rdv'] = rdvs

    imgs = [dict(r) for r in
        db.execute(
            "SELECT * FROM documents WHERE patient_id=? AND source='imagerie' AND deleted=0",
            (pid,)
        )]
    docs = [dict(r) for r in
        db.execute(
            "SELECT * FROM documents WHERE patient_id=? AND source='document' AND deleted=0",
            (pid,)
        )]
    for item in imgs + docs:
        item['has_image'] = bool(item.get('image_b64'))
    if strip_images:
        for item in imgs + docs:
            item.pop('image_b64', None)
    p['imagerie']  = imgs
    p['documents'] = docs

    questions = [decrypt_question_fields(dict(r)) for r in
        db.execute(
            "SELECT * FROM questions WHERE patient_id=? AND deleted=0 ORDER BY date DESC LIMIT 50",
            (pid,)
        )]
    for q in questions:
        q['reponse_validee'] = bool(q['reponse_validee'])
    p['questions'] = questions

    p['ivt'] = [dict(r) for r in
        db.execute(
            "SELECT * FROM ivt WHERE patient_id=? AND (deleted IS NULL OR deleted=0) "
            "ORDER BY date DESC, numero DESC LIMIT 100", (pid,)
        )]

    ordonnances = [decrypt_ordonnance_fields(dict(r)) for r in
        db.execute(
            "SELECT * FROM ordonnances WHERE patient_id=? AND (deleted IS NULL OR deleted=0) "
            "ORDER BY date DESC LIMIT 50", (pid,)
        )]
    for o in ordonnances:
        try:
            o['contenu'] = json.loads(o['contenu'] or '{}')
        except Exception:
            o['contenu'] = {}
    p['ordonnances'] = ordonnances

    return p


# ─── ANONYMIZATION ─────────────────────────────────────────────────────────────

def _anonymize(p):
    import hashlib
    return {
        "id":          p["id"],
        "code":        hashlib.md5(p["id"].encode()).hexdigest()[:8].upper(),
        "sexe":        p["sexe"],
        "age":         datetime.datetime.now().year - int(p["ddn"][:4]) if p.get("ddn") else 0,
        "antecedents": p["antecedents"],
        "nb_rdv":      len(p["rdv"]),
        "nb_imagerie": len(p["imagerie"])
    }


# ─── DATE MATH ─────────────────────────────────────────────────────────────────

def _add_months(d, months):
    """Add a number of months to a date, clamping to end-of-month."""
    month = d.month - 1 + months
    year  = d.year + month // 12
    month = month % 12 + 1
    day   = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


SUIVI_ETAPES = [
    ("Jour 2",  lambda d: d + datetime.timedelta(days=2)),
    ("Jour 7",  lambda d: d + datetime.timedelta(days=7)),
    ("1 Mois",  lambda d: d + datetime.timedelta(days=30)),
    ("2 Mois",  lambda d: _add_months(d, 2)),
    ("3 Mois",  lambda d: _add_months(d, 3)),
    ("6 Mois",  lambda d: _add_months(d, 6)),
    ("1 An",    lambda d: _add_months(d, 12)),
    ("18 Mois", lambda d: _add_months(d, 18)),
    ("2 Ans",   lambda d: _add_months(d, 24)),
]


# ─── SURGERY / POST-OP ─────────────────────────────────────────────────────────

def _generate_suivi(db, pid, date_chirurgie_str, medecin_nom='', type_chirurgie='',
                    add_to_agenda=True, medecin_id=''):
    """Create post-op follow-up steps, optionally also creating linked agenda RDVs.

    add_to_agenda=True  → also insert a confirmed RDV for each step (original behaviour).
    add_to_agenda=False → create suivi steps only; rdv_id stays empty. Doctor can book
                          individual steps later via the "Ajouter au planning" button.
    Skips etapes that already exist for this patient.
    Returns the number of new steps created.
    """
    try:
        base = datetime.date.fromisoformat(date_chirurgie_str)
    except ValueError:
        return 0
    existing = {r['etape'] for r in
                db.execute("SELECT etape FROM suivi_postop WHERE patient_id=?", (pid,)).fetchall()}
    created = 0
    for etape, calc in SUIVI_ETAPES:
        if etape in existing:
            continue
        sid         = "S" + str(uuid.uuid4())[:7].upper()
        date_prevue = calc(base).isoformat()
        rdv_id      = ''
        if add_to_agenda:
            rdv_id    = "RDV" + str(uuid.uuid4())[:6].upper()
            type_rdv  = f"Suivi post-op {etape}"
            notes_rdv = f"Suivi post-opératoire {etape} — {type_chirurgie or 'chirurgie'}"
            db.execute(
                "INSERT INTO rdv (id, patient_id, date, heure, type, statut, medecin, notes, urgent, demande_par, medecin_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (rdv_id, pid, date_prevue, '09:00', type_rdv, 'confirmé',
                 medecin_nom, notes_rdv, 0, 'system', medecin_id)
            )
        db.execute(
            "INSERT INTO suivi_postop (id, patient_id, etape, date_prevue, statut, rdv_id) VALUES (?,?,?,?,?,?)",
            (sid, pid, etape, date_prevue, 'a_faire', rdv_id)
        )
        created += 1
    db.commit()
    return created


# ─── ACCOUNT AUTO-CREATION ─────────────────────────────────────────────────────

def _auto_create_account(db, pid, nom, prenom, email='', app_host=''):
    """Auto-create a user account for a patient and email credentials if possible.

    Returns dict with username/password/email_sent, or None if account already exists.
    """
    import re as _re, secrets as _sec, string as _str
    from werkzeug.security import generate_password_hash as _hash

    if db.execute("SELECT id FROM users WHERE patient_id=?", (pid,)).fetchone():
        return None  # already has an account

    base = _re.sub(r'[^a-z0-9._-]', '',
                   f"patient.{prenom.lower().strip()}.{nom.lower().strip()}")
    if not base or base == 'patient..':
        base = f"patient.{pid.lower()}"
    username = base
    counter  = 1
    while db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
        username = f"{base}{counter}"
        counter += 1

    alphabet = _str.ascii_letters + _str.digits
    password = ''.join(_sec.choice(alphabet) for _ in range(12))

    uid = "U" + str(uuid.uuid4())[:6].upper()
    db.execute(
        "INSERT INTO users (id, username, password_hash, role, nom, prenom, patient_id, status) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (uid, username, _hash(password), 'patient', nom, prenom, pid, 'active')
    )

    email_sent = False
    if email and '@' in email:
        try:
            from email_notif import send_credentials_email
            email_sent = send_credentials_email(email, prenom, nom, username, password, app_host)
        except Exception:
            pass

    return {"username": username, "password": password, "email_sent": email_sent}


# ─── PATIENT ID GENERATOR ──────────────────────────────────────────────────────

def _next_patient_id(db):
    row = db.execute(
        "SELECT MAX(CAST(SUBSTR(id,2) AS INTEGER)) FROM patients WHERE id GLOB 'P[0-9]*'"
    ).fetchone()
    n = (row[0] or 0) + 1
    return f"P{n:03d}"
