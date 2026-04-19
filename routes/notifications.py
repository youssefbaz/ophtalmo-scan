import re, json, time
from flask import Blueprint, jsonify, Response, stream_with_context, request
from database import get_db, current_user
from security_utils import decrypt_field
from extensions import limiter

bp = Blueprint('notifications', __name__)

# Fernet tokens are base64url strings starting with gAAAAA (version byte 0x80)
_FERNET_RE = re.compile(r'gAAAAA[A-Za-z0-9_\-]{40,}={0,2}')


def _decrypt_message(msg: str) -> str:
    """Replace any embedded Fernet tokens inside a notification message with their plaintext."""
    if not msg or 'gAAAAA' not in msg:
        return msg
    def _replace(m):
        decrypted = decrypt_field(m.group(0))
        # decrypt_field returns the original string on failure, so this is safe
        return decrypted
    return _FERNET_RE.sub(_replace, msg)


@bp.route('/api/notifications', methods=['GET'])
def get_notifications():
    u = current_user()
    if not u:
        return jsonify([]), 401
    db = get_db()

    if u['role'] == 'medecin':
        # Show notifications:
        #   1. Explicitly targeted at this doctor (medecin_id = me)
        #   2. From patients in this doctor's roster (patient_id IN my patients)
        #   3. System-wide broadcasts (no patient_id, no medecin_id) but NOT admin actions
        # Exclude anything sent by 'admin' with no patient — those are admin-only events
        rows = db.execute("""
            SELECT n.* FROM notifications n
            WHERE n.medecin_id = ?
               OR n.patient_id IN (
                   SELECT id FROM patients WHERE medecin_id = ?
               )
               OR (
                   (n.patient_id IS NULL OR n.patient_id = '')
                   AND (n.medecin_id IS NULL OR n.medecin_id = '')
                   AND n.from_role != 'admin'
               )
            ORDER BY n.date DESC LIMIT 30
        """, (u['id'], u['id'])).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM notifications WHERE patient_id=? AND from_role='medecin' "
            "ORDER BY date DESC LIMIT 10",
            (u.get('patient_id'),)
        ).fetchall()

    result = []
    for row in rows:
        n = dict(row)
        n['lu'] = bool(n['lu'])
        n['message'] = _decrypt_message(n.get('message') or '')
        try:
            n['data'] = json.loads(n.get('data') or '{}')
        except Exception:
            n['data'] = {}
        result.append(n)
    return jsonify(result)


_SSE_POLL_INTERVAL = 15   # seconds between DB checks
_SSE_MAX_DURATION  = 300  # seconds before closing (client auto-reconnects via EventSource)


@bp.route('/api/stream/notifications', methods=['GET'])
@limiter.limit("10 per minute")
def stream_notifications():
    """Server-Sent Events stream — pushes new notifications every 15 s.

    Each connection lives at most _SSE_MAX_DURATION seconds then closes cleanly;
    the browser EventSource reconnects automatically. This bounds resource usage
    even when running under a threading worker. With the gevent worker class
    (see Procfile) time.sleep is non-blocking, so thousands of connections are
    handled concurrently without starving threads.
    """
    u = current_user()
    if not u:
        return Response('data: {"error":"unauthenticated"}\n\n',
                        mimetype='text/event-stream', status=401)

    uid      = u['id']
    role     = u['role']
    pat_id   = u.get('patient_id')
    deadline = time.monotonic() + _SSE_MAX_DURATION

    def _generate():
        last_seen_id = None
        while time.monotonic() < deadline:
            try:
                db = get_db()
                if role == 'medecin':
                    row = db.execute("""
                        SELECT id FROM notifications n
                        WHERE n.medecin_id = ?
                           OR n.patient_id IN (SELECT id FROM patients WHERE medecin_id = ?)
                           OR (
                               (n.patient_id IS NULL OR n.patient_id = '')
                               AND (n.medecin_id IS NULL OR n.medecin_id = '')
                               AND n.from_role != 'admin'
                           )
                        ORDER BY n.date DESC LIMIT 1
                    """, (uid, uid)).fetchone()
                    unread = db.execute(
                        "SELECT COUNT(*) FROM notifications n "
                        "WHERE n.lu=0 AND (n.medecin_id=? OR n.patient_id IN "
                        "(SELECT id FROM patients WHERE medecin_id=?))",
                        (uid, uid)
                    ).fetchone()[0]
                else:
                    row = db.execute(
                        "SELECT id FROM notifications WHERE patient_id=? AND from_role='medecin' "
                        "ORDER BY date DESC LIMIT 1",
                        (pat_id,)
                    ).fetchone()
                    unread = db.execute(
                        "SELECT COUNT(*) FROM notifications WHERE patient_id=? AND lu=0",
                        (pat_id,)
                    ).fetchone()[0]

                latest_id = row['id'] if row else None
                if latest_id != last_seen_id:
                    last_seen_id = latest_id
                    payload = json.dumps({"unread": unread, "latest": latest_id})
                    yield f"event: notifications\ndata: {payload}\n\n"
                else:
                    yield ": heartbeat\n\n"
            except Exception:
                yield ": error\n\n"
            time.sleep(_SSE_POLL_INTERVAL)
        # Signal client to reconnect after max duration
        yield "event: reconnect\ndata: {}\n\n"

    return Response(stream_with_context(_generate()),
                    mimetype='text/event-stream',
                    headers={
                        'Cache-Control': 'no-cache',
                        'X-Accel-Buffering': 'no',
                    })


@bp.route('/api/notifications/<nid>/lu', methods=['POST'])
def mark_lu(nid):
    u = current_user()
    if not u:
        return jsonify({"error": "Non connecté"}), 401
    db = get_db()
    db.execute("UPDATE notifications SET lu=1 WHERE id=?", (nid,))
    db.commit()
    return jsonify({"ok": True})


@bp.route('/api/notifications', methods=['DELETE'])
def clear_notifications():
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    # Only delete notifications visible to this doctor — mirrors the GET scope.
    # Never wipes another doctor's notifications.
    db.execute("""
        DELETE FROM notifications
        WHERE medecin_id = ?
           OR patient_id IN (SELECT id FROM patients WHERE medecin_id = ?)
           OR (
               (patient_id IS NULL OR patient_id = '')
               AND (medecin_id IS NULL OR medecin_id = '')
               AND from_role != 'admin'
           )
    """, (u['id'], u['id']))
    db.commit()
    return jsonify({"ok": True})
