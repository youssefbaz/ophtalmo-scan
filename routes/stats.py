"""
routes/stats.py — Analytics & statistics dashboard for médecins.
All queries are scoped to the requesting médecin's own patients.

Scoping uses SQL subqueries instead of loading patient IDs into Python first,
so query time is O(log n) regardless of roster size.
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

    _nd = "(deleted IS NULL OR deleted=0)"  # not-deleted shorthand

    # ── Scope helpers — subqueries instead of Python-side IN lists ────────────
    # _scope_p  : WHERE clause for the patients table itself
    # _sp       : bound params for _scope_p
    # _scope_fk : WHERE clause for tables joined via patient_id
    if role == 'admin':
        _scope_p   = _nd
        _sp        = []
        _scope_fk  = f"patient_id IN (SELECT id FROM patients WHERE {_nd})"
    else:
        _scope_p   = f"medecin_id=? AND {_nd}"
        _sp        = [mid]
        _scope_fk  = f"patient_id IN (SELECT id FROM patients WHERE medecin_id=? AND {_nd})"

    # Total and new-patient counts
    total_patients = db.execute(
        f"SELECT COUNT(*) FROM patients WHERE {_scope_p}", _sp
    ).fetchone()[0]

    new_this_month = db.execute(
        f"SELECT COUNT(*) FROM patients WHERE {_scope_p} AND created_at >= ?",
        _sp + [month_start]
    ).fetchone()[0]

    new_this_year = db.execute(
        f"SELECT COUNT(*) FROM patients WHERE {_scope_p} AND created_at >= ?",
        _sp + [year_start]
    ).fetchone()[0]

    # ── Shared: last-12-months label list & cutoff ────────────────────────────
    _12m = []
    for _i in range(11, -1, -1):
        _d = today.replace(day=1) - datetime.timedelta(days=_i * 30)
        _12m.append(_d.strftime('%Y-%m'))
    _12m_cutoff = (today - datetime.timedelta(days=365)).isoformat()

    # ── Patients per month (last 12) — one GROUP BY instead of 12 queries ────
    _pm_rows = db.execute(
        f"SELECT strftime('%Y-%m', created_at) AS ym, COUNT(*) AS n "
        f"FROM patients WHERE {_scope_p} AND created_at >= ? GROUP BY ym",
        _sp + [_12m_cutoff]
    ).fetchall()
    _pm_map = {r['ym']: r['n'] for r in _pm_rows}
    patients_per_month = [{'month': ym, 'count': _pm_map.get(ym, 0)} for ym in _12m]

    # ── Patients per year (last 4) — one GROUP BY instead of 4 queries ───────
    _yr_cutoff = f"{today.year - 3}-01-01"
    _py_rows = db.execute(
        f"SELECT strftime('%Y', created_at) AS yr, COUNT(*) AS n "
        f"FROM patients WHERE {_scope_p} AND created_at >= ? GROUP BY yr",
        _sp + [_yr_cutoff]
    ).fetchall()
    _py_map = {r['yr']: r['n'] for r in _py_rows}
    patients_per_year = [
        {'year': str(y), 'count': _py_map.get(str(y), 0)}
        for y in range(today.year - 3, today.year + 1)
    ]

    # ── Sex distribution ───────────────────────────────────────────────────────
    sex_dist = {}
    for row in db.execute(
        f"SELECT sexe, COUNT(*) as n FROM patients WHERE {_scope_p} GROUP BY sexe", _sp
    ).fetchall():
        key = (row['sexe'] or '').strip().upper()
        if key not in ('M', 'F'):
            key = 'N/R'
        sex_dist[key] = sex_dist.get(key, 0) + row['n']

    # ── Age distribution ───────────────────────────────────────────────────────
    # birth_year is a plaintext INTEGER derived from ddn at write-time — no decryption needed.
    age_bands = {'0-17': 0, '18-39': 0, '40-59': 0, '60-79': 0, '80+': 0}
    current_year = today.year
    for row in db.execute(
        f"SELECT birth_year, COUNT(*) as n FROM patients "
        f"WHERE birth_year > 0 AND {_scope_p} GROUP BY birth_year",
        _sp
    ).fetchall():
        try:
            age = current_year - row['birth_year']
            n   = row['n']
            if age < 18:    age_bands['0-17']  += n
            elif age < 40:  age_bands['18-39'] += n
            elif age < 60:  age_bands['40-59'] += n
            elif age < 80:  age_bands['60-79'] += n
            else:           age_bands['80+']   += n
        except Exception:
            pass

    # ── RDV metrics ────────────────────────────────────────────────────────────
    today_str  = today.isoformat()
    week_start = (today - datetime.timedelta(days=today.weekday())).isoformat()

    def _rdv_count(extra="", extra_params=None):
        q = f"SELECT COUNT(*) FROM rdv WHERE {_scope_fk}{extra}"
        p = list(_sp) + (extra_params or [])
        return db.execute(q, p).fetchone()[0]

    total_rdv     = _rdv_count()
    rdv_confirmed = _rdv_count(" AND statut='confirmé'")
    rdv_pending   = _rdv_count(" AND statut='en_attente'")
    rdv_cancelled = _rdv_count(" AND statut='annulé'")
    rdv_urgent    = _rdv_count(" AND urgent=1")
    rdv_today     = _rdv_count(" AND date=?",  [today_str])
    rdv_week      = _rdv_count(" AND date>=?", [week_start])
    rdv_month     = _rdv_count(" AND date>=?", [month_start])

    # ── RDV per month (last 12) — one GROUP BY instead of 12 queries ─────────
    _rm_rows = db.execute(
        f"SELECT strftime('%Y-%m', date) AS ym, COUNT(*) AS n "
        f"FROM rdv WHERE {_scope_fk} AND date >= ? GROUP BY ym",
        _sp + [_12m_cutoff]
    ).fetchall()
    _rm_map = {r['ym']: r['n'] for r in _rm_rows}
    rdv_per_month = [{'month': ym, 'count': _rm_map.get(ym, 0)} for ym in _12m]

    rdv_by_type = []
    for row in db.execute(
        f"SELECT type, COUNT(*) as n FROM rdv WHERE {_scope_fk} "
        f"GROUP BY type ORDER BY n DESC LIMIT 8",
        _sp
    ).fetchall():
        rdv_by_type.append({'type': row['type'], 'count': row['n']})

    # ── RDV per weekday — one GROUP BY instead of 7 queries ──────────────────
    weekdays_fr = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
    _rw_rows = db.execute(
        f"SELECT strftime('%w', date) AS wd, COUNT(*) AS n "
        f"FROM rdv WHERE {_scope_fk} GROUP BY wd",
        _sp
    ).fetchall()
    _rw_map = {r['wd']: r['n'] for r in _rw_rows}
    rdv_per_weekday = [
        {'day': weekdays_fr[i], 'count': _rw_map.get(str((i + 1) % 7), 0)}
        for i in range(7)
    ]

    # ── Consultation metrics ───────────────────────────────────────────────────
    total_consults = db.execute(
        f"SELECT COUNT(*) FROM historique WHERE {_scope_fk}", _sp
    ).fetchone()[0]

    avg_consults = round(total_consults / total_patients, 1) if total_patients else 0

    # ── Consults per month (last 12) — one GROUP BY instead of 12 queries ─────
    _cm_rows = db.execute(
        f"SELECT strftime('%Y-%m', date) AS ym, COUNT(*) AS n "
        f"FROM historique WHERE {_scope_fk} AND date >= ? GROUP BY ym",
        _sp + [_12m_cutoff]
    ).fetchall()
    _cm_map = {r['ym']: r['n'] for r in _cm_rows}
    consults_per_month = [{'month': ym, 'count': _cm_map.get(ym, 0)} for ym in _12m]

    top_diagnostics = []
    for row in db.execute(
        f"SELECT diagnostic, COUNT(*) as n FROM historique "
        f"WHERE diagnostic != '' AND {_scope_fk} "
        f"GROUP BY diagnostic ORDER BY n DESC LIMIT 10",
        _sp
    ).fetchall():
        top_diagnostics.append({'label': row['diagnostic'], 'count': row['n']})

    top_motifs = []
    for row in db.execute(
        f"SELECT motif, COUNT(*) as n FROM historique "
        f"WHERE motif != '' AND {_scope_fk} "
        f"GROUP BY motif ORDER BY n DESC LIMIT 10",
        _sp
    ).fetchall():
        top_motifs.append({'label': row['motif'], 'count': row['n']})

    # ── Antécédents distribution ──────────────────────────────────────────────
    antecedents_count = {}
    for row in db.execute(
        f"SELECT antecedents FROM patients "
        f"WHERE antecedents != '[]' AND antecedents != '' AND {_scope_p}",
        _sp
    ).fetchall():
        try:
            for a in _json.loads(row['antecedents'] or '[]'):
                antecedents_count[a] = antecedents_count.get(a, 0) + 1
        except Exception:
            pass
    top_antecedents = sorted(antecedents_count.items(), key=lambda x: -x[1])[:10]
    top_antecedents = [{'label': k, 'count': v} for k, v in top_antecedents]

    # ── Surgery metrics ───────────────────────────────────────────────────────
    patients_with_surgery = db.execute(
        f"SELECT COUNT(*) FROM patients WHERE date_chirurgie != '' AND {_scope_p}", _sp
    ).fetchone()[0]

    surgery_types = []
    for row in db.execute(
        f"SELECT type_chirurgie, COUNT(*) as n FROM patients "
        f"WHERE date_chirurgie != '' AND type_chirurgie != '' AND {_scope_p} "
        f"GROUP BY type_chirurgie ORDER BY n DESC LIMIT 8",
        _sp
    ).fetchall():
        surgery_types.append({'label': row['type_chirurgie'], 'count': row['n']})

    # ── IVT metrics ───────────────────────────────────────────────────────────
    total_ivt = db.execute(
        f"SELECT COUNT(*) FROM ivt WHERE {_scope_fk}", _sp
    ).fetchone()[0]

    ivt_by_med = []
    for row in db.execute(
        f"SELECT medicament, COUNT(*) as n FROM ivt WHERE {_scope_fk} "
        f"GROUP BY medicament ORDER BY n DESC",
        _sp
    ).fetchall():
        ivt_by_med.append({'label': row['medicament'], 'count': row['n']})

    return jsonify({
        'total_patients':        total_patients,
        'new_this_month':        new_this_month,
        'new_this_year':         new_this_year,
        'patients_per_month':    patients_per_month,
        'patients_per_year':     patients_per_year,
        'sex_dist':              sex_dist,
        'age_bands':             age_bands,
        'total_rdv':             total_rdv,
        'rdv_confirmed':         rdv_confirmed,
        'rdv_pending':           rdv_pending,
        'rdv_cancelled':         rdv_cancelled,
        'rdv_urgent':            rdv_urgent,
        'rdv_today':             rdv_today,
        'rdv_week':              rdv_week,
        'rdv_month':             rdv_month,
        'rdv_per_month':         rdv_per_month,
        'rdv_by_type':           rdv_by_type,
        'rdv_per_weekday':       rdv_per_weekday,
        'total_consults':        total_consults,
        'avg_consults':          avg_consults,
        'consults_per_month':    consults_per_month,
        'top_diagnostics':       top_diagnostics,
        'top_motifs':            top_motifs,
        'top_antecedents':       top_antecedents,
        'patients_with_surgery': patients_with_surgery,
        'surgery_types':         surgery_types,
        'total_ivt':             total_ivt,
        'ivt_by_med':            ivt_by_med,
    })
