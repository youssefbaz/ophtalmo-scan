// ─── RÉASSIGNATION MÉDECIN ────────────────────────────────────────────────────
async function openAssignerMedecin(pid) {
  const medecins = MEDECINS.length ? MEDECINS : await api('/api/medecins');
  const patient = window._currentPatient;
  const currentMedecinId = patient?.medecin_id || '';
  const options = medecins.map(m =>
    `<option value="${m.id}" ${m.id===currentMedecinId?'selected':''}>${m.nom} ${m.prenom} (${m.username})</option>`
  ).join('');
  document.getElementById('modalRdvContent').innerHTML = `
    <div style="margin-bottom:16px">
      <label class="lbl">Assigner à un médecin</label>
      <select class="input" id="assignMedecinSelect">${options}</select>
    </div>
    <div style="display:flex;gap:10px;justify-content:flex-end">
      <button class="btn btn-ghost" onclick="closeModal('modalRdv')">Annuler</button>
      <button class="btn btn-primary" onclick="submitAssignerMedecin('${pid}')">Enregistrer</button>
    </div>`;
  document.getElementById('modalRdvTitle').textContent = 'Assigner un médecin';
  openModal('modalRdv');
}

async function submitAssignerMedecin(pid) {
  const medecin_id = document.getElementById('assignMedecinSelect').value;
  const res = await api(`/api/patients/${pid}/assigner`, 'POST', { medecin_id });
  if (res.ok) {
    closeModal('modalRdv');
    loadPatient(pid);
    loadPatientsSidebar();
  } else {
    alert(res.error || 'Erreur');
  }
}

