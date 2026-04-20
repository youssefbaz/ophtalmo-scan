import os
import time
import logging
import requests as http_requests

logger = logging.getLogger(__name__)

GROQ_API_KEY    = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL      = "llama-3.3-70b-versatile"
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL    = "gemini-2.0-flash"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Gemini fallback chain — only models that accept image input.
# 2.0-flash-lite was removed: it does NOT support vision despite the name.
GEMINI_FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]

# OpenRouter free models — text and vision.
# Vision chain refreshed April 2026 — the previous qwen2.5-vl-7b and
# llama-3.2-11b-vision free endpoints were retired by OpenRouter.
OPENROUTER_TEXT_MODEL   = "meta-llama/llama-3.3-70b-instruct:free"
OPENROUTER_VISION_MODELS = [
    "google/gemma-4-31b-it:free",                 # newest Gemma, strong vision
    "google/gemma-3-27b-it:free",                 # proven free VL
    "nvidia/nemotron-nano-12b-v2-vl:free",        # dedicated VL model
    "google/gemma-4-26b-a4b-it:free",
    "google/gemma-3-12b-it:free",
]

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

SYSTEM_IMAGE_ANALYSIS = """Tu es un ophtalmologiste expert en interprétation d'imagerie oculaire (rétinographie, OCT maculaire/RNFL, angiographie à la fluorescéine, topographie cornéenne, échographie B, champ visuel, photographie du segment antérieur).

Ton rôle : fournir au médecin une lecture structurée, précise et cliniquement utile de l'image — PAS un diagnostic définitif. Tu es un outil d'aide à la décision.

Méthode d'analyse obligatoire :
1. Identifie le type d'examen et la qualité/lisibilité de l'image (nette, floue, artéfacts, cadrage).
2. Décris les structures anatomiques visibles de façon systématique selon le type d'examen :
   - Fond d'œil / rétinographie : papille (excavation C/D, coloration, bords), macula (reflet fovéolaire, pigmentation), vaisseaux (rapport A/V, tortuosité, croisements), périphérie rétinienne, hémorragies/exsudats/drusen.
   - OCT maculaire : épaisseur fovéolaire, intégrité des couches (EPR, ellipsoïde, MLE), logettes, DSR, DEP, membrane épirétinienne, trou maculaire.
   - OCT RNFL/papille : épaisseur des fibres par quadrant, asymétrie inter-œil, rim, C/D.
   - Topographie cornéenne : kératométrie, asymétrie, pattern (régulier, asymétrique, en pince, keratocône suspect), pachymétrie.
   - Segment antérieur : cornée (transparence, dépôts), chambre antérieure, iris, cristallin.
   - Angiographie : temps circulatoires, diffusions, zones d'hypo/hyperfluorescence.
3. Liste les ANOMALIES détectées, localisées précisément (quadrant, œil, distance à la fovéa).
4. Propose des HYPOTHÈSES DIAGNOSTIQUES hiérarchisées (principale + différentiels) avec le raisonnement.
5. Recommande les EXAMENS COMPLÉMENTAIRES pertinents et la CONDUITE À TENIR (urgence, suivi, traitement à discuter).
6. Termine par les LIMITES de ton analyse (ce que l'image ne permet pas de conclure).

Format de sortie strict en markdown :
### 🔍 Type et qualité de l'image
### 🧿 Description anatomique
### ⚠️ Anomalies détectées
### 🩺 Hypothèses diagnostiques
### 📋 Examens complémentaires / Conduite à tenir
### ⚡ Limites de l'analyse

Règles : français médical rigoureux, terminologie AAO/SFO, concis mais complet, jamais alarmiste, toujours rappeler que la validation par le médecin est indispensable. Si l'image n'est pas interprétable, dis-le clairement."""

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


def _detect_mime(image_b64):
    try:
        import base64 as _b64
        hdr = _b64.b64decode(image_b64[:16])
        if hdr[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        if hdr[:3] == b'\xff\xd8\xff':
            return "image/jpeg"
    except Exception:
        pass
    return "image/jpeg"


def _call_gemini_model(model, prompt, system, max_tokens, image_b64=None):
    parts = []
    if image_b64:
        parts.append({"inline_data": {"mime_type": _detect_mime(image_b64), "data": image_b64}})
    parts.append({"text": f"{system}\n\n{prompt}"})
    r = http_requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": GEMINI_API_KEY},
        json={
            "contents": [{"parts": parts}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.3}
        },
        timeout=60
    )
    r.raise_for_status()
    return r.json()['candidates'][0]['content']['parts'][0]['text']


def _call_gemini(prompt, system, max_tokens, image_b64=None):
    """Try each Gemini model in sequence, with retry on 429."""
    last_error = None
    for model in GEMINI_FALLBACK_MODELS:
        for attempt in range(2):
            try:
                result = _call_gemini_model(model, prompt, system, max_tokens, image_b64)
                logger.info(f"[LLM] Réponse via Gemini ({model})")
                return result
            except http_requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 429:
                    wait = 10 * (attempt + 1)   # 10s, then 20s
                    logger.warning(f"[LLM] Gemini {model} rate-limited (429), attente {wait}s…")
                    time.sleep(wait)
                    last_error = e
                    continue
                logger.error(f"[LLM] Gemini {model} erreur HTTP ({e}), modèle suivant…")
                last_error = e
                break
            except Exception as e:
                logger.error(f"[LLM] Gemini {model} échoué ({e}), modèle suivant…")
                last_error = e
                break
    raise last_error or Exception("Tous les modèles Gemini sont indisponibles")


