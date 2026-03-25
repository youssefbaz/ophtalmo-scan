#!/usr/bin/env python3
"""
OphtalmoScan v2 — Multi-Role Ophthalmology Management Platform
Roles: Médecin | Assistant | Patient
LLM: Groq API (llama-3.1-8b-instant) — gratuit, rapide, sans abonnement
"""

import json, base64, os, re, csv, io, datetime, uuid, hashlib
from flask import Flask, request, jsonify, session, render_template_string, redirect
import urllib.request, urllib.error

app = Flask(__name__)
app.secret_key = 'ophthalmo_v2_secret_2025'
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ─── CONFIGURATION LLM ────────────────────────────────────────────────────────
# Mettre la clé Groq dans la variable d'environnement GROQ_API_KEY
# Lancer avec: set GROQ_API_KEY=gsk_... && python app.py  (Windows)
#              export GROQ_API_KEY=gsk_... && python app.py (Mac/Linux)
# Créer un compte gratuit sur: https://console.groq.com

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"  # Meilleur modèle Groq gratuit

# ─── IN-MEMORY DATABASE ───────────────────────────────────────────────────────

USERS = {
    "dr.martin": {"password": "medecin123", "role": "medecin", "nom": "Dr. Martin", "prenom": "Jean", "id": "U001"},
    "assist.sara": {"password": "assist123", "role": "assistant", "nom": "Benali", "prenom": "Sara", "id": "U002"},
    "patient.marie": {"password": "patient123", "role": "patient", "nom": "Dupont", "prenom": "Marie", "patient_id": "P001", "id": "U003"},
    "patient.jp": {"password": "patient123", "role": "patient", "nom": "Bernard", "prenom": "Jean-Paul", "patient_id": "P002", "id": "U004"},
}

PATIENTS = {
    "P001": {
        "id": "P001", "nom": "Dupont", "prenom": "Marie", "ddn": "1975-03-15", "sexe": "F",
        "telephone": "06 12 34 56 78", "email": "marie.dupont@email.com",
        "antecedents": ["Glaucome chronique", "Myopie forte (-6D)"],
        "allergies": ["Pénicilline"],
        "historique": [
            {"date": "2024-01-15", "motif": "Suivi glaucome", "diagnostic": "Glaucome angle ouvert stabilisé",
             "traitement": "Timolol 0.5% x2/j", "tension_od": "16 mmHg", "tension_og": "17 mmHg",
             "acuite_od": "8/10", "acuite_og": "7/10", "notes": "Champ visuel stable.", "medecin": "Dr. Martin"},
            {"date": "2023-09-20", "motif": "Contrôle annuel", "diagnostic": "Myopie stable",
             "traitement": "Renouvellement ordonnance", "tension_od": "15 mmHg", "tension_og": "16 mmHg",
             "acuite_od": "9/10", "acuite_og": "8/10", "notes": "Fond d'œil normal.", "medecin": "Dr. Martin"},
        ],
        "imagerie": [
            {"id": "IMG001", "type": "OCT Macula", "date": "2024-01-15", "description": "OCT macula OD et OG",
             "notes": "Épaisseur rétinienne normale.", "uploaded_by": "medecin", "valide": True}
        ],
        "rdv": [
            {"id": "RDV001", "date": "2024-04-22", "heure": "10:30", "type": "Suivi glaucome",
             "statut": "confirmé", "medecin": "Dr. Martin", "notes": "", "urgent": False},
            {"id": "RDV002", "date": "2024-07-15", "heure": "14:00", "type": "OCT de contrôle",
             "statut": "programmé", "medecin": "Dr. Martin", "notes": "", "urgent": False},
        ],
        "questions": [],
        "documents": []
    },
    "P002": {
        "id": "P002", "nom": "Bernard", "prenom": "Jean-Paul", "ddn": "1958-11-28", "sexe": "M",
        "telephone": "06 98 76 54 32", "email": "jp.bernard@email.com",
        "antecedents": ["DMLA exsudative OG", "Diabète type 2"],
        "allergies": [],
        "historique": [
            {"date": "2024-02-05", "motif": "IVT anti-VEGF #6", "diagnostic": "DMLA exsudative OG",
             "traitement": "Ranibizumab 0.5mg IVT OG", "tension_od": "13 mmHg", "tension_og": "14 mmHg",
             "acuite_od": "9/10", "acuite_og": "4/10", "notes": "Bonne réponse au traitement.", "medecin": "Dr. Martin"},
        ],
        "imagerie": [],
        "rdv": [
            {"id": "RDV003", "date": "2024-04-10", "heure": "09:00", "type": "IVT anti-VEGF #7",
             "statut": "confirmé", "medecin": "Dr. Martin", "notes": "", "urgent": False},
        ],
        "questions": [],
        "documents": []
    }
}

