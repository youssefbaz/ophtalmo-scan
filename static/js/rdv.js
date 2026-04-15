// ─── RDV MODALS ───────────────────────────────────────────────────────────────
function openAddRdv(pid) {
  document.getElementById('modalRdvTitle').textContent = 'Nouveau rendez-vous';
  document.getElementById('modalRdvContent').innerHTML = `
    <div class="form-row">
      <div><label class="lbl">Patient</label>
        <input class="input" id="rdvPid" value="${pid||''}" placeholder="ID patient (ex: P001)">
      </div>
      <div><label class="lbl">Type</label>
        <input class="input" id="rdvType" placeholder="Ex: Suivi glaucome" value="Consultation">
      </div>
    </div>
    <div class="form-row">
      <div><label class="lbl">Date</label><input type="date" class="input" id="rdvDate"></div>
      <div><label class="lbl">Heure</label><input type="time" class="input" id="rdvHeure" value="09:00"></div>
    </div>
    <div class="form-full"><label class="lbl">Médecin</label><input class="input" id="rdvMedecin" value="${USER.nom}"></div>
    <div class="form-full"><label class="lbl">Notes</label><textarea class="input" id="rdvNotes" rows="2" placeholder="Instructions particulières..."></textarea></div>
    <div style="margin-top:14px;display:flex;gap:10px">
      <button class="btn btn-primary" onclick="submitRdv(false)">Créer le RDV</button>
      <button class="btn btn-ghost" onclick="closeModal('modalRdv')">Annuler</button>
    </div>`;
  openModal('modalRdv');
}

function _rdvDoctorPickerHtml(defaultHeure) {
  return `
    <div class="form-full" style="margin-bottom:14px">
      <label class="lbl">Médecin</label>
      <input class="input" id="rdvDoctorSearch" placeholder="Rechercher un médecin par nom..." autocomplete="off"
        oninput="debounceRdvDoctorSearch(this.value)">
      <input type="hidden" id="rdvMedecinId">
      <input type="hidden" id="rdvMedecin">
      <div id="rdvDoctorResults" style="display:none;border:1px solid var(--border);border-radius:8px;margin-top:4px;background:var(--card);max-height:180px;overflow-y:auto;z-index:10;position:relative"></div>
      <div id="rdvDoctorSelected" style="display:none;margin-top:6px;padding:8px 12px;background:var(--teal-dim);border:1px solid rgba(14,165,160,0.3);border-radius:8px;font-size:13px;display:flex;align-items:center;gap:8px">
        <span id="rdvDoctorSelectedName" style="flex:1"></span>
        <button type="button" class="btn btn-ghost" style="padding:2px 8px;font-size:11px" onclick="clearRdvDoctorSelection()">✕</button>
      </div>
    </div>`;
}

let _rdvDoctorTimer = null;
function debounceRdvDoctorSearch(q) {
  clearTimeout(_rdvDoctorTimer);
  _rdvDoctorTimer = setTimeout(() => searchRdvDoctors(q), 300);
}
async function searchRdvDoctors(q) {
  const box = document.getElementById('rdvDoctorResults');
  if (!box) return;
  if (!q || q.length < 2) { box.style.display = 'none'; return; }
  const results = await api(`/api/doctors/search?q=${encodeURIComponent(q)}`);
  if (!results || !results.length) {
    box.innerHTML = '<div style="padding:10px 14px;font-size:13px;color:var(--text3)">Aucun médecin trouvé</div>';
    box.style.display = 'block'; return;
  }
  box.innerHTML = results.map(d => `
    <div style="padding:10px 14px;cursor:pointer;font-size:13px;border-bottom:1px solid var(--border)"
      onmouseover="this.style.background='var(--bg2)'" onmouseout="this.style.background=''"
      onclick="selectRdvDoctor('${d.id}','${escH(d.prenom)} ${escH(d.nom)}','${escH(d.organisation||'')}')">
      <div style="font-weight:600">Dr. ${escH(d.prenom)} ${escH(d.nom)}</div>
      ${d.organisation ? `<div style="font-size:11px;color:var(--text2)">${escH(d.organisation)}</div>` : ''}
    </div>`).join('');
  box.style.display = 'block';
}
function selectRdvDoctor(id, name, org) {
  document.getElementById('rdvMedecinId').value = id;
  document.getElementById('rdvMedecin').value = name;
  document.getElementById('rdvDoctorSearch').value = '';
  document.getElementById('rdvDoctorResults').style.display = 'none';
  const sel = document.getElementById('rdvDoctorSelected');
  document.getElementById('rdvDoctorSelectedName').textContent = `👨‍⚕️ Dr. ${name}${org ? ' · ' + org : ''}`;
  sel.style.display = 'flex';
}
function clearRdvDoctorSelection() {
  document.getElementById('rdvMedecinId').value = '';
  document.getElementById('rdvMedecin').value = '';
  document.getElementById('rdvDoctorSelected').style.display = 'none';
  document.getElementById('rdvDoctorSearch').value = '';
}