def _call_openrouter_model(model, prompt, system, max_tokens, image_b64=None):
    content = [
        {"type": "image_url", "image_url": {"url": f"data:{_detect_mime(image_b64)};base64,{image_b64}"}},
        {"type": "text", "text": prompt},
    ] if image_b64 else prompt
    r = http_requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://ophtalmo-scan.local",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": content},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content']


def _call_openrouter(prompt, system, max_tokens, image_b64=None):
    models = OPENROUTER_VISION_MODELS if image_b64 else [OPENROUTER_TEXT_MODEL]
    last_error = None
    for model in models:
        try:
            result = _call_openrouter_model(model, prompt, system, max_tokens, image_b64)
            logger.info(f"[LLM] Réponse via OpenRouter ({model})")
            return result
        except http_requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            body = e.response.text[:300] if e.response is not None else ''
            if status == 429:
                logger.warning(f"[LLM] OpenRouter {model} rate-limited, modèle suivant… {body}")
            else:
                logger.error(f"[LLM] OpenRouter {model} erreur {status}: {body}")
            last_error = e
        except Exception as e:
            logger.error(f"[LLM] OpenRouter {model} échoué ({e}), modèle suivant…")
            last_error = e
    raise last_error or Exception("OpenRouter indisponible")


def _is_temporary_error(exc) -> bool:
    """True for transient failures (network, rate-limit, 5xx) vs config errors (no key, 401)."""
    if isinstance(exc, http_requests.exceptions.ConnectionError):
        return True
    if isinstance(exc, http_requests.exceptions.Timeout):
        return True
    if isinstance(exc, http_requests.exceptions.HTTPError):
        status = exc.response.status_code if exc.response is not None else 0
        return status in (429, 500, 502, 503, 504)
    return False  # unknown — assume permanent to avoid misleading "retry" prompts


def call_llm(prompt, system, image_b64=None, max_tokens=800):
    """Call the LLM chain. Returns a plaintext string on success.

    Raises LLMUnavailableError on total failure so callers can distinguish
    temporary (retryable) from permanent (config) outages.
    """
    last_exc = None

    # 1. Text-only → Groq first (generous free tier, no vision needed)
    if GROQ_API_KEY and not image_b64:
        try:
            logger.info("[LLM] Réponse via Groq")
            return _call_groq(prompt, system, max_tokens)
        except Exception as e:
            logger.warning(f"[LLM] Groq échoué ({e}), bascule…")
            last_exc = e

    # For image requests, try OpenRouter first — its free vision chain is
    # deeper and less rate-limited than Gemini's free tier.
    providers_for_images = []
    if image_b64:
        if OPENROUTER_API_KEY:
            providers_for_images.append('openrouter')
        if GEMINI_API_KEY:
            providers_for_images.append('gemini')
    else:
        if GEMINI_API_KEY:
            providers_for_images.append('gemini')
        if OPENROUTER_API_KEY:
            providers_for_images.append('openrouter')

    for provider in providers_for_images:
        try:
            if provider == 'gemini':
                return _call_gemini(prompt, system, max_tokens, image_b64)
            else:
                result = _call_openrouter(prompt, system, max_tokens, image_b64)
                logger.info(f"[LLM] Réponse via OpenRouter ({'vision' if image_b64 else 'text'})")
                return result
        except Exception as e:
            logger.warning(f"[LLM] {provider} indisponible ({e}), bascule…")
            last_exc = e

    # 4. Last resort: Groq text-only even for image requests
    if image_b64 and GROQ_API_KEY:
        try:
            degraded = (
                f"[Image non analysable visuellement — tous les modèles vision sont indisponibles. "
                f"Analyse contextuelle uniquement.]\n\n{prompt}"
            )
            result = _call_groq(degraded, system, max_tokens)
            logger.warning("[LLM] Analyse dégradée via Groq (sans vision)")
            return f"⚠️ Analyse visuelle indisponible. Analyse contextuelle :\n\n{result}"
        except Exception as e:
            logger.error(f"[LLM] Groq dégradé échoué ({e})")
            last_exc = e

    # Determine if failure is temporary or permanent
    no_keys = not any([GROQ_API_KEY, GEMINI_API_KEY, OPENROUTER_API_KEY])
    temporary = (not no_keys) and (last_exc is None or _is_temporary_error(last_exc))
    raise LLMUnavailableError(
        "Tous les services IA sont indisponibles.",
        temporary=temporary,
        cause=last_exc,
    )


class LLMUnavailableError(Exception):
    """Raised when all LLM providers fail.

    Attributes:
        temporary — True if the failure is likely transient (retry makes sense)
        cause     — the underlying exception from the last provider
    """
    def __init__(self, message: str, temporary: bool = True, cause: Exception = None):
        super().__init__(message)
        self.temporary = temporary
        self.cause = cause
