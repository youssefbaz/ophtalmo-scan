"""
routes/patients_import.py — CSV import/export, global search, audit log, and post-op gap detection.
"""
import json, hashlib, re, csv, io, datetime, logging
from flask import Blueprint, request, jsonify, Response
from database import get_db, current_user, add_notif, require_role, log_audit
from llm import call_llm, SYSTEM_IMPORT
from security_utils import decrypt_patient, decrypt_field, encrypt_patient_fields, sanitize
from routes.patients_helpers import _build_patient, _anonymize, _auto_create_account, _next_patient_id, _assert_owns_patient

logger = logging.getLogger(__name__)

bp = Blueprint('patients_import', __name__)


@bp.route('/api/import/csv', methods=['POST'])
def import_csv():
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data     = request.json or {}
    csv_text = data.get('content', '')

    content_preview = csv_text[:6000]
    try:
        patients_raw = list(csv.DictReader(io.StringIO(csv_text)))
        prompt = (f"Voici des données de patients:\n{content_preview}\n\nNormalise et retourne le JSON."
                  if patients_raw
                  else f"Extrais les patients de ce texte:\n{content_preview}")
    except Exception:
        prompt = f"Extrais les patients de ce texte:\n{content_preview}"

    try:
        result_str = call_llm(prompt, SYSTEM_IMPORT, max_tokens=3000)
    except Exception as e:
        logger.error(f"LLM import failed: {e}")
        return jsonify({"ok": False, "error": "Service IA indisponible, réessayez dans quelques minutes."}), 503
    db = get_db()
    try:
        # Strip markdown fences then extract the first JSON array or object
        clean = re.sub(r'```(?:json)?|```', '', result_str).strip()
        # Find outermost [...] block
        m = re.search(r'\[.*\]', clean, re.DOTALL)
        if m:
            clean = m.group(0)
        else:
            # Maybe LLM returned a single object — wrap it
            m2 = re.search(r'\{.*\}', clean, re.DOTALL)
            if m2:
                clean = f"[{m2.group(0)}]"
        patients_list = json.loads(clean)
        if isinstance(patients_list, dict):
            patients_list = [patients_list]
        host  = request.host_url.rstrip('/')
        added = []
        for pd_data in patients_list:
            pid    = _next_patient_id(db)
            nom    = sanitize(pd_data.get("nom",""),    max_len=100)
            prenom = sanitize(pd_data.get("prenom",""), max_len=100)
            email  = sanitize(pd_data.get("email",""),  max_len=200)
            ddn_plain = sanitize(pd_data.get("ddn", ""), max_len=20)
            try:
                birth_year = int(ddn_plain[:4]) if len(ddn_plain) >= 4 else 0
            except (ValueError, TypeError):
                birth_year = 0
            pii = encrypt_patient_fields({
                "nom": nom, "prenom": prenom,
                "ddn":       ddn_plain,
                "telephone": sanitize(pd_data.get("telephone",""), max_len=30),
                "email":     email,
            })
            db.execute(
                "INSERT INTO patients (id,nom,prenom,ddn,sexe,telephone,email,antecedents,allergies,medecin_id,birth_year) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (pid, pii["nom"], pii["prenom"], pii["ddn"],
                 pd_data.get("sexe",""), pii["telephone"], pii["email"],
                 json.dumps(pd_data.get("antecedents",[])), json.dumps(pd_data.get("allergies",[])),
                 u['id'], birth_year)
            )
            creds = _auto_create_account(db, pid, nom=nom, prenom=prenom, email=email, app_host=host)
            added.append({"id": pid, "nom": nom, "prenom": prenom, "credentials": creds})
        db.commit()
        add_notif(db, "import", f"{len(added)} patient(s) importés depuis CSV", "medecin")
        return jsonify({"ok": True, "added": added, "count": len(added)})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Impossible de parser: {e}", "raw": result_str[:500]})