NOTIFICATIONS = []

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def add_notif(type_, message, from_role, patient_id=None, data=None):
    NOTIFICATIONS.insert(0, {
        "id": str(uuid.uuid4())[:8],
        "type": type_, "message": message, "from_role": from_role,
        "patient_id": patient_id, "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "lu": False, "data": data or {}
    })

def current_user():
    return USERS.get(session.get('username'))

def require_role(*roles):
    u = current_user()
    if not u or u['role'] not in roles:
        return False
    return True

def anonymize_patient(p):
    return {
        "id": p["id"],
        "code": hashlib.md5(p["id"].encode()).hexdigest()[:8].upper(),
        "sexe": p["sexe"], "age": datetime.datetime.now().year - int(p["ddn"][:4]),
        "antecedents": p["antecedents"],
        "nb_rdv": len(p["rdv"]), "nb_imagerie": len(p["imagerie"])
    }

# ─── LLM API (GROQ) ───────────────────────────────────────────────────────────

def call_llm(prompt, system, image_b64=None, max_tokens=800):
    """
    Appel Groq API — format compatible OpenAI.
    Note: Groq ne supporte pas les images. Si image_b64 fourni,
    on indique au médecin d'analyser manuellement.
    """
    if not GROQ_API_KEY:
        return "⚠️ Clé GROQ_API_KEY manquante. Configurez la variable d'environnement."

    # Groq ne supporte pas les images — on le signale proprement
    if image_b64:
        return ("⚠️ L'analyse automatique d'images n'est pas disponible dans cette version. "
                "Veuillez analyser l'image manuellement et saisir vos observations dans les notes.")

    payload = json.dumps({
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3
    }).encode('utf-8')

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_API_KEY}"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read())['choices'][0]['message']['content']
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        return f"Erreur Groq ({e.code}): {body[:200]}"
    except Exception as e:
        return f"Erreur IA: {str(e)}"

# ─── PROMPTS SYSTÈME ──────────────────────────────────────────────────────────

SYSTEM_OPHTHALMO = """Tu es un assistant IA expert en ophtalmologie clinique, conçu pour aider les médecins ophtalmologistes francophones.
Tu maîtrises: glaucome, DMLA, cataracte, kératocône, rétinopathie diabétique, uvéites, chirurgie réfractive, OCT, angiographie, topographie cornéenne.
Réponds toujours en français, de façon précise et structurée. Cite les guidelines HAS/AAO quand pertinent.
Sois concis, cliniquement rigoureux, et adapte tes réponses au contexte du patient fourni."""

SYSTEM_IMPORT = """Tu es un assistant d'extraction de données médicales. 
À partir du texte fourni (issu d'un CSV, PDF ou formulaire), extrais les informations des patients et retourne UNIQUEMENT un JSON valide.
Format attendu (tableau de patients):
[{"nom":"...","prenom":"...","ddn":"YYYY-MM-DD","sexe":"M/F","telephone":"...","email":"...","antecedents":["..."],"allergies":["..."]}]
Si une info est manquante, utilise une chaîne vide "". Ne retourne rien d'autre que le JSON."""