// ─── CONSULTATION ─────────────────────────────────────────────────────────────
function openAddConsultation(pid) {
  const today = new Date().toISOString().slice(0,10);
  document.getElementById('modalConsultationContent').innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
      <div><label class="lbl">Date</label><input class="input" type="date" id="cDate" value="${today}"></div>
      <div><label class="lbl">Motif</label><input class="input" id="cMotif" placeholder="Ex: Suivi glaucome"></div>
    </div>
    <div style="background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:14px;margin-bottom:14px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--teal2);margin-bottom:12px">Examen par œil</div>
      <table class="exam-table" style="width:100%;border-collapse:collapse">
        <thead><tr>
          <th style="text-align:left;padding:6px 10px;font-size:11px;color:var(--text2);font-weight:500;width:130px"></th>
          <th style="padding:6px 10px;font-size:12px;color:var(--text);font-weight:600;text-align:center">OD (Droit)</th>
          <th style="padding:6px 10px;font-size:12px;color:var(--text);font-weight:600;text-align:center">OG (Gauche)</th>
        </tr></thead>
        <tbody>
          <tr>
            <td style="padding:6px 10px;font-size:11px;color:var(--text2)">Acuité visuelle</td>
            <td style="padding:4px 6px"><input class="input" id="cAvOd" placeholder="8/10" style="text-align:center" inputmode="decimal"></td>
            <td style="padding:4px 6px"><input class="input" id="cAvOg" placeholder="9/10" style="text-align:center" inputmode="decimal"></td>
          </tr>
          <tr>
            <td style="padding:6px 10px;font-size:11px;color:var(--text2)">Tonus (mmHg)</td>
            <td style="padding:4px 6px"><input class="input" id="cTopOd" placeholder="16" style="text-align:center" inputmode="numeric"></td>
            <td style="padding:4px 6px"><input class="input" id="cTopOg" placeholder="17" style="text-align:center" inputmode="numeric"></td>
          </tr>
          <tr>
            <td style="padding:6px 10px;font-size:11px;color:var(--text2)">Sphère</td>
            <td style="padding:4px 6px"><input class="input" id="cSphOd" placeholder="-3.00" style="text-align:center" inputmode="decimal"></td>
            <td style="padding:4px 6px"><input class="input" id="cSphOg" placeholder="-3.25" style="text-align:center" inputmode="decimal"></td>
          </tr>
          <tr>
            <td style="padding:6px 10px;font-size:11px;color:var(--text2)">Cylindre</td>
            <td style="padding:4px 6px"><input class="input" id="cCylOd" placeholder="-0.75" style="text-align:center" inputmode="decimal"></td>
            <td style="padding:4px 6px"><input class="input" id="cCylOg" placeholder="-0.50" style="text-align:center" inputmode="decimal"></td>
          </tr>
          <tr>
            <td style="padding:6px 10px;font-size:11px;color:var(--text2)">Axe (°)</td>
            <td style="padding:4px 6px"><input class="input" id="cAxeOd" placeholder="90" style="text-align:center" inputmode="numeric"></td>
            <td style="padding:4px 6px"><input class="input" id="cAxeOg" placeholder="85" style="text-align:center" inputmode="numeric"></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div style="margin-bottom:12px">
      <label class="lbl">Segment antérieur</label>
      <input class="input" id="cSegAnt" placeholder="Ex: Cornée claire, chambre antérieure calme...">
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
      <div><label class="lbl">Diagnostic</label><textarea class="input" id="cDiag" rows="3" placeholder="Diagnostic principal..."></textarea></div>
      <div><label class="lbl">Traitement / Prescription</label><textarea class="input" id="cTrait" rows="3" placeholder="Traitement prescrit..."></textarea></div>
    </div>
    <div style="margin-bottom:16px">
      <label class="lbl">Notes</label>
      <textarea class="input" id="cNotes" rows="2" placeholder="Notes libres..."></textarea>
    </div>
    <div style="display:flex;gap:10px;justify-content:flex-end">
      <button class="btn btn-ghost" onclick="closeModal('modalConsultation')">Annuler</button>
      <button class="btn btn-primary" onclick="submitConsultation('${pid}')">Enregistrer la consultation</button>
    </div>`;
  openModal('modalConsultation');
}

async function submitConsultation(pid) {
  const body = {
    date:               document.getElementById('cDate').value,
    motif:              document.getElementById('cMotif').value.trim(),
    acuite_od:          document.getElementById('cAvOd').value.trim(),
    acuite_og:          document.getElementById('cAvOg').value.trim(),
    tension_od:         document.getElementById('cTopOd').value.trim(),
    tension_og:         document.getElementById('cTopOg').value.trim(),
    refraction_od_sph:  document.getElementById('cSphOd').value.trim(),
    refraction_od_cyl:  document.getElementById('cCylOd').value.trim(),
    refraction_od_axe:  document.getElementById('cAxeOd').value.trim(),
    refraction_og_sph:  document.getElementById('cSphOg').value.trim(),
    refraction_og_cyl:  document.getElementById('cCylOg').value.trim(),
    refraction_og_axe:  document.getElementById('cAxeOg').value.trim(),
    segment_ant:        document.getElementById('cSegAnt').value.trim(),
    diagnostic:         document.getElementById('cDiag').value.trim(),
    traitement:         document.getElementById('cTrait').value.trim(),
    notes:              document.getElementById('cNotes').value.trim(),
  };
  const res = await api(`/api/patients/${pid}/historique`, 'POST', body);
  if (res.ok) {
    closeModal('modalConsultation');
    loadPatient(pid);
  } else {
    alert(res.error || 'Erreur');
  }
}

async function deleteConsultation(pid, hid) {
  if (!confirm('Supprimer cette consultation ?')) return;
  await api(`/api/patients/${pid}/historique/${hid}`, 'DELETE');
  loadPatient(pid);
}

function openEditConsultation(pid, hid) {
  const h = (window._currentPatient?.historique || []).find(x => x.id === hid);
  if (!h) { alert('Consultation introuvable'); return; }
  document.getElementById('modalConsultationContent').innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px">
      <div><label class="lbl">Date</label><input class="input" type="date" id="cDate" value="${h.date}"></div>
      <div><label class="lbl">Motif</label><input class="input" id="cMotif" value="${escH(h.motif)}"></div>
    </div>
    <div style="background:var(--bg3);border:1px solid var(--border);border-radius:12px;padding:14px;margin-bottom:14px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--teal2);margin-bottom:12px">Examen par œil</div>
      <table class="exam-table" style="width:100%;border-collapse:collapse">
        <thead><tr>
          <th style="text-align:left;padding:6px 10px;font-size:11px;color:var(--text2);font-weight:500;width:130px"></th>
          <th style="padding:6px 10px;font-size:12px;color:var(--text);font-weight:600;text-align:center">OD (Droit)</th>
          <th style="padding:6px 10px;font-size:12px;color:var(--text);font-weight:600;text-align:center">OG (Gauche)</th>
        </tr></thead>
        <tbody>
          <tr>
            <td style="padding:6px 10px;font-size:11px;color:var(--text2)">Acuité visuelle</td>
            <td style="padding:4px 6px"><input class="input" id="cAvOd" value="${h.acuite_od||''}" placeholder="8/10" style="text-align:center" inputmode="decimal"></td>
            <td style="padding:4px 6px"><input class="input" id="cAvOg" value="${h.acuite_og||''}" placeholder="9/10" style="text-align:center" inputmode="decimal"></td>
          </tr>
          <tr>
            <td style="padding:6px 10px;font-size:11px;color:var(--text2)">Tonus (mmHg)</td>
            <td style="padding:4px 6px"><input class="input" id="cTopOd" value="${h.tension_od||''}" placeholder="16" style="text-align:center" inputmode="numeric"></td>
            <td style="padding:4px 6px"><input class="input" id="cTopOg" value="${h.tension_og||''}" placeholder="17" style="text-align:center" inputmode="numeric"></td>
          </tr>
          <tr>
            <td style="padding:6px 10px;font-size:11px;color:var(--text2)">Sphère</td>
            <td style="padding:4px 6px"><input class="input" id="cSphOd" value="${h.refraction_od_sph||''}" placeholder="-3.00" style="text-align:center" inputmode="decimal"></td>
            <td style="padding:4px 6px"><input class="input" id="cSphOg" value="${h.refraction_og_sph||''}" placeholder="-3.25" style="text-align:center" inputmode="decimal"></td>
          </tr>
          <tr>
            <td style="padding:6px 10px;font-size:11px;color:var(--text2)">Cylindre</td>
            <td style="padding:4px 6px"><input class="input" id="cCylOd" value="${h.refraction_od_cyl||''}" placeholder="-0.75" style="text-align:center" inputmode="decimal"></td>
            <td style="padding:4px 6px"><input class="input" id="cCylOg" value="${h.refraction_og_cyl||''}" placeholder="-0.50" style="text-align:center" inputmode="decimal"></td>
          </tr>
          <tr>
            <td style="padding:6px 10px;font-size:11px;color:var(--text2)">Axe (°)</td>
            <td style="padding:4px 6px"><input class="input" id="cAxeOd" value="${h.refraction_od_axe||''}" placeholder="90" style="text-align:center" inputmode="numeric"></td>
            <td style="padding:4px 6px"><input class="input" id="cAxeOg" value="${h.refraction_og_axe||''}" placeholder="85" style="text-align:center" inputmode="numeric"></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div style="margin-bottom:12px">
      <label class="lbl">Segment antérieur</label>
      <input class="input" id="cSegAnt" value="${escH(h.segment_ant||'')}" placeholder="Ex: Cornée claire...">
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
      <div><label class="lbl">Diagnostic</label><textarea class="input" id="cDiag" rows="3">${escH(h.diagnostic||'')}</textarea></div>
      <div><label class="lbl">Traitement / Prescription</label><textarea class="input" id="cTrait" rows="3">${escH(h.traitement||'')}</textarea></div>
    </div>
    <div style="margin-bottom:16px">
      <label class="lbl">Notes</label>
      <textarea class="input" id="cNotes" rows="2">${escH(h.notes||'')}</textarea>
    </div>
    <div style="display:flex;gap:10px;justify-content:flex-end">
      <button class="btn btn-ghost" onclick="closeModal('modalConsultation')">Annuler</button>
      <button class="btn btn-primary" onclick="submitEditConsultation('${pid}','${h.id}')">Enregistrer les modifications</button>
    </div>`;
  document.querySelector('#modalConsultation .modal-title').textContent = 'Modifier la consultation';
  openModal('modalConsultation');
}

