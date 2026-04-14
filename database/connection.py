import sqlite3, json, uuid, datetime, os, re, logging
from functools import wraps
from flask import g, session, jsonify
from werkzeug.security import generate_password_hash

logger = logging.getLogger(__name__)

_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_USE_PG = _DATABASE_URL.startswith("postgresql://") or _DATABASE_URL.startswith("postgres://")
DB_PATH  = os.environ.get("OPHTALMO_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ophtalmo.db")
DB_PATH  = os.path.abspath(DB_PATH)
DATABASE = DB_PATH

"""
database.py — DB layer supporting SQLite (dev) and PostgreSQL (prod).

Set DATABASE_URL=postgresql://user:pass@host:5432/dbname for PostgreSQL.
Omit it (or set it to a file path) to use SQLite.

Step 1 : PostgreSQL adapter with automatic ? → %s + SQLite→PG SQL translation
Step 5 : Enhanced audit_log (ip_address, user_agent, full READ logging)
Step 3 : login_attempts table for account lockout
Step 9 : patient_consents table
Step 3 : users.totp_secret, users.totp_enabled, users.locked_until columns
"""
import sqlite3, json, uuid, datetime, os, re, logging
from functools import wraps
from flask import g, session, jsonify
from werkzeug.security import generate_password_hash

logger = logging.getLogger(__name__)

_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_USE_PG = _DATABASE_URL.startswith("postgresql://") or _DATABASE_URL.startswith("postgres://")
# DB_PATH can be overridden by tests via os.environ["OPHTALMO_DB_PATH"] or direct attribute assignment
DB_PATH  = os.environ.get("OPHTALMO_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "ophtalmo.db")
DATABASE = DB_PATH  # legacy alias


# ─── POSTGRESQL ADAPTER ───────────────────────────────────────────────────────

class _PgRow:
    """Dict-like row wrapper for psycopg2 results."""
    def __init__(self, row, description):
        self._d = {d[0]: row[i] for i, d in enumerate(description)} if description else {}
        self._l = list(row) if row else []

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._l[key]
        return self._d[key]

    def __contains__(self, key): return key in self._d
    def __iter__(self):          return iter(self._d)
    def get(self, key, default=None): return self._d.get(key, default)
    def keys(self):              return self._d.keys()
    def items(self):             return self._d.items()
    def __repr__(self):          return repr(self._d)


class _PgCursor:
    def __init__(self, cur): self._cur = cur

    def fetchone(self):
        row = self._cur.fetchone()
        return _PgRow(row, self._cur.description) if row is not None else None

    def fetchall(self):
        return [_PgRow(r, self._cur.description) for r in (self._cur.fetchall() or [])]

    def __iter__(self):
        for row in self._cur:
            yield _PgRow(row, self._cur.description)

    @property
    def lastrowid(self): return getattr(self._cur, "lastrowid", None)
    @property
    def rowcount(self): return self._cur.rowcount


_PG_SQL_SUBS = [
    # datetime('now') → NOW()
    (re.compile(r"datetime\('now'\)",    re.I), "NOW()"),
    # strftime('%Y-%m', col) → TO_CHAR(col::timestamp, 'YYYY-MM')
    (re.compile(r"strftime\('%Y-%m',\s*(\w+)\)", re.I),
     lambda m: f"TO_CHAR({m.group(1)}::timestamp, 'YYYY-MM')"),
    # strftime('%Y', col) → TO_CHAR(col::timestamp, 'YYYY')
    (re.compile(r"strftime\('%Y',\s*(\w+)\)", re.I),
     lambda m: f"TO_CHAR({m.group(1)}::timestamp, 'YYYY')"),
    # strftime('%w', col) → EXTRACT(DOW FROM col::timestamp)::TEXT
    (re.compile(r"strftime\('%w',\s*(\w+)\)", re.I),
     lambda m: f"EXTRACT(DOW FROM {m.group(1)}::timestamp)::TEXT"),
    # GLOB 'M[0-9]*' → SIMILAR TO 'M[0-9]+' (PostgreSQL regex)
    (re.compile(r"GLOB\s+'([^']+)'", re.I),
     lambda m: f"SIMILAR TO '{m.group(1).replace('*', '%').replace('[0-9]', '[0-9]')}'"),
    # INTEGER DEFAULT 0 autoincrement not needed (PG uses SERIAL)
]


def _translate_sql(sql: str) -> str:
    """Convert SQLite-flavoured SQL to PostgreSQL."""
    for pattern, replacement in _PG_SQL_SUBS:
        if callable(replacement):
            sql = pattern.sub(replacement, sql)
        else:
            sql = pattern.sub(replacement, sql)
    # Replace ? placeholders with %s
    result, i = [], 0
    in_str = False
    for ch in sql:
        if ch == "'" and not in_str:
            in_str = True
        elif ch == "'" and in_str:
            in_str = False
        if ch == "?" and not in_str:
            result.append("%s")
        else:
            result.append(ch)
    return "".join(result)


class _PgConnection:
    """Thin wrapper around a psycopg2 connection that mimics sqlite3 API."""
    def __init__(self, conn):
        self._conn = conn
        self.row_factory = None  # ignored — we always use _PgRow

    def execute(self, sql: str, params=None):
        sql_pg = _translate_sql(sql)
        cur = self._conn.cursor()
        cur.execute(sql_pg, params or [])
        return _PgCursor(cur)

    def executemany(self, sql: str, seq):
        sql_pg = _translate_sql(sql)
        cur = self._conn.cursor()
        cur.executemany(sql_pg, seq)
        return _PgCursor(cur)

    def executescript(self, sql: str):
        """Execute multiple semicolon-separated statements."""
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    cur = self._conn.cursor()
                    cur.execute(_translate_sql(stmt))
                except Exception as e:
                    logger.debug(f"executescript stmt skipped: {e}")

    def commit(self):  self._conn.commit()
    def rollback(self): self._conn.rollback()
    def close(self):   self._conn.close()


def _open_pg():
    import psycopg2
    conn = psycopg2.connect(_DATABASE_URL)
    conn.autocommit = False
    return _PgConnection(conn)


# ─── CONNECTION ───────────────────────────────────────────────────────────────

def get_db():
    if "db" not in g:
        if _USE_PG:
            g.db = _open_pg()
        else:
            conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            g.db = conn
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

