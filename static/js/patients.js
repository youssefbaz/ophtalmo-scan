// ─── PATIENT PROFILE (MÉDECIN) ────────────────────────────────────────────────
function _renderConsultItem(h, pid) {
  return `
  <div class="tl-item">
    <div style="display:flex;justify-content:space-between;align-items:flex-start">
      <div>
        <div class="tl-date">${fmtDateLong(h.date)} — ${h.medecin}</div>
        <div class="tl-title">${h.motif}</div>
      </div>
      <div style="display:flex;gap:6px">
        <button class="btn btn-ghost btn-sm" style="font-size:11px" onclick="openEditConsultation('${pid}','${h.id}')">✏</button>
        <button class="btn btn-ghost btn-sm" style="font-size:11px;opacity:.6" onclick="deleteConsultation('${pid}','${h.id}')">🗑</button>
      </div>
    </div>
    ${(h.acuite_od||h.tension_od||h.refraction_od_sph) ? `
    <table class="exam-table">
      <thead><tr><th></th><th>OD (Droit)</th><th>OG (Gauche)</th></tr></thead>
      <tbody>
        ${h.acuite_od ? `<tr><td>Acuité visuelle</td><td>${h.acuite_od}</td><td>${h.acuite_og||'—'}</td></tr>` : ''}
        ${h.tension_od ? `<tr><td>Tonus (mmHg)</td><td>${h.tension_od}</td><td>${h.tension_og||'—'}</td></tr>` : ''}
        ${h.refraction_od_sph ? `<tr><td>Sphère</td><td>${h.refraction_od_sph}</td><td>${h.refraction_og_sph||'—'}</td></tr>` : ''}
        ${h.refraction_od_cyl ? `<tr><td>Cylindre</td><td>${h.refraction_od_cyl}</td><td>${h.refraction_og_cyl||'—'}</td></tr>` : ''}
        ${h.refraction_od_axe ? `<tr><td>Axe (°)</td><td>${h.refraction_od_axe}</td><td>${h.refraction_og_axe||'—'}</td></tr>` : ''}
      </tbody>
    </table>` : ''}
    ${h.segment_ant ? `<div class="tl-field" style="margin-top:8px"><div class="tl-field-label">Segment antérieur</div><div class="tl-field-value">${h.segment_ant}</div></div>` : ''}
    <div class="tl-grid" style="margin-top:8px">
      ${h.diagnostic ? `<div class="tl-field"><div class="tl-field-label">Diagnostic</div><div class="tl-field-value">${h.diagnostic}</div></div>` : ''}
      ${h.traitement ? `<div class="tl-field"><div class="tl-field-label">Traitement</div><div class="tl-field-value">${h.traitement}</div></div>` : ''}
    </div>
    ${h.notes?`<div class="tl-note">📝 ${h.notes}</div>`:''}
  </div>`;
}

function _renderConsultTimeline(historique, pid, showAll) {
  if (!historique || !historique.length) {
    return '<div style="color:var(--text3);text-align:center;padding:40px">Aucune consultation enregistrée</div>';
  }
  const sorted = [...historique].sort((a,b) => b.date.localeCompare(a.date));
  const VISIBLE = 3;
  const visible = sorted.slice(0, showAll ? sorted.length : VISIBLE);
  const hidden  = sorted.slice(VISIBLE);
  let html = visible.map(h => _renderConsultItem(h, pid)).join('');
  if (!showAll && hidden.length > 0) {
    html += `
    <div id="consultHiddenSection-${pid}" style="display:none">
      ${hidden.map(h => _renderConsultItem(h, pid)).join('')}
    </div>
    <div style="text-align:center;margin:14px 0">
      <button class="btn btn-ghost btn-sm" id="consultShowAllBtn-${pid}"
        onclick="document.getElementById('consultHiddenSection-${pid}').style.display='';this.style.display='none';document.getElementById('consultCollapseBtn-${pid}').style.display=''">
        ▼ Voir les ${hidden.length} consultation(s) précédente(s)
      </button>
      <button class="btn btn-ghost btn-sm" id="consultCollapseBtn-${pid}" style="display:none"
        onclick="document.getElementById('consultHiddenSection-${pid}').style.display='none';this.style.display='none';document.getElementById('consultShowAllBtn-${pid}').style.display=''">
        ▲ Réduire
      </button>
    </div>`;
  }
  return html;
}