async function submitEditConsultation(pid, hid) {
  const body = {
    date:               document.getElementById('cDate').value,
    motif:              document.getElementById('cMotif').value.trim(),
    acuite_od:          document.getElementById('cAvOd').value.trim(),
    acuite_og:          document.getElementById('cAvOg').value.trim(),
    tension_od:         document.getElementById('cTopOd').value.trim(),
    tension_og:         document.getElementById('cTopOg').value.trim(),
    refraction_od_sph:  document.getElementById('cSphOd').value.trim(),
    refraction_od_cyl:  document.getElementById('cCylOd').value.trim(),
    refraction_od_axe:  document.getElementById('cAxeOd').value.trim(),
    refraction_og_sph:  document.getElementById('cSphOg').value.trim(),
    refraction_og_cyl:  document.getElementById('cCylOg').value.trim(),
    refraction_og_axe:  document.getElementById('cAxeOg').value.trim(),
    segment_ant:        document.getElementById('cSegAnt').value.trim(),
    diagnostic:         document.getElementById('cDiag').value.trim(),
    traitement:         document.getElementById('cTrait').value.trim(),
    notes:              document.getElementById('cNotes').value.trim(),
  };
  const res = await api(`/api/patients/${pid}/historique/${hid}`, 'PUT', body);
  if (res.ok) {
    closeModal('modalConsultation');
    document.querySelector('#modalConsultation .modal-title').textContent = 'Nouvelle consultation';
    loadPatient(pid);
  } else {
    alert(res.error || 'Erreur');
  }
}

// ─── EVOLUTION CHARTS ─────────────────────────────────────────────────────────
const _charts = {};

function parseAV(s) {
  if (!s) return null;
  const m = s.match(/(\d+)\/(\d+)/);
  if (m) return parseFloat(m[1]) / parseFloat(m[2]);
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

function parseIOP(s) {
  if (!s) return null;
  const n = parseFloat(s);
  return isNaN(n) ? null : n;
}

function renderEvolutionCharts(patient, pid) {
  const hist = [...patient.historique].reverse(); // chronological order
  const labels = hist.map(h => fmtDate(h.date));
  const chartDefaults = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: { legend: { labels: { color: '#8ba7be', font: { size: 11 } } } },
    scales: {
      x: { ticks: { color: '#8ba7be', font: { size: 10 } }, grid: { color: '#153045' } },
      y: { ticks: { color: '#8ba7be', font: { size: 10 } }, grid: { color: '#153045' } }
    }
  };

  const iopOd = hist.map(h => parseIOP(h.tension_od));
  const iopOg = hist.map(h => parseIOP(h.tension_og));
  if (iopOd.some(v=>v!==null)) {
    if (_charts[`iop-${pid}`]) _charts[`iop-${pid}`].destroy();
    const ctxIop = document.getElementById(`chart-iop-${pid}`);
    if (ctxIop) {
      _charts[`iop-${pid}`] = new Chart(ctxIop, {
        type: 'line',
        data: {
          labels,
          datasets: [
            { label: 'OD', data: iopOd, borderColor: '#0ea5a0', backgroundColor: 'rgba(14,165,160,.1)', tension: .3, pointRadius: 4 },
            { label: 'OG', data: iopOg, borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,.1)', tension: .3, pointRadius: 4 }
          ]
        },
        options: chartDefaults
      });
    }
  }

  const avOd = hist.map(h => parseAV(h.acuite_od));
  const avOg = hist.map(h => parseAV(h.acuite_og));
  if (avOd.some(v=>v!==null)) {
    if (_charts[`av-${pid}`]) _charts[`av-${pid}`].destroy();
    const ctxAv = document.getElementById(`chart-av-${pid}`);
    if (ctxAv) {
      _charts[`av-${pid}`] = new Chart(ctxAv, {
        type: 'line',
        data: {
          labels,
          datasets: [
            { label: 'OD', data: avOd, borderColor: '#0ea5a0', backgroundColor: 'rgba(14,165,160,.1)', tension: .3, pointRadius: 4 },
            { label: 'OG', data: avOg, borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,.1)', tension: .3, pointRadius: 4 }
          ]
        },
        options: { ...chartDefaults, scales: { ...chartDefaults.scales, y: { ...chartDefaults.scales.y, min: 0, max: 1 } } }
      });
    }
  }
}