SYSTEM_RESPONSE_DRAFT = """Tu es un assistant médical en ophtalmologie. Un patient a posé une question à son médecin.
Génère une réponse professionnelle, rassurante et claire que le médecin pourra valider ou modifier.
La réponse doit être compréhensible pour un patient non-médecin. Reste concis (3-5 phrases max).
Réponds toujours en français."""

# ─── AUTH ROUTES ──────────────────────────────────────────────────────────────

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    user = USERS.get(username)
    if user and user['password'] == password:
        session['username'] = username
        return jsonify({"ok": True, "role": user['role'], "nom": user['nom'], "prenom": user.get('prenom','')})
    return jsonify({"ok": False, "error": "Identifiants incorrects"}), 401

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"ok": True})

@app.route('/me', methods=['GET'])
def me():
    u = current_user()
    if not u:
        return jsonify({"authenticated": False}), 401
    info = {"authenticated": True, "role": u['role'], "nom": u['nom'], "prenom": u.get('prenom','')}
    if u['role'] == 'patient':
        info['patient_id'] = u.get('patient_id')
    return jsonify(info)

# ─── PATIENT ROUTES ───────────────────────────────────────────────────────────

@app.route('/api/patients', methods=['GET'])
def get_patients():
    u = current_user()
    if not u: return jsonify([]), 401
    q = request.args.get('q', '').lower()
    if u['role'] == 'patient':
        pid = u.get('patient_id')
        p = PATIENTS.get(pid)
        return jsonify([{"id": p['id'], "nom": p['nom'], "prenom": p['prenom']}] if p else [])
    if u['role'] == 'assistant':
        return jsonify([anonymize_patient(p) for p in PATIENTS.values()])
    result = []
    for p in PATIENTS.values():
        if not q or q in p['nom'].lower() or q in p['prenom'].lower() or q in p['id'].lower():
            result.append({"id": p['id'], "nom": p['nom'], "prenom": p['prenom'],
                           "ddn": p['ddn'], "antecedents": p['antecedents'][:2],
                           "nb_rdv_urgent": sum(1 for r in p['rdv'] if r.get('urgent') and r['statut'] == 'en_attente')})
    return jsonify(result)

@app.route('/api/patients/<pid>', methods=['GET'])
def get_patient(pid):
    u = current_user()
    if not u: return jsonify({}), 401
    p = PATIENTS.get(pid)
    if not p: return jsonify({"error": "Non trouvé"}), 404
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    if u['role'] == 'assistant':
        return jsonify(anonymize_patient(p))
    if u['role'] == 'patient':
        # Patient sees their own data but not clinical notes and raw tension
        patient_view = {k: v for k, v in p.items()}
        patient_view['historique'] = [
            {
                "date": h["date"],
                "motif": h["motif"],
                "traitement": h["traitement"],
                "acuite_od": h.get("acuite_od",""),
                "acuite_og": h.get("acuite_og",""),
                # Hidden from patient: diagnostic détaillé, tension, notes médecin
            }
            for h in p["historique"]
        ]
        return jsonify(patient_view)
    return jsonify(p)

@app.route('/api/patients', methods=['POST'])
def add_patient():
    u = current_user()
    if not u or u['role'] != 'medecin': return jsonify({"error": "Accès refusé"}), 403
    data = request.json
    pid = "P" + str(1000 + len(PATIENTS)).zfill(3)
    PATIENTS[pid] = {
        "id": pid, "nom": data.get("nom",""), "prenom": data.get("prenom",""),
        "ddn": data.get("ddn",""), "sexe": data.get("sexe",""),
        "telephone": data.get("telephone",""), "email": data.get("email",""),
        "antecedents": data.get("antecedents",[]), "allergies": data.get("allergies",[]),
        "historique": [], "imagerie": [], "rdv": [], "questions": [], "documents": []
    }
    add_notif("patient_added", f"Nouveau patient ajouté: {data.get('prenom','')} {data.get('nom','')}", "medecin", pid)
    return jsonify({"ok": True, "id": pid})