async function renderPatientProfile(c, pid) {
  const [patient, docs, questions, suivi, ivtData, accountInfo] = await Promise.all([
    api(`/api/patients/${pid}`),
    api(`/api/patients/${pid}/documents`),
    api(`/api/patients/${pid}/questions`),
    api(`/api/patients/${pid}/suivi`),
    api(`/api/patients/${pid}/ivt`),
    USER.role === 'medecin' ? api(`/api/patients/${pid}/has-account`) : Promise.resolve({has_account: false})
  ]);
  window._currentPatient = patient;
  window._currentIVT = ivtData || [];

  const age = new Date().getFullYear() - new Date(patient.ddn).getFullYear();
  const lastConsult = patient.historique?.[0] || null;
  const today = new Date().toISOString().slice(0,10);
  const nextRdv = (patient.rdv || [])
    .filter(r => r.date >= today && r.statut !== 'annulé')
    .sort((a,b) => a.date.localeCompare(b.date))[0] || null;
  const pendingQ = questions.filter(q => q.statut === 'en_attente').length;
  const medecinName = MEDECINS.find(m => m.id === patient.medecin_id)?.nom || '';
  const totalMedia = (patient.imagerie?.length || 0) + (docs?.length || 0);

  const iopColor = v => {
    const n = parseFloat(v);
    if (!v || isNaN(n)) return 'var(--text2)';
    if (n > 21) return 'var(--red)';
    if (n > 18) return 'var(--amber)';
    return 'var(--green)';
  };

  c.innerHTML = `
    <!-- ── HEADER V2 ── -->
    <div class="patient-header-v2">

      <!-- LEFT: Identité -->
      <div class="ph-identity">
        <div class="patient-avatar-lg ${patient.sexe==='F'?'female':'male'}">${(patient.prenom||'?')[0]}${(patient.nom||'?')[0]}</div>
        <div class="ph-id-info">
          <div class="patient-fullname">${patient.prenom} ${patient.nom}</div>
          <div class="ph-meta-row">
            <span class="ph-meta-chip">🎂 ${age} ans · ${fmtDate(patient.ddn)}</span>
            <span class="ph-meta-chip">⚧ ${patient.sexe==='F'?'Féminin':'Masculin'}</span>
            ${medecinName ? `<span class="ph-meta-chip">🩺 ${medecinName}</span>` : ''}
            ${patient.date_chirurgie ? `
              <span class="ph-meta-chip amber" style="cursor:pointer" onclick="editChirurgie('${pid}','${patient.date_chirurgie}','${escJ(patient.type_chirurgie||'')}')">✂ Post-op ${fmtDate(patient.date_chirurgie)} ✏</span>
              <span class="ph-meta-chip" style="cursor:pointer;border-color:rgba(239,68,68,.4);color:var(--red)" onclick="deleteChirurgie('${pid}')">🗑</span>
            ` : ''}
          </div>
          <div class="ph-contact-row">
            <span class="ph-contact-item">📱 ${patient.telephone || '—'}</span>
            <span class="ph-contact-item">✉ ${patient.email || '—'}</span>
          </div>
          <div class="badges" style="margin-top:10px">
            ${patient.allergies.map(a=>`<span class="badge badge-red">⚠ ${a}</span>`).join('')}
            ${patient.antecedents.map(a=>`<span class="badge badge-teal">${a}</span>`).join('')}
          </div>
        </div>
      </div>

      <!-- MIDDLE: Snapshot clinique -->
      <div class="ph-snapshot">
        <div class="ph-snapshot-title">
          Dernière consultation${lastConsult ? ' · ' + fmtDate(lastConsult.date) : ''}
        </div>
        <div class="ph-snapshot-grid">
          <div class="ph-snap-card">
            <div class="ph-snap-label">Acuité OD</div>
            <div class="ph-snap-value">${lastConsult?.acuite_od || '—'}</div>
          </div>
          <div class="ph-snap-card">
            <div class="ph-snap-label">Acuité OG</div>
            <div class="ph-snap-value">${lastConsult?.acuite_og || '—'}</div>
          </div>
          <div class="ph-snap-card">
            <div class="ph-snap-label">Tonus OD</div>
            <div class="ph-snap-value" style="color:${iopColor(lastConsult?.tension_od)}">${lastConsult?.tension_od ? lastConsult.tension_od + ' mmHg' : '—'}</div>
          </div>
          <div class="ph-snap-card">
            <div class="ph-snap-label">Tonus OG</div>
            <div class="ph-snap-value" style="color:${iopColor(lastConsult?.tension_og)}">${lastConsult?.tension_og ? lastConsult.tension_og + ' mmHg' : '—'}</div>
          </div>
        </div>
        <div class="ph-snap-footer">
          <span style="font-size:11px;color:${nextRdv?'var(--teal2)':'var(--text3)'}">
            📅 ${nextRdv ? fmtDate(nextRdv.date) + ' · ' + nextRdv.heure : 'Aucun RDV à venir'}
          </span>
          <span style="font-size:11px;color:var(--text3)">${patient.historique.length} consul.</span>
        </div>
        ${(() => {
          const ivtList = ivtData || [];
          if (!ivtList.length) return '';
          const countOD = ivtList.filter(i=>i.oeil==='OD').length;
          const countOG = ivtList.filter(i=>i.oeil==='OG').length;
          const last = ivtList[0];
          return `<div style="margin-top:10px;padding:8px 10px;background:rgba(14,165,160,.08);border:1px solid rgba(14,165,160,.2);border-radius:8px;font-size:11px">
            <div style="font-weight:700;color:var(--teal2);margin-bottom:4px">💉 Injections IVT</div>
            <div style="display:flex;gap:12px;color:var(--text2)">
              ${countOD?`<span>OD × ${countOD}</span>`:''}
              ${countOG?`<span>OG × ${countOG}</span>`:''}
              ${last?`<span style="color:var(--text3)">↳ ${last.medicament} ${fmtDate(last.date)}</span>`:''}
            </div>
          </div>`;
        })()}
      </div>

      <!-- RIGHT: Actions -->
      <div class="ph-actions">
        <button class="btn btn-primary btn-sm" onclick="openAddConsultation('${pid}')">+ Consultation</button>
        <button class="btn btn-ghost btn-sm" onclick="openAddRdv('${pid}')">📅 Rendez-vous</button>
        <button class="btn btn-ghost btn-sm" onclick="openMessageModal('${pid}','','')">✉ Message</button>
        <button class="btn btn-ghost btn-sm" onclick="startAiContext('${pid}')">🤖 Assistant IA</button>
        <button class="btn btn-ghost btn-sm" onclick="generateConsultationSummary('${pid}')" title="Générer compte-rendu IA">📝 Compte-rendu</button>
        <div class="ph-actions-row" style="margin-top:2px">
          <button class="btn btn-ghost btn-sm" onclick="openEditPatient('${pid}')" title="Modifier">✏ Modifier</button>
          <button class="btn btn-ghost btn-sm" onclick="openAssignerMedecin('${pid}')" title="Médecin">👨‍⚕️</button>
          <button class="btn btn-ghost btn-sm" onclick="downloadPatientPDF('${pid}')" title="Télécharger fiche PDF">📄 PDF</button>
          <button class="btn btn-export btn-sm" onclick="exportPatientAnon('${pid}')" title="Exporter JSON">⬇</button>
          <button class="btn btn-sm" style="background:var(--red-dim);border:1px solid rgba(239,68,68,0.3);color:var(--red)" onclick="deletePatient('${pid}','${patient.prenom} ${patient.nom}')" title="Supprimer">🗑</button>
        </div>
        ${!patient.date_chirurgie ? `<button class="btn btn-ghost btn-sm" onclick="setDateChirurgie('${pid}')">✂ Déf. chirurgie</button>` : `<button class="btn btn-ghost btn-sm" onclick="editChirurgie('${pid}','${patient.date_chirurgie}','${escJ(patient.type_chirurgie||'')}')">✂ Modifier chirurgie</button>`}
        <div class="ph-actions-row" style="margin-top:2px">
          <button class="btn btn-ghost btn-sm" onclick="printPatientSummary('${pid}')">🖨 Résumé</button>
          <button class="btn btn-ghost btn-sm" onclick="copyPatientPortalLink('${escJ(accountInfo.username||'')}','${escJ(patient.prenom)} ${escJ(patient.nom)}')" title="Copier lien portail patient">🔗 Lien portail</button>
          ${accountInfo.has_account
            ? `<button class="btn btn-ghost btn-sm" style="opacity:.6;cursor:default" disabled title="Compte: ${accountInfo.username}">👤 ${accountInfo.username}</button>`
            : `<button class="btn btn-ghost btn-sm" onclick="openCreateAccount('${pid}','${escJ(patient.prenom)} ${escJ(patient.nom)}','${escJ(patient.email||'')}')">👤 Créer compte</button>
               ${patient.email ? `<button class="btn btn-ghost btn-sm" onclick="sendPatientInvite('${pid}')" title="Envoyer lien d'inscription par email">📧 Lien</button>` : ''}`
          }
        </div>
      </div>
    </div>

    <!-- ── TABS (5) ── -->
    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab('hist','${pid}',this)">
        📋 Consultations<span class="tab-count">${patient.historique.length}</span>
      </button>
      <button class="tab-btn" onclick="switchTab('ordo','${pid}',this)">
        📄 Ordonnances${(patient.ordonnances||[]).length ? `<span class="tab-count">${patient.ordonnances.length}</span>` : ''}
      </button>
      <button class="tab-btn" onclick="switchTab('media','${pid}',this)">
        🔬 Documents${totalMedia ? `<span class="tab-count">${totalMedia}</span>` : ''}
      </button>
      <button class="tab-btn" onclick="switchTab('rdvp','${pid}',this)">
        📅 RDV${patient.rdv?.length ? `<span class="tab-count">${patient.rdv.length}</span>` : ''}
      </button>
      <button class="tab-btn" onclick="switchTab('qst','${pid}',this)">
        💬 Questions${pendingQ ? `<span class="tab-count tab-count-amber">${pendingQ}</span>` : ''}
      </button>
      <button class="tab-btn" onclick="switchTab('suivi','${pid}',this)">
        🗓 Suivi Post-Op${(() => {
          const today = new Date().toISOString().slice(0,10);
          const overdue = (suivi||[]).filter(s => s.statut==='a_faire' && s.date_prevue < today).length;
          const soon    = (suivi||[]).filter(s => s.statut==='a_faire' && s.date_prevue >= today).length;
          if (overdue) return `<span class="tab-count" style="background:var(--red)">${overdue}</span>`;
          if (soon)    return `<span class="tab-count tab-count-amber">${soon}</span>`;
          return '';
        })()}
      </button>
      <button class="tab-btn" onclick="switchTab('ivt','${pid}',this)">
        💉 IVT${(ivtData||[]).length ? `<span class="tab-count">${(ivtData||[]).length}</span>` : ''}
      </button>
    </div>

    <!-- ── TAB: Consultations (+ Post-Op intégré) ── -->
    <div class="tab-content active" id="tab-hist">
      ${patient.date_chirurgie ? `
      <div class="postop-banner" onclick="togglePostOp()">
        <div style="display:flex;align-items:center;gap:12px">
          <div style="width:34px;height:34px;border-radius:10px;background:var(--teal-dim);border:1px solid rgba(14,165,160,0.3);display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0">✂</div>
          <div>
            <div style="font-size:12px;font-weight:600;color:var(--teal2)">${patient.type_chirurgie || 'Chirurgie ophtalmologique'}</div>
            <div style="font-size:11px;color:var(--text3)">Suivi post-opératoire · Opéré le ${fmtDate(patient.date_chirurgie)}</div>
          </div>
        </div>
        <span id="postopToggleLabel" style="font-size:11px;color:var(--text3);white-space:nowrap">Afficher le suivi ▼</span>
      </div>
      <div id="postop-section" style="display:none;margin-bottom:24px;padding:18px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius)">
        ${renderPostOpTimeline(patient)}
      </div>` : ''}

      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <div style="font-size:13px;color:var(--text2)">${patient.historique.length} consultation(s) enregistrée(s)</div>
        <button class="btn btn-primary btn-sm" onclick="openAddConsultation('${pid}')">+ Nouvelle consultation</button>
      </div>
      ${patient.historique.length >= 2 ? `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px">
        <div class="card card-sm">
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--teal2);margin-bottom:8px">Évolution Tonus (mmHg)</div>
          <canvas id="chart-iop-${pid}" style="max-height:160px"></canvas>
        </div>
        <div class="card card-sm">
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--teal2);margin-bottom:8px">Évolution Acuité Visuelle</div>
          <canvas id="chart-av-${pid}" style="max-height:160px"></canvas>
        </div>
      </div>` : ''}
      <div class="timeline" id="consultTimeline-${pid}">
        ${_renderConsultTimeline(patient.historique, pid, false)}
      </div>
    </div>

    <!-- ── TAB: Ordonnances ── -->
    <div class="tab-content" id="tab-ordo">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
        <div style="font-size:13px;color:var(--text2)">${(patient.ordonnances||[]).length} ordonnance(s)</div>
        <button class="btn btn-primary btn-sm" onclick="openAddOrdonnance('${pid}')">+ Nouvelle ordonnance</button>
      </div>
      ${renderOrdonnancesList(patient.ordonnances||[], pid)}
    </div>

    <!-- ── TAB: Documents & Imagerie (fusionnés) ── -->
    <div class="tab-content" id="tab-media">
      <div class="subtabs">
        <button class="subtab-btn active" onclick="switchSubtab('stab-img',this)">
          🔬 Imagerie médicale
          ${patient.imagerie?.length ? `<span class="tab-count">${patient.imagerie.length}</span>` : ''}
        </button>
        <button class="subtab-btn" onclick="switchSubtab('stab-docs',this)">
          📎 Documents patient
          ${docs?.length ? `<span class="tab-count">${docs.length}</span>` : ''}
        </button>
      </div>

      <div id="stab-img" class="subtab-content active">
        <div style="margin-bottom:14px;display:flex;justify-content:space-between;align-items:center">
          <div style="font-size:13px;color:var(--text2)">OCT, rétinographies, angiographies…</div>
          <button class="btn btn-primary btn-sm" onclick="openUploadImagerie('${pid}')">+ Ajouter imagerie</button>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px">
          ${patient.imagerie.map(img=>_imgCard(img, pid, patient)).join('')
            || '<div style="color:var(--text3);text-align:center;padding:40px">Aucune imagerie enregistrée</div>'}
        </div>

        ${(() => {
          const patImgs = (docs||[]).filter(d => d.has_image);
          if (!patImgs.length) return '';
          return `
            <div style="margin-top:24px">
              <div style="font-size:12px;font-weight:700;color:var(--amber);text-transform:uppercase;letter-spacing:1px;margin-bottom:12px">
                📤 Radios & scanners transmis par le patient (${patImgs.length})
              </div>
              <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px">
                ${patImgs.map(d=>_imgCard(d, pid, patient, true)).join('')}
              </div>
            </div>`;
        })()}
      </div>

      <div id="stab-docs" class="subtab-content">
        <div style="font-size:13px;color:var(--text2);margin-bottom:14px">Documents transmis par le patient</div>
        <div id="docs-grid-${pid}">${renderDocsGrid((docs||[]).filter(d=>!d.has_image), pid)}</div>
        <div style="margin-top:24px">
          <button class="btn btn-ghost btn-sm" onclick="toggleDeletedDocs('${pid}',this)" style="opacity:.6">
            🗂 Voir l'historique des documents supprimés
          </button>
          <div id="deleted-docs-${pid}" style="display:none;margin-top:12px"></div>
        </div>
      </div>
    </div>

    <!-- ── TAB: RDV ── -->
    <div class="tab-content" id="tab-rdvp">
      <div style="margin-bottom:14px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
        <button class="btn btn-primary btn-sm" onclick="openAddRdv('${pid}')">+ Nouveau RDV</button>
        ${USER.role==='medecin' ? `<button class="btn btn-ghost btn-sm" onclick="triggerEmailReminders()" title="Envoyer rappels email pour demain">📧 Rappels email</button>` : ''}
      </div>
      ${patient.rdv.sort((a,b)=>b.date.localeCompare(a.date)).map(r=>{
        const isPast = r.date < new Date().toISOString().slice(0,10);
        return `
        <div class="rdv-card ${r.urgent?'urgent':''}" style="${isPast?'opacity:.65':''}">
          <div class="rdv-date-block ${r.urgent?'urgent':''}">
            <div class="rdv-day ${r.urgent?'urgent':''}">${new Date(r.date).getDate()}</div>
            <div class="rdv-month">${new Date(r.date).toLocaleString('fr-FR',{month:'short'})} ${new Date(r.date).getFullYear()}</div>
          </div>
          <div class="rdv-info" style="flex:1">
            <div class="rdv-type">${r.urgent?'🚨 ':''}${_normRdvType(r.type)}</div>
            <div class="rdv-meta">⏰ ${r.heure} · ${r.medecin}</div>
            <div id="rdv-detail-${r.id}" style="display:none;margin-top:8px;padding:10px;background:var(--bg2);border-radius:8px;font-size:12px;color:var(--text2)">
              <div><strong>Date :</strong> ${fmtDateLong(r.date)}</div>
              <div><strong>Heure :</strong> ${r.heure}</div>
              <div><strong>Type :</strong> ${_normRdvType(r.type)}</div>
              <div><strong>Médecin :</strong> ${r.medecin}</div>
              <div><strong>Statut :</strong> ${r.statut}</div>
              ${r.notes?`<div><strong>Notes :</strong> ${r.notes}</div>`:''}
              ${r.urgent?`<div style="color:var(--red);margin-top:4px">⚠ RDV urgent</div>`:''}
              ${r.demande_par?`<div><strong>Demandé par :</strong> ${r.demande_par}</div>`:''}
            </div>
          </div>
          <div style="display:flex;flex-direction:column;gap:5px;align-items:flex-end">
            <span class="badge ${r.statut==='confirmé'?'badge-teal':r.statut==='en_attente'?'badge-amber':'badge-red'}">${r.statut}</span>
            <button class="btn btn-ghost btn-sm" style="font-size:10px" onclick="toggleRdvDetail('${r.id}')">+ infos</button>
            ${r.statut==='en_attente'&&USER.role==='medecin'?`<button class="btn btn-primary btn-sm" onclick="validerRdv('${r.id}','confirmé')">Confirmer</button>`:''}
            ${USER.role==='medecin'?`<button class="btn btn-ghost btn-sm" onclick="openEditRdvModal('${r.id}')">✏</button>`:''}
            ${USER.role==='medecin'?`<button class="btn btn-red btn-sm" onclick="deleteRdv('${r.id}')">🗑</button>`:''}
          </div>
        </div>`; }).join('') || '<div style="color:var(--text3);text-align:center;padding:40px">Aucun rendez-vous</div>'}
    </div>

    <!-- ── TAB: Questions ── -->
    <div class="tab-content" id="tab-qst">
      ${renderQuestionsPanel(questions, pid)}
    </div>

    <!-- ── TAB: Suivi Post-Op ── -->
    <div class="tab-content" id="tab-suivi">
      ${renderSuiviTab(suivi, patient, pid)}
    </div>

    <!-- ── TAB: IVT ── -->
    <div class="tab-content" id="tab-ivt">
      ${renderIVTTab(ivtData||[], patient, pid)}
    </div>`;

  if (patient.historique.length >= 2) {
    setTimeout(() => renderEvolutionCharts(patient, pid), 50);
  }
  if ((ivtData||[]).length >= 2) {
    setTimeout(() => renderIVTChart(ivtData, pid), 80);
  }
  setTimeout(_applyPendingTab, 100);
}