// ─── ORDONNANCES ──────────────────────────────────────────────────────────────
function renderOrdonnancesList(ordonnances, pid) {
  if (!ordonnances.length) return '<div style="color:var(--text3);text-align:center;padding:30px">Aucune ordonnance</div>';
  return ordonnances.map(o => {
    let body = '';
    if (o.type === 'lunettes') {
      const c = o.contenu;
      body = `
        <table class="ordo-table">
          <thead><tr><th></th><th>Sphère</th><th>Cylindre</th><th>Axe</th><th>Addition</th></tr></thead>
          <tbody>
            <tr><td>OD</td><td>${c.od_sph||'—'}</td><td>${c.od_cyl||'—'}</td><td>${c.od_axe||'—'}</td><td>${c.od_add||'—'}</td></tr>
            <tr><td>OG</td><td>${c.og_sph||'—'}</td><td>${c.og_cyl||'—'}</td><td>${c.og_axe||'—'}</td><td>${c.og_add||'—'}</td></tr>
          </tbody>
        </table>
        ${c.type_verre ? `<div style="margin-top:8px;font-size:12px;color:var(--text2)">Verres : <strong>${c.type_verre}</strong></div>` : ''}`;
    } else if (o.type === 'medicaments') {
      const meds = o.contenu.medicaments || [];
      body = meds.map(m => `
        <div class="med-item">
          <div style="font-size:18px">💊</div>
          <div><div class="med-name">${m.nom}</div><div class="med-posologie">${m.posologie}${m.duree?` · ${m.duree}`:''}</div></div>
        </div>`).join('');
    } else if (o.type === 'bilan') {
      const exams = o.contenu.examens || [];
      body = `<div style="font-size:13px;color:var(--text2)">${exams.map(e=>`<div style="padding:4px 0;border-bottom:1px solid var(--border)">🔬 ${e}</div>`).join('')}</div>`;
    }
    return `
      <div class="ordo-card">
        <div class="ordo-header">
          <div style="display:flex;align-items:center;gap:10px">
            <span class="ordo-type-badge">${o.type}</span>
            <span class="ordo-meta">${fmtDate(o.date)} · ${o.medecin}</span>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-ghost btn-sm" onclick="printOrdonnance('${o.id}','${pid}')">🖨 Imprimer</button>
            <button class="btn btn-ghost btn-sm" onclick="downloadOrdonnancePDF('${pid}','${o.id}')" title="Télécharger PDF">📄 PDF</button>
            <button class="btn btn-ghost btn-sm" style="opacity:.6" onclick="deleteOrdonnance('${pid}','${o.id}')">🗑</button>
          </div>
        </div>
        ${body}
        ${o.notes ? `<div style="margin-top:10px;font-size:12px;color:var(--text3)">📝 ${o.notes}</div>` : ''}
      </div>`;
  }).join('');
}

function openAddOrdonnance(pid) {
  document.getElementById('modalOrdonnanceContent').innerHTML = `
    <div style="margin-bottom:14px">
      <label class="lbl">Type d'ordonnance</label>
      <select class="input" id="oType" onchange="updateOrdoForm()">
        <option value="medicaments">Médicaments / Collyres</option>
        <option value="lunettes">Correction optique (lunettes)</option>
        <option value="bilan">Bilan / Examens complémentaires</option>
      </select>
    </div>
    <div id="ordoFormBody">${buildOrdoMedsForm()}</div>
    <div style="margin-top:14px">
      <label class="lbl">Notes</label>
      <input class="input" id="oNotes" placeholder="Remarques éventuelles...">
    </div>
    <div style="display:flex;gap:10px;justify-content:flex-end;margin-top:18px">
      <button class="btn btn-ghost" onclick="closeModal('modalOrdonnance')">Annuler</button>
      <button class="btn btn-primary" onclick="submitOrdonnance('${pid}')">Créer l'ordonnance</button>
    </div>`;
  openModal('modalOrdonnance');
}

function buildOrdoMedsForm(n=1) {
  let rows = '';
  for (let i=0;i<n;i++) rows += `
    <div class="med-row" style="display:grid;grid-template-columns:2fr 2fr 1fr;gap:8px;margin-bottom:8px">
      <input class="input med-nom" placeholder="Médicament (ex: Timolol 0.5%)">
      <input class="input med-posologie" placeholder="Posologie (ex: 1 gtte x2/j OD)">
      <input class="input med-duree" placeholder="Durée (ex: 3 mois)">
    </div>`;
  return `
    <div id="medRows">${rows}</div>
    <button class="btn btn-ghost btn-sm" onclick="addMedRow()">+ Ajouter un médicament</button>`;
}

function buildOrdoLunettesForm() {
  return `
    <table class="exam-table" style="width:100%;border-collapse:collapse;margin-bottom:12px">
      <thead><tr>
        <th style="padding:6px 10px;font-size:11px;color:var(--text2);font-weight:500;text-align:left"></th>
        <th style="padding:6px 10px;font-size:12px;text-align:center">Sphère</th>
        <th style="padding:6px 10px;font-size:12px;text-align:center">Cylindre</th>
        <th style="padding:6px 10px;font-size:12px;text-align:center">Axe (°)</th>
        <th style="padding:6px 10px;font-size:12px;text-align:center">Addition</th>
      </tr></thead>
      <tbody>
        <tr>
          <td style="padding:4px 10px;font-size:12px;font-weight:600">OD</td>
          <td style="padding:4px 6px"><input class="input" id="lOdSph" placeholder="-3.00" style="text-align:center"></td>
          <td style="padding:4px 6px"><input class="input" id="lOdCyl" placeholder="-0.75" style="text-align:center"></td>
          <td style="padding:4px 6px"><input class="input" id="lOdAxe" placeholder="90" style="text-align:center"></td>
          <td style="padding:4px 6px"><input class="input" id="lOdAdd" placeholder="+2.00" style="text-align:center"></td>
        </tr>
        <tr>
          <td style="padding:4px 10px;font-size:12px;font-weight:600">OG</td>
          <td style="padding:4px 6px"><input class="input" id="lOgSph" placeholder="-3.25" style="text-align:center"></td>
          <td style="padding:4px 6px"><input class="input" id="lOgCyl" placeholder="-0.50" style="text-align:center"></td>
          <td style="padding:4px 6px"><input class="input" id="lOgAxe" placeholder="85" style="text-align:center"></td>
          <td style="padding:4px 6px"><input class="input" id="lOgAdd" placeholder="+2.00" style="text-align:center"></td>
        </tr>
      </tbody>
    </table>
    <div><label class="lbl">Type de verres</label>
    <select class="input" id="lTypeVerre">
      <option value="unifocaux">Unifocaux</option>
      <option value="progressifs">Progressifs</option>
      <option value="bifocaux">Bifocaux</option>
    </select></div>`;
}

