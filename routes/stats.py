"""
routes/stats.py — Analytics & statistics dashboard for médecins.
All queries are scoped to the requesting médecin's own patients.
"""
import datetime, json as _json
from flask import Blueprint, jsonify
from database import get_db, current_user, require_role

bp = Blueprint('stats', __name__)


@bp.route('/api/stats', methods=['GET'])
@require_role('medecin', 'admin')
def get_stats():
    db   = get_db()
    u    = current_user()
    mid  = u['id']
    role = u['role']
    today       = datetime.date.today()
    month_start = today.replace(day=1).isoformat()
    year_start  = today.replace(month=1, day=1).isoformat()

    # ── Build the scoped patient id list ──────────────────────────────────────
    # Admin: all patients. Médecin: own patients only.
    if role == 'admin':
        patient_ids = [r[0] for r in db.execute("SELECT id FROM patients").fetchall()]
    else:
        patient_ids = [r[0] for r in db.execute(
            "SELECT id FROM patients WHERE medecin_id=?", (mid,)
        ).fetchall()]

    total_patients = len(patient_ids)

    def _pid_in():
        """Return (sql_fragment, params) for patient_id IN (...)"""
        if not patient_ids:
            return "1=0", []
        return f"patient_id IN ({','.join('?'*len(patient_ids))})", list(patient_ids)

    def _pid_col_in(col='id'):
        """Return (sql_fragment, params) for patients table."""
        if not patient_ids:
            return "1=0", []
        return f"{col} IN ({','.join('?'*len(patient_ids))})", list(patient_ids)

    # ── New patients ──────────────────────────────────────────────────────────
    if role == 'admin':
        new_this_month = db.execute(
            "SELECT COUNT(*) FROM patients WHERE created_at >= ?", (month_start,)
        ).fetchone()[0]
        new_this_year = db.execute(
            "SELECT COUNT(*) FROM patients WHERE created_at >= ?", (year_start,)
        ).fetchone()[0]
    else:
        new_this_month = db.execute(
            "SELECT COUNT(*) FROM patients WHERE medecin_id=? AND created_at >= ?",
            (mid, month_start)
        ).fetchone()[0]
        new_this_year = db.execute(
            "SELECT COUNT(*) FROM patients WHERE medecin_id=? AND created_at >= ?",
            (mid, year_start)
        ).fetchone()[0]

    # ── Patients per month (last 12 months) ───────────────────────────────────
    patients_per_month = []
    for i in range(11, -1, -1):
        d  = (today.replace(day=1) - datetime.timedelta(days=i * 30))
        ym = d.strftime('%Y-%m')
        if role == 'admin':
            cnt = db.execute(
                "SELECT COUNT(*) FROM patients WHERE strftime('%Y-%m', created_at)=?", (ym,)
            ).fetchone()[0]
        else:
            cnt = db.execute(
                "SELECT COUNT(*) FROM patients WHERE medecin_id=? AND strftime('%Y-%m', created_at)=?",
                (mid, ym)
            ).fetchone()[0]
        patients_per_month.append({'month': ym, 'count': cnt})

    # ── Patients per year (last 4 years) ──────────────────────────────────────
    patients_per_year = []
    for y in range(today.year - 3, today.year + 1):
        if role == 'admin':
            cnt = db.execute(
                "SELECT COUNT(*) FROM patients WHERE strftime('%Y', created_at)=?", (str(y),)
            ).fetchone()[0]
        else:
            cnt = db.execute(
                "SELECT COUNT(*) FROM patients WHERE medecin_id=? AND strftime('%Y', created_at)=?",
                (mid, str(y))
            ).fetchone()[0]
        patients_per_year.append({'year': str(y), 'count': cnt})

    # ── Sex distribution ───────────────────────────────────────────────────────
    sex_dist = {}
    if patient_ids:
        pid_frag, pid_params = _pid_col_in('id')
        for row in db.execute(
            f"SELECT sexe, COUNT(*) as n FROM patients WHERE {pid_frag} GROUP BY sexe",
            pid_params
        ).fetchall():
            sex_dist[row['sexe'] or 'N/R'] = row['n']

    # ── Age distribution ───────────────────────────────────────────────────────
    age_bands = {'0-17': 0, '18-39': 0, '40-59': 0, '60-79': 0, '80+': 0}
    if patient_ids:
        pid_frag, pid_params = _pid_col_in('id')
        for row in db.execute(
            f"SELECT ddn FROM patients WHERE ddn != '' AND {pid_frag}", pid_params
        ).fetchall():
            try:
                age = today.year - int(row['ddn'][:4])
                if age < 18:    age_bands['0-17']  += 1
                elif age < 40:  age_bands['18-39'] += 1
                elif age < 60:  age_bands['40-59'] += 1
                elif age < 80:  age_bands['60-79'] += 1
                else:           age_bands['80+']   += 1
            except Exception:
                pass

    # ── RDV metrics ────────────────────────────────────────────────────────────
    pid_frag, pid_params = _pid_in()
    today_str  = today.isoformat()
    week_start = (today - datetime.timedelta(days=today.weekday())).isoformat()

    def _rdv_count(extra="", params=None):
        q = f"SELECT COUNT(*) FROM rdv WHERE {pid_frag}{extra}"
        p = list(pid_params) + (params or [])
        return db.execute(q, p).fetchone()[0]

    total_rdv     = _rdv_count()
    rdv_confirmed = _rdv_count(" AND statut='confirmé'")
    rdv_pending   = _rdv_count(" AND statut='en_attente'")
    rdv_cancelled = _rdv_count(" AND statut='annulé'")
    rdv_urgent    = _rdv_count(" AND urgent=1")
    rdv_today     = _rdv_count(" AND date=?",  [today_str])
    rdv_week      = _rdv_count(" AND date>=?", [week_start])
    rdv_month     = _rdv_count(" AND date>=?", [month_start])

    # RDV per month (last 12)
    rdv_per_month = []
    for i in range(11, -1, -1):
        d  = (today.replace(day=1) - datetime.timedelta(days=i * 30))
        ym = d.strftime('%Y-%m')
        cnt = _rdv_count(" AND strftime('%Y-%m', date)=?", [ym])
        rdv_per_month.append({'month': ym, 'count': cnt})

    # RDV by type (top 8)
    rdv_by_type = []
    if patient_ids:
        for row in db.execute(
            f"SELECT type, COUNT(*) as n FROM rdv WHERE {pid_frag} GROUP BY type ORDER BY n DESC LIMIT 8",
            pid_params
        ).fetchall():
            rdv_by_type.append({'type': row['type'], 'count': row['n']})

    # RDV per weekday (Mon=1 … Sun=0 in SQLite strftime %w)
    weekdays_fr = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
    rdv_per_weekday = []
    for i in range(7):
        sqlite_wd = (i + 1) % 7  # Mon→1, Tue→2 … Sun→0
        cnt = _rdv_count(f" AND strftime('%w', date)=?", [str(sqlite_wd)])
        rdv_per_weekday.append({'day': weekdays_fr[i], 'count': cnt})

    # ── Consultation metrics ───────────────────────────────────────────────────
    h_frag, h_params = _pid_in()

    total_consults = db.execute(
        f"SELECT COUNT(*) FROM historique WHERE {h_frag}", h_params
    ).fetchone()[0] if patient_ids else 0

    avg_consults = round(total_consults / total_patients, 1) if total_patients else 0

    # Consultations per month (last 12)
    consults_per_month = []
    for i in range(11, -1, -1):
        d  = (today.replace(day=1) - datetime.timedelta(days=i * 30))
        ym = d.strftime('%Y-%m')
        cnt = db.execute(
            f"SELECT COUNT(*) FROM historique WHERE strftime('%Y-%m', date)=? AND {h_frag}",
            [ym] + h_params
        ).fetchone()[0] if patient_ids else 0
        consults_per_month.append({'month': ym, 'count': cnt})

    # Top 10 diagnostics
    top_diagnostics = []
    if patient_ids:
        for row in db.execute(
            f"SELECT diagnostic, COUNT(*) as n FROM historique "
            f"WHERE diagnostic != '' AND {h_frag} "
            f"GROUP BY diagnostic ORDER BY n DESC LIMIT 10",
            h_params
        ).fetchall():
            top_diagnostics.append({'label': row['diagnostic'], 'count': row['n']})

    # Top 10 motifs
    top_motifs = []
    if patient_ids:
        for row in db.execute(
            f"SELECT motif, COUNT(*) as n FROM historique "
            f"WHERE motif != '' AND {h_frag} "
            f"GROUP BY motif ORDER BY n DESC LIMIT 10",
            h_params
        ).fetchall():
            top_motifs.append({'label': row['motif'], 'count': row['n']})

    # ── Antécédents distribution ──────────────────────────────────────────────
    antecedents_count = {}
    if patient_ids:
        pid_frag2, pid_params2 = _pid_col_in('id')
        for row in db.execute(
            f"SELECT antecedents FROM patients WHERE antecedents != '[]' AND {pid_frag2}",
            pid_params2
        ).fetchall():
            try:
                for a in _json.loads(row['antecedents'] or '[]'):
                    antecedents_count[a] = antecedents_count.get(a, 0) + 1
            except Exception:
                pass
    top_antecedents = sorted(antecedents_count.items(), key=lambda x: -x[1])[:10]
    top_antecedents = [{'label': k, 'count': v} for k, v in top_antecedents]

    # ── Surgery metrics ───────────────────────────────────────────────────────
    patients_with_surgery = 0
    surgery_types = []
    if patient_ids:
        pid_frag2, pid_params2 = _pid_col_in('id')
        patients_with_surgery = db.execute(
            f"SELECT COUNT(*) FROM patients WHERE date_chirurgie != '' AND {pid_frag2}",
            pid_params2
        ).fetchone()[0]
        for row in db.execute(
            f"SELECT type_chirurgie, COUNT(*) as n FROM patients "
            f"WHERE date_chirurgie != '' AND type_chirurgie != '' AND {pid_frag2} "
            f"GROUP BY type_chirurgie ORDER BY n DESC LIMIT 8",
            pid_params2
        ).fetchall():
            surgery_types.append({'label': row['type_chirurgie'], 'count': row['n']})

    # ── IVT metrics ───────────────────────────────────────────────────────────
    total_ivt = 0
    ivt_by_med = []
    if patient_ids:
        ivt_frag, ivt_params = _pid_in()
        total_ivt = db.execute(
            f"SELECT COUNT(*) FROM ivt WHERE {ivt_frag}", ivt_params
        ).fetchone()[0]
        for row in db.execute(
            f"SELECT medicament, COUNT(*) as n FROM ivt WHERE {ivt_frag} "
            f"GROUP BY medicament ORDER BY n DESC",
            ivt_params
        ).fetchall():
            ivt_by_med.append({'label': row['medicament'], 'count': row['n']})

    return jsonify({
        'total_patients':       total_patients,
        'new_this_month':       new_this_month,
        'new_this_year':        new_this_year,
        'patients_per_month':   patients_per_month,
        'patients_per_year':    patients_per_year,
        'sex_dist':             sex_dist,
        'age_bands':            age_bands,
        'total_rdv':            total_rdv,
        'rdv_confirmed':        rdv_confirmed,
        'rdv_pending':          rdv_pending,
        'rdv_cancelled':        rdv_cancelled,
        'rdv_urgent':           rdv_urgent,
        'rdv_today':            rdv_today,
        'rdv_week':             rdv_week,
        'rdv_month':            rdv_month,
        'rdv_per_month':        rdv_per_month,
        'rdv_by_type':          rdv_by_type,
        'rdv_per_weekday':      rdv_per_weekday,
        'total_consults':       total_consults,
        'avg_consults':         avg_consults,
        'consults_per_month':   consults_per_month,
        'top_diagnostics':      top_diagnostics,
        'top_motifs':           top_motifs,
        'top_antecedents':      top_antecedents,
        'patients_with_surgery': patients_with_surgery,
        'surgery_types':        surgery_types,
        'total_ivt':            total_ivt,
        'ivt_by_med':           ivt_by_med,
    })