function togglePostOp() {
  const section = document.getElementById('postop-section');
  const label   = document.getElementById('postopToggleLabel');
  if (!section) return;
  const open = section.style.display !== 'none';
  section.style.display = open ? 'none' : 'block';
  label.textContent = open ? 'Afficher le suivi ▼' : 'Masquer le suivi ▲';
}

function switchSubtab(targetId, btn) {
  const parent = btn.closest('.tab-content');
  parent.querySelectorAll('.subtab-btn').forEach(b => b.classList.remove('active'));
  parent.querySelectorAll('.subtab-content').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  const el = document.getElementById(targetId);
  if (el) el.classList.add('active');
}

function openUploadImagerie(pid) {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'image/*,application/pdf,.pdf,.dcm,application/dicom';
  input.onchange = () => {
    const file = input.files[0]; if (!file) return;
    _showUploadPreviewModal(pid, file);
  };
  input.click();
}

function _showUploadPreviewModal(pid, file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    const dataUrl = e.target.result;
    const imgSrc  = dataUrl;
    showModal('📎 Téléverser une imagerie', `
      <div style="text-align:center;margin-bottom:16px">
        <img src="${imgSrc}" alt="Aperçu" style="max-width:100%;max-height:280px;border-radius:8px;border:2px solid var(--teal);object-fit:contain">
        <div style="font-size:11px;color:var(--text3);margin-top:6px">${escH(file.name)} — ${(file.size/1024).toFixed(0)} Ko</div>
      </div>
      <div class="form-group">
        <label class="form-label">Type d'imagerie</label>
        <select class="form-input" id="uploadTypeSelect">
          ${['OCT Macula','OCT RNFL','Fond d\'œil','Champ visuel','Topographie cornéenne','Biométrie','Rétinographie','Angiographie','Autre']
            .map(t=>`<option>${t}</option>`).join('')}
        </select>
      </div>
      <div class="form-group">
        <label class="form-label">Type personnalisé (facultatif)</label>
        <input class="form-input" id="uploadTypeCustom" placeholder="Saisir un type…">
      </div>
      <div id="uploadProgress" style="display:none;margin-top:10px">
        <div style="font-size:12px;color:var(--text2);margin-bottom:4px" id="uploadProgressLabel">Envoi en cours…</div>
        <div style="height:8px;background:var(--bg2);border-radius:4px;overflow:hidden">
          <div id="uploadProgressBar" style="height:100%;background:var(--teal);width:0%;transition:width .2s"></div>
        </div>
      </div>
    `, async () => {
      const custom = document.getElementById('uploadTypeCustom')?.value.trim();
      const type   = custom || document.getElementById('uploadTypeSelect')?.value || 'Imagerie';
      const prog   = document.getElementById('uploadProgress');
      const bar    = document.getElementById('uploadProgressBar');
      const lbl    = document.getElementById('uploadProgressLabel');
      if (prog) prog.style.display = '';

      // XHR for progress tracking — multipart so DICOM/large OCT files don't
      // pay the ~33 % base64 inflation tax.
      await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', `/api/patients/${pid}/upload`);
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        xhr.withCredentials = true;
        xhr.timeout = 300000;
        xhr.upload.onprogress = (ev) => {
          if (ev.lengthComputable && bar && lbl) {
            const pct = Math.round(ev.loaded / ev.total * 100);
            bar.style.width = pct + '%';
            lbl.textContent = `Envoi… ${pct}%`;
          }
        };
        xhr.onload = () => {
          try {
            const res = JSON.parse(xhr.responseText);
            if (res.ok) { closeModal(); loadPatient(pid); resolve(); }
            else { showToast(res.error || 'Erreur upload', 'error'); reject(); }
          } catch(ex) { showToast('Erreur upload', 'error'); reject(); }
        };
        xhr.onerror   = () => { showToast('Erreur réseau', 'error'); reject(); };
        xhr.ontimeout = () => { showToast("Envoi trop long — réessayez.", 'error'); reject(); };
        const fd = new FormData();
        fd.append('file', file, file.name);
        fd.append('type', type);
        fd.append('description', file.name);
        fd.append('source', 'imagerie');
        xhr.send(fd);
      });
    });
  };
  reader.readAsDataURL(file);
}