function buildOrdoBilanForm() {
  return `
    <div id="bilanRows">
      <input class="input bilan-exam" placeholder="Ex: OCT macula OD+OG" style="margin-bottom:8px">
    </div>
    <button class="btn btn-ghost btn-sm" onclick="addBilanRow()">+ Ajouter un examen</button>`;
}

function updateOrdoForm() {
  const t = document.getElementById('oType').value;
  const body = t==='lunettes' ? buildOrdoLunettesForm() : t==='bilan' ? buildOrdoBilanForm() : buildOrdoMedsForm();
  document.getElementById('ordoFormBody').innerHTML = body;
}

function addMedRow() {
  const row = document.createElement('div');
  row.className = 'med-row';
  row.style.cssText = 'display:grid;grid-template-columns:2fr 2fr 1fr;gap:8px;margin-bottom:8px';
  row.innerHTML = `<input class="input med-nom" placeholder="Médicament"><input class="input med-posologie" placeholder="Posologie"><input class="input med-duree" placeholder="Durée">`;
  document.getElementById('medRows').appendChild(row);
}

function addBilanRow() {
  const inp = document.createElement('input');
  inp.className = 'input bilan-exam';
  inp.placeholder = 'Examen complémentaire';
  inp.style.marginBottom = '8px';
  document.getElementById('bilanRows').appendChild(inp);
}

async function submitOrdonnance(pid) {
  const type = document.getElementById('oType').value;
  const notes = document.getElementById('oNotes').value.trim();
  let contenu = {};
  if (type === 'medicaments') {
    contenu.medicaments = [...document.querySelectorAll('.med-row')].map(r => ({
      nom:       r.querySelector('.med-nom').value.trim(),
      posologie: r.querySelector('.med-posologie').value.trim(),
      duree:     r.querySelector('.med-duree').value.trim(),
    })).filter(m => m.nom);
  } else if (type === 'lunettes') {
    contenu = {
      od_sph: document.getElementById('lOdSph').value.trim(),
      od_cyl: document.getElementById('lOdCyl').value.trim(),
      od_axe: document.getElementById('lOdAxe').value.trim(),
      od_add: document.getElementById('lOdAdd').value.trim(),
      og_sph: document.getElementById('lOgSph').value.trim(),
      og_cyl: document.getElementById('lOgCyl').value.trim(),
      og_axe: document.getElementById('lOgAxe').value.trim(),
      og_add: document.getElementById('lOgAdd').value.trim(),
      type_verre: document.getElementById('lTypeVerre').value,
    };
  } else if (type === 'bilan') {
    contenu.examens = [...document.querySelectorAll('.bilan-exam')].map(i=>i.value.trim()).filter(Boolean);
  }
  const res = await api(`/api/patients/${pid}/ordonnances`, 'POST', { type, contenu, notes });
  if (res.ok) {
    closeModal('modalOrdonnance');
    loadPatient(pid);
  } else {
    alert(res.error || 'Erreur');
  }
}

async function deleteOrdonnance(pid, oid) {
  if (!confirm('Supprimer cette ordonnance ?')) return;
  await api(`/api/patients/${pid}/ordonnances/${oid}`, 'DELETE');
  loadPatient(pid);
}

