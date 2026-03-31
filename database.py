import sqlite3, json, uuid, datetime, os
from flask import g, session
from werkzeug.security import generate_password_hash

DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ophtalmo.db')


# ─── CONNECTION ───────────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


# ─── SESSION HELPER ───────────────────────────────────────────────────────────

def current_user():
    """Return the logged-in user dict, cached in g for the request lifetime."""
    if 'current_user' in g:
        return g.current_user
    username = session.get('username')
    if not username:
        g.current_user = None
        return None
    row = get_db().execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    g.current_user = dict(row) if row else None
    return g.current_user


# ─── NOTIFICATIONS ────────────────────────────────────────────────────────────

def add_notif(db, type_, message, from_role, patient_id=None, data=None):
    db.execute(
        "INSERT INTO notifications (id, type, message, from_role, patient_id, date, lu, data) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            str(uuid.uuid4())[:8],
            type_, message, from_role, patient_id,
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            0,
            json.dumps(data or {})
        )
    )
    db.commit()


# ─── INIT ─────────────────────────────────────────────────────────────────────

def _migrate(db):
    """Add columns/tables introduced after initial schema."""
    new_cols = [
        ("historique", "refraction_od_sph",  "TEXT DEFAULT ''"),
        ("historique", "refraction_od_cyl",  "TEXT DEFAULT ''"),
        ("historique", "refraction_od_axe",  "TEXT DEFAULT ''"),
        ("historique", "refraction_og_sph",  "TEXT DEFAULT ''"),
        ("historique", "refraction_og_cyl",  "TEXT DEFAULT ''"),
        ("historique", "refraction_og_axe",  "TEXT DEFAULT ''"),
        ("historique", "segment_ant",         "TEXT DEFAULT ''"),
        ("patients",   "medecin_id",          "TEXT DEFAULT ''"),
    ]
    for table, col, typedef in new_cols:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
        except Exception:
            pass
    # Assign existing patients without a doctor to U001 (dr.martin)
    db.execute("UPDATE patients SET medecin_id='U001' WHERE medecin_id='' OR medecin_id IS NULL")
    db.commit()


def init_db(app):
    with app.app_context():
        db = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
        _create_tables(db)
        _migrate(db)
        _seed_data(db)
        db.close()