# ─── IMPORT ROUTES ────────────────────────────────────────────────────────────

@app.route('/api/import/csv', methods=['POST'])
def import_csv():
    u = current_user()
    if not u or u['role'] != 'medecin': return jsonify({"error": "Accès refusé"}), 403
    data = request.json
    csv_text = data.get('content', '')
    try:
        reader = csv.DictReader(io.StringIO(csv_text))
        patients_raw = list(reader)
        if patients_raw and len(patients_raw) > 0:
            prompt = f"Voici des données CSV de patients:\n{csv_text[:3000]}\n\nNormalise et retourne le JSON."
            result_str = call_llm(prompt, SYSTEM_IMPORT, max_tokens=1500)
        else:
            result_str = call_llm(f"Extrais les patients de ce texte:\n{csv_text[:3000]}", SYSTEM_IMPORT, max_tokens=1500)
    except:
        result_str = call_llm(f"Extrais les patients de ce texte:\n{csv_text[:3000]}", SYSTEM_IMPORT, max_tokens=1500)

    try:
        clean = re.sub(r'```(?:json)?|```', '', result_str).strip()
        patients_list = json.loads(clean)
        added = []
        for pd in patients_list:
            pid = "P" + str(1000 + len(PATIENTS)).zfill(3)
            PATIENTS[pid] = {
                "id": pid, "nom": pd.get("nom",""), "prenom": pd.get("prenom",""),
                "ddn": pd.get("ddn",""), "sexe": pd.get("sexe",""),
                "telephone": pd.get("telephone",""), "email": pd.get("email",""),
                "antecedents": pd.get("antecedents",[]), "allergies": pd.get("allergies",[]),
                "historique": [], "imagerie": [], "rdv": [], "questions": [], "documents": []
            }
            added.append({"id": pid, "nom": pd.get("nom",""), "prenom": pd.get("prenom","")})
        add_notif("import", f"{len(added)} patient(s) importés depuis CSV", "medecin")
        return jsonify({"ok": True, "added": added, "count": len(added)})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Impossible de parser: {str(e)}", "raw": result_str[:500]})

@app.route('/api/import/image', methods=['POST'])
def import_image():
    u = current_user()
    if not u or u['role'] != 'medecin': return jsonify({"error": "Accès refusé"}), 403
    # Groq ne supporte pas les images
    return jsonify({"ok": False, "error": "L'import par image n'est pas disponible dans cette version. Utilisez l'import CSV."})

# ─── RDV ROUTES ───────────────────────────────────────────────────────────────

@app.route('/api/rdv', methods=['GET'])
def get_rdv():
    u = current_user()
    if not u: return jsonify([]), 401
    all_rdv = []
    for p in PATIENTS.values():
        if u['role'] == 'patient' and u.get('patient_id') != p['id']:
            continue
        for r in p['rdv']:
            all_rdv.append({**r, "patient_id": p['id'],
                            "patient_nom": p['nom'], "patient_prenom": p['prenom']})
    all_rdv.sort(key=lambda x: x['date'] + x['heure'])
    return jsonify(all_rdv)