function _imgCard(img, pid, patient, isPatientDoc = false) {
  const patName    = escJ(patient.prenom + ' ' + patient.nom);
  const antecedents = escJ(patient.antecedents.join(', '));
  const imgNotes   = escJ(img.notes || img.description || '');
  const imgType    = escJ(img.type);
  const hasImg     = img.has_image;
  const analyzed   = img.analyse_ia;

  return `
    <div class="doc-card" style="${isPatientDoc ? 'border-color:rgba(245,158,11,.3)' : ''}"
         onclick="openImageViewer('${img.id}','${pid}','${imgType}','${imgNotes}','${patName}','${antecedents}')">
      <div class="doc-preview" style="position:relative;background:var(--bg2);min-height:90px;display:flex;align-items:center;justify-content:center">
        <div style="font-size:32px">${hasImg ? '🖼️' : '🔬'}</div>
        ${isPatientDoc ? `<span style="position:absolute;top:6px;right:6px;background:var(--amber);color:#000;font-size:9px;font-weight:700;padding:2px 5px;border-radius:4px">PATIENT</span>` : ''}
        ${analyzed    ? `<span style="position:absolute;bottom:6px;right:6px;background:var(--teal);color:#fff;font-size:9px;padding:2px 5px;border-radius:4px">✓ IA</span>` : ''}
        ${img.analysis_status==='failed_temp' ? `<span style="position:absolute;bottom:6px;left:6px;background:var(--amber,#f59e0b);color:#000;font-size:9px;padding:2px 5px;border-radius:4px">⚠ Réessayer</span>` : ''}
        ${img.analysis_status==='failed_perm' ? `<span style="position:absolute;bottom:6px;left:6px;background:var(--danger,#ef4444);color:#fff;font-size:9px;padding:2px 5px;border-radius:4px">⚠ Clé API</span>` : ''}
      </div>
      <div class="doc-info">
        <div class="doc-type">${img.type}</div>
        <div class="doc-date">${fmtDate(img.date)}</div>
        ${img.notes ? `<div class="doc-uploader">${img.notes}</div>` : ''}
        <div style="display:flex;gap:6px;margin-top:8px">
          <button class="btn btn-ghost btn-sm" style="flex:1;justify-content:center;color:var(--red)"
            onclick="event.stopPropagation();softDeleteDoc('${pid}','${img.id}','${imgType}')"
            title="Supprimer (conservé en historique)">🗑 Supprimer</button>
        </div>
      </div>
    </div>`;
}

