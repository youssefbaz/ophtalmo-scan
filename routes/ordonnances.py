import json, uuid, datetime, logging
from flask import Blueprint, request, jsonify, Response
from database import get_db, current_user, require_role, log_audit
from security_utils import decrypt_patient, encrypt_ordonnance_fields, decrypt_ordonnance_fields

logger = logging.getLogger(__name__)

bp = Blueprint('ordonnances', __name__)


@bp.route('/api/patients/<pid>/ordonnances', methods=['GET'])
def get_ordonnances(pid):
    u = current_user()
    if not u:
        return jsonify([]), 401
    if u['role'] == 'patient' and u.get('patient_id') != pid:
        return jsonify({"error": "Accès refusé"}), 403
    db = get_db()
    rows = db.execute(
        "SELECT * FROM ordonnances WHERE patient_id=? AND (deleted IS NULL OR deleted=0) ORDER BY date DESC",
        (pid,)
    ).fetchall()
    result = []
    for r in rows:
        o = decrypt_ordonnance_fields(dict(r))
        try:
            o['contenu'] = json.loads(o['contenu'] or '{}')
        except Exception:
            o['contenu'] = {}
        result.append(o)
    return jsonify(result)


@bp.route('/api/patients/<pid>/ordonnances', methods=['POST'])
def add_ordonnance(pid):
    u = current_user()
    if not u or u['role'] != 'medecin':
        return jsonify({"error": "Accès refusé"}), 403
    data = request.json or {}
    db = get_db()
    if not db.execute("SELECT id FROM patients WHERE id=?", (pid,)).fetchone():
        return jsonify({"error": "Patient non trouvé"}), 404
    oid = "O" + str(uuid.uuid4())[:6].upper()
    raw = {"contenu": json.dumps(data.get('contenu', {})), "notes": data.get('notes', '')}
    enc = encrypt_ordonnance_fields(raw)
    db.execute(
        "INSERT INTO ordonnances (id,patient_id,date,medecin,type,contenu,notes) "
        "VALUES (?,?,?,?,?,?,?)",
        (oid, pid,
         data.get('date', datetime.date.today().isoformat()),
         u['nom'],
         data.get('type', 'medicaments'),
         enc['contenu'],
         enc['notes'])
    )
    log_audit(db, 'INSERT', 'ordonnances', oid, u['id'], pid,
              data.get('type', 'medicaments'))
    db.commit()
    return jsonify({"ok": True, "id": oid}), 201


@bp.route('/api/patients/<pid>/ordonnances/<oid>', methods=['DELETE'])
@require_role('medecin')
def delete_ordonnance(pid, oid):
    db = get_db()
    if not db.execute("SELECT id FROM ordonnances WHERE id=? AND patient_id=?", (oid, pid)).fetchone():
        return jsonify({"error": "Non trouvé"}), 404
    db.execute(
        "UPDATE ordonnances SET deleted=1, deleted_at=? WHERE id=? AND patient_id=?",
        (datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), oid, pid)
    )
    u = current_user()
    log_audit(db, 'DELETE', 'ordonnances', oid, u['id'] if u else None, pid, 'soft-delete')
    db.commit()
    return jsonify({"ok": True})


# ─── ORDONNANCE PDF EXPORT ────────────────────────────────────────────────────