@app.route('/api/rdv', methods=['POST'])
def add_rdv():
    u = current_user()
    if not u: return jsonify({}), 401
    data = request.json
    pid = data.get('patient_id') or u.get('patient_id')
    p = PATIENTS.get(pid)
    if not p: return jsonify({"error": "Patient non trouvé"}), 404
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403

    urgent = data.get('urgent', False)
    statut = 'en_attente' if urgent or u['role'] == 'patient' else data.get('statut', 'programmé')

    rdv = {
        "id": "RDV" + str(uuid.uuid4())[:6].upper(),
        "date": data.get('date',''), "heure": data.get('heure',''),
        "type": data.get('type','Consultation'), "statut": statut,
        "medecin": data.get('medecin', 'Dr. Martin'),
        "notes": data.get('notes',''), "urgent": urgent,
        "demande_par": u['role']
    }
    p['rdv'].append(rdv)

    if urgent or u['role'] == 'patient':
        add_notif("rdv_urgent" if urgent else "rdv_demande",
                  f"{'🚨 RDV URGENT' if urgent else 'Nouveau RDV'} demandé par {p['prenom']} {p['nom']}",
                  u['role'], pid, {"rdv_id": rdv['id']})
    return jsonify({"ok": True, "rdv": rdv})

@app.route('/api/rdv/<rdv_id>/valider', methods=['POST'])
def valider_rdv(rdv_id):
    u = current_user()
    if not u or u['role'] not in ('medecin', 'assistant'):
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json
    for p in PATIENTS.values():
        for r in p['rdv']:
            if r['id'] == rdv_id:
                r['statut'] = data.get('statut', 'confirmé')
                r['notes'] = data.get('notes', r.get('notes',''))
                add_notif("rdv_validé", f"RDV confirmé pour {p['prenom']} {p['nom']} le {r['date']}", u['role'], p['id'])
                return jsonify({"ok": True})
    return jsonify({"error": "RDV non trouvé"}), 404

# ─── DOCUMENTS / IMAGERIE ─────────────────────────────────────────────────────

@app.route('/api/patients/<pid>/upload', methods=['POST'])
def upload_document(pid):
    u = current_user()
    if not u: return jsonify({}), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    p = PATIENTS.get(pid)
    if not p: return jsonify({"error": "Patient non trouvé"}), 404

    data = request.json
    image_b64 = data.get('image')
    doc_type = data.get('type', 'Document')

    doc_id = "DOC" + str(uuid.uuid4())[:6].upper()
    doc = {
        "id": doc_id, "type": doc_type,
        "date": datetime.datetime.now().strftime("%Y-%m-%d"),
        "description": data.get('description', ''),
        "uploaded_by": u['role'],
        "valide": u['role'] == 'medecin',
        "image_b64": image_b64,
        "notes": "", "analyse_ia": ""
    }

    if u['role'] == 'patient':
        p['documents'].append(doc)
        add_notif("document_uploaded",
                  f"📎 {p['prenom']} {p['nom']} a uploadé: {doc_type}",
                  "patient", pid, {"doc_id": doc_id})
    else:
        p['imagerie'].append({**doc, "url": "uploaded"})

    return jsonify({"ok": True, "id": doc_id})

@app.route('/api/patients/<pid>/chirurgie', methods=['POST'])
def set_chirurgie(pid):
    u = current_user()
    if not u or u['role'] != 'medecin': return jsonify({"error": "Accès refusé"}), 403
    p = PATIENTS.get(pid)
    if not p: return jsonify({"error": "Non trouvé"}), 404
    data = request.json
    p['date_chirurgie'] = data.get('date_chirurgie', '')
    p['type_chirurgie'] = data.get('type_chirurgie', '')
    add_notif("chirurgie", f"✂️ Date chirurgie définie pour {p['prenom']} {p['nom']}: {p['date_chirurgie']}", "medecin", pid)
    return jsonify({"ok": True})

