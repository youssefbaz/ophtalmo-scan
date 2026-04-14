// ─── MES RDV (PATIENT) ────────────────────────────────────────────────────────
function _rdvDateBig(dateStr, heure, opts = {}) {
  const d = new Date(dateStr + 'T00:00:00');
  const weekday = d.toLocaleString('fr-FR', {weekday:'short'}).replace('.','').toUpperCase();
  const dayNum  = d.getDate();
  const monthYr = d.toLocaleString('fr-FR', {month:'short', year:'numeric'});
  const cls = opts.past ? 'past' : opts.urgent ? 'urgent-bg' : '';
  return `<div class="rdv-date-big ${cls}">
    <div class="rdv-weekday">${weekday}</div>
    <div class="rdv-daynum">${dayNum}</div>
    <div class="rdv-monthyear">${monthYr}</div>
    <div class="rdv-time-chip">${heure}</div>
    ${opts.today    ? `<div style="font-size:9px;font-weight:700;color:var(--teal2);margin-top:4px;letter-spacing:.5px">AUJOURD&#x2019;HUI</div>` : ''}
    ${opts.tomorrow ? `<div style="font-size:9px;font-weight:700;color:var(--amber);margin-top:4px;letter-spacing:.5px">DEMAIN</div>` : ''}
  </div>`;
}

async function renderMesRdv(c) {
  const rdvs     = await api('/api/rdv');
  const today    = new Date().toISOString().slice(0,10);
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0,10);
  const prochains = rdvs.filter(r=>r.date>=today).sort((a,b)=>(a.date+a.heure).localeCompare(b.date+b.heure));
  const passes    = rdvs.filter(r=>r.date<today).sort((a,b)=>b.date.localeCompare(a.date));

  c.innerHTML = `
    <div style="display:flex;gap:10px;margin-bottom:20px">
      <button class="btn btn-primary btn-sm" onclick="openAddRdvPatient()">&#128197; Demander un RDV</button>
      <button class="btn btn-red btn-sm" onclick="openRdvUrgent()">&#128680; RDV Urgent</button>
    </div>
    <div class="section-title" style="display:flex;align-items:center;gap:8px">
      Prochains rendez-vous
      ${prochains.length ? `<span style="background:var(--teal);color:#fff;font-size:11px;font-weight:700;padding:2px 9px;border-radius:12px">${prochains.length}</span>` : ''}
    </div>
    ${prochains.map(r => `
      <div class="rdv-card" style="${r.date===today ? 'border-color:var(--teal);box-shadow:0 0 0 2px rgba(14,165,160,0.15)' : ''}">
        ${_rdvDateBig(r.date, r.heure, {today: r.date===today, tomorrow: r.date===tomorrow, urgent: r.urgent})}
        <div class="rdv-info">
          <div class="rdv-type">${r.urgent ? '&#128680; ' : ''}<strong>${escH(_normRdvType(r.type))}</strong></div>
          <div class="rdv-meta" style="margin-top:5px">&#x1F3E5; ${escH(r.medecin || 'Médecin')}</div>
        </div>
        <span class="badge ${r.statut==='confirmé'?'badge-teal':r.statut==='en_attente'?'badge-amber':'badge-red'}">${r.statut}</span>
      </div>
    `).join('') || '<div style="color:var(--text3);text-align:center;padding:20px;background:var(--card);border-radius:var(--radius);border:1px dashed var(--border)">Aucun RDV à venir</div>'}
    ${passes.length ? `
    <div class="section-title" style="margin-top:20px;display:flex;align-items:center;gap:8px">
      Historique des RDV
      <span style="background:var(--bg2);color:var(--text2);font-size:11px;font-weight:700;padding:2px 9px;border-radius:12px">${passes.length}</span>
    </div>
    ${passes.map(r => `
      <div class="rdv-card" style="opacity:0.6">
        ${_rdvDateBig(r.date, r.heure, {past: true})}
        <div class="rdv-info">
          <div class="rdv-type">${escH(_normRdvType(r.type))}</div>
          <div class="rdv-meta" style="margin-top:5px">&#x1F3E5; ${escH(r.medecin || 'Médecin')}</div>
        </div>
        <span class="badge badge-teal">pass&#233;</span>
      </div>
    `).join('')}` : ''}`;
}

// ─── MES DOCUMENTS (PATIENT) ──────────────────────────────────────────────────
async function renderMesDocuments(c) {
  const pid = USER.patient_id;
  const [docs, myDoctors] = await Promise.all([
    api(`/api/patients/${pid}/documents`),
    api('/api/my-doctors')
  ]);

  // Build doctor options HTML — first one is pre-selected (most recent RDV)
  let doctorOptionsHtml = '';
  if (myDoctors && myDoctors.length) {
    doctorOptionsHtml = myDoctors.map((d, i) => {
      const label = `Dr. ${escH(d.prenom)} ${escH(d.nom)}${d.organisation ? ' - ' + escH(d.organisation) : ''}${d.last_rdv ? ' (dernier RDV: ' + fmtDate(d.last_rdv) + ')' : ''}`;
      return `<option value="${d.id}" ${i===0?'selected':''}>${label}</option>`;
    }).join('');
  }

  c.innerHTML = `
    <div style="margin-bottom:18px">
      <div style="font-size:13px;color:var(--text2);margin-bottom:12px">Uploadez vos radios, scanners et examens pour que votre medecin puisse les consulter.</div>
      <div class="import-zone" id="docUploadZone"
        onclick="document.getElementById('docFileInput').click()"
        ondragover="event.preventDefault();this.classList.add('drag')"
        ondragleave="this.classList.remove('drag')"
        ondrop="handleDocDrop(event)">
        <div class="import-icon">&#128206;</div>
        <div id="docUploadStatus" class="import-text">Cliquez ou glissez votre document ici</div>
        <div class="import-sub">Radio, Scanner, OCT, Ordonnance — JPG, PNG, PDF</div>
      </div>
      <input type="file" id="docFileInput" accept="image/*,application/pdf,.pdf" style="display:none" onchange="uploadPatientDoc(this)">

      <div id="docTypePickerWrap" style="display:none;margin-top:10px;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px">
        <div id="docUploadFilename" style="font-size:12px;color:var(--teal2);margin-bottom:12px;font-weight:600"></div>

        <div style="margin-bottom:10px">
          <label class="lbl">Pour quel medecin ?</label>
          ${myDoctors && myDoctors.length
            ? `<select class="input" id="docMedecinSelect" style="font-size:13px">${doctorOptionsHtml}</select>`
            : `<div style="font-size:13px;color:var(--amber);padding:8px 0">Aucun medecin associe. Prenez d abord un rendez-vous.</div>
               <input type="hidden" id="docMedecinSelect" value="">`
          }
        </div>

        <div style="margin-bottom:12px">
          <label class="lbl">Type de document</label>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <select class="input" id="docTypeSelect" style="flex:1;min-width:160px;font-size:13px">
              <option value="Radio / Scanner">Radio / Scanner</option>
              <option value="OCT">OCT</option>
              <option value="Fond d oeil">Fond d oeil</option>
              <option value="Ordonnance">Ordonnance</option>
              <option value="Resultats analyses">Resultats analyses</option>
              <option value="Autre">Autre</option>
            </select>
            <input class="input" id="docTypeCustom" placeholder="Ou type personnalise" style="flex:1;min-width:140px;font-size:13px">
          </div>
        </div>

        <div style="display:flex;gap:8px">
          <button class="btn btn-primary" onclick="confirmDocUpload()">Envoyer</button>
          <button class="btn btn-ghost" onclick="cancelDocUpload()">Annuler</button>
        </div>
      </div>
    </div>

    <div class="section-title">Mes documents (${docs.length})</div>
    <div style="display:flex;flex-direction:column;gap:10px" id="patientDocsGrid">
      ${docs.length ? docs.map(d => {
        const isPdf = (d.description||'').toLowerCase().endsWith('.pdf');
        const icon  = isPdf ? '&#128196;' : '&#128444;';
        const stat  = d.valide
          ? '<span style="font-size:11px;color:var(--teal2)">&#10003; Vu par le medecin</span>'
          : '<span style="font-size:11px;color:var(--amber)">&#8987; En attente</span>';
        return `<div style="display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px 16px">
          <div style="font-size:28px;flex-shrink:0">${icon}</div>
          <div style="flex:1;min-width:0">
            <div style="font-weight:600;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escH(d.type)}</div>
            <div style="font-size:12px;color:var(--text2);margin-top:2px">${fmtDate(d.date)} · ${escH(d.description||'')}</div>
            <div style="margin-top:4px">${stat}</div>
          </div>
          <button class="btn btn-ghost btn-sm" style="color:var(--red);flex-shrink:0"
            onclick="deletePatientDoc('${pid}','${d.id}',this)" title="Supprimer">&#128465;</button>
        </div>`;
      }).join('') : '<div style="color:var(--text3);text-align:center;padding:30px;background:var(--card);border:1px dashed var(--border);border-radius:12px">Aucun document uploade</div>'}
    </div>`;
}

let _pendingUploadFile = null;

function cancelDocUpload() {
  _pendingUploadFile = null;
  const wrap = document.getElementById('docTypePickerWrap');
  const status = document.getElementById('docUploadStatus');
  const zone = document.getElementById('docUploadZone');
  const inp = document.getElementById('docFileInput');
  if (wrap)   wrap.style.display = 'none';
  if (status) status.textContent = 'Cliquez ou glissez votre document ici';
  if (zone)   zone.style.opacity = '1';
  if (inp)    inp.value = '';
}

async function confirmDocUpload() {
  const customVal = (document.getElementById('docTypeCustom')?.value || '').trim();
  const selectVal = document.getElementById('docTypeSelect')?.value || 'Document';
  const type = customVal || selectVal;
  const medecinId = document.getElementById('docMedecinSelect')?.value || '';
  if (!_pendingUploadFile) return;
  const file = _pendingUploadFile;
  _pendingUploadFile = null;
  await _doUploadFile(file, type, medecinId);
}

async function deletePatientDoc(pid, docId, btn) {
  if (!confirm('Supprimer ce document ?')) return;
  btn.disabled = true;
  const res = await api(`/api/patients/${pid}/documents/${docId}`, 'DELETE');
  if (res.ok) {
    const row = btn.closest('div[style]');
    if (row) row.remove();
  } else {
    alert(res.error || 'Erreur lors de la suppression');
    btn.disabled = false;
  }
}

// ─── MES QUESTIONS (PATIENT) ──────────────────────────────────────────────────
async function renderMesQuestions(c) {
  const pid = USER.patient_id;
  const questions = await api(`/api/patients/${pid}/questions`);
  
  c.innerHTML = `
    <div style="margin-bottom:18px">
      <div style="font-size:13px;color:var(--text2);margin-bottom:12px">Posez une question à votre médecin. Vous recevrez une réponse dès que possible.</div>
      <div class="card">
        <label class="lbl">Votre question</label>
        <textarea class="input" id="newQuestion" placeholder="Ex: Est-ce que je dois continuer mes gouttes les jours suivants l'opération ?" rows="3"></textarea>
        <button class="btn btn-primary btn-sm" style="margin-top:10px" onclick="submitQuestion()">Envoyer ma question →</button>
      </div>
    </div>
    <div class="section-title">Mes questions</div>
    <div id="questionsListPatient">
      ${questions.length?questions.map(q=>`
        <div class="question-card ${q.statut==='en_attente'?'pending':'answered'}">
          <div class="q-text">❓ ${q.question}</div>
          <div class="q-date">${q.date}</div>
          ${q.statut==='répondu'?
            `<div style="margin-top:10px;background:var(--teal-dim);border:1px solid rgba(14,165,160,0.2);border-radius:10px;padding:12px;font-size:13px;color:var(--text)">
              <div style="font-size:10px;color:var(--teal2);margin-bottom:5px;text-transform:uppercase;letter-spacing:0.5px">✅ Réponse du médecin</div>
              ${q.reponse}
             </div>`:
            `<div style="margin-top:8px"><span class="badge badge-amber">⏳ En attente de réponse</span></div>`}
        </div>
      `).join(''):'<div style="color:var(--text3);text-align:center;padding:20px">Aucune question pour le moment</div>'}
    </div>`;
}