function openAddRdvPatient() {
  document.getElementById('modalRdvTitle').textContent = 'Demander un rendez-vous';
  document.getElementById('modalRdvContent').innerHTML = `
    <div style="font-size:13px;color:var(--text2);margin-bottom:16px">Votre demande sera envoyée au médecin pour validation.</div>
    ${_rdvDoctorPickerHtml('09:00')}
    <div class="form-full"><label class="lbl">Motif de consultation</label>
      <input class="input" id="rdvType" placeholder="Ex: Baisse de vision, contrôle, irritation...">
    </div>
    <div class="form-row">
      <div><label class="lbl">Date souhaitée</label><input type="date" class="input" id="rdvDate"></div>
      <div><label class="lbl">Heure souhaitée</label><input type="time" class="input" id="rdvHeure" value="09:00"></div>
    </div>
    <div class="form-full"><label class="lbl">Message (optionnel)</label><textarea class="input" id="rdvNotes" rows="2" placeholder="Décrivez brièvement votre problème..."></textarea></div>
    <div style="margin-top:14px;display:flex;gap:10px">
      <button class="btn btn-primary" onclick="submitRdv(false)">Envoyer la demande</button>
      <button class="btn btn-ghost" onclick="closeModal('modalRdv')">Annuler</button>
    </div>`;
  openModal('modalRdv');
}

function openRdvUrgent() {
  document.getElementById('modalRdvTitle').textContent = '🚨 Demande de RDV Urgent';
  document.getElementById('modalRdvContent').innerHTML = `
    <div style="background:var(--color-red-bg);border:1px solid rgba(239,68,68,0.35);border-radius:10px;padding:12px 16px;margin-bottom:16px;font-size:13px;color:var(--color-red)">
      ⚠️ Cette demande sera marquée urgente et notifiée immédiatement au médecin.
    </div>
    ${_rdvDoctorPickerHtml('08:00')}
    <div class="form-full"><label class="lbl">Motif urgent</label>
      <input class="input" id="rdvType" placeholder="Ex: Douleur oculaire intense, baisse vision soudaine...">
    </div>
    <div class="form-row">
      <div><label class="lbl">Date</label><input type="date" class="input" id="rdvDate"></div>
      <div><label class="lbl">Heure</label><input type="time" class="input" id="rdvHeure" value="08:00"></div>
    </div>
    <div class="form-full"><label class="lbl">Description</label><textarea class="input" id="rdvNotes" rows="3" placeholder="Décrivez vos symptômes en détail..."></textarea></div>
    <div style="margin-top:14px;display:flex;gap:10px">
      <button class="btn btn-red" onclick="submitRdv(true)">🚨 Envoyer RDV Urgent</button>
      <button class="btn btn-ghost" onclick="closeModal('modalRdv')">Annuler</button>
    </div>`;
  openModal('modalRdv');
}

async function submitRdv(urgent) {
  const pid = USER.role==='patient' ? USER.patient_id : document.getElementById('rdvPid')?.value;
  const medecinId = document.getElementById('rdvMedecinId')?.value || '';
  const medecinNom = document.getElementById('rdvMedecin')?.value || '';
  if (USER.role === 'patient' && !medecinId) {
    alert('Veuillez sélectionner un médecin.');
    return;
  }
  const payload = {
    patient_id: pid, type: document.getElementById('rdvType').value,
    date: document.getElementById('rdvDate').value, heure: document.getElementById('rdvHeure').value,
    medecin: medecinNom || document.getElementById('rdvMedecin')?.value || USER.nom,
    medecin_id: medecinId,
    notes: document.getElementById('rdvNotes').value, urgent
  };
  const res = await api('/api/rdv','POST',payload);
  if(res.ok) { closeModal('modalRdv'); showView(currentView); loadNotifications(); }
}

// ─── PATIENT MODAL ────────────────────────────────────────────────────────────
function openAddPatient() {
  document.getElementById('modalAddPatientContent').innerHTML = `
    <div class="form-row">
      <div><label class="lbl">Nom</label><input class="input" id="pNom" placeholder="Nom de famille"></div>
      <div><label class="lbl">Prénom</label><input class="input" id="pPrenom" placeholder="Prénom"></div>
    </div>
    <div class="form-row">
      <div><label class="lbl">Date de naissance</label><input type="date" class="input" id="pDdn"></div>
      <div><label class="lbl">Sexe</label>
        <select class="input" id="pSexe"><option value="">-- Choisir --</option><option value="M">Masculin</option><option value="F">Féminin</option></select>
      </div>
    </div>
    <div class="form-row">
      <div><label class="lbl">Téléphone</label><input class="input" id="pTel" placeholder="06 xx xx xx xx"></div>
      <div><label class="lbl">Email *</label><input class="input" type="email" id="pEmail" placeholder="email@example.com" required></div>
    </div>
    <div class="form-full"><label class="lbl">Antécédents (séparés par virgule)</label>
      <input class="input" id="pAnt" placeholder="Ex: Glaucome, Diabète...">
    </div>
    <div class="form-full"><label class="lbl">Allergies (séparés par virgule)</label>
      <input class="input" id="pAllerg" placeholder="Ex: Pénicilline...">
    </div>
    <div class="form-full" style="margin-top:8px">
      <label class="lbl">Médecin référent</label>
      <select class="input" id="pMedecinId">
        ${MEDECINS.map(m=>`<option value="${m.id}" ${m.id===USER.id?'selected':''}>${m.nom} ${m.prenom}</option>`).join('')}
      </select>
    </div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:10px">
      <input type="checkbox" id="pSendEmail" checked style="width:16px;height:16px;cursor:pointer">
      <label for="pSendEmail" style="font-size:13px;cursor:pointer">Envoyer les identifiants par email au patient</label>
    </div>
    <div style="margin-top:14px;display:flex;gap:10px">
      <button class="btn btn-primary" onclick="submitAddPatient()">Ajouter le patient</button>
      <button class="btn btn-ghost" onclick="closeModal('modalAddPatient')">Annuler</button>
    </div>`;
  openModal('modalAddPatient');
}