function renderDocsGrid(docs, pid) {
  if (!docs.length) return '<div style="color:var(--text3);text-align:center;padding:30px">Aucun document uploadé par le patient</div>';
  return `<div style="display:flex;flex-direction:column;gap:10px">
    ${docs.map(d => {
      const isPdf = (d.description||'').toLowerCase().endsWith('.pdf');
      const icon  = isPdf ? '📄' : '🖼';
      const isValidated = d.valide;
      return `
      <div class="doc-card" id="doc-row-${d.id}" style="display:flex;align-items:center;gap:12px;padding:12px 14px">
        <div style="font-size:28px;flex-shrink:0;cursor:pointer" onclick="viewDocImage('${pid}','${d.id}','${escJ(d.type)}')">${icon}</div>
        <div style="flex:1;min-width:0">
          <div style="font-weight:600;font-size:13px">${escH(d.type)}</div>
          <div style="font-size:11px;color:var(--text2);margin-top:1px">${fmtDate(d.date)} · ${escH(d.description||'')}</div>
          <div style="margin-top:3px">
            ${isValidated
              ? `<span style="font-size:11px;color:var(--teal2)">✓ Validé</span>`
              : `<span style="font-size:11px;color:var(--amber)">⏳ Non validé</span>`}
            ${d.analyse_ia ? `<span style="font-size:11px;color:var(--teal2);margin-left:8px">· IA</span>` : ''}
          </div>
        </div>
        <div style="display:flex;gap:6px;flex-shrink:0">
          <button class="btn btn-ghost btn-sm" title="Voir" onclick="event.stopPropagation();viewDocImage('${pid}','${d.id}','${escJ(d.type)}')">👁</button>
          <button class="btn btn-primary btn-sm" title="Analyse IA" onclick="event.stopPropagation();analyzeDocAI('${pid}','${d.id}','${escJ(d.type)}')">🤖</button>
          ${!isValidated ? `<button class="btn btn-ghost btn-sm" id="val-btn-${d.id}" title="Valider" style="color:var(--teal2)" onclick="event.stopPropagation();validateDoc('${pid}','${d.id}')">✓ Valider</button>` : ''}
          <button class="btn btn-ghost btn-sm" style="color:var(--red)" title="Supprimer" onclick="event.stopPropagation();softDeleteDoc('${pid}','${d.id}','${escJ(d.type)}')">🗑</button>
        </div>
      </div>`
    }).join('')}
  </div>`;
}