@app.route('/api/patients/<pid>/export', methods=['GET'])
def export_patient(pid):
    u = current_user()
    if not u or u['role'] != 'medecin': return jsonify({"error": "Accès refusé"}), 403
    p = PATIENTS.get(pid)
    if not p: return jsonify({"error": "Non trouvé"}), 404
    # Anonymized export — no name, phone, email
    anon = {
        "code": hashlib.md5(p["id"].encode()).hexdigest()[:8].upper(),
        "sexe": p["sexe"],
        "age": datetime.datetime.now().year - int(p["ddn"][:4]),
        "antecedents": p["antecedents"],
        "allergies": p["allergies"],
        "date_chirurgie": p.get("date_chirurgie", ""),
        "type_chirurgie": p.get("type_chirurgie", ""),
        "historique": [
            {k: v for k, v in h.items() if k not in ('medecin',)}
            for h in p["historique"]
        ],
        "nb_rdv": len(p["rdv"]),
        "export_date": datetime.datetime.now().strftime("%Y-%m-%d")
    }
    return jsonify(anon)


def get_documents(pid):
    u = current_user()
    if not u: return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    p = PATIENTS.get(pid)
    if not p: return jsonify([]), 404
    docs = []
    for d in p.get('documents', []):
        docs.append({k: v for k, v in d.items() if k != 'image_b64'})
    return jsonify(docs)

@app.route('/api/patients/<pid>/documents/<doc_id>', methods=['GET'])
def get_document(pid, doc_id):
    u = current_user()
    if not u: return jsonify({}), 401
    p = PATIENTS.get(pid)
    if not p: return jsonify({}), 404
    doc = next((d for d in p.get('documents',[]) if d['id'] == doc_id), None)
    if not doc: return jsonify({}), 404
    return jsonify(doc)

@app.route('/api/patients/<pid>/documents/<doc_id>/analyze', methods=['POST'])
def analyze_document(doc_id, pid):
    u = current_user()
    if not u or u['role'] != 'medecin': return jsonify({"error": "Accès refusé"}), 403
    p = PATIENTS.get(pid)
    if not p: return jsonify({}), 404
    doc = next((d for d in p.get('documents',[]) if d['id'] == doc_id), None)
    if not doc: return jsonify({}), 404

    # Groq ne supporte pas les images — analyse textuelle uniquement
    context = f"Patient: {p['prenom']} {p['nom']}, {datetime.datetime.now().year - int(p['ddn'][:4])} ans. Antécédents: {', '.join(p['antecedents'])}"
    prompt = f"Le médecin a uploadé un document de type '{doc['type']}'. Décrivez les éléments cliniques à vérifier et les recommandations générales pour ce type d'examen. Contexte: {context}"
    analysis = call_llm(prompt, SYSTEM_OPHTHALMO, max_tokens=600)
    doc['analyse_ia'] = analysis
    doc['valide'] = True
    return jsonify({"ok": True, "analysis": analysis})

# ─── QUESTIONS ────────────────────────────────────────────────────────────────

@app.route('/api/patients/<pid>/questions', methods=['GET'])
def get_questions(pid):
    u = current_user()
    if not u: return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    p = PATIENTS.get(pid)
    if not p: return jsonify([]), 404
    return jsonify(p.get('questions', []))

@app.route('/api/patients/<pid>/questions', methods=['POST'])
def add_question(pid):
    u = current_user()
    if not u: return jsonify({}), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    p = PATIENTS.get(pid)
    if not p: return jsonify({"error": "Non trouvé"}), 404

    data = request.json
    question_text = data.get('question', '')

    q = {
        "id": "Q" + str(uuid.uuid4())[:6].upper(),
        "question": question_text,
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "statut": "en_attente",
        "reponse": "", "reponse_ia": "", "reponse_validee": False
    }

    context = f"Patient: {p['prenom']} {p['nom']}, {datetime.datetime.now().year - int(p['ddn'][:4])} ans. Antécédents: {', '.join(p['antecedents'])}"
    q['reponse_ia'] = call_llm(
        f"Question du patient: {question_text}\nContexte: {context}",
        SYSTEM_RESPONSE_DRAFT, max_tokens=400
    )

    p['questions'].append(q)
    add_notif("question", f"❓ {p['prenom']} {p['nom']} a posé une question", "patient", pid, {"question_id": q['id']})
    return jsonify({"ok": True, "question": q})

