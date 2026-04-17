"""
Backup/restore smoke test — verifies:
  1. A SQLite DB can be encrypted with an ESCROWED key (BACKUP_ENCRYPTION_KEY)
     that is distinct from the live field-encryption key.
  2. The resulting .enc file cannot be decrypted with FIELD_ENCRYPTION_KEY.
  3. The backup round-trips: restore produces bytes identical to the source.
  4. A missing escrow key falls back to FIELD_ENCRYPTION_KEY (dev path only).
"""
import os
import sqlite3
import tempfile

import pytest
from cryptography.fernet import Fernet, InvalidToken

os.environ.setdefault("SESSION_COOKIE_SECURE", "0")


def _make_fake_db(path: str) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    con.execute("INSERT INTO t (v) VALUES ('alpha'), ('beta'), ('gamma')")
    con.commit()
    con.close()


def test_backup_roundtrip_with_escrowed_key(monkeypatch, tmp_path):
    import backup

    live_key = Fernet.generate_key().decode()
    escrow_key = Fernet.generate_key().decode()
    assert live_key != escrow_key

    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", live_key)
    monkeypatch.setenv("BACKUP_ENCRYPTION_KEY", escrow_key)

    src_db = tmp_path / "source.db"
    _make_fake_db(str(src_db))
    src_bytes = src_db.read_bytes()

    monkeypatch.setattr(backup, "DB_PATH", str(src_db))
    dest_dir = tmp_path / "backups"

    enc_path = backup.backup_sqlite(str(dest_dir))
    assert os.path.exists(enc_path)
    assert enc_path.endswith(".db.enc")

    # The backup must NOT be decryptable with the live field-encryption key.
    ciphertext = open(enc_path, "rb").read()
    with pytest.raises(InvalidToken):
        Fernet(live_key.encode()).decrypt(ciphertext)

    # Round-trip: restoring with the escrow key must reproduce the original DB.
    restored = backup.restore_backup(enc_path, str(tmp_path / "restored.db"))
    assert open(restored, "rb").read() == src_bytes

    # Sanity-check the restored DB is openable and contains the original rows.
    con = sqlite3.connect(restored)
    rows = [r[0] for r in con.execute("SELECT v FROM t ORDER BY id").fetchall()]
    con.close()
    assert rows == ["alpha", "beta", "gamma"]


def test_backup_falls_back_to_field_key_when_escrow_unset(monkeypatch, tmp_path):
    import backup

    live_key = Fernet.generate_key().decode()
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", live_key)
    monkeypatch.delenv("BACKUP_ENCRYPTION_KEY", raising=False)

    # security_utils caches its Fernet — reset so it picks up the new live key.
    import security_utils
    security_utils._FERNET = None

    src_db = tmp_path / "source.db"
    _make_fake_db(str(src_db))
    monkeypatch.setattr(backup, "DB_PATH", str(src_db))
    dest_dir = tmp_path / "backups"

    enc_path = backup.backup_sqlite(str(dest_dir))

    # With escrow unset, the backup IS decryptable with the live key (dev fallback).
    ciphertext = open(enc_path, "rb").read()
    plaintext = Fernet(live_key.encode()).decrypt(ciphertext)
    assert plaintext == src_db.read_bytes()