async function printOrdonnance(oid, pid) {
  const patient = window._currentPatient;
  const ordo = patient.ordonnances.find(o => o.id === oid);
  if (!ordo) return;
  let body = '';
  if (ordo.type === 'lunettes') {
    const c = ordo.contenu;
    body = `<table class="exam-table" border="1" cellpadding="8" style="width:100%;border-collapse:collapse;margin:16px 0">
      <tr style="background:#f5f5f5"><th></th><th>Sphère</th><th>Cylindre</th><th>Axe</th><th>Addition</th></tr>
      <tr><td><b>Œil Droit (OD)</b></td><td>${c.od_sph||''}</td><td>${c.od_cyl||''}</td><td>${c.od_axe||''}</td><td>${c.od_add||''}</td></tr>
      <tr><td><b>Œil Gauche (OG)</b></td><td>${c.og_sph||''}</td><td>${c.og_cyl||''}</td><td>${c.og_axe||''}</td><td>${c.og_add||''}</td></tr>
    </table>
    ${c.type_verre ? `<p>Type de verres : <b>${c.type_verre}</b></p>` : ''}`;
  } else if (ordo.type === 'medicaments') {
    const meds = ordo.contenu.medicaments || [];
    body = meds.map((m,i)=>`<div style="margin:10px 0;padding:8px 12px;border-left:3px solid #333">
      <b>${i+1}. ${m.nom}</b><br>
      <span style="color:#333">${m.posologie}${m.duree?` — Durée : ${m.duree}`:''}</span>
    </div>`).join('');
  } else if (ordo.type === 'bilan') {
    body = `<ul style="margin:10px 0">${(ordo.contenu.examens||[]).map(e=>`<li style="margin:6px 0">${e}</li>`).join('')}</ul>`;
  }
  const age = new Date().getFullYear() - new Date(patient.ddn).getFullYear();
  const medecinName = ordo.medecin || 'Dr. —';
  const clinique = 'Cabinet d\'Ophtalmologie';
  const w = window.open('', '_blank', 'width=760,height=1000');
  w.document.write(`<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Ordonnance — ${patient.prenom} ${patient.nom}</title>
  <style>
    *{box-sizing:border-box}
    body{font-family:'Times New Roman',serif;padding:0;margin:0;color:#000;background:#fff}
    .page{width:210mm;min-height:297mm;margin:0 auto;padding:20mm 20mm 15mm 20mm}
    .header{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #000;padding-bottom:12px;margin-bottom:14px}
    .clinic-name{font-size:20px;font-weight:bold;letter-spacing:1px}
    .clinic-info{font-size:11px;color:#333;margin-top:4px;line-height:1.6}
    .doc-title{font-size:22px;font-weight:bold;text-align:center;margin:14px 0;text-transform:uppercase;letter-spacing:3px;color:#000}
    .patient-box{background:#f9f9f9;border:1px solid #ccc;border-radius:4px;padding:10px 14px;margin-bottom:16px;font-size:13px;line-height:1.7}
    .body-section{margin:18px 0;font-size:13px;line-height:1.8}
    .notes{font-style:italic;margin-top:16px;font-size:12px;color:#444;border-top:1px dashed #ccc;padding-top:10px}
    .footer{margin-top:40px;display:flex;justify-content:space-between;font-size:12px}
    .signature-box{border:1px solid #999;width:180px;height:70px;display:flex;align-items:flex-end;padding:6px;font-size:11px;color:#666}
    .stamp-box{border:1px solid #999;width:100px;height:70px;display:flex;align-items:center;justify-content:center;font-size:10px;color:#aaa}
    @media print{body{margin:0}.page{padding:15mm 15mm 10mm 15mm}}
  </style>
  </head><body>
  <div class="page">
    <div class="header">
      <div>
        <div class="clinic-name">${clinique}</div>
        <div class="clinic-info">
          Médecin : <b>${medecinName}</b><br>
          Spécialité : Ophtalmologie
        </div>
      </div>
      <div style="text-align:right;font-size:11px;color:#333">
        <div>Date : <b>${fmtDate(ordo.date)}</b></div>
        <div>Réf : <b>${ordo.id}</b></div>
      </div>
    </div>

    <div class="doc-title">Ordonnance${ordo.type==='lunettes'?' — Correction Optique':ordo.type==='bilan'?' — Bilan':''}</div>

    <div class="patient-box">
      <b>Patient :</b> ${patient.prenom} ${patient.nom} &nbsp;|&nbsp;
      <b>Âge :</b> ${age} ans &nbsp;|&nbsp;
      <b>Sexe :</b> ${patient.sexe==='F'?'Féminin':'Masculin'}<br>
      ${patient.ddn ? `<b>Né(e) le :</b> ${fmtDate(patient.ddn)} &nbsp;` : ''}
      ${patient.telephone ? `&nbsp;| <b>Tél :</b> ${patient.telephone}` : ''}
    </div>

    <div class="body-section">${body}</div>
    ${ordo.notes ? `<div class="notes">📝 ${ordo.notes}</div>` : ''}

    <div class="footer">
      <div>
        <div style="margin-bottom:6px;font-size:12px">Signature &amp; Cachet du médecin :</div>
        <div class="signature-box">${medecinName}</div>
      </div>
      <div>
        <div style="margin-bottom:6px;font-size:12px">Cachet :</div>
        <div class="stamp-box">Cachet<br>médecin</div>
      </div>
    </div>
  </div>
  </body></html>`);
  w.document.close();
  setTimeout(() => w.print(), 300);
}

// ─── PRINT PATIENT SUMMARY ─────────────────────────────────────────────────

