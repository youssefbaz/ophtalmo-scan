# OphtalmoScan — Production deployment

## 1. Prerequisites

- Python 3.11+
- Redis (for rate-limit storage under multi-worker gunicorn)
- TLS termination (nginx or similar) — required because `SESSION_COOKIE_SECURE=1`
- SMTP relay credentials (Gmail App Password, Mailjet, etc.)
- At least one LLM API key (Groq or Gemini)

## 2. One-time setup

```bash
git clone <repo> /opt/ophtalmo && cd /opt/ophtalmo
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install "sentry-sdk[flask]"   # optional, if using SENTRY_DSN

# Generate secrets
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python -c "from cryptography.fernet import Fernet; print('FIELD_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
python -c "from cryptography.fernet import Fernet; print('BACKUP_ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

cp .env.example .env
# → paste the three generated values into .env, fill in SMTP / LLM keys
# → set SESSION_COOKIE_SECURE=1
# → set RATELIMIT_STORAGE_URI=redis://… (point at your Redis)
# → on the singleton worker only, set ENABLE_SCHEDULER=1
```

**CRITICAL:** `FIELD_ENCRYPTION_KEY` and `BACKUP_ENCRYPTION_KEY` must be backed up
separately from the database. Losing the field key = losing all patient PII
irreversibly. Store copies in a password manager AND an offline location.

## 3. Run

Single-process (dev / small install):
```bash
gunicorn "app:create_app()" -b 0.0.0.0:8000
```

Multi-worker (recommended production):
```bash
# Main pool — scheduler OFF
ENABLE_SCHEDULER=0 gunicorn "app:create_app()" \
  -b 127.0.0.1:8000 --workers 4 --threads 2 --timeout 120

# Single dedicated scheduler process
ENABLE_SCHEDULER=1 gunicorn "app:create_app()" \
  -b 127.0.0.1:8001 --workers 1
```
Only the second process runs the cron jobs (email reminders 08:05, post-op gaps
07:30, encrypted backup 02:00). Running multiple workers with `ENABLE_SCHEDULER=1`
would fire each job N times per day.

## 4. nginx / systemd

Reference configs are in `deploy/nginx.conf` and `deploy/ophtalmo.service`.
Adjust paths and the upstream port to match your `gunicorn` bind.

## 5. Verify boot

```bash
curl -s http://127.0.0.1:8000/health
# {"ok": true, "time": "...", "version": "2.0"}
```

The startup log should include:
- `Encryption key fingerprint: …` (same fingerprint across restarts)
- `Encryption key self-test: OK`
- `APScheduler started — 3 job(s) registered` (only on the scheduler worker)
- `Sentry error monitoring initialised` (if SENTRY_DSN set)

The app refuses to boot if:
- `SECRET_KEY` is unset
- `SESSION_COOKIE_SECURE` is unset or not exactly `0` / `1`
- `FIELD_ENCRYPTION_KEY` round-trip test fails

## 6. Backups & restore

With `ENABLE_SCHEDULER=1` the scheduler writes a Fernet-encrypted backup to
`backups/ophtalmo_YYYYMMDD_HHMMSS.db.enc` daily at 02:00. Manual run:

```bash
python -c "import backup; print(backup.run_backup())"
```

Restore procedure:
```bash
python -c "import backup; backup.restore_backup('backups/<file>.db.enc', '/tmp/restored.db')"
# then inspect /tmp/restored.db with sqlite3 before swapping in for ophtalmo.db
```

Copy backups offsite daily (rsync / S3 / rclone). They are useless without
`BACKUP_ENCRYPTION_KEY` — store that key separately from the backup bucket.

## 7. Tests

```bash
pytest -q
```

Security-relevant coverage (must stay green): CSRF, idle timeout, rate-limit
config, cross-patient IDOR, TOTP regen auth, upload MIME reject, GDPR audit
scrub.

## 8. Post-deploy checks

- [ ] Hit the login page over HTTPS; confirm `Set-Cookie: … Secure; HttpOnly; SameSite=Lax`
- [ ] Trigger a password reset; confirm email arrives and link works
- [ ] Create a test patient, upload a JPEG, run AI analysis
- [ ] Confirm `/api/admin/smtp-status` reports configured=true
- [ ] Enable 2FA on an account; confirm backup-code regeneration works
- [ ] Wait past 02:00 and confirm a new file appears in `backups/`
- [ ] (If Sentry configured) trigger a test error and confirm it appears in the Sentry project
