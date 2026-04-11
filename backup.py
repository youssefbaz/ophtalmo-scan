"""
backup.py — Encrypted database backup utility (Step 8 — DR/Backup).

Usage:
  python backup.py              # manual backup to ./backups/
  python backup.py --dest /mnt/backup

The backup is:
  1. A consistent snapshot (WAL checkpoint for SQLite, pg_dump for PostgreSQL)
  2. Fernet-encrypted using FIELD_ENCRYPTION_KEY (same key as field-level encryption)
  3. Named with a UTC timestamp: ophtalmo_backup_<YYYYMMDD_HHMMSS>.db.enc

Restore:
  python backup.py --restore backups/ophtalmo_backup_20250101_120000.db.enc

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
    """Get Fernet instance using the same key as security_utils."""
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
