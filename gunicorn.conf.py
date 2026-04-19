"""Gunicorn config for production deployment.

Run:
  gunicorn -c gunicorn.conf.py 'app:app'

Environment notes:
  - ENABLE_SCHEDULER=1 must be set on EXACTLY ONE worker (or a separate
    singleton process). With multiple workers all setting it, each cron job
    fires N times per day. Easiest pattern: run N workers without the flag,
    and a single `python -m bootstrap.scheduler_worker` sidecar (or a cron
    entry invoking `python backup.py` / etc.) that handles scheduled work.
  - RATELIMIT_STORAGE_URI should point at Redis in production so the
    per-IP rate limiter is shared across workers.
"""
import multiprocessing
import os

# Bind to all interfaces on $PORT (Heroku/Render/Fly) or 8000 by default.
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# CPU-bound work is minimal; most of this app is I/O (SQLite, LLM calls).
# 2×cores+1 is a safe default; override with WEB_CONCURRENCY in the env.
workers = int(os.environ.get('WEB_CONCURRENCY', (multiprocessing.cpu_count() * 2) + 1))

# Threads per worker — helps while the LLM call is blocking in the background
# thread we spawn in routes/documents.py. 4 is a reasonable baseline.
threads = int(os.environ.get('GUNICORN_THREADS', '4'))
worker_class = 'gthread'

# Give the LLM calls time to finish before gunicorn kills the worker.
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '120'))
graceful_timeout = 30
keepalive = 5

# Rotate after N requests to bound any slow memory leaks.
max_requests = 1000
max_requests_jitter = 100

# Logs go to stdout/stderr so the platform's log collector picks them up.
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOGLEVEL', 'info')

# Respect X-Forwarded-For / X-Forwarded-Proto when running behind a proxy.
forwarded_allow_ips = os.environ.get('FORWARDED_ALLOW_IPS', '127.0.0.1')

# Preload the app once in the master, then fork workers. Faster boot, lower
# memory. Side effect: module-level code (including create_app()) runs once
# in the master — SAFE for our bootstrap because scheduler start is gated
# on ENABLE_SCHEDULER=1 which we keep unset for gunicorn workers.
preload_app = True
