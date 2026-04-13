"""
security_utils.py — Central security utilities for OphtalmoScan.

Covers:
  • Step 4 : Field-level Fernet encryption / decryption
  • Step 3 : Password policy validation
  • Step 6 : Input sanitisation (bleach)
  • Step 5 : Audit-log helper with IP + User-Agent
"""
import os, re, hashlib, logging
from cryptography.fernet import Fernet, InvalidToken
from bleach import clean as _bleach_clean
from flask import request as _flask_request

logger = logging.getLogger(__name__)

# ─── FIELD ENCRYPTION (Step 4) ────────────────────────────────────────────────

_FERNET = None

_KEY_BACKUP_BANNER = """
╔══════════════════════════════════════════════════════════════╗
║          OPHTALMO-SCAN  —  ENCRYPTION KEY BACKUP             ║
╠══════════════════════════════════════════════════════════════╣
║  A new field-encryption key was auto-generated.              ║
║  ALL patient PII (names, DOB, phone, email) is encrypted     ║
║  with this key.  If you lose it, that data is UNREADABLE.    ║
║                                                              ║
║  ACTION REQUIRED:                                            ║
║  1. Copy the FIELD_ENCRYPTION_KEY line from .env             ║
║  2. Store it in a password manager / secure vault            ║
║  3. Keep it separate from this server                        ║
║                                                              ║
║  Key fingerprint (SHA-256 prefix) is logged at startup       ║
║  so you can verify key consistency across deployments.       ║
╚══════════════════════════════════════════════════════════════╝
"""


def get_key_fingerprint() -> str:
    """Return first 16 hex chars of SHA-256(key) — safe to log, cannot reconstruct key."""
    key = os.environ.get("FIELD_ENCRYPTION_KEY", "")
    if not key:
        return "NO-KEY"
    return hashlib.sha256(key.encode()).hexdigest()[:16].upper()


def _get_fernet() -> Fernet:
    global _FERNET
    if _FERNET:
        return _FERNET
    key = os.environ.get("FIELD_ENCRYPTION_KEY", "")
    if not key:
        # Auto-generate on first run and persist to .env only if not already present
        key      = Fernet.generate_key().decode()
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        already_set = False
        try:
            with open(env_path, "r") as f:
                already_set = "FIELD_ENCRYPTION_KEY=" in f.read()
        except FileNotFoundError:
            pass
        if not already_set:
            try:
                with open(env_path, "a") as f:
                    f.write(f"\nFIELD_ENCRYPTION_KEY={key}\n")
            except Exception:
                logger.error("Could not persist FIELD_ENCRYPTION_KEY to .env — set it manually!")

            # Write a standalone backup file alongside .env so the key is harder to lose
            backup_path = os.path.join(os.path.dirname(__file__), "ENCRYPTION_KEY_BACKUP.txt")
            try:
                with open(backup_path, "w") as bf:
                    bf.write(_KEY_BACKUP_BANNER)
                    bf.write(f"\nFIELD_ENCRYPTION_KEY={key}\n\n")
                    bf.write("Delete this file after you have stored the key safely.\n")
                logger.critical(
                    "FIELD_ENCRYPTION_KEY auto-generated. "
                    "Backup written to ENCRYPTION_KEY_BACKUP.txt — "
                    "move it to a password manager NOW and delete the file."
                )
            except Exception:
                # Backup file failed — at minimum the key is in .env and logs
                logger.critical(
                    "FIELD_ENCRYPTION_KEY auto-generated and saved to .env. "
                    "STORE IT SAFELY — losing this key means losing all patient PII. "
                    "Key fingerprint: %s", hashlib.sha256(key.encode()).hexdigest()[:16].upper()
                )
        else:
            logger.warning(
                "FIELD_ENCRYPTION_KEY not set in environment but .env already has one — "
                "call load_dotenv() before initialising the app."
            )
        os.environ["FIELD_ENCRYPTION_KEY"] = key
    _FERNET = Fernet(key.encode() if isinstance(key, str) else key)
    return _FERNET


