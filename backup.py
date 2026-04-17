"""
backup.py — Encrypted database backup utility (Step 8 — DR/Backup).

Usage:
  python backup.py              # manual backup to ./backups/
  python backup.py --dest /mnt/backup

The backup is:
  1. A consistent snapshot (WAL checkpoint for SQLite, pg_dump for PostgreSQL)
  2. Fernet-encrypted using an ESCROWED key (BACKUP_ENCRYPTION_KEY), distinct
     from the live FIELD_ENCRYPTION_KEY. This ensures that compromise of the
     running application server does NOT automatically compromise historical
     backups (an attacker with only the field-encryption key cannot decrypt
     offsite backups).
  3. Named with a UTC timestamp: ophtalmo_backup_<YYYYMMDD_HHMMSS>.db.enc

Key handling:
  - BACKUP_ENCRYPTION_KEY: 44-char urlsafe base64 Fernet key, stored OUT OF
    BAND from the app server (KMS, HSM, offline hardware token, paper escrow).
    The app does not need this key to run — only the operator running a
    restore does. This is the 'escrowed' property.
  - If BACKUP_ENCRYPTION_KEY is unset, backup falls back to
    FIELD_ENCRYPTION_KEY with a loud warning. That fallback means backups are
    only as safe as the live key — acceptable only for dev, never for prod.

Rotation:
  - MAX_BACKUPS controls retention on the backup destination directory.

Restore procedure (documented — see also tests/test_backup_restore.py):
  1. Provision a recovery host with python + requirements.txt installed.
  2. Retrieve BACKUP_ENCRYPTION_KEY from escrow (KMS / offline / paper).
  3. Export it in that shell session only (never to the app server env):
       export BACKUP_ENCRYPTION_KEY="<escrowed key>"
  4. Decrypt:
       python backup.py --restore /path/to/ophtalmo_backup_<ts>.db.enc
  5. Inspect the restored file (sqlite3 restored.db ".tables") before
     swapping it into the running deployment.
  6. Stop the app, move the restored .db into place, start the app.

Cron example (daily 2 AM):
  0 2 * * * cd /opt/ophtalmo && python backup.py --dest /mnt/offsite
"""
import os
import sys
import shutil
import argparse
import datetime
import logging

logger = logging.getLogger("backup")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DB_PATH     = os.path.join(os.path.dirname(__file__), "ophtalmo.db")
BACKUP_DIR  = os.path.join(os.path.dirname(__file__), "backups")
MAX_BACKUPS = 30  # keep last 30 encrypted backups (≈ 1 month of daily runs)


def _get_fernet():
    """Return a Fernet instance for backup encryption.

    Prefers BACKUP_ENCRYPTION_KEY (escrowed, stored separately from the app).
    Falls back to FIELD_ENCRYPTION_KEY with a warning so existing deployments
    don't break the instant this is introduced — but production ops should
    migrate to a distinct backup key.
    """
    from cryptography.fernet import Fernet
    backup_key = os.environ.get("BACKUP_ENCRYPTION_KEY", "").strip()
    if backup_key:
        try:
            return Fernet(backup_key.encode("utf-8"))
        except Exception as e:
            raise RuntimeError(
                f"BACKUP_ENCRYPTION_KEY is set but invalid: {e}. "
                "Expected a 44-character urlsafe base64 Fernet key."
            ) from e
    logger.warning(
        "BACKUP_ENCRYPTION_KEY is not set — falling back to FIELD_ENCRYPTION_KEY. "
        "In production, set a distinct escrowed key so that a live-key compromise "
        "does not expose historical backups."
    )
    from security_utils import _get_fernet as _su_fernet
    return _su_fernet()


def _timestamp() -> str:
    return datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def backup_sqlite(dest_dir: str) -> str:
    """
    Checkpoint WAL, copy the SQLite file, encrypt it, return dest path.
    """
    import sqlite3
    os.makedirs(dest_dir, exist_ok=True)

    # Checkpoint WAL to consolidate all changes into the main DB file
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()

    raw_copy = os.path.join(dest_dir, f"_raw_{_timestamp()}.db")
    shutil.copy2(DB_PATH, raw_copy)

    enc_path = os.path.join(dest_dir, f"ophtalmo_backup_{_timestamp()}.db.enc")
    fernet   = _get_fernet()
    with open(raw_copy, "rb") as f:
        plaintext = f.read()
    with open(enc_path, "wb") as f:
        f.write(fernet.encrypt(plaintext))

    os.remove(raw_copy)
    logger.info(f"SQLite backup written: {enc_path} ({os.path.getsize(enc_path):,} bytes)")
    return enc_path


def backup_postgres(dest_dir: str) -> str:
    """
    Run pg_dump, encrypt the output, return dest path.
    Requires pg_dump on PATH and DATABASE_URL in env.
    """
    import subprocess
    os.makedirs(dest_dir, exist_ok=True)

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url.startswith("postgresql://"):
        raise RuntimeError("DATABASE_URL is not a PostgreSQL URL")

    dump_path = os.path.join(dest_dir, f"_raw_{_timestamp()}.sql")
    result    = subprocess.run(
        ["pg_dump", "--format=plain", "--no-password", database_url],
        capture_output=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {result.stderr.decode()[:500]}")

    enc_path = os.path.join(dest_dir, f"ophtalmo_backup_{_timestamp()}.sql.enc")
    fernet   = _get_fernet()
    with open(enc_path, "wb") as f:
        f.write(fernet.encrypt(result.stdout))

    logger.info(f"PostgreSQL backup written: {enc_path} ({os.path.getsize(enc_path):,} bytes)")
    return enc_path


def restore_backup(enc_path: str, out_path: str | None = None):
    """Decrypt an encrypted backup file."""
    fernet = _get_fernet()
    with open(enc_path, "rb") as f:
        ciphertext = f.read()
    plaintext = fernet.decrypt(ciphertext)

    if out_path is None:
        ext      = ".db" if enc_path.endswith(".db.enc") else ".sql"
        out_path = enc_path.replace(".enc", "_restored" + ext) if ".enc" in enc_path \
                   else enc_path + "_restored" + ext

    with open(out_path, "wb") as f:
        f.write(plaintext)
    logger.info(f"Backup restored to: {out_path}")
    return out_path


def rotate_backups(dest_dir: str, keep: int = MAX_BACKUPS):
    """Delete oldest encrypted backups beyond the keep limit."""
    files = sorted([
        os.path.join(dest_dir, f)
        for f in os.listdir(dest_dir)
        if f.startswith("ophtalmo_backup_") and f.endswith(".enc")
    ])
    for old in files[:-keep]:
        os.remove(old)
        logger.info(f"Rotated old backup: {old}")


def run_backup(dest_dir: str = BACKUP_DIR) -> str:
    """Entry point for scheduled or manual backup."""
    from dotenv import load_dotenv
    load_dotenv()

    database_url = os.environ.get("DATABASE_URL", "")
    if database_url.startswith("postgresql://"):
        path = backup_postgres(dest_dir)
    else:
        path = backup_sqlite(dest_dir)

    rotate_backups(dest_dir)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OphtalmoScan encrypted backup utility")
    parser.add_argument("--dest",    default=BACKUP_DIR, help="Backup destination directory")
    parser.add_argument("--restore", default=None,       help="Path to .enc file to restore")
    parser.add_argument("--out",     default=None,       help="Output path for restore (optional)")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    if args.restore:
        restored = restore_backup(args.restore, args.out)
        print(f"Restored to: {restored}")
    else:
        path = run_backup(args.dest)
        print(f"Backup complete: {path}")