async function submitAddPatient() {
  const nom    = document.getElementById('pNom').value.trim();
  const prenom = document.getElementById('pPrenom').value.trim();
  const email  = document.getElementById('pEmail').value.trim();
  if (!nom || !prenom) {
    showToast('Nom et prénom sont requis.', 'error'); return;
  }
  if (!email || !email.includes('@')) {
    showToast('L\'adresse email est obligatoire.', 'error'); return;
  }
  const payload = {
    nom, prenom, email,
    ddn: document.getElementById('pDdn').value, sexe: document.getElementById('pSexe').value,
    telephone: document.getElementById('pTel').value,
    antecedents: document.getElementById('pAnt').value.split(',').map(s=>s.trim()).filter(Boolean),
    allergies: document.getElementById('pAllerg').value.split(',').map(s=>s.trim()).filter(Boolean),
    medecin_id: document.getElementById('pMedecinId')?.value || USER.id,
    send_email: document.getElementById('pSendEmail')?.checked ?? true
  };
  const res = await api('/api/patients','POST',payload);
  if(res.ok) {
    closeModal('modalAddPatient');
    loadPatientsSidebar();
    if (res.credentials) _showCredentialsModal(payload.prenom + ' ' + payload.nom, res.credentials, res.id);
  }
}

// ─── IMPORT MODAL ─────────────────────────────────────────────────────────────
function openImport() {
  document.getElementById('modalImportContent').innerHTML = `
    <div style="font-size:13px;color:var(--text2);margin-bottom:12px">Collez le contenu de votre fichier CSV ou copiez-collez depuis Excel. L'IA normalisera automatiquement les colonnes.</div>
    <textarea class="input" id="csvContent" rows="8" placeholder="nom,prenom,ddn,telephone&#10;Dupont,Marie,1975-03-15,06...&#10;..."></textarea>
    <div style="margin-top:12px;display:flex;gap:10px">
      <button class="btn btn-primary" onclick="submitImportCsv()">🤖 Importer avec IA</button>
      <label class="btn btn-ghost" style="cursor:pointer">📁 Charger fichier<input type="file" accept=".csv,.txt,.xlsx" style="display:none" onchange="loadCsvFile(this)"></label>
    </div>
    <div id="importResult" style="margin-top:14px"></div>`;
  openModal('modalImport');
}

function loadCsvFile(input) {
  const file = input.files[0]; if(!file) return;
  const reader = new FileReader();
  reader.onload = e => { document.getElementById('csvContent').value = e.target.result; };
  reader.readAsText(file);
}

async function submitImportCsv() {
  const content = document.getElementById('csvContent').value.trim();
  if(!content) return;
  const res_el = document.getElementById('importResult');
  res_el.innerHTML = '<div style="color:var(--teal2)"><span class="loading-dots"><span></span><span></span><span></span></span> Import en cours par IA...</div>';
  const res = await api('/api/import/csv','POST',{content});
  if(res.ok) {
    const credLines = res.added.map(p => {
      const c = p.credentials;
      const sent = c?.email_sent ? ' <span style="color:var(--teal2);font-size:11px">✉️ email envoyé</span>' : '';
      const cred = c ? ` — <span style="font-family:monospace;font-size:11px">${c.username} / ${c.password}</span>${sent}` : '';
      return `<div style="padding:4px 0;border-bottom:1px solid rgba(255,255,255,.07)"><strong>${p.prenom} ${p.nom}</strong> (${p.id})${cred}</div>`;
    }).join('');
    res_el.innerHTML = `<div style="background:var(--green-dim);border:1px solid rgba(34,197,94,0.3);border-radius:10px;padding:14px">
      <div style="font-weight:600;margin-bottom:10px">✅ ${res.count} patient(s) importé(s) — comptes créés</div>
      <div style="font-size:12px;color:var(--text2)">${credLines}</div>
      <div style="font-size:11px;color:var(--text3);margin-top:10px">⚠️ Notez les mots de passe — ils ne seront plus affichés.</div>
    </div>`;
    loadPatientsSidebar();
  } else {
    res_el.innerHTML = `<div style="background:var(--red-dim);border:1px solid rgba(239,68,68,0.3);border-radius:10px;padding:12px">❌ Erreur: ${res.error}<br><small>${res.raw||''}</small></div>`;
  }
}