def _create_tables(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id           TEXT PRIMARY KEY,
        username     TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role         TEXT NOT NULL CHECK(role IN ('medecin','patient')),
        nom          TEXT NOT NULL,
        prenom       TEXT DEFAULT '',
        patient_id   TEXT,
        created_at   TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS patients (
        id              TEXT PRIMARY KEY,
        nom             TEXT NOT NULL,
        prenom          TEXT NOT NULL,
        ddn             TEXT DEFAULT '',
        sexe            TEXT DEFAULT '',
        telephone       TEXT DEFAULT '',
        email           TEXT DEFAULT '',
        antecedents     TEXT DEFAULT '[]',
        allergies       TEXT DEFAULT '[]',
        date_chirurgie  TEXT DEFAULT '',
        type_chirurgie  TEXT DEFAULT '',
        medecin_id      TEXT DEFAULT '',
        created_at      TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS historique (
        id                  TEXT PRIMARY KEY,
        patient_id          TEXT NOT NULL,
        date                TEXT DEFAULT '',
        motif               TEXT DEFAULT '',
        diagnostic          TEXT DEFAULT '',
        traitement          TEXT DEFAULT '',
        tension_od          TEXT DEFAULT '',
        tension_og          TEXT DEFAULT '',
        acuite_od           TEXT DEFAULT '',
        acuite_og           TEXT DEFAULT '',
        refraction_od_sph   TEXT DEFAULT '',
        refraction_od_cyl   TEXT DEFAULT '',
        refraction_od_axe   TEXT DEFAULT '',
        refraction_og_sph   TEXT DEFAULT '',
        refraction_og_cyl   TEXT DEFAULT '',
        refraction_og_axe   TEXT DEFAULT '',
        segment_ant         TEXT DEFAULT '',
        notes               TEXT DEFAULT '',
        medecin             TEXT DEFAULT '',
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS ordonnances (
        id          TEXT PRIMARY KEY,
        patient_id  TEXT NOT NULL,
        date        TEXT DEFAULT '',
        medecin     TEXT DEFAULT '',
        type        TEXT DEFAULT 'medicaments',
        contenu     TEXT DEFAULT '{}',
        notes       TEXT DEFAULT '',
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS rdv (
        id          TEXT PRIMARY KEY,
        patient_id  TEXT NOT NULL,
        date        TEXT DEFAULT '',
        heure       TEXT DEFAULT '',
        type        TEXT DEFAULT 'Consultation',
        statut      TEXT DEFAULT 'programmé',
        medecin     TEXT DEFAULT '',
        notes       TEXT DEFAULT '',
        urgent      INTEGER DEFAULT 0,
        demande_par TEXT DEFAULT '',
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS documents (
        id          TEXT PRIMARY KEY,
        patient_id  TEXT NOT NULL,
        type        TEXT DEFAULT 'Document',
        date        TEXT DEFAULT '',
        description TEXT DEFAULT '',
        uploaded_by TEXT DEFAULT '',
        valide      INTEGER DEFAULT 0,
        image_b64   TEXT DEFAULT '',
        notes       TEXT DEFAULT '',
        analyse_ia  TEXT DEFAULT '',
        source      TEXT DEFAULT 'document',
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS questions (
        id               TEXT PRIMARY KEY,
        patient_id       TEXT NOT NULL,
        question         TEXT DEFAULT '',
        date             TEXT DEFAULT '',
        statut           TEXT DEFAULT 'en_attente',
        reponse          TEXT DEFAULT '',
        reponse_ia       TEXT DEFAULT '',
        reponse_validee  INTEGER DEFAULT 0,
        repondu_par      TEXT DEFAULT '',
        date_reponse     TEXT DEFAULT '',
        FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id          TEXT PRIMARY KEY,
        type        TEXT DEFAULT '',
        message     TEXT DEFAULT '',
        from_role   TEXT DEFAULT '',
        patient_id  TEXT,
        date        TEXT DEFAULT '',
        lu          INTEGER DEFAULT 0,
        data        TEXT DEFAULT '{}'
    );
    """)
    db.commit()


def _seed_data(db):
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        return

    db.executemany(
        "INSERT INTO users (id, username, password_hash, role, nom, prenom, patient_id) "
        "VALUES (?,?,?,?,?,?,?)",
        [
            ("U001", "dr.martin",     generate_password_hash("medecin123"), "medecin",   "Dr. Martin", "Jean",      None),
            ("U003", "patient.marie", generate_password_hash("patient123"), "patient",   "Dupont",     "Marie",     "P001"),
            ("U004", "patient.jp",    generate_password_hash("patient123"), "patient",   "Bernard",    "Jean-Paul", "P002"),
        ]
    )

    db.executemany(
        "INSERT INTO patients (id, nom, prenom, ddn, sexe, telephone, email, antecedents, allergies, medecin_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("P001", "Dupont",  "Marie",    "1975-03-15", "F",
             "06 12 34 56 78", "marie.dupont@email.com",
             '["Glaucome chronique","Myopie forte (-6D)"]', '["Pénicilline"]', "U001"),
            ("P002", "Bernard", "Jean-Paul", "1958-11-28", "M",
             "06 98 76 54 32", "jp.bernard@email.com",
             '["DMLA exsudative OG","Diabète type 2"]', '[]', "U001"),
        ]
    )

    db.executemany(
        "INSERT INTO historique (id,patient_id,date,motif,diagnostic,traitement,"
        "tension_od,tension_og,acuite_od,acuite_og,notes,medecin) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("H001","P001","2024-01-15","Suivi glaucome","Glaucome angle ouvert stabilisé",
             "Timolol 0.5% x2/j","16 mmHg","17 mmHg","8/10","7/10","Champ visuel stable.","Dr. Martin"),
            ("H002","P001","2023-09-20","Contrôle annuel","Myopie stable",
             "Renouvellement ordonnance","15 mmHg","16 mmHg","9/10","8/10","Fond d'œil normal.","Dr. Martin"),
            ("H003","P002","2024-02-05","IVT anti-VEGF #6","DMLA exsudative OG",
             "Ranibizumab 0.5mg IVT OG","13 mmHg","14 mmHg","9/10","4/10","Bonne réponse au traitement.","Dr. Martin"),
        ]
    )

    db.executemany(
        "INSERT INTO rdv (id,patient_id,date,heure,type,statut,medecin,notes,urgent,demande_par) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("RDV001","P001","2024-04-22","10:30","Suivi glaucome",   "confirmé", "Dr. Martin","",0,"medecin"),
            ("RDV002","P001","2024-07-15","14:00","OCT de contrôle",  "programmé","Dr. Martin","",0,"medecin"),
            ("RDV003","P002","2024-04-10","09:00","IVT anti-VEGF #7", "confirmé", "Dr. Martin","",0,"medecin"),
        ]
    )

    db.execute(
        "INSERT INTO documents (id,patient_id,type,date,description,uploaded_by,valide,notes,source) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("IMG001","P001","OCT Macula","2024-01-15","OCT macula OD et OG","medecin",1,
         "Épaisseur rétinienne normale.","imagerie")
    )

    db.commit()