def encrypt_field(value: str) -> str:
    """Encrypt a plaintext string. Returns empty string for empty input."""
    if not value:
        return value
    try:
        return _get_fernet().encrypt(value.encode("utf-8")).decode("ascii")
    except Exception as e:
        logger.error(f"Encryption failed: {e}")
        return value  # fail-open to prevent data loss; log the issue


def decrypt_field(value: str) -> str:
    """Decrypt a Fernet-encrypted string. Returns original on failure (already plaintext or error)."""
    if not value:
        return value
    try:
        return _get_fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, Exception):
        return value  # already plaintext (pre-encryption data) or corrupted


def decrypt_patient(row: dict) -> dict:
    """Decrypt all PII fields in a patient dict. Safe to call on already-plaintext data."""
    ENCRYPTED_PATIENT_FIELDS = ("nom", "prenom", "ddn", "telephone", "email")
    if not row:
        return row
    result = dict(row)
    for field in ENCRYPTED_PATIENT_FIELDS:
        if field in result and result[field]:
            result[field] = decrypt_field(str(result[field]))
    return result


def encrypt_patient_fields(data: dict) -> dict:
    """Return a copy of data with PII fields encrypted."""
    ENCRYPTED_PATIENT_FIELDS = ("nom", "prenom", "ddn", "telephone", "email")
    result = dict(data)
    for field in ENCRYPTED_PATIENT_FIELDS:
        if field in result:
            result[field] = encrypt_field(str(result[field]))
    return result


# ─── PASSWORD POLICY (Step 3) ─────────────────────────────────────────────────

# Common passwords to block (top-50 subset relevant to healthcare)
_COMMON_PASSWORDS = {
    "password","password1","password123","123456","123456789","12345678",
    "qwerty","azerty","111111","dragon","master","hello","letmein","monkey",
    "admin","admin123","welcome","login","pass","1234","abcdef","abc123",
    "sunshine","princess","iloveyou","football","shadow","superman",
    "ophtalmo","clinique","medecin","patient","sante","maroc","casablanca",
}

def validate_password(password: str) -> tuple[bool, str]:
    """
    Returns (is_valid: bool, error_message: str).
    Enforces: 12+ chars, upper, lower, digit, special, not common.
    """
    if len(password) < 12:
        return False, "Le mot de passe doit contenir au moins 12 caractères."
    if not re.search(r"[A-Z]", password):
        return False, "Le mot de passe doit contenir au moins une lettre majuscule."
    if not re.search(r"[a-z]", password):
        return False, "Le mot de passe doit contenir au moins une lettre minuscule."
    if not re.search(r"\d", password):
        return False, "Le mot de passe doit contenir au moins un chiffre."
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]", password):
        return False, "Le mot de passe doit contenir au moins un caractère spécial (!@#$…)."
    if password.lower() in _COMMON_PASSWORDS:
        return False, "Ce mot de passe est trop courant. Choisissez-en un plus unique."
    return True, ""


# ─── INPUT SANITISATION (Step 6) ──────────────────────────────────────────────

def sanitize(value, max_len: int = 500) -> str:
    """Strip all HTML tags and limit length. Safe for free-text fields."""
    if value is None:
        return ""
    cleaned = _bleach_clean(str(value), tags=[], strip=True).strip()
    return cleaned[:max_len]


def sanitize_rich(value, max_len: int = 2000) -> str:
    """Allow a small safe subset of tags (bold, italic, br). For notes fields."""
    ALLOWED = ["b", "i", "em", "strong", "br"]
    if value is None:
        return ""
    cleaned = _bleach_clean(str(value), tags=ALLOWED, strip=True).strip()
    return cleaned[:max_len]


# ─── REQUEST CONTEXT HELPERS (Step 5) ─────────────────────────────────────────

def get_client_ip() -> str:
    """Get real client IP, respecting X-Forwarded-For behind a proxy."""
    try:
        xff = _flask_request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
        return _flask_request.remote_addr or "unknown"
    except Exception:
        return "unknown"


def get_user_agent() -> str:
    try:
        return (_flask_request.headers.get("User-Agent") or "")[:200]
    except Exception:
        return ""