// ─── PATIENT DOCUMENT UPLOAD ──────────────────────────────────────────────────
function handleDocDrop(e) {
  e.preventDefault();
  document.getElementById('docUploadZone').classList.remove('drag');
  const file = e.dataTransfer.files[0]; if (!file) return;
  _prepareUpload(file);
}

async function uploadPatientDoc(input) {
  const file = input.files[0]; if (!file) return;
  _prepareUpload(file);
}

function _prepareUpload(file) {
  _pendingUploadFile = file;
  const status = document.getElementById('docUploadStatus');
  const zone   = document.getElementById('docUploadZone');
  const wrap   = document.getElementById('docTypePickerWrap');
  const fname  = document.getElementById('docUploadFilename');
  const custom = document.getElementById('docTypeCustom');
  if (status) status.textContent = 'Fichier selectionne — choisissez le type ci-dessous';
  if (zone)   zone.style.opacity = '0.6';
  if (fname)  fname.textContent  = 'Fichier : ' + file.name;
  if (custom) custom.value = '';
  if (wrap)   wrap.style.display = 'block';
}

async function _doUploadFile(file, type, medecinId) {
  const status = document.getElementById('docUploadStatus');
  const zone   = document.getElementById('docUploadZone');
  if (status) { status.textContent = '⏳ Envoi en cours…'; zone.style.opacity = '0.5'; }

  return new Promise(resolve => {
    const reader = new FileReader();
    reader.onload = async (ev) => {
      const b64 = ev.target.result.split(',')[1];
      const pid = USER.patient_id;
      try {
        const res = await api(`/api/patients/${pid}/upload`, 'POST',
          { image: b64, type, description: file.name, source: 'document', medecin_id: medecinId || '' });
        if (res.ok) {
          showView('mes-documents');
        } else {
          alert(res.error || "Erreur lors de l'envoi du document.");
          if (status) { status.textContent = 'Cliquez ou glissez votre document ici'; zone.style.opacity = '1'; }
          const wrap = document.getElementById('docTypePickerWrap');
          if (wrap) wrap.style.display = 'none';
        }
      } catch(err) {
        alert('Erreur reseau lors de l\'envoi.');
        if (status) { status.textContent = 'Cliquez ou glissez votre document ici'; zone.style.opacity = '1'; }
      }
      resolve();
    };
    reader.onerror = () => { alert('Impossible de lire le fichier.'); resolve(); };
    reader.readAsDataURL(file);
  });
}

// ─── QUESTIONS ────────────────────────────────────────────────────────────────
async function softDeleteQuestion(pid, qid, btn) {
  btn.disabled = true;
  const res = await api(`/api/patients/${pid}/questions/${qid}`, 'DELETE');
  if (res.ok) {
    // Remove card from view, keep history toggle visible
    const card = btn.closest('.question-card');
    if (card) card.remove();
  } else {
    alert(res.error || 'Erreur');
    btn.disabled = false;
  }
}

async function toggleDeletedQuestions(pid, btn) {
  const panel = document.getElementById(`deleted-questions-${pid}`);
  if (panel.style.display !== 'none') {
    panel.style.display = 'none';
    btn.textContent = '🗂 Voir l\'historique des questions archivées';
    return;
  }
  btn.textContent = '⏳ Chargement…';
  const deleted = await api(`/api/patients/${pid}/questions/deleted`);
  if (!deleted.length) {
    panel.innerHTML = '<div style="color:var(--text3);font-size:13px;padding:10px 0">Aucune question archivée.</div>';
  } else {
    panel.innerHTML = `
      <div style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:1px;margin-bottom:10px">
        Historique — ${deleted.length} question(s) archivée(s)
      </div>
      ${deleted.map(q => `
        <div style="padding:12px 14px;background:var(--card);border:1px solid var(--border);border-radius:10px;margin-bottom:8px;opacity:.75">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <span style="font-size:11px;color:var(--text3)">${q.date} · archivé le ${fmtDate(q.deleted_at)}</span>
            <span class="badge badge-green" style="font-size:10px">répondu</span>
          </div>
          <div style="font-size:13px;color:var(--text2);margin-bottom:6px">❓ ${q.question}</div>
          <div style="font-size:12px;color:var(--text2);background:var(--green-dim);border-radius:8px;padding:8px 10px">✅ ${q.reponse}</div>
          <div style="font-size:11px;color:var(--text3);margin-top:4px">Répondu par ${q.repondu_par} · ${q.date_reponse}</div>
        </div>`).join('')}`;
  }
  panel.style.display = 'block';
  btn.textContent = '🗂 Masquer l\'historique';
}

