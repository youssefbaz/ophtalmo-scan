import sqlite3, json, uuid, datetime, os, logging
from werkzeug.security import generate_password_hash
from database.connection import DB_PATH, _USE_PG, _open_pg

logger = logging.getLogger(__name__)


def init_db(app):
    with app.app_context():
        if _USE_PG:
            db = _open_pg()
        else:
            db = sqlite3.connect(DB_PATH)
            db.row_factory = sqlite3.Row
        _create_tables(db)
        _seed_data(db)
        _migrate(db)
        db.close()


def _create_tables(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id                    TEXT PRIMARY KEY,
        username              TEXT UNIQUE NOT NULL,
        password_hash         TEXT NOT NULL,
        role                  TEXT NOT NULL,
        nom                   TEXT NOT NULL,
        prenom                TEXT DEFAULT '',
        email                 TEXT DEFAULT '',
        date_naissance        TEXT DEFAULT '',
        organisation          TEXT DEFAULT '',
        status                TEXT DEFAULT 'active',
        patient_id            TEXT,
        medecin_code          TEXT DEFAULT '',
        totp_secret           TEXT DEFAULT '',
        totp_enabled          INTEGER DEFAULT 0,
        locked_until          TEXT DEFAULT '',
        force_password_change INTEGER DEFAULT 0,
        created_at            TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS password_resets (
        token       TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL,
        expires_at  TEXT NOT NULL,
        used        INTEGER DEFAULT 0,
        created_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS patient_invitations (
        token      TEXT PRIMARY KEY,
        patient_id TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        used       INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
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
        deleted         INTEGER DEFAULT 0,
        deleted_at      TEXT DEFAULT '',
        birth_year      INTEGER DEFAULT 0,
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
        deleted             INTEGER DEFAULT 0,
        deleted_at          TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS ordonnances (
        id          TEXT PRIMARY KEY,
        patient_id  TEXT NOT NULL,
        date        TEXT DEFAULT '',
        medecin     TEXT DEFAULT '',
        type        TEXT DEFAULT 'medicaments',
        contenu     TEXT DEFAULT '{}',
        notes       TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS rdv (
        id           TEXT PRIMARY KEY,
        patient_id   TEXT NOT NULL,
        date         TEXT DEFAULT '',
        heure        TEXT DEFAULT '',
        type         TEXT DEFAULT 'Consultation',
        statut       TEXT DEFAULT 'programme',
        medecin      TEXT DEFAULT '',
        medecin_id   TEXT DEFAULT '',
        notes        TEXT DEFAULT '',
        urgent       INTEGER DEFAULT 0,
        demande_par  TEXT DEFAULT '',
        sms_envoye   INTEGER DEFAULT 0,
        email_envoye INTEGER DEFAULT 0,
        deleted      INTEGER DEFAULT 0,
        deleted_at   TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS documents (
        id               TEXT PRIMARY KEY,
        patient_id       TEXT NOT NULL,
        type             TEXT DEFAULT 'Document',
        date             TEXT DEFAULT '',
        description      TEXT DEFAULT '',
        uploaded_by      TEXT DEFAULT '',
        valide           INTEGER DEFAULT 0,
        image_b64        TEXT DEFAULT '',
        image_path       TEXT DEFAULT '',
        notes            TEXT DEFAULT '',
        analyse_ia       TEXT DEFAULT '',
        analysis_status  TEXT DEFAULT '',
        source           TEXT DEFAULT 'document',
        deleted          INTEGER DEFAULT 0,
        deleted_at       TEXT DEFAULT ''
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
        deleted          INTEGER DEFAULT 0,
        deleted_at       TEXT DEFAULT ''
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

    CREATE TABLE IF NOT EXISTS suivi_postop (
        id            TEXT PRIMARY KEY,
        patient_id    TEXT NOT NULL,
        etape         TEXT NOT NULL,
        date_prevue   TEXT DEFAULT '',
        date_reelle   TEXT DEFAULT '',
        statut        TEXT DEFAULT 'a_faire',
        historique_id TEXT DEFAULT '',
        rdv_id        TEXT DEFAULT '',
        notes         TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS ivt (
        id          TEXT PRIMARY KEY,
        patient_id  TEXT NOT NULL,
        oeil        TEXT DEFAULT 'OG',
        medicament  TEXT DEFAULT 'Ranibizumab',
        dose        TEXT DEFAULT '0.5mg',
        date        TEXT DEFAULT '',
        numero      INTEGER DEFAULT 1,
        notes       TEXT DEFAULT '',
        medecin     TEXT DEFAULT '',
        deleted     INTEGER DEFAULT 0,
        deleted_at  TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id          TEXT PRIMARY KEY,
        action      TEXT NOT NULL,
        table_name  TEXT NOT NULL,
        record_id   TEXT NOT NULL,
        user_id     TEXT DEFAULT '',
        patient_id  TEXT DEFAULT '',
        detail      TEXT DEFAULT '',
        ip_address  TEXT DEFAULT '',
        user_agent  TEXT DEFAULT '',
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS login_attempts (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL,
        ip_address  TEXT DEFAULT '',
        success     INTEGER DEFAULT 0,
        created_at  TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS totp_backup_codes (
        id          TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL,
        code_hash   TEXT NOT NULL,
        used        INTEGER DEFAULT 0,
        used_at     TEXT DEFAULT '',
        created_at  TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_backup_codes ON totp_backup_codes(user_id, used);

    CREATE TABLE IF NOT EXISTS patient_consents (
        id           TEXT PRIMARY KEY,
        patient_id   TEXT NOT NULL,
        user_id      TEXT NOT NULL,
        consent_type TEXT NOT NULL,
        granted      INTEGER DEFAULT 0,
        granted_at   TEXT DEFAULT '',
        revoked_at   TEXT DEFAULT '',
        ip_address   TEXT DEFAULT '',
        created_at   TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_patients_medecin    ON patients(medecin_id);
    CREATE INDEX IF NOT EXISTS idx_historique_patient  ON historique(patient_id, date);
    CREATE INDEX IF NOT EXISTS idx_rdv_patient         ON rdv(patient_id, date);
    CREATE INDEX IF NOT EXISTS idx_rdv_date_statut     ON rdv(date, statut);
    CREATE INDEX IF NOT EXISTS idx_documents_patient   ON documents(patient_id, source);
    CREATE INDEX IF NOT EXISTS idx_questions_patient   ON questions(patient_id, statut);
    CREATE INDEX IF NOT EXISTS idx_notifs_lu           ON notifications(lu, date);
    CREATE INDEX IF NOT EXISTS idx_suivi_patient       ON suivi_postop(patient_id);
    CREATE INDEX IF NOT EXISTS idx_ivt_patient         ON ivt(patient_id, date);
    CREATE INDEX IF NOT EXISTS idx_audit_patient       ON audit_log(patient_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_audit_user          ON audit_log(user_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_login_attempts      ON login_attempts(user_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_consent_patient     ON patient_consents(patient_id, consent_type);
    """)
    db.commit()


def _migrate(db):
    """Idempotent migrations — add columns/tables added after initial deploy."""
    # Security columns on users
    new_user_cols = [
        ("totp_secret",           "TEXT DEFAULT ''"),
        ("totp_enabled",          "INTEGER DEFAULT 0"),
        ("locked_until",          "TEXT DEFAULT ''"),
        ("date_naissance",        "TEXT DEFAULT ''"),
        ("organisation",          "TEXT DEFAULT ''"),
        ("status",                "TEXT DEFAULT 'active'"),
        ("medecin_code",          "TEXT DEFAULT ''"),
        ("email",                 "TEXT DEFAULT ''"),
        ("force_password_change", "INTEGER DEFAULT 0"),
    ]
    for col, typedef in new_user_cols:
        try:
            db.execute(f"ALTER TABLE users ADD COLUMN {col} {typedef}")
        except Exception:
            pass

    # New audit_log columns
    for col, typedef in [("ip_address","TEXT DEFAULT ''"), ("user_agent","TEXT DEFAULT ''")]:
        try:
            db.execute(f"ALTER TABLE audit_log ADD COLUMN {col} {typedef}")
        except Exception:
            pass

    # login_attempts table
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                ip_address TEXT DEFAULT '', success INTEGER DEFAULT 0, created_at TEXT NOT NULL
            )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_login_attempts ON login_attempts(user_id, created_at)")
    except Exception:
        pass

    # patient_invitations table
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS patient_invitations (
                token TEXT PRIMARY KEY, patient_id TEXT NOT NULL,
                expires_at TEXT NOT NULL, used INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )""")
    except Exception:
        pass

    # patient_consents table
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS patient_consents (
                id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, user_id TEXT NOT NULL,
                consent_type TEXT NOT NULL, granted INTEGER DEFAULT 0,
                granted_at TEXT DEFAULT '', revoked_at TEXT DEFAULT '',
                ip_address TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now'))
            )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_consent_patient ON patient_consents(patient_id, consent_type)")
    except Exception:
        pass

    # suivi_postop rdv_id
    try:
        db.execute("ALTER TABLE suivi_postop ADD COLUMN rdv_id TEXT DEFAULT ''")
    except Exception:
        pass

    # rdv medecin_id (so a patient can book with any doctor, not just their assigned one)
    try:
        db.execute("ALTER TABLE rdv ADD COLUMN medecin_id TEXT DEFAULT ''")
    except Exception:
        pass

    # notifications medecin_id (route notification to a specific doctor)
    try:
        db.execute("ALTER TABLE notifications ADD COLUMN medecin_id TEXT DEFAULT ''")
    except Exception:
        pass

    # documents medecin_id (which doctor this upload is directed to)
    try:
        db.execute("ALTER TABLE documents ADD COLUMN medecin_id TEXT DEFAULT ''")
    except Exception:
        pass

    # patient_doctors: many-to-many link so a patient can appear in multiple doctors' lists
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS patient_doctors (
                patient_id TEXT NOT NULL,
                medecin_id TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (patient_id, medecin_id)
            )
        """)
        db.execute("CREATE INDEX IF NOT EXISTS idx_pd_medecin ON patient_doctors(medecin_id)")
    except Exception:
        pass

    # image_path column: stores path to encrypted image file (replaces image_b64 for new uploads)
    try:
        cols = [r[1] for r in db.execute("PRAGMA table_info(documents)")]
        if 'image_path' not in cols:
            db.execute("ALTER TABLE documents ADD COLUMN image_path TEXT DEFAULT ''")
            logger.info("Migrated documents table: added image_path column")
    except Exception as e:
        logger.error("Failed to add image_path column to documents: %s", e)

    # Soft-delete columns on various tables
    soft_delete = [
        ("documents","deleted"), ("documents","deleted_at"),
        ("questions","deleted"),  ("questions","deleted_at"),
        ("ordonnances","deleted"),("ordonnances","deleted_at"),
        ("ivt","deleted"),        ("ivt","deleted_at"),
        ("rdv","sms_envoye"),     ("rdv","email_envoye"),
        # New: soft-delete on patients, rdv, historique
        ("patients","deleted"),   ("patients","deleted_at"),
        ("rdv","deleted"),        ("rdv","deleted_at"),
        ("historique","deleted"), ("historique","deleted_at"),
        # New: async analysis status on documents
        ("documents","analysis_status"),
    ]
    for table, col in soft_delete:
        try:
            if col == "analysis_status":
                typedef = "TEXT DEFAULT ''"
            elif col.endswith("_at"):
                typedef = "TEXT DEFAULT ''"
            else:
                typedef = "INTEGER DEFAULT 0"
            db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
        except Exception:
            pass

    # TOTP backup codes table
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS totp_backup_codes (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                code_hash TEXT NOT NULL, used INTEGER DEFAULT 0,
                used_at TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now'))
            )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_backup_codes ON totp_backup_codes(user_id, used)")
    except Exception:
        pass

    # historique extra columns
    for col, typedef in [
        ("refraction_od_sph","TEXT DEFAULT ''"),("refraction_od_cyl","TEXT DEFAULT ''"),
        ("refraction_od_axe","TEXT DEFAULT ''"),("refraction_og_sph","TEXT DEFAULT ''"),
        ("refraction_og_cyl","TEXT DEFAULT ''"),("refraction_og_axe","TEXT DEFAULT ''"),
        ("segment_ant","TEXT DEFAULT ''"),
    ]:
        try:
            db.execute(f"ALTER TABLE historique ADD COLUMN {col} {typedef}")
        except Exception:
            pass

    try:
        db.execute("ALTER TABLE patients ADD COLUMN medecin_id TEXT DEFAULT ''")
    except Exception:
        pass

    # birth_year: plaintext integer derived from ddn — avoids decrypting on every stats query
    try:
        db.execute("ALTER TABLE patients ADD COLUMN birth_year INTEGER DEFAULT 0")
    except Exception:
        pass
    # Backfill birth_year for existing rows where it is not yet set
    try:
        from security_utils import decrypt_field as _df
        rows = db.execute(
            "SELECT id, ddn FROM patients WHERE ddn != '' AND (birth_year IS NULL OR birth_year = 0)"
        ).fetchall()
        for _r in rows:
            try:
                _plain = _df(str(_r['ddn']))
                _year  = int(_plain[:4])
                if 1900 < _year < 2100:
                    db.execute("UPDATE patients SET birth_year=? WHERE id=?", (_year, _r['id']))
            except Exception:
                pass
        if rows:
            db.commit()
            logger.info("birth_year backfill complete: %d row(s) updated", len(rows))
    except Exception as _bfe:
        logger.warning("birth_year backfill skipped: %s", _bfe)

    # suivi_postop table
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS suivi_postop (
                id TEXT PRIMARY KEY, patient_id TEXT NOT NULL, etape TEXT NOT NULL,
                date_prevue TEXT DEFAULT '', date_reelle TEXT DEFAULT '',
                statut TEXT DEFAULT 'a_faire', historique_id TEXT DEFAULT '',
                rdv_id TEXT DEFAULT '', notes TEXT DEFAULT ''
            )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_suivi_patient ON suivi_postop(patient_id)")
    except Exception:
        pass

    # ivt table
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS ivt (
                id TEXT PRIMARY KEY, patient_id TEXT NOT NULL,
                oeil TEXT DEFAULT 'OG', medicament TEXT DEFAULT 'Ranibizumab',
                dose TEXT DEFAULT '0.5mg', date TEXT DEFAULT '',
                numero INTEGER DEFAULT 1, notes TEXT DEFAULT '', medecin TEXT DEFAULT '',
                deleted INTEGER DEFAULT 0, deleted_at TEXT DEFAULT ''
            )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_ivt_patient ON ivt(patient_id, date)")
    except Exception:
        pass

    # messages table
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                patient_id TEXT NOT NULL,
                medecin_id TEXT NOT NULL,
                rdv_id TEXT DEFAULT '',
                contenu TEXT DEFAULT '',
                date TEXT DEFAULT '',
                lu INTEGER DEFAULT 0,
                deleted INTEGER DEFAULT 0,
                deleted_at TEXT DEFAULT ''
            )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_messages_patient ON messages(patient_id)")
    except Exception:
        pass

    # Audio columns on questions (patient question audio + doctor response audio)
    for col, typedef in [
        ("question_audio_path",     "TEXT DEFAULT ''"),
        ("question_audio_duration", "INTEGER DEFAULT 0"),
        ("reponse_audio_path",      "TEXT DEFAULT ''"),
        ("reponse_audio_duration",  "INTEGER DEFAULT 0"),
    ]:
        try:
            db.execute(f"ALTER TABLE questions ADD COLUMN {col} {typedef}")
        except Exception:
            pass

    # conversations table — groups messages between a patient and a doctor into threads
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id              TEXT PRIMARY KEY,
                patient_id      TEXT NOT NULL,
                medecin_id      TEXT NOT NULL,
                subject         TEXT DEFAULT '',
                status          TEXT DEFAULT 'open',
                created_at      TEXT DEFAULT '',
                last_message_at TEXT DEFAULT '',
                closed_at       TEXT DEFAULT '',
                closed_by       TEXT DEFAULT ''
            )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_conv_patient ON conversations(patient_id, status)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_conv_medecin ON conversations(medecin_id, status)")
    except Exception:
        pass

    # New columns on messages for conversations + audio
    for col, typedef in [
        ("conversation_id",    "TEXT DEFAULT ''"),
        ("sender_role",        "TEXT DEFAULT 'medecin'"),
        ("audio_path",         "TEXT DEFAULT ''"),
        ("audio_duration_sec", "INTEGER DEFAULT 0"),
    ]:
        try:
            db.execute(f"ALTER TABLE messages ADD COLUMN {col} {typedef}")
        except Exception:
            pass
    try:
        db.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, date)")
    except Exception:
        pass

    # Backfill: any legacy messages rows without a conversation_id get wrapped in a
    # per (patient, medecin) synthetic conversation so nothing is orphaned.
    try:
        orphan_rows = db.execute(
            "SELECT DISTINCT patient_id, medecin_id FROM messages "
            "WHERE conversation_id IS NULL OR conversation_id=''"
        ).fetchall()
        for r in orphan_rows:
            pid, mid = r['patient_id'], r['medecin_id']
            cid = "CONV" + str(uuid.uuid4())[:6].upper()
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            db.execute(
                "INSERT INTO conversations (id,patient_id,medecin_id,subject,status,created_at,last_message_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (cid, pid, mid, '', 'closed', now, now)
            )
            db.execute(
                "UPDATE messages SET conversation_id=?, sender_role=COALESCE(NULLIF(sender_role,''),'medecin') "
                "WHERE patient_id=? AND medecin_id=? AND (conversation_id IS NULL OR conversation_id='')",
                (cid, pid, mid)
            )
        if orphan_rows:
            logger.info("Backfilled %d legacy message group(s) into conversations", len(orphan_rows))
    except Exception as _be:
        logger.warning("Conversation backfill skipped: %s", _be)

    # Medecin codes
    medecins_without_code = db.execute(
        "SELECT id FROM users WHERE role='medecin' AND (medecin_code IS NULL OR medecin_code='')"
        " ORDER BY created_at"
    ).fetchall()
    for i, row in enumerate(medecins_without_code, start=1):
        existing = {r[0] for r in db.execute(
            "SELECT medecin_code FROM users WHERE medecin_code != ''"
        ).fetchall()}
        code = f"M{i:03d}"
        while code in existing:
            i += 1
            code = f"M{i:03d}"
        db.execute("UPDATE users SET medecin_code=? WHERE id=?", (code, row[0]))

    # Ensure admin exists on upgraded DBs
    has_users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if has_users > 0 and not db.execute("SELECT id FROM users WHERE role='admin'").fetchone():
        import secrets as _s
        _pw = _s.token_urlsafe(16)
        logger.warning(f"\n{'='*60}\n  ADMIN CRÉÉ — mot de passe: {_pw}\n{'='*60}")
        db.execute(
            "INSERT INTO users(id,username,password_hash,role,nom,prenom,email,organisation,status) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            ("U000","admin",generate_password_hash(_pw),
             "admin","Administrateur","Système","admin@ophtalmo.local","OphtalmoScan","active")
        )

    db.execute(
        "UPDATE patients SET medecin_id='U001' WHERE medecin_id='' OR medecin_id IS NULL"
    )

    # Encrypt any pre-existing plaintext clinical records (idempotent)
    _migrate_encrypt_clinical(db)

    db.commit()


def _migrate_encrypt_clinical(db):
    """Encrypt plaintext clinical fields in historique, ordonnances, and questions.

    Uses _is_encrypted() to skip already-encrypted rows — safe to call repeatedly.
    """
    try:
        from security_utils import encrypt_field as _ef, _is_encrypted as _ie
    except ImportError:
        return

    # ── historique ─────────────────────────────────────────────────────────────
    clinical_fields = ("motif", "diagnostic", "traitement", "notes", "segment_ant")
    hist_rows = db.execute(
        "SELECT id, motif, diagnostic, traitement, notes, segment_ant FROM historique"
    ).fetchall()
    for row in hist_rows:
        updates = {}
        for field in clinical_fields:
            v = row[field] or ""
            if v and not _ie(v):
                updates[field] = _ef(v)
        if updates:
            set_clause = ", ".join(f"{f}=?" for f in updates)
            db.execute(
                f"UPDATE historique SET {set_clause} WHERE id=?",
                (*updates.values(), row["id"])
            )

    # ── ordonnances ────────────────────────────────────────────────────────────
    ord_rows = db.execute("SELECT id, contenu, notes FROM ordonnances").fetchall()
    for row in ord_rows:
        updates = {}
        for field in ("contenu", "notes"):
            v = row[field] or ""
            if v and not _ie(v):
                updates[field] = _ef(v)
        if updates:
            set_clause = ", ".join(f"{f}=?" for f in updates)
            db.execute(
                f"UPDATE ordonnances SET {set_clause} WHERE id=?",
                (*updates.values(), row["id"])
            )

    # ── questions ──────────────────────────────────────────────────────────────
    q_rows = db.execute(
        "SELECT id, question, reponse, reponse_ia FROM questions"
    ).fetchall()
    for row in q_rows:
        updates = {}
        for field in ("question", "reponse", "reponse_ia"):
            v = row[field] or ""
            if v and not _ie(v):
                updates[field] = _ef(v)
        if updates:
            set_clause = ", ".join(f"{f}=?" for f in updates)
            db.execute(
                f"UPDATE questions SET {set_clause} WHERE id=?",
                (*updates.values(), row["id"])
            )

    try:
        db.commit()
        logger.info("Clinical field encryption migration complete.")
    except Exception as _ce:
        logger.warning("Clinical encryption migration commit failed: %s", _ce)


def _seed_data(db):
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0:
        return

    import secrets as _s
    _admin_pw   = _s.token_urlsafe(16)
    _medecin_pw = _s.token_urlsafe(16)
    _patient_pw = _s.token_urlsafe(16)

    logger.warning(
        "\n" + "="*60 +
        "\n  COMPTES DE DÉMONSTRATION CRÉÉS — CHANGEZ CES MOTS DE PASSE" +
        f"\n  admin      / {_admin_pw}" +
        f"\n  dr.martin  / {_medecin_pw}" +
        f"\n  patient.*  / {_patient_pw}" +
        "\n" + "="*60
    )

    db.executemany(
        "INSERT INTO users (id,username,password_hash,role,nom,prenom,email,organisation,status,patient_id,medecin_code,force_password_change) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("U000","admin",generate_password_hash(_admin_pw),
             "admin","Administrateur","Système","admin@ophtalmo.local","OphtalmoScan","active",None,None,1),
            ("U001","dr.martin",generate_password_hash(_medecin_pw),
             "medecin","Martin","Jean","dr.martin@clinique.com","Clinique de la Vision","active",None,"M001",1),
            ("U003","patient.marie",generate_password_hash(_patient_pw),
             "patient","Dupont","Marie","marie.dupont@email.com","","active","P001",None,1),
            ("U004","patient.jp",generate_password_hash(_patient_pw),
             "patient","Bernard","Jean-Paul","jp.bernard@email.com","","active","P002",None,1),
        ]
    )
    db.executemany(
        "INSERT INTO patients (id,nom,prenom,ddn,sexe,telephone,email,antecedents,allergies,medecin_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("P001","Dupont","Marie","1975-03-15","F","06 12 34 56 78","marie.dupont@email.com",
             '["Glaucome chronique","Myopie forte (-6D)"]','["Pénicilline"]',"U001"),
            ("P002","Bernard","Jean-Paul","1958-11-28","M","06 98 76 54 32","jp.bernard@email.com",
             '["DMLA exsudative OG","Diabète type 2"]','[]',"U001"),
        ]
    )
    db.executemany(
        "INSERT INTO historique (id,patient_id,date,motif,diagnostic,traitement,"
        "tension_od,tension_og,acuite_od,acuite_og,notes,medecin) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("H001","P001","2024-01-15","Suivi glaucome","Glaucome angle ouvert stabilisé",
             "Timolol 0.5% x2/j","16","17","8/10","7/10","Champ visuel stable.","Dr. Martin"),
            ("H002","P001","2023-09-20","Contrôle annuel","Myopie stable",
             "Renouvellement ordonnance","15","16","9/10","8/10","Fond d'œil normal.","Dr. Martin"),
            ("H003","P002","2024-02-05","IVT anti-VEGF #6","DMLA exsudative OG",
             "Ranibizumab 0.5mg IVT OG","13","14","9/10","4/10","Bonne réponse.","Dr. Martin"),
        ]
    )
    db.executemany(
        "INSERT INTO rdv (id,patient_id,date,heure,type,statut,medecin,notes,urgent,demande_par) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("RDV001","P001","2024-04-22","10:30","Suivi glaucome","confirmé","Dr. Martin","",0,"medecin"),
            ("RDV002","P001","2024-07-15","14:00","OCT de contrôle","programmé","Dr. Martin","",0,"medecin"),
            ("RDV003","P002","2024-04-10","09:00","IVT anti-VEGF #7","confirmé","Dr. Martin","",0,"medecin"),
        ]
    )
    db.commit()