@bp.route('/api/patients/<pid>/export', methods=['GET'])
def export_patient(pid):
    u = current_user()
    if not u or u['role'] not in ('medecin', 'admin'):
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    _assert_owns_patient(db, u, pid)
    p = _build_patient(db, pid)
    if not p:
        return jsonify({"error": "Non trouvé"}), 404
    anon = {
        "code":           hashlib.md5(p["id"].encode()).hexdigest()[:8].upper(),
        "sexe":           p["sexe"],
        "age":            datetime.datetime.now().year - int(p["ddn"][:4]) if p.get("ddn") else 0,
        "antecedents":    p["antecedents"],
        "allergies":      p["allergies"],
        "date_chirurgie": p.get("date_chirurgie",""),
        "type_chirurgie": p.get("type_chirurgie",""),
        "historique":     [{k: v for k, v in h.items() if k != 'medecin'} for h in p["historique"]],
        "nb_rdv":         len(p["rdv"]),
        "export_date":    datetime.datetime.now().strftime("%Y-%m-%d")
    }
    return jsonify(anon)


@bp.route('/api/patients/export-csv', methods=['GET'])
@require_role('medecin')
def export_patients_csv():
    u = current_user()
    db = get_db()
    rows = db.execute(
        "SELECT id, nom, prenom, ddn, sexe, telephone, email, "
        "antecedents, allergies, date_chirurgie, type_chirurgie, created_at "
        "FROM patients WHERE medecin_id=? AND (deleted IS NULL OR deleted=0) ORDER BY nom, prenom",
        (u['id'],)
    ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID","Nom","Prénom","DDN","Sexe","Téléphone","Email",
                     "Antécédents","Allergies","Date chirurgie","Type chirurgie","Créé le"])
    for r in rows:
        p           = decrypt_patient(dict(r))
        antecedents = ', '.join(json.loads(p['antecedents'] or '[]'))
        allergies   = ', '.join(json.loads(p['allergies']   or '[]'))
        writer.writerow([
            p['id'], p['nom'], p['prenom'], p['ddn'], p['sexe'],
            p['telephone'], p['email'], antecedents, allergies,
            p['date_chirurgie'], p['type_chirurgie'], p['created_at']
        ])
    csv_content = output.getvalue()
    return Response(
        csv_content,
        mimetype='text/csv; charset=utf-8',
        headers={"Content-Disposition": "attachment; filename=patients_export.csv"}
    )


@bp.route('/api/search', methods=['GET'])
def search_global():
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify([]), 403
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    db  = get_db()
    ql  = f"%{q.lower()}%"
    results = []

    scope_where  = "WHERE p.medecin_id=? AND (p.deleted IS NULL OR p.deleted=0)" if u['role'] == 'medecin' else "WHERE (p.deleted IS NULL OR p.deleted=0)"
    scope_params = (u['id'],) if u['role'] == 'medecin' else ()
    pat_rows = db.execute(
        f"SELECT id, nom, prenom, ddn FROM patients p {scope_where}", scope_params
    ).fetchall()
    for r in pat_rows:
        dec     = decrypt_patient(dict(r))
        nom_l   = (dec['nom']    or '').lower()
        prenom_l = (dec['prenom'] or '').lower()
        id_l    = (dec['id']     or '').lower()
        if q in nom_l or q in prenom_l or q in id_l:
            results.append({
                "type":  "patient", "pid": dec["id"],
                "label": f"{dec['prenom']} {dec['nom']}",
                "sub":   f"Patient · {dec['ddn'] or '—'}"
            })

    del_filter = "AND (h.deleted IS NULL OR h.deleted=0)"
    scope_join = (
        f"JOIN patients p ON h.patient_id=p.id WHERE p.medecin_id=? {del_filter}"
        if u['role'] == 'medecin' else
        f"JOIN patients p ON h.patient_id=p.id WHERE 1=1 {del_filter}"
    )
    scope_params2 = (u['id'],) if u['role'] == 'medecin' else ()
    hist_rows = db.execute(
        f"SELECT h.id, h.patient_id, h.date, h.motif, h.diagnostic, p.nom, p.prenom "
        f"FROM historique h {scope_join} "
        f"AND (lower(h.motif) LIKE ? OR lower(h.diagnostic) LIKE ? OR lower(h.notes) LIKE ?)",
        scope_params2 + (ql, ql, ql)
    ).fetchall()
    for r in hist_rows:
        dec = decrypt_patient({"nom": r["nom"], "prenom": r["prenom"]})
        results.append({
            "type":  "consultation", "pid": r["patient_id"],
            "label": f"{r['motif'] or r['diagnostic'] or 'Consultation'}",
            "sub":   f"{dec['prenom']} {dec['nom']} · {r['date']}"
        })

    return jsonify(results[:12])