async function submitQuestion() {
  const text = document.getElementById('newQuestion').value.trim();
  if(!text) return;
  const pid = USER.patient_id;
  const btn = document.querySelector('#newQuestion + button') || document.querySelector('[onclick="submitQuestion()"]');
  if(btn) { btn.disabled = true; btn.textContent = '⏳ Envoi...'; }
  const res = await api(`/api/patients/${pid}/questions`,'POST',{question:text});
  if(res.ok) {
    document.getElementById('newQuestion').value = '';
    showView('mes-questions');
  } else {
    alert('Erreur: ' + (res.error || 'inconnue'));
  }
  if(btn) { btn.disabled = false; btn.textContent = 'Envoyer ma question →'; }
}

async function sendReponse(pid, qid) {
  const rep = document.getElementById('rep-'+qid)?.value;
  const res = await api(`/api/patients/${pid}/questions/${qid}/repondre`,'POST',{reponse:rep});
  if(res.ok) { showView(currentView); }
}

async function sendReponseIA(pid, qid) {
  const el = document.getElementById('rep-'+qid);
  const rep = el ? el.value : '';
  const res = await api(`/api/patients/${pid}/questions/${qid}/repondre`,'POST',{reponse:rep});
  if(res.ok) { showView(currentView); }
}

// ─── POST-OP TIMELINE ─────────────────────────────────────────────────────────
function renderSuiviTab(suivi, patient, pid) {
  if (!patient.date_chirurgie) {
    return `
      <div style="text-align:center;padding:48px 24px;color:var(--text3)">
        <div style="font-size:40px;margin-bottom:12px">✂️</div>
        <div style="font-size:14px;margin-bottom:16px">Aucune chirurgie enregistrée pour ce patient.</div>
        <button class="btn btn-primary btn-sm" onclick="setDateChirurgie('${pid}')">Définir la date de chirurgie</button>
      </div>`;
  }

  const today    = new Date().toISOString().slice(0,10);
  const steps    = suivi || [];
  const total    = steps.length;
  const done     = steps.filter(s => s.statut === 'fait').length;
  const overdue  = steps.filter(s => s.statut === 'a_faire' && s.date_prevue < today).length;

  const statusBadge = s => {
    if (s.statut === 'fait')     return `<span style="background:var(--green);color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700">✓ FAIT</span>`;
    if (s.statut === 'manque')   return `<span style="background:var(--red);color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700">✗ MANQUÉ</span>`;
    if (s.statut === 'reporte')  return `<span style="background:var(--blue);color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700">↩ REPORTÉ</span>`;
    if (s.date_prevue < today)   return `<span style="background:var(--red);color:#fff;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700">⚠ EN RETARD</span>`;
    const days = Math.round((new Date(s.date_prevue) - new Date(today)) / 86400000);
    if (days <= 14) return `<span style="background:var(--amber);color:#000;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:700">⏰ dans ${days}j</span>`;
    return `<span style="background:var(--bg2);color:var(--text3);border:1px solid var(--border);padding:2px 8px;border-radius:10px;font-size:10px">dans ${days}j</span>`;
  };

  const cardBorder = s => {
    if (s.statut === 'fait')   return 'border-color:var(--green)';
    if (s.statut === 'manque') return 'border-color:rgba(239,68,68,.6)';
    if (s.statut === 'a_faire' && s.date_prevue < today) return 'border-color:rgba(239,68,68,.4)';
    return '';
  };

  const stepCards = steps.map(s => {
    const lbl = _suiviLabel(s.etape);
    return `
    <div style="background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 16px;display:flex;align-items:center;gap:14px;${cardBorder(s)}">
      <div style="min-width:54px;height:54px;border-radius:12px;background:var(--teal-dim);display:flex;flex-direction:column;align-items:center;justify-content:center;flex-shrink:0;font-weight:700;color:var(--teal2);border:1px solid rgba(14,165,160,0.25);padding:0 6px;text-align:center;line-height:1.2">
        ${lbl.includes(' ') ? `<span style="font-size:13px">${lbl.replace(' ','<br>')}</span>` : `<span style="font-size:15px">${lbl}</span>`}
      </div>
      <div style="flex:1;min-width:0">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px">
          <span style="font-size:13px;font-weight:600;color:var(--text)">Contrôle ${lbl}</span>
          ${statusBadge(s)}
        </div>
        <div style="font-size:11px;color:var(--text3)">Prévu : ${new Date(s.date_prevue).toLocaleDateString('fr-FR',{day:'numeric',month:'long',year:'numeric'})}</div>
        ${s.date_reelle ? `<div style="font-size:11px;color:var(--green)">Réalisé : ${new Date(s.date_reelle).toLocaleDateString('fr-FR',{day:'numeric',month:'long',year:'numeric'})}</div>` : ''}
        ${s.notes ? `<div style="font-size:11px;color:var(--text2);margin-top:3px;font-style:italic">📝 ${s.notes}</div>` : ''}
      </div>
      <div style="display:flex;gap:6px;flex-shrink:0;flex-wrap:wrap;justify-content:flex-end">
        ${s.statut !== 'fait' ? `<button class="btn btn-primary btn-sm" style="font-size:11px" onclick="markSuiviDone('${s.id}','${pid}','${s.etape}',this)">✓ Fait</button>` : ''}
        <button class="btn btn-ghost btn-sm" style="font-size:11px" onclick="editSuivi('${s.id}','${pid}','${s.etape}','${s.date_prevue}','${s.heure||'09:00'}')">✏</button>
        ${s.statut !== 'manque' && s.statut !== 'fait' ? `<button class="btn btn-ghost btn-sm" style="font-size:11px;color:var(--amber)" onclick="markSuiviStatut('${s.id}','${pid}','manque')">✗</button>` : ''}
        ${s.statut !== 'a_faire' ? `<button class="btn btn-ghost btn-sm" style="font-size:11px;opacity:.6" onclick="markSuiviStatut('${s.id}','${pid}','reset')">↩</button>` : ''}
        <button class="btn btn-ghost btn-sm" style="font-size:11px;color:var(--red)" onclick="deleteSuivi('${s.id}','${pid}','${s.etape}')">🗑</button>
      </div>
    </div>`;
  }).join('');

  return `
    <div style="margin-bottom:20px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">
      <div>
        <div style="font-size:14px;font-weight:700;color:var(--text)">✂️ ${patient.type_chirurgie || 'Chirurgie ophtalmologique'}</div>
        <div style="font-size:12px;color:var(--text3);margin-top:2px">Opéré le ${new Date(patient.date_chirurgie).toLocaleDateString('fr-FR',{day:'numeric',month:'long',year:'numeric'})}</div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <span class="badge badge-teal">✓ ${done}/${total} effectués</span>
        ${overdue ? `<span class="badge badge-red">⚠ ${overdue} en retard</span>` : ''}
      </div>
    </div>

    <!-- Progress bar -->
    <div style="background:var(--bg2);border-radius:8px;height:8px;margin-bottom:20px;overflow:hidden">
      <div style="height:100%;border-radius:8px;background:var(--teal);width:${total ? Math.round(done/total*100) : 0}%;transition:width .4s"></div>
    </div>

    <div style="display:flex;flex-direction:column;gap:10px">
      ${stepCards || '<div style="color:var(--text3);text-align:center;padding:30px">Aucun suivi généré — définissez d\'abord la date de chirurgie.</div>'}
    </div>`;
}

