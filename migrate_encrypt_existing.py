"""
migrate_encrypt_existing.py — One-time migration to encrypt existing plaintext PII.

Run ONCE after deploying security_utils.py with FIELD_ENCRYPTION_KEY set in .env.
Safe to re-run: already-encrypted values (Fernet tokens) are left untouched.

Usage:
  python migrate_encrypt_existing.py [--dry-run]
"""
import os
import sys
import argparse
import sqlite3
from dotenv import load_dotenv

_HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_HERE, ".env"), override=True)
sys.path.insert(0, _HERE)
import security_utils as _su; _su._FERNET = None
from security_utils import encrypt_field, decrypt_field
from cryptography.fernet import InvalidToken

DB_PATH  = os.path.join(os.path.dirname(__file__), "ophtalmo.db")
FIELDS   = ("nom", "prenom", "ddn", "telephone", "email")


def is_already_encrypted(value: str) -> bool:
    """
    Fernet ciphertext starts with 'gAAAAA' (base64 of the version byte 0x80).
    This heuristic avoids double-encrypting already-encrypted values.
    """
    return bool(value and value.startswith("gAAAAA"))


def migrate(dry_run: bool = False):
    con  = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur  = con.cursor()

    rows = cur.execute("SELECT id, nom, prenom, ddn, telephone, email FROM patients").fetchall()
    total     = len(rows)
    encrypted = 0
    skipped   = 0

    print(f"Found {total} patient records.")

    for row in rows:
        updates = {}
        for field in FIELDS:
            val = row[field]
            if not val:
                continue
            if is_already_encrypted(val):
                skipped += 1
                continue
            updates[field] = encrypt_field(val)

        if updates:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            values     = list(updates.values()) + [row['id']]
            if not dry_run:
                cur.execute(f"UPDATE patients SET {set_clause} WHERE id=?", values)
            encrypted += len(updates)
            print(f"  {'[DRY-RUN] ' if dry_run else ''}Patient {row['id']}: encrypted {list(updates.keys())}")

    if not dry_run:
        con.commit()
        print(f"\nDone. {encrypted} field(s) encrypted, {skipped} already-encrypted skipped.")
    else:
        print(f"\n[DRY-RUN] Would encrypt {encrypted} field(s). {skipped} already encrypted.")

    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Encrypt existing plaintext PII in patients table")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed without modifying the DB")
    args = parser.parse_args()

    if not os.environ.get("FIELD_ENCRYPTION_KEY"):
        print("ERROR: FIELD_ENCRYPTION_KEY is not set in environment / .env")
        print("       Run the app once first to auto-generate the key, then re-run this script.")
        sys.exit(1)

    migrate(dry_run=args.dry_run)
