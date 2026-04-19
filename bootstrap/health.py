"""Health and readiness endpoints for orchestrators (k8s, ECS, Render, Fly.io).

  /api/health  — liveness: process is running. Never touches the DB.
  /api/ready   — readiness: DB reachable AND encryption key valid.

These endpoints intentionally bypass auth and rate limiting so probes
don't fail during incident recovery. They return no PII.
"""
from flask import jsonify


def register(app) -> None:
    @app.route('/api/health', methods=['GET'])
    def _health():
        return jsonify({"status": "ok"}), 200

    @app.route('/api/ready', methods=['GET'])
    def _ready():
        checks = {"db": False, "encryption": False}
        try:
            from database import get_db
            get_db().execute("SELECT 1").fetchone()
            checks["db"] = True
        except Exception as e:
            return jsonify({"status": "not_ready", "checks": checks, "error": str(e)[:120]}), 503
        try:
            import security_utils as _su
            _su.verify_encryption_key()
            checks["encryption"] = True
        except Exception as e:
            return jsonify({"status": "not_ready", "checks": checks, "error": str(e)[:120]}), 503
        return jsonify({"status": "ready", "checks": checks}), 200