function printPatientSummary(pid) {
  const patient = window._currentPatient;
  if (!patient) return;
  const age = new Date().getFullYear() - new Date(patient.ddn).getFullYear();
  const ivtList = window._currentIVT || [];
  const today = new Date().toISOString().slice(0,10);
  const nextRdv = (patient.rdv||[]).filter(r=>r.date>=today && r.statut!=='annulé').sort((a,b)=>a.date.localeCompare(b.date))[0];
  const ordos = (patient.ordonnances||[]).slice(0,3);
  const sortedHist = [...(patient.historique||[])].sort((a,b)=>b.date.localeCompare(a.date));
  const last3 = sortedHist.slice(0,3);
  const older = sortedHist.slice(3);

  const ivtSummary = ivtList.length
    ? `OD×${ivtList.filter(i=>i.oeil==='OD').length} OG×${ivtList.filter(i=>i.oeil==='OG').length} (dernier : ${ivtList[0]?.medicament} ${fmtDate(ivtList[0]?.date)})`
    : 'Aucune';

  const _consultRow = (h) => `
    <div style="margin-bottom:16px;padding:12px;border:1px solid #ddd;border-radius:6px">
      <div style="font-weight:700;font-size:13px;margin-bottom:6px">${fmtDate(h.date)} — ${h.motif||'—'} <span style="font-weight:400;color:#666;font-size:11px">(${h.medecin})</span></div>
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr><th style="background:#f5f5f5;padding:4px 8px;border:1px solid #ddd;text-align:left"></th><th style="background:#f5f5f5;padding:4px 8px;border:1px solid #ddd">OD (Droit)</th><th style="background:#f5f5f5;padding:4px 8px;border:1px solid #ddd">OG (Gauche)</th></tr></thead>
        <tbody>
          ${h.acuite_od?`<tr><td style="padding:4px 8px;border:1px solid #ddd">Acuité</td><td style="padding:4px 8px;border:1px solid #ddd">${h.acuite_od}</td><td style="padding:4px 8px;border:1px solid #ddd">${h.acuite_og||'—'}</td></tr>`:''}
          ${h.tension_od?`<tr><td style="padding:4px 8px;border:1px solid #ddd">Tonus (mmHg)</td><td style="padding:4px 8px;border:1px solid #ddd">${h.tension_od}</td><td style="padding:4px 8px;border:1px solid #ddd">${h.tension_og||'—'}</td></tr>`:''}
          ${h.refraction_od_sph?`<tr><td style="padding:4px 8px;border:1px solid #ddd">Sphère</td><td style="padding:4px 8px;border:1px solid #ddd">${h.refraction_od_sph}</td><td style="padding:4px 8px;border:1px solid #ddd">${h.refraction_og_sph||'—'}</td></tr>`:''}
          ${h.diagnostic?`<tr><td style="padding:4px 8px;border:1px solid #ddd;color:#555" colspan="3">Diagnostic : ${h.diagnostic}</td></tr>`:''}
          ${h.traitement?`<tr><td style="padding:4px 8px;border:1px solid #ddd;color:#555" colspan="3">Traitement : ${h.traitement}</td></tr>`:''}
        </tbody>
      </table>
    </div>`;

  const w = window.open('', '_blank', 'width=800,height=1050');
  w.document.write(`<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Résumé — ${patient.prenom} ${patient.nom}</title>
  <style>
    body{font-family:Arial,sans-serif;padding:30px 40px;color:#000;font-size:13px;max-width:800px;margin:0 auto}
    h1{font-size:20px;border-bottom:2px solid #000;padding-bottom:8px;margin-bottom:18px}
    h2{font-size:13px;text-transform:uppercase;letter-spacing:1px;color:#555;margin:22px 0 8px;border-left:3px solid #0e7a76;padding-left:8px}
    table.main{width:100%;border-collapse:collapse;margin:8px 0}
    table.main td,table.main th{border:1px solid #ccc;padding:6px 8px}
    table.main th{background:#f0f0f0;text-align:left;font-weight:600}
    .badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:11px;margin:2px;background:#eee}
    .badge-red{background:#fee2e2;color:#b91c1c}
    .badge-teal{background:#e0f2fe;color:#0369a1}
    .footer{margin-top:30px;font-size:11px;color:#888;border-top:1px solid #ddd;padding-top:10px}
    .no-print{display:flex;gap:10px;margin-bottom:24px}
    button{padding:8px 20px;border-radius:6px;border:1px solid #ccc;cursor:pointer;font-size:13px}
    button.primary{background:#0e7a76;color:#fff;border-color:#0e7a76}
    .older-consult{opacity:.8;border-color:#e5e5e5!important}
    @media print{.no-print{display:none!important}body{padding:15mm}}
  </style>
  </head><body>
  <div class="no-print">
    <button class="primary" onclick="window.print()">🖨 Imprimer</button>
    <button onclick="window.close()">✕ Fermer</button>
  </div>
  <h1>Résumé Clinique — ${patient.prenom} ${patient.nom}</h1>
  <table class="main">
    <tr><th>Date de naissance</th><td>${fmtDate(patient.ddn)} (${age} ans)</td><th>Sexe</th><td>${patient.sexe==='F'?'Féminin':'Masculin'}</td></tr>
    <tr><th>Téléphone</th><td>${patient.telephone||'—'}</td><th>Email</th><td>${patient.email||'—'}</td></tr>
    ${patient.date_chirurgie?`<tr><th>Chirurgie</th><td>${patient.type_chirurgie||'—'}</td><th>Date</th><td>${fmtDate(patient.date_chirurgie)}</td></tr>`:''}
  </table>

  <h2>Antécédents & Allergies</h2>
  <div>${patient.antecedents.map(a=>`<span class="badge badge-teal">${a}</span>`).join('')||'Aucun'}</div>
  <div style="margin-top:6px">${patient.allergies.map(a=>`<span class="badge badge-red">⚠ ${a}</span>`).join('')||'Aucune allergie connue'}</div>

  <h2>Dernières consultations (${last3.length})</h2>
  ${last3.map(h => _consultRow(h)).join('') || '<p style="color:#888">Aucune consultation</p>'}

  ${older.length ? `
  <h2>Consultations précédentes (${older.length})</h2>
  <div>
  ${older.map(h=>`<div class="older-consult" style="margin-bottom:12px;padding:10px;border:1px solid #e5e5e5;border-radius:6px;font-size:12px">
    <b>${fmtDate(h.date)}</b> — ${h.motif||'—'} · Diag: ${h.diagnostic||'—'} · Trait: ${h.traitement||'—'}
  </div>`).join('')}
  </div>` : ''}

  <h2>Injections IVT</h2>
  <p>${ivtSummary}</p>
  ${ivtList.length ? `<table class="main"><tr><th>#</th><th>Œil</th><th>Médicament</th><th>Dose</th><th>Date</th><th>Médecin</th></tr>
  ${ivtList.slice(0,10).map(i=>`<tr><td>${i.numero}</td><td>${i.oeil}</td><td>${i.medicament}</td><td>${i.dose}</td><td>${fmtDate(i.date)}</td><td>${i.medecin}</td></tr>`).join('')}
  ${ivtList.length>10?`<tr><td colspan="6" style="text-align:center;color:#888">…et ${ivtList.length-10} autres</td></tr>`:''}
  </table>` : ''}

  ${nextRdv ? `<h2>Prochain RDV</h2><p>${fmtDate(nextRdv.date)} à ${nextRdv.heure} — ${nextRdv.type} (${nextRdv.medecin})</p>` : ''}

  ${ordos.length ? `<h2>Dernières ordonnances</h2><ul>
  ${ordos.map(o=>`<li>${fmtDate(o.date)} — ${o.type} — ${o.medecin}</li>`).join('')}
  </ul>` : ''}

  <div class="footer">Document généré le ${new Date().toLocaleDateString('fr-FR', {weekday:'long',year:'numeric',month:'long',day:'numeric'})} — OphtalmoScan</div>
  </body></html>`);
  w.document.close();
}

// ─── IVT TAB ───────────────────────────────────────────────────────────────

