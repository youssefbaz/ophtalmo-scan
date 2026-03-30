import os
import requests as http_requests

GROQ_API_KEY   = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL     = "llama-3.3-70b-versatile"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = "gemini-1.5-flash"

# ─── SYSTEM PROMPTS ───────────────────────────────────────────────────────────

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

# ─── LLM CALLS ────────────────────────────────────────────────────────────────

def _call_groq(prompt, system, max_tokens):
    r = http_requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt}
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3
        },
        timeout=40
    )
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']


def _call_gemini(prompt, system, max_tokens):
    r = http_requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        params={"key": GEMINI_API_KEY},
        json={
            "contents": [{"parts": [{"text": f"{system}\n\n{prompt}"}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3}
        },
        timeout=40
    )
    r.raise_for_status()
    return r.json()['candidates'][0]['content']['parts'][0]['text']


def call_llm(prompt, system, image_b64=None, max_tokens=800):
    if image_b64:
        return ("⚠️ L'analyse automatique d'images n'est pas disponible dans cette version. "
                "Veuillez analyser l'image manuellement et saisir vos observations dans les notes.")

    if GROQ_API_KEY:
        try:
            result = _call_groq(prompt, system, max_tokens)
            print("[LLM] Réponse via Groq")
            return result
        except Exception as e:
            print(f"[LLM] Groq échoué ({e}), bascule sur Gemini…")

    if GEMINI_API_KEY:
        try:
            result = _call_gemini(prompt, system, max_tokens)
            print("[LLM] Réponse via Gemini (fallback)")
            return result
        except Exception as e:
            print(f"[LLM] Gemini échoué ({e})")
            return f"⚠️ Les deux APIs IA sont indisponibles. Dernière erreur : {e}"

    return "⚠️ Aucune clé API configurée (GROQ_API_KEY ou GEMINI_API_KEY)."