// Maps old DB codes AND normalises RDV type strings (e.g. "Suivi post-op J2Mois")
const _SUIVI_LEGACY = {
  'J2':'Jour 2', 'J7':'Jour 7', 'J30':'1 Mois',
  'J2Mois':'2 Mois', 'J3Mois':'3 Mois', 'J6Mois':'6 Mois',
  'J12M':'1 An', 'J12Mois':'1 An',
  'J18Mois':'18 Mois', 'A2':'2 Ans'
};
function _suiviLabel(etape) {
  return _SUIVI_LEGACY[etape] || etape;
}
function _normRdvType(type) {
  // Convert "Suivi post-op J2Mois" → "Suivi post-op 2 Mois"
  return (type || '').replace(/Suivi post-op (\S+)/, (_, code) =>
    'Suivi post-op ' + (_SUIVI_LEGACY[code] || code)
  );
}

async function markSuiviDone(sid, pid, etape, btn) {
  const dateReelle = prompt(`Date de réalisation du ${etape} (YYYY-MM-DD) :`, new Date().toISOString().slice(0,10));
  if (!dateReelle) return;
  const notes = prompt('Notes (optionnel) :', '') || '';
  btn.disabled = true;
  const res = await api(`/api/patients/${pid}/suivi/${sid}`, 'PUT', { statut:'fait', date_reelle: dateReelle, notes });
  if (res.ok) loadPatient(pid);
  else { alert(res.error || 'Erreur'); btn.disabled = false; }
}

async function markSuiviStatut(sid, pid, statut) {
  if (statut === 'reset') {
    const res = await api(`/api/patients/${pid}/suivi/${sid}/reset`, 'POST');
    if (res.ok) loadPatient(pid);
    return;
  }
  const res = await api(`/api/patients/${pid}/suivi/${sid}`, 'PUT', { statut, date_reelle: '' });
  if (res.ok) loadPatient(pid);
  else alert(res.error || 'Erreur');
}

async function editSuivi(sid, pid, etape, datePrevue, heure) {
  const newDate = prompt(`Nouvelle date pour ${etape} (YYYY-MM-DD) :`, datePrevue);
  if (!newDate) return;
  const newHeure = prompt(`Heure du RDV (HH:MM) :`, heure || '09:00');
  if (newHeure === null) return;
  const res = await api(`/api/patients/${pid}/suivi/${sid}`, 'PUT', { date_prevue: newDate, heure: newHeure });
  if (res.ok) loadPatient(pid);
  else alert(res.error || 'Erreur');
}