async function validateDoc(pid, docId) {
  const btn = document.getElementById(`val-btn-${docId}`);
  if (btn) btn.disabled = true;
  const res = await api(`/api/patients/${pid}/documents/${docId}/validate`, 'POST');
  if (res.ok) {
    if (btn) {
      btn.remove();
      const row = document.getElementById(`doc-row-${docId}`);
      if (row) {
        const status = row.querySelector('span[style*="amber"]');
        if (status) { status.style.color = 'var(--teal2)'; status.textContent = '✓ Validé'; }
      }
    }
  } else {
    alert(res.error || 'Erreur');
    if (btn) btn.disabled = false;
  }
}

async function viewDocImage(pid, docId, type) {
  const doc = await api(`/api/patients/${pid}/documents/${docId}`);
  if (!doc || doc.error) { alert('Document introuvable'); return; }

  document.getElementById('modalImageTitle').textContent = type || 'Document patient';
  document.getElementById('modalImageContent').innerHTML = doc.image_b64 ? `
    <div style="text-align:center;padding:10px">
      <img src="data:image/jpeg;base64,${doc.image_b64}" style="max-width:100%;max-height:65vh;border-radius:10px;object-fit:contain">
      <div style="margin-top:12px;font-size:12px;color:var(--text3)">Uploadé le ${fmtDate(doc.date)} par ${doc.uploaded_by}</div>
      ${doc.analyse_ia ? `<div style="margin-top:10px;background:var(--teal-dim);border:1px solid rgba(14,165,160,0.2);border-radius:10px;padding:12px;text-align:left;font-size:13px;color:var(--text2)">${doc.analyse_ia}</div>` : ''}
    </div>` : `
    <div style="text-align:center;padding:40px;color:var(--text3)">
      <div style="font-size:40px;margin-bottom:12px">📎</div>
      <div>Aucune image disponible pour ce document</div>
    </div>`;
  openModal('modalImage');
}