@app.route('/api/patients/<pid>/questions/<qid>/repondre', methods=['POST'])
def repondre_question(pid, qid):
    u = current_user()
    if not u or u['role'] not in ('medecin',): return jsonify({"error": "Accès refusé"}), 403
    p = PATIENTS.get(pid)
    if not p: return jsonify({}), 404
    q = next((x for x in p['questions'] if x['id'] == qid), None)
    if not q: return jsonify({}), 404

    data = request.json
    q['reponse'] = data.get('reponse', q.get('reponse_ia',''))
    q['reponse_validee'] = True
    q['statut'] = 'répondu'
    q['repondu_par'] = u['nom']
    q['date_reponse'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    add_notif("reponse", f"Le médecin a répondu à votre question", "medecin", pid)
    return jsonify({"ok": True})

# ─── AI ROUTES ────────────────────────────────────────────────────────────────

@app.route('/api/ai/question', methods=['POST'])
def ai_question():
    u = current_user()
    if not u: return jsonify({}), 401
    data = request.json
    answer = call_llm(data.get('question',''), SYSTEM_OPHTHALMO, max_tokens=800)
    return jsonify({"answer": answer})

@app.route('/api/ai/analyze-image', methods=['POST'])
def ai_analyze():
    u = current_user()
    if not u or u['role'] != 'medecin': return jsonify({"error": "Accès refusé"}), 403
    # Groq ne supporte pas les images
    return jsonify({"analysis": "⚠️ L'analyse automatique d'images n'est pas disponible dans cette version. Veuillez saisir vos observations manuellement dans les notes du patient."})

# ─── NOTIFICATIONS ────────────────────────────────────────────────────────────

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    u = current_user()
    if not u: return jsonify([]), 401
    if u['role'] == 'medecin':
        notifs = NOTIFICATIONS[:20]
    elif u['role'] == 'assistant':
        notifs = [n for n in NOTIFICATIONS if n['type'] in ('rdv_demande','rdv_urgent')][:10]
    else:
        pid = u.get('patient_id')
        notifs = [n for n in NOTIFICATIONS if n.get('patient_id') == pid and n['from_role'] == 'medecin'][:10]
    return jsonify(notifs)

@app.route('/api/notifications/<nid>/lu', methods=['POST'])
def mark_lu(nid):
    for n in NOTIFICATIONS:
        if n['id'] == nid:
            n['lu'] = True
    return jsonify({"ok": True})

# ─── MAIN PAGE ────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    import sys
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), 'templates', 'index.html'),
        os.path.join(os.getcwd(), 'templates', 'index.html'),
        'templates/index.html',
        'index.html',
    ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return render_template_string(f.read())
    return "ERROR: Cannot find templates/index.html", 500

if __name__ == '__main__':
    if not GROQ_API_KEY:
        print("\n⚠️  ATTENTION: Variable GROQ_API_KEY non définie!")
        print("   Créez un compte gratuit sur https://console.groq.com")
        print("   Puis lancez: set GROQ_API_KEY=gsk_... && python app.py\n")
    print("\n" + "="*60)
    print("  👁  OphtalmoScan v2 — Multi-Rôles (Groq Edition)")
    print("="*60)
    print("  Comptes de démonstration:")
    print("  🩺 Médecin  : dr.martin / medecin123")
    print("  👩‍💼 Assistant: assist.sara / assist123")
    print("  🧑 Patient 1: patient.marie / patient123")
    print("  🧑 Patient 2: patient.jp / patient123")
    print("="*60)
    print(f"  🤖 Modèle IA : {GROQ_MODEL}")
    print(f"  🔑 Groq API  : {'✅ Configurée' if GROQ_API_KEY else '❌ Manquante'}")
    print("  → http://localhost:5000\n")
    app.run(debug=False, host='0.0.0.0', port=5000)