async function deleteSuivi(sid, pid, etape) {
  if (!confirm(`Supprimer le suivi ${etape} et son RDV associé dans l'agenda ?`)) return;
  const res = await api(`/api/patients/${pid}/suivi/${sid}`, 'DELETE');
  if (res.ok) loadPatient(pid);
  else alert(res.error || 'Erreur');
}

function renderPostOpTimeline(patient) {
  const JALONS = [7, 14, 21, 30, 60, 90, 120, 180, 247];
  const dateChir = new Date(patient.date_chirurgie);
  const today = new Date();
  const histoDates = (patient.historique || []).map(h => h.date);

  const jalonsHtml = JALONS.map(j => {
    const jalDate = new Date(dateChir);
    jalDate.setDate(jalDate.getDate() + j);
    const jalStr = jalDate.toISOString().slice(0,10);
    const daysDiff = Math.round((jalDate - today) / 86400000);

    // Check if consultation exists around this date ±5 days
    const done = histoDates.some(d => Math.abs(new Date(d) - jalDate) <= 5 * 86400000);
    const overdue = !done && daysDiff < 0;
    const cls = done ? 'done' : overdue ? 'overdue' : 'upcoming';
    const icon = done ? '✅' : overdue ? '⚠️' : '🔜';

    return `
      <div class="jalon ${cls}" title="${jalStr}">
        <div class="jalon-day">J${j}</div>
        <div class="jalon-status">${icon}</div>
        <div class="jalon-label">${jalDate.toLocaleDateString('fr-FR',{day:'numeric',month:'short'})}</div>
        ${overdue ? `<div style="font-size:9px;color:var(--color-amber);margin-top:2px">${Math.abs(daysDiff)}j de retard</div>` : ''}
        ${!done && daysDiff >= 0 ? `<div style="font-size:9px;color:var(--text3);margin-top:2px">dans ${daysDiff}j</div>` : ''}
      </div>`;
  }).join('');

  // Post-op consultations from historique
  const postOpConsults = (patient.historique || []).filter(h => h.date >= patient.date_chirurgie);

  return `
    <div style="margin-bottom:20px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
        <div>
          <div style="font-size:13px;color:var(--text2)">Chirurgie : <strong style="color:var(--teal2)">${patient.type_chirurgie || 'Intervention ophtalmologique'}</strong></div>
          <div style="font-size:12px;color:var(--text3);margin-top:2px">Date : ${fmtDate(patient.date_chirurgie)}</div>
        </div>
        <div style="font-family:'Space Mono',monospace;font-size:12px;color:var(--teal2)">
          J+${Math.round((today - new Date(patient.date_chirurgie)) / 86400000)} aujourd'hui
        </div>
      </div>
      <div class="postop-track">${jalonsHtml}</div>
      <div style="display:flex;gap:16px;font-size:11px;color:var(--text3);margin-bottom:20px">
        <span>✅ Consultation effectuée</span>
        <span>⚠️ En retard</span>
        <span>🔜 À venir</span>
      </div>
    </div>
    <div class="section-title">Consultations post-opératoires</div>
    ${postOpConsults.length ? `
      <div class="timeline">
        ${postOpConsults.map(h => {
          const jx = Math.round((new Date(h.date) - new Date(patient.date_chirurgie)) / 86400000);
          return `
          <div class="tl-item">
            <div class="tl-date">${fmtDateLong(h.date)} — <span style="color:var(--amber)">J+${jx}</span> — ${h.medecin}</div>
            <div class="tl-title">${h.motif}</div>
            <div class="tl-grid">
              <div class="tl-field"><div class="tl-field-label">Diagnostic</div><div class="tl-field-value">${h.diagnostic}</div></div>
              <div class="tl-field"><div class="tl-field-label">Traitement</div><div class="tl-field-value">${h.traitement}</div></div>
              ${h.tension_od?`<div class="tl-field"><div class="tl-field-label">Tonus</div><div class="tl-field-value">OD: ${h.tension_od} mmHg | OG: ${h.tension_og} mmHg</div></div>`:''}
              ${h.acuite_od?`<div class="tl-field"><div class="tl-field-label">Acuité</div><div class="tl-field-value">OD: ${h.acuite_od} | OG: ${h.acuite_og}</div></div>`:''}
            </div>
            ${h.notes?`<div class="tl-note">📝 ${h.notes}</div>`:''}
          </div>`;
        }).join('')}
      </div>` : '<div style="color:var(--text3);text-align:center;padding:20px">Aucune consultation post-opératoire enregistrée</div>'}`;
}