function renderIVTTab(ivtList, patient, pid) {
  const countOD = ivtList.filter(i=>i.oeil==='OD').length;
  const countOG = ivtList.filter(i=>i.oeil==='OG').length;
  return `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <div style="display:flex;gap:16px">
        <div style="text-align:center;padding:12px 20px;background:var(--card);border:1px solid var(--border);border-radius:10px">
          <div style="font-size:24px;font-weight:700;color:var(--teal2)">${countOD}</div>
          <div style="font-size:11px;color:var(--text3)">Injections OD</div>
        </div>
        <div style="text-align:center;padding:12px 20px;background:var(--card);border:1px solid var(--border);border-radius:10px">
          <div style="font-size:24px;font-weight:700;color:var(--teal2)">${countOG}</div>
          <div style="font-size:11px;color:var(--text3)">Injections OG</div>
        </div>
        <div style="text-align:center;padding:12px 20px;background:var(--card);border:1px solid var(--border);border-radius:10px">
          <div style="font-size:24px;font-weight:700;color:var(--text2)">${ivtList.length}</div>
          <div style="font-size:11px;color:var(--text3)">Total</div>
        </div>
      </div>
      ${USER.role==='medecin' ? `<button class="btn btn-primary btn-sm" onclick="openAddIVT('${pid}')">+ Ajouter injection</button>` : ''}
    </div>
    ${ivtList.length >= 2 ? `
    <div class="card card-sm" style="margin-bottom:16px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--teal2);margin-bottom:8px">Chronologie des injections IVT</div>
      <canvas id="chart-ivt-${pid}" style="max-height:140px"></canvas>
    </div>` : ''}
    ${ivtList.length ? `
    <table class="exam-table" style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="border-bottom:1px solid var(--border)">
          <th style="text-align:left;padding:8px;color:var(--text3);font-weight:600">#</th>
          <th style="text-align:left;padding:8px;color:var(--text3);font-weight:600">Œil</th>
          <th style="text-align:left;padding:8px;color:var(--text3);font-weight:600">Médicament</th>
          <th style="text-align:left;padding:8px;color:var(--text3);font-weight:600">Dose</th>
          <th style="text-align:left;padding:8px;color:var(--text3);font-weight:600">Date</th>
          <th style="text-align:left;padding:8px;color:var(--text3);font-weight:600">Médecin</th>
          ${USER.role==='medecin'?'<th></th>':''}
        </tr>
      </thead>
      <tbody>
        ${ivtList.map(i=>`
        <tr style="border-bottom:1px solid var(--border);${i.oeil==='OD'?'':'background:var(--bg2)'}">
          <td style="padding:8px;font-weight:700;color:var(--teal2)">${i.numero}</td>
          <td style="padding:8px"><span class="badge ${i.oeil==='OD'?'badge-teal':'badge-amber'}">${i.oeil}</span></td>
          <td style="padding:8px">${i.medicament}</td>
          <td style="padding:8px;color:var(--text3)">${i.dose}</td>
          <td style="padding:8px">${fmtDate(i.date)}</td>
          <td style="padding:8px;color:var(--text3)">${i.medecin}</td>
          ${USER.role==='medecin'?`<td style="padding:8px"><button class="btn btn-ghost btn-sm" style="font-size:10px;opacity:.6" onclick="deleteIVT('${pid}','${i.id}')">🗑</button></td>`:''}
        </tr>`).join('')}
      </tbody>
    </table>` : `<div style="color:var(--text3);text-align:center;padding:40px">Aucune injection IVT enregistrée</div>`}
  `;
}

async function openAddIVT(pid) {
  const medicaments = ['Ranibizumab','Aflibercept','Bevacizumab','Faricimab','Brolucizumab'];
  showModal('Ajouter une injection IVT', `
    <div class="form-group">
      <label class="lbl">Œil</label>
      <select id="ivt-oeil" class="input">
        <option value="OG">OG (Gauche)</option>
        <option value="OD">OD (Droit)</option>
      </select>
    </div>
    <div class="form-group">
      <label class="lbl">Médicament</label>
      <select id="ivt-med" class="input" onchange="
        const autres = document.getElementById('ivt-med-autre-wrap');
        autres.style.display = this.value === '__autre__' ? 'block' : 'none';
      ">
        ${medicaments.map(m=>`<option value="${m}">${m}</option>`).join('')}
        <option value="__autre__">Autre…</option>
      </select>
    </div>
    <div class="form-group" id="ivt-med-autre-wrap" style="display:none">
      <label class="lbl">Précisez le médicament</label>
      <input id="ivt-med-autre" class="input" placeholder="Ex : Conbercept, Pegaptanib…">
    </div>
    <div class="form-group">
      <label class="lbl">Dose</label>
      <input id="ivt-dose" class="input" value="0.5mg">
    </div>
    <div class="form-group">
      <label class="lbl">Date</label>
      <input type="date" id="ivt-date" class="input" value="${new Date().toISOString().slice(0,10)}">
    </div>
    <div class="form-group">
      <label class="lbl">Notes</label>
      <input id="ivt-notes" class="input" placeholder="Observations (optionnel)">
    </div>
  `, async () => {
    const medSelect = document.getElementById('ivt-med').value;
    const medAutre  = document.getElementById('ivt-med-autre').value.trim();
    if (medSelect === '__autre__' && !medAutre) {
      alert('Veuillez préciser le nom du médicament.'); return false;
    }
    const data = {
      oeil:       document.getElementById('ivt-oeil').value,
      medicament: medSelect === '__autre__' ? medAutre : medSelect,
      dose:       document.getElementById('ivt-dose').value,
      date:       document.getElementById('ivt-date').value,
      notes:      document.getElementById('ivt-notes').value
    };
    const res = await api(`/api/patients/${pid}/ivt`, 'POST', data);
    if (res.ok) { closeModal(); loadPatient(pid); }
    else alert(res.error || 'Erreur');
  });
}

async function deleteIVT(pid, iid) {
  if (!confirm('Supprimer cette injection ?')) return;
  await api(`/api/patients/${pid}/ivt/${iid}`, 'DELETE');
  loadPatient(pid);
}