@bp.route('/api/patients/<pid>/ordonnances/<oid>/pdf', methods=['GET'])
@require_role('medecin')
def ordonnance_pdf(pid, oid):
    """Generate a printable PDF for an ordonnance using ReportLab."""
    db = get_db()
    p_row = db.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    ord_row = db.execute("SELECT * FROM ordonnances WHERE id=? AND patient_id=?", (oid, pid)).fetchone()
    if not p_row or not ord_row:
        return jsonify({"error": "Non trouvé"}), 404
    p    = decrypt_patient(dict(p_row))
    ord_ = decrypt_ordonnance_fields(dict(ord_row))

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        import io as _io

        try:
            contenu = json.loads(ord_['contenu'] or '{}')
        except Exception:
            contenu = {}

        buf = _io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4,
                                rightMargin=2*cm, leftMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        teal   = colors.HexColor('#0e7a76')

        title_style  = ParagraphStyle('title',  parent=styles['Heading1'],
                                       textColor=teal, alignment=TA_CENTER, fontSize=18)
        sub_style    = ParagraphStyle('sub',    parent=styles['Normal'],
                                       textColor=colors.grey, alignment=TA_CENTER, fontSize=10)
        label_style  = ParagraphStyle('label',  parent=styles['Normal'],
                                       textColor=teal, fontSize=10, spaceAfter=2)
        normal_style = styles['Normal']

        age = datetime.datetime.now().year - int(p['ddn'][:4]) if (p.get('ddn') and p['ddn'][:4].isdigit()) else '?'

        elements = [
            Paragraph("👁  OphtalmoScan", title_style),
            Paragraph("Ordonnance Médicale", sub_style),
            Spacer(1, 0.4*cm),
            HRFlowable(width="100%", thickness=1, color=teal),
            Spacer(1, 0.4*cm),
        ]

        # Patient block
        elements.append(Paragraph(f"<b>Patient :</b> {p['prenom']} {p['nom']} — {age} ans — {p.get('sexe','')}", normal_style))
        elements.append(Paragraph(f"<b>Date :</b> {ord_['date']}   <b>Médecin :</b> {ord_['medecin']}", normal_style))
        elements.append(Spacer(1, 0.4*cm))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        elements.append(Spacer(1, 0.4*cm))

        # Medications / content
        if isinstance(contenu, dict):
            medicaments = contenu.get('medicaments', [])
        elif isinstance(contenu, list):
            medicaments = contenu
        else:
            medicaments = []

        if medicaments:
            elements.append(Paragraph("<b>Médicaments prescrits :</b>", label_style))
            data = [["Médicament", "Posologie", "Durée"]]
            for m in medicaments:
                if isinstance(m, dict):
                    data.append([
                        str(m.get('nom', m.get('name', ''))),
                        str(m.get('posologie', m.get('dosage', ''))),
                        str(m.get('duree', m.get('duration', '')))
                    ])
                else:
                    data.append([str(m), '', ''])
            tbl = Table(data, colWidths=[6*cm, 5*cm, 4*cm])
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), teal),
                ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
                ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE',   (0,0), (-1,-1), 9),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f0faf9')]),
                ('GRID',       (0,0), (-1,-1), 0.5, colors.lightgrey),
                ('VALIGN',     (0,0), (-1,-1), 'MIDDLE'),
                ('PADDING',    (0,0), (-1,-1), 6),
            ]))
            elements.append(tbl)
            elements.append(Spacer(1, 0.3*cm))
        else:
            # Fallback: dump raw content
            raw = json.dumps(contenu, ensure_ascii=False, indent=2) if contenu else str(contenu)
            elements.append(Paragraph(f"<b>Contenu :</b> {raw}", normal_style))

        if ord_.get('notes'):
            elements.append(Spacer(1, 0.2*cm))
            elements.append(Paragraph(f"<b>Notes :</b> {ord_['notes']}", normal_style))

        elements.append(Spacer(1, 1*cm))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
        elements.append(Spacer(1, 0.3*cm))
        elements.append(Paragraph(
            "OphtalmoScan · Ordonnance générée automatiquement · À conserver",
            ParagraphStyle('footer', parent=styles['Normal'],
                           textColor=colors.grey, fontSize=8, alignment=TA_CENTER)
        ))

        doc.build(elements)
        pdf_bytes = buf.getvalue()

        return Response(
            pdf_bytes,
            mimetype='application/pdf',
            headers={
                "Content-Disposition": f"attachment; filename=ordonnance_{oid}.pdf",
                "Content-Length": str(len(pdf_bytes))
            }
        )

    except ImportError:
        return jsonify({"error": "ReportLab non installé. Ajoutez 'reportlab' à requirements.txt"}), 501
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        return jsonify({"error": f"Erreur génération PDF : {e}"}), 500