const CHIRURGIE_TYPES = [
  'Cataracte (phacoémulsification)',
  'Cataracte + implant torique',
  'Cataracte + implant multifocal',
  'Greffe de cornée (kératoplastie lamellaire — DSAEK)',
  'Greffe de cornée (kératoplastie transfixiante — PK)',
  'Chirurgie réfractive — LASIK',
  'Chirurgie réfractive — PKR / PRK',
  'Chirurgie réfractive — SMILE',
  'Implant phaque chambre postérieure (ICL)',
  'Trabéculectomie (glaucome)',
  'Implant de drainage glaucome',
  'Décollement de rétine (vitrectomie)',
  'Décollement de rétine (indentation sclérale)',
  'Membrane épirétinienne (vitrectomie)',
  'Chirurgie du strabisme',
  'Ptérygion',
  'Dacryocystorhinostomie (DCR)',
  'Ptose palpébrale',
  'Autre',
];

function _openChirurgieModal(pid, currentDate, currentType) {
  document.getElementById('modalChirurgieTitle').textContent =
    currentDate ? 'Modifier la chirurgie' : 'Définir la chirurgie';
  const today = new Date().toISOString().slice(0,10);
  const isOther = currentType && !CHIRURGIE_TYPES.slice(0,-1).includes(currentType);
  const selectedType = isOther ? 'Autre' : (currentType || '');
  document.getElementById('modalChirurgieContent').innerHTML = `
    <div style="padding:20px">
      <div class="form-group">
        <label class="form-label">Date de la chirurgie *</label>
        <input class="form-input" type="date" id="chirDate" value="${currentDate || today}">
      </div>
      <div class="form-group">
        <label class="form-label">Type d'opération *</label>
        <select class="form-input" id="chirType" onchange="onChirTypeChange()">
          <option value="">— Sélectionner —</option>
          ${CHIRURGIE_TYPES.map(t =>
            `<option value="${t}" ${t === selectedType ? 'selected' : ''}>${t}</option>`
          ).join('')}
        </select>
      </div>
      <div class="form-group" id="chirAutreGroup" style="display:${(selectedType === 'Autre') ? '' : 'none'}">
        <label class="form-label">Préciser le type d'opération</label>
        <input class="form-input" id="chirAutre" placeholder="Nom de l'opération..."
               value="${isOther ? currentType : ''}">
      </div>
      <div id="chirMsg" style="margin-bottom:10px"></div>
      <div style="display:flex;gap:10px;margin-top:4px">
        <button class="btn btn-primary" style="flex:1;justify-content:center"
                onclick="submitChirurgie('${pid}')">Enregistrer</button>
        <button class="btn btn-ghost" onclick="closeModal('modalChirurgie')">Annuler</button>
      </div>
    </div>`;
  openModal('modalChirurgie');
}

function onChirTypeChange() {
  const sel = document.getElementById('chirType').value;
  document.getElementById('chirAutreGroup').style.display = sel === 'Autre' ? '' : 'none';
}

async function submitChirurgie(pid) {
  const date = document.getElementById('chirDate').value;
  let   type = document.getElementById('chirType').value;
  if (type === 'Autre') type = document.getElementById('chirAutre').value.trim();
  const msgEl = document.getElementById('chirMsg');
  if (!date) { msgEl.innerHTML = '<div class="auth-msg auth-msg-error">La date est requise.</div>'; return; }
  if (!type) { msgEl.innerHTML = '<div class="auth-msg auth-msg-error">Le type d\'opération est requis.</div>'; return; }
  const res = await api(`/api/patients/${pid}/chirurgie`, 'POST', {date_chirurgie: date, type_chirurgie: type});
  if (res.ok) { closeModal('modalChirurgie'); loadPatient(pid); }
  else msgEl.innerHTML = `<div class="auth-msg auth-msg-error">${res.error || 'Erreur inconnue'}</div>`;
}

function setDateChirurgie(pid) { _openChirurgieModal(pid, '', ''); }
function editChirurgie(pid, currentDate, currentType) { _openChirurgieModal(pid, currentDate, currentType); }

async function deleteChirurgie(pid) {
  if (!confirm('Supprimer la chirurgie et tous les RDV post-op associés dans l\'agenda ?')) return;
  const res = await api(`/api/patients/${pid}/chirurgie`, 'DELETE');
  if (res.ok) loadPatient(pid);
  else alert('Erreur: ' + (res.error || 'inconnue'));
}

async function deletePatient(pid, name) {
  if (!confirm(`Supprimer définitivement le patient ${name} ?\n\nToutes ses consultations, rendez-vous, documents et ordonnances seront supprimés. Cette action est irréversible.`)) return;
  const res = await api(`/api/patients/${pid}`, 'DELETE');
  if (res.ok) {
    loadPatientsSidebar();
    document.getElementById('main-content').innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text3)">Sélectionnez un patient</div>';
  } else {
    alert('Erreur : ' + (res.error || 'Impossible de supprimer'));
  }
}

async function exportPatientAnon(pid) {
  const res = await api(`/api/patients/${pid}/export`);
  if (res.error) { alert('Erreur export'); return; }
  const blob = new Blob([JSON.stringify(res, null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url;
  a.download = `patient_anon_${res.code}_${new Date().toISOString().slice(0,10)}.json`;
  a.click(); URL.revokeObjectURL(url);
}