@bp.route('/api/patients/<pid>/audit', methods=['GET'])
@require_role('medecin')
def get_audit(pid):
    db = get_db()
    rows = db.execute(
        "SELECT a.*, u.username FROM audit_log a "
        "LEFT JOIN users u ON a.user_id = u.id "
        "WHERE a.patient_id=? ORDER BY a.created_at DESC LIMIT 100",
        (pid,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route('/api/patients/<pid>/pdf', methods=['GET'])
@require_role('medecin', 'admin')
def patient_pdf(pid):
    """Generate a one-page printable patient handover PDF using ReportLab."""
    from database import medecin_can_access_patient
    u  = current_user()
    db = get_db()
    if u['role'] == 'medecin' and not medecin_can_access_patient(db, u['id'], pid):
        return jsonify({"error": "Accès refusé"}), 403
    p = _build_patient(db, pid)
    if not p:
        return jsonify({"error": "Non trouvé"}), 404

    try:
        import io as _io
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.enums import TA_CENTER, TA_LEFT

        from xml.sax.saxutils import escape as _esc

        def s(v): return _esc(str(v or '').strip())

        buf  = _io.BytesIO()
        doc  = SimpleDocTemplate(buf, pagesize=A4,
                                 rightMargin=2*cm, leftMargin=2*cm,
                                 topMargin=2*cm, bottomMargin=2*cm)
        styl = getSampleStyleSheet()
        teal = colors.HexColor('#0e7a76')

        h1 = ParagraphStyle('h1', parent=styl['Heading1'], textColor=teal,
                             alignment=TA_CENTER, fontSize=16, spaceAfter=4)
        sub = ParagraphStyle('sub', parent=styl['Normal'], textColor=colors.grey,
                             alignment=TA_CENTER, fontSize=9, spaceAfter=8)
        sec = ParagraphStyle('sec', parent=styl['Heading2'], textColor=teal,
                             fontSize=11, spaceBefore=10, spaceAfter=4)
        normal = styl['Normal']
        small  = ParagraphStyle('sm', parent=normal, fontSize=9, leading=12)

        now = datetime.datetime.now().strftime('%d/%m/%Y %H:%M')
        age = datetime.datetime.now().year - int(p['ddn'][:4]) if (p.get('ddn') and p['ddn'][:4].isdigit()) else '?'

        els = [
            Paragraph("👁  OphtalmoScan", h1),
            Paragraph(f"Fiche patient — Généré le {now}", sub),
            HRFlowable(width='100%', thickness=1, color=teal, spaceAfter=8),
        ]

        # Patient identity
        rows_id = [
            ['Nom / Prénom', f"{s(p['prenom'])} {s(p['nom'])}",
             'Date naissance', f"{s(p['ddn'])} ({age} ans)"],
            ['Identifiant', s(p['id']),
             'Sexe', s(p.get('sexe',''))],
            ['Téléphone', s(p.get('telephone','')),
             'Email', s(p.get('email',''))],
        ]
        t_id = Table(rows_id, colWidths=[3.5*cm,6*cm,3.5*cm,4*cm])
        t_id.setStyle(TableStyle([
            ('FONTSIZE',  (0,0), (-1,-1), 9),
            ('TEXTCOLOR', (0,0), (0,-1), colors.grey),
            ('TEXTCOLOR', (2,0), (2,-1), colors.grey),
            ('FONTNAME',  (1,0), (1,-1), 'Helvetica-Bold'),
            ('FONTNAME',  (3,0), (3,-1), 'Helvetica-Bold'),
            ('GRID',      (0,0), (-1,-1), 0.3, colors.HexColor('#dde7e6')),
            ('BACKGROUND',(0,0), (-1,-1), colors.HexColor('#f0faf9')),
            ('TOPPADDING',(0,0),(-1,-1),4),
            ('BOTTOMPADDING',(0,0),(-1,-1),4),
        ]))
        els += [t_id, Spacer(1, 0.3*cm)]

        # Antécédents
        ants = p.get('antecedents') or []
        if ants:
            els.append(Paragraph("Antécédents", sec))
            els.append(Paragraph(', '.join(s(a) for a in ants), small))

        # Last 5 consultations
        histo = p.get('historique') or []
        if histo:
            els.append(Paragraph("Consultations récentes", sec))
            histo_sorted = sorted(histo, key=lambda x: x.get('date',''), reverse=True)[:5]
            h_rows = [['Date','Motif','Traitement','AV OD','AV OG']]
            for h in histo_sorted:
                h_rows.append([
                    s(h.get('date','')), s(h.get('motif','')),
                    s(h.get('traitement','')),
                    s(h.get('acuite_od','')), s(h.get('acuite_og',''))
                ])
            t_h = Table(h_rows, colWidths=[2.5*cm,4*cm,5*cm,2*cm,2*cm])
            t_h.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),teal),
                ('TEXTCOLOR',(0,0),(-1,0),colors.white),
                ('FONTNAME', (0,0),(-1,0),'Helvetica-Bold'),
                ('FONTSIZE', (0,0),(-1,-1),8),
                ('GRID',     (0,0),(-1,-1),0.3,colors.HexColor('#dde7e6')),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f8fefe')]),
                ('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3),
            ]))
            els += [t_h, Spacer(1,0.2*cm)]

        # Ordonnances summary
        ords = p.get('ordonnances') or []
        if ords:
            els.append(Paragraph("Ordonnances (5 dernières)", sec))
            for o in sorted(ords, key=lambda x: x.get('date',''), reverse=True)[:5]:
                try:
                    c_data = json.loads(o.get('contenu') or '{}')
                    meds_txt = '; '.join(
                        s(m.get('medicament','')) for m in (c_data.get('medicaments') or []) if m.get('medicament')
                    ) or '—'
                except Exception:
                    meds_txt = '—'
                els.append(Paragraph(f"<b>{s(o.get('date',''))}</b> — {s(o.get('type',''))} : {meds_txt}", small))

        # Upcoming RDV
        rdvs = [r for r in (p.get('rdv') or []) if r.get('date','') >= datetime.date.today().isoformat()][:5]
        if rdvs:
            els.append(Paragraph("Prochains rendez-vous", sec))
            for r in sorted(rdvs, key=lambda x: x.get('date','')):
                els.append(Paragraph(f"{s(r['date'])} {s(r.get('heure',''))} — {s(r.get('type',''))} ({s(r.get('statut',''))})", small))

        # Signature block
        els += [
            Spacer(1, 1*cm),
            HRFlowable(width='100%', thickness=0.5, color=colors.grey),
            Paragraph("Signature du médecin : ______________________", small),
        ]

        doc.build(els)
        buf.seek(0)
        fname = f"patient_{pid}_{datetime.date.today().isoformat()}.pdf"
        return Response(
            buf.read(), mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{fname}"'}
        )
    except ImportError:
        return jsonify({"error": "ReportLab non installé"}), 501
    except Exception as e:
        logger.error("patient_pdf failed: %s", e)
        return jsonify({"error": str(e)}), 500


@bp.route('/api/postop-gaps', methods=['GET'])
@require_role('medecin')
def get_postop_gaps():
    """Return all overdue post-op follow-up steps for this doctor's patients."""
    u = current_user()
    db = get_db()
    today = datetime.date.today().isoformat()
    rows = db.execute("""
        SELECT s.id, s.patient_id, s.etape, s.date_prevue, s.statut,
               p.nom, p.prenom
        FROM suivi_postop s
        JOIN patients p ON s.patient_id = p.id
        WHERE p.medecin_id = ?
          AND s.statut = 'a_faire'
          AND s.date_prevue < ?
          AND (p.deleted IS NULL OR p.deleted = 0)
        ORDER BY s.date_prevue ASC
    """, (u['id'], today)).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d['nom']    = decrypt_field(d.get('nom',    '') or '')
        d['prenom'] = decrypt_field(d.get('prenom', '') or '')
        result.append(d)
    return jsonify(result)
