# Production image for OphtalmoScan.
# Build:  docker build -t ophtalmoscan .
# Run:    docker run --env-file .env -p 8000:8000 ophtalmoscan
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps: libpq for Postgres, curl for the healthcheck.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first — this layer is cached unless requirements change.
COPY requirements.txt ./
RUN pip install -r requirements.txt \
 && pip install gunicorn psycopg2-binary sentry-sdk[flask]

# Copy application code.
COPY . .

# Non-root user — never run the app as root.
RUN useradd --create-home --uid 1000 app \
 && chown -R app:app /app \
 && mkdir -p /app/uploads/documents /app/backups \
 && chown -R app:app /app/uploads /app/backups
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl --fail http://localhost:8000/api/health || exit 1

CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