function renderQuestionsPanel(questions, pid) {
  if (!questions.length) return '<div style="color:var(--text3);text-align:center;padding:30px">Aucune question</div>';
  return questions.map(q=>`
    <div class="question-card ${q.statut==='en_attente'?'pending':'answered'}" id="qcard-${q.id}">
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div class="q-text">❓ ${q.question}</div>
        <span class="badge ${q.statut==='en_attente'?'badge-amber':'badge-green'}">${q.statut}</span>
      </div>
      <div class="q-date">${q.date}</div>
      ${q.reponse_ia?`
        <div class="ai-draft">
          <div class="ai-draft-label">🤖 Réponse suggérée par l'IA</div>
          <div class="ai-draft-text">${q.reponse_ia}</div>
        </div>` : ''}
      ${q.statut==='en_attente'?`
        <div class="answer-area">
          <label class="lbl">Votre réponse (modifiez si nécessaire)</label>
          <textarea class="input" id="rep-${q.id}" rows="3">${q.reponse_ia||''}</textarea>
          <div style="margin-top:8px;display:flex;gap:8px">
            <button class="btn btn-primary btn-sm" onclick="sendReponse('${pid}','${q.id}')">✓ Envoyer réponse</button>
            <button class="btn btn-ghost btn-sm" onclick="sendReponseIA('${pid}','${q.id}')">✓ Valider réponse IA</button>
          </div>
        </div>` :
        `<div style="margin-top:10px;display:flex;align-items:flex-start;gap:8px">
          <div style="flex:1;background:var(--green-dim);border:1px solid rgba(34,197,94,0.2);border-radius:10px;padding:10px 14px;font-size:13px;color:var(--text2)">✅ ${q.reponse||'—'}</div>
          <button class="btn btn-ghost btn-sm" style="color:var(--red);flex-shrink:0" title="Archiver (conservé en historique)" onclick="softDeleteQuestion('${pid}','${q.id}',this)">🗑</button>
        </div>`}
    </div>
  `).join('')
  + `<div style="margin-top:16px">
      <button class="btn btn-ghost btn-sm" onclick="toggleDeletedQuestions('${pid}',this)" style="opacity:.6">
        🗂 Voir l'historique des questions archivées
      </button>
      <div id="deleted-questions-${pid}" style="display:none;margin-top:12px"></div>
    </div>`;
}

