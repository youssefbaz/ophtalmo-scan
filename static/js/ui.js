// ─── PATIENTS SIDEBAR ─────────────────────────────────────────────────────────
let _showAllPatients = false;

function setSidebarFilter(showAll) {
  _showAllPatients = showAll;
  const btnMes  = document.getElementById('btnMesPatients');
  const btnTous = document.getElementById('btnTousPatients');
  if (btnMes)  btnMes.className  = showAll ? 'btn btn-sm btn-ghost'   : 'btn btn-sm btn-primary';
  if (btnTous) btnTous.className = showAll ? 'btn btn-sm btn-primary' : 'btn btn-sm btn-ghost';
  loadPatientsSidebar();
}

async function loadPatientsSidebar(q='') {
  let url = '/api/patients';
  const params = [];
  if (q) params.push(`q=${encodeURIComponent(q)}`);
  if (_showAllPatients) params.push('all=1');
  if (params.length) url += '?' + params.join('&');
  const patients = await api(url);
  const el = document.getElementById('patientListSidebar');
  if (!el) return;
  el.innerHTML = (Array.isArray(patients) ? patients : []).map(p => {
    const dr = (_showAllPatients && p.medecin_id)
      ? MEDECINS.find(m => m.id === p.medecin_id) : null;
    return `
      <div class="patient-mini ${currentPatientId===p.id?'active':''}" onclick="loadPatient('${p.id}')">
        <div class="pm-name">${p.prenom} ${p.nom}${p.linked?` <span style="font-size:9px;background:rgba(14,165,160,0.15);color:var(--teal2);padding:1px 5px;border-radius:6px;vertical-align:middle">RDV</span>`:''}</div>
        <div class="pm-id">${p.id}${dr?` · <span style="color:var(--teal2);font-size:10px">${dr.nom}</span>`:''}</div>
        ${(p.nb_rdv_urgent||0)>0?`<span class="pm-badge">🚨 ${p.nb_rdv_urgent}</span>`:''}
      </div>`;
  }).join('') || '<div style="color:var(--text3);font-size:12px;padding:16px;text-align:center">Aucun patient</div>';
}

function searchPatients(q) { clearTimeout(window._st); window._st=setTimeout(()=>loadPatientsSidebar(q),200); }

async function loadPatient(pid) {
  currentPatientId = pid;
  const p = await api(`/api/patients/${pid}`);
  if (p.error || !p.id) {
    alert(p.error || 'Patient introuvable');
    return;
  }
  showView('patient-profile', `${p.prenom} ${p.nom}`);
  loadPatientsSidebar();
}

// ─── RDV ACTIONS ─────────────────────────────────────────────────────────────
async function modifierRdv(rdvId, dateActuelle, heureActuelle) {
  openEditRdvModal(rdvId);
}

async function openEditRdvModal(rdvId) {
  // Fetch current RDV data
  const rdvs = await api('/api/rdv');
  const r = rdvs.find(x => x.id === rdvId);
  if (!r) { alert('RDV introuvable'); return; }

  const statutOptions = ['programmé','confirmé','en_attente','arrivé','en_cours','terminé','annulé']
    .map(s => `<option value="${s}" ${s === r.statut ? 'selected' : ''}>${s}</option>`).join('');

  document.getElementById('modalRdvTitle').textContent = 'Modifier le rendez-vous';
  document.getElementById('modalRdvContent').innerHTML = `
    <div class="form-row">
      <div><label class="lbl">Patient</label>
        <input class="input" value="${escH((r.patient_prenom||'') + ' ' + (r.patient_nom||''))} (${r.patient_id})" disabled style="opacity:.6">
      </div>
      <div><label class="lbl">Type</label>
        <input class="input" id="editRdvType" value="${escH(r.type)}">
      </div>
    </div>
    <div class="form-row">
      <div><label class="lbl">Date</label><input type="date" class="input" id="editRdvDate" value="${r.date}"></div>
      <div><label class="lbl">Heure</label><input type="time" class="input" id="editRdvHeure" value="${r.heure}"></div>
    </div>
    <div class="form-row">
      <div><label class="lbl">Médecin</label><input class="input" id="editRdvMedecin" value="${escH(r.medecin)}"></div>
      <div><label class="lbl">Statut</label><select class="input" id="editRdvStatut">${statutOptions}</select></div>
    </div>
    <div class="form-full"><label class="lbl">Notes</label>
      <textarea class="input" id="editRdvNotes" rows="2">${escH(r.notes||'')}</textarea>
    </div>
    <div style="margin-top:14px;display:flex;gap:10px">
      <button class="btn btn-primary" onclick="submitEditRdv('${rdvId}')">Enregistrer</button>
      <button class="btn btn-ghost" onclick="closeModal('modalRdv')">Annuler</button>
    </div>`;
  openModal('modalRdv');
}

async function submitEditRdv(rdvId) {
  const payload = {
    date:   document.getElementById('editRdvDate').value,
    heure:  document.getElementById('editRdvHeure').value,
    type:   document.getElementById('editRdvType').value,
    statut: document.getElementById('editRdvStatut').value,
    medecin:document.getElementById('editRdvMedecin').value,
    notes:  document.getElementById('editRdvNotes').value,
  };
  const res = await api(`/api/rdv/${rdvId}`, 'PUT', payload);
  if (res.ok) { closeModal('modalRdv'); showView(currentView); loadNotifications(); }
  else alert(res.error || 'Erreur');
}

async function validerRdv(rdvId, statut) {
  await api(`/api/rdv/${rdvId}/valider`,'POST',{statut});
  showView(currentView);
  loadNotifications();
}

async function deleteRdv(rdvId) {
  if (!confirm('Supprimer ce rendez-vous ?')) return;
  await api(`/api/rdv/${rdvId}`, 'DELETE');
  showView(currentView);
  loadNotifications();
}

function openEditPatient(pid) {
  const patient = window._currentPatient;
  document.getElementById('modalEditPatientContent').innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
      <div><label class="lbl">Nom</label><input class="input" id="epNom" value="${escH(patient.nom)}"></div>
      <div><label class="lbl">Prénom</label><input class="input" id="epPrenom" value="${escH(patient.prenom)}"></div>
      <div><label class="lbl">Date de naissance</label><input class="input" type="date" id="epDdn" value="${patient.ddn}"></div>
      <div><label class="lbl">Sexe</label>
        <select class="input" id="epSexe">
          <option value="M" ${patient.sexe==='M'?'selected':''}>Masculin</option>
          <option value="F" ${patient.sexe==='F'?'selected':''}>Féminin</option>
        </select>
      </div>
      <div><label class="lbl">Téléphone</label><input class="input" id="epTel" value="${escH(patient.telephone||'')}"></div>
      <div><label class="lbl">Email</label><input class="input" id="epEmail" value="${escH(patient.email||'')}"></div>
    </div>
    <div style="margin-top:12px">
      <label class="lbl">Antécédents (un par ligne)</label>
      <textarea class="input" id="epAntecedents" rows="3">${(patient.antecedents||[]).join('\n')}</textarea>
    </div>
    <div style="margin-top:12px">
      <label class="lbl">Allergies (une par ligne)</label>
      <textarea class="input" id="epAllergies" rows="2">${(patient.allergies||[]).join('\n')}</textarea>
    </div>
    <div style="display:flex;gap:10px;margin-top:18px;justify-content:flex-end">
      <button class="btn btn-ghost" onclick="closeModal('modalEditPatient')">Annuler</button>
      <button class="btn btn-primary" onclick="submitEditPatient('${pid}')">Enregistrer</button>
    </div>`;
  openModal('modalEditPatient');
}

async function submitEditPatient(pid) {
  const body = {
    nom:         document.getElementById('epNom').value.trim(),
    prenom:      document.getElementById('epPrenom').value.trim(),
    ddn:         document.getElementById('epDdn').value,
    sexe:        document.getElementById('epSexe').value,
    telephone:   document.getElementById('epTel').value.trim(),
    email:       document.getElementById('epEmail').value.trim(),
    antecedents: document.getElementById('epAntecedents').value.split('\n').map(s=>s.trim()).filter(Boolean),
    allergies:   document.getElementById('epAllergies').value.split('\n').map(s=>s.trim()).filter(Boolean),
  };
  const res = await api(`/api/patients/${pid}`, 'PUT', body);
  if (res.ok) {
    closeModal('modalEditPatient');
    loadPatient(pid);
  }
}

// ─── NOTIFICATIONS ────────────────────────────────────────────────────────────
async function loadNotifications() {
  const notifs = await api('/api/notifications');
  const unread = notifs.filter(n=>!n.lu).length;
  const cnt = document.getElementById('notifCount');
  if(unread > 0) { cnt.style.display='flex'; cnt.textContent=unread; }
  else { cnt.style.display='none'; }
  
  document.getElementById('notifList').innerHTML = notifs.length ?
    notifs.map(n=>`
      <div class="notif-item ${n.lu?'':'unread'}" onclick="handleNotifClick('${n.id}','${n.type}','${n.patient_id||''}')">
        <div class="notif-msg">${n.message}</div>
        <div class="notif-time">${n.date}</div>
      </div>`).join('') :
    '<div style="padding:20px;text-align:center;color:var(--text3);font-size:13px">Aucune notification</div>';
}

function toggleNotifs() { notifOpen=!notifOpen; document.getElementById('notifPanel').classList.toggle('open',notifOpen); }
document.addEventListener('click', e=>{ if(!e.target.closest('.notif-panel')&&!e.target.closest('.notif-btn')){ notifOpen=false; document.getElementById('notifPanel').classList.remove('open'); }});

async function handleNotifClick(nid, type, pid) {
  await api(`/api/notifications/${nid}/lu`, 'POST');
  toggleNotifs();
  loadNotifications();

  // Navigate to the relevant page/tab
  if (USER.role === 'medecin') {
    const TAB = {
      'document_uploaded': 'media',
      'question':          'qst',
      'chirurgie':         'suivi',
      'rdv_urgent':        'rdvp',
      'rdv_demande':       'rdvp',
      'rdv_validé':        'rdvp',
    };
    const tab = TAB[type] || null;

    if (type === 'rdv_urgent' || type === 'rdv_demande') {
      // Go to agenda so the doctor can act on it directly
      if (pid) {
        window._pendingTab = 'rdvp';
        await loadPatient(pid);
      } else {
        showView('agenda');
      }
    } else if (type === 'import') {
      // Nothing specific — stay on current view
    } else if (pid) {
      window._pendingTab = tab;
      await loadPatient(pid);
    }
  } else {
    // Patient side
    if (type === 'reponse' || type === 'question') showView('mes-questions');
    else if (type === 'rdv_validé')               showView('mes-rdv');
    else if (type === 'document_uploaded')         showView('mes-documents');
  }
}

function _applyPendingTab() {
  if (!window._pendingTab) return;
  const tab = window._pendingTab;
  window._pendingTab = null;
  const btn = document.querySelector(`.tab-btn[onclick*="switchTab('${tab}'"]`);
  if (btn) { btn.click(); }
}

async function markNotifLu(nid) { await api(`/api/notifications/${nid}/lu`,'POST'); loadNotifications(); }

// ─── NOTES RAPIDES ────────────────────────────────────────────────────────────
function getNotes() {
  try { return JSON.parse(localStorage.getItem('ophtalmo_notes') || '[]'); } catch { return []; }
}
function saveNotes(notes) { localStorage.setItem('ophtalmo_notes', JSON.stringify(notes)); }

function renderNotesList() {
  const notes = getNotes();
  if (!notes.length) return '<div style="color:var(--text3);font-size:13px">Aucune note</div>';
  return notes.map((n, i) => `
    <div style="display:flex;align-items:flex-start;gap:8px;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:10px 12px">
      <div style="flex:1;font-size:13px;color:var(--text);white-space:pre-wrap">${n.text}</div>
      <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0">
        <div style="font-size:10px;color:var(--text3)">${n.date}</div>
        <button class="btn btn-ghost btn-sm" style="font-size:10px;padding:2px 6px" onclick="deleteNote(${i})">✕</button>
      </div>
    </div>`).join('');
}

function addNote() {
  const input = document.getElementById('noteInput');
  const text  = input.value.trim();
  if (!text) return;
  const notes = getNotes();
  notes.unshift({ text, date: new Date().toLocaleDateString('fr-FR', {day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit'}) });
  saveNotes(notes);
  input.value = '';
  document.getElementById('notesList').innerHTML = renderNotesList();
}

function deleteNote(i) {
  const notes = getNotes();
  notes.splice(i, 1);
  saveNotes(notes);
  document.getElementById('notesList').innerHTML = renderNotesList();
}

// ─── RECHERCHE GLOBALE ────────────────────────────────────────────────────────
let _searchTimer = null;
function globalSearchDebounce() {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(runGlobalSearch, 250);
}

async function runGlobalSearch() {
  const q = document.getElementById('globalSearchInput').value.trim();
  const dd = document.getElementById('globalSearchDropdown');
  if (q.length < 2) { dd.classList.remove('open'); return; }
  dd.innerHTML = '<div style="padding:12px 14px;color:var(--text3);font-size:13px">Recherche…</div>';
  dd.classList.add('open');
  const results = await api(`/api/search?q=${encodeURIComponent(q)}`);
  if (!results.length) {
    dd.innerHTML = '<div style="padding:12px 14px;color:var(--text3);font-size:13px">Aucun résultat</div>';
    return;
  }
  dd.innerHTML = results.map(r => `
    <div class="gsd-item" onclick="globalSearchSelect('${r.pid}')">
      <div class="gsd-icon">${r.type === 'patient' ? '👤' : '📋'}</div>
      <div>
        <div class="gsd-label">${r.label}</div>
        <div class="gsd-sub">${r.sub}</div>
      </div>
    </div>`).join('');
}

function globalSearchSelect(pid) {
  closeGlobalSearch();
  loadPatient(pid);
}

function closeGlobalSearch() {
  document.getElementById('globalSearchInput').value = '';
  document.getElementById('globalSearchDropdown').classList.remove('open');
}

document.addEventListener('click', e => {
  if (!e.target.closest('.global-search-wrap')) closeGlobalSearch();
});

function toggleRdvDetail(rdvId) {
  const el = document.getElementById('rdv-detail-' + rdvId);
  if (!el) return;
  const btn = el.closest('.rdv-card').querySelector('.btn-ghost');
  const open = el.style.display !== 'none';
  el.style.display = open ? 'none' : 'block';
  btn.textContent = open ? '+ infos' : '- infos';
}

async function clearActivite() {
  if (!confirm('Effacer tout l\'historique d\'activité ?')) return;
  await api('/api/notifications', 'DELETE');
  loadNotifications();
  showView('dashboard-medecin');
}

// ─── TABS ─────────────────────────────────────────────────────────────────────
function switchTab(tab, pid, btn) {
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-'+tab).classList.add('active');
}

// ─── MODALS ───────────────────────────────────────────────────────────────────
function openModal(id) { document.getElementById(id).classList.add('open'); }
function closeModal(id) {
  if (id) { document.getElementById(id)?.classList.remove('open'); }
  else { document.getElementById('modalDynamic')?.classList.remove('open'); }
}
document.querySelectorAll('.modal-overlay').forEach(el=>el.addEventListener('click',e=>{if(e.target===el)el.classList.remove('open');}));

/** Dynamic modal — showModal(title, bodyHTML, onConfirm, confirmOnly=false) */
function showModal(title, bodyHTML, onConfirm, confirmOnly=false) {
  let el = document.getElementById('modalDynamic');
  if (!el) {
    el = document.createElement('div');
    el.className = 'modal-overlay';
    el.id = 'modalDynamic';
    el.innerHTML = `<div class="modal" style="max-width:520px;width:90%">
      <div class="modal-header" style="display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid var(--border)">
        <h3 id="modalDynTitle" style="margin:0;font-size:15px"></h3>
        <button class="modal-close" onclick="closeModal()">×</button>
      </div>
      <div id="modalDynBody" style="padding:20px"></div>
      <div id="modalDynFooter" style="display:flex;justify-content:flex-end;gap:8px;padding:12px 20px;border-top:1px solid var(--border)"></div>
    </div>`;
    el.addEventListener('click', e => { if(e.target===el) closeModal(); });
    document.body.appendChild(el);
  }
  document.getElementById('modalDynTitle').textContent = title;
  document.getElementById('modalDynBody').innerHTML = bodyHTML;
  initPasswordToggles();
  const footer = document.getElementById('modalDynFooter');
  if (confirmOnly) {
    footer.innerHTML = `<button class="btn btn-primary btn-sm" onclick="if(window._dynConfirm)window._dynConfirm()">OK</button>`;
  } else {
    footer.innerHTML = `
      <button class="btn btn-ghost btn-sm" onclick="closeModal()">Annuler</button>
      <button class="btn btn-primary btn-sm" id="modalDynConfirmBtn">Confirmer</button>`;
    document.getElementById('modalDynConfirmBtn').onclick = onConfirm;
  }
  window._dynConfirm = onConfirm;
  el.classList.add('open');
}

// ─── API HELPER ───────────────────────────────────────────────────────────────
async function api(url, method='GET', body=null) {
  const opts = { method, headers:{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'}, credentials:'include' };
  if(body) opts.body = JSON.stringify(body);
  try {
    const r = await fetch(url, opts);
    if (r.status === 429) return {error: 'Trop de tentatives. Réessayez dans une minute.'};
    return await r.json();
  } catch(e) { return {error:e.message}; }
}

// ─── MOBILE SIDEBAR ───────────────────────────────────────────────────────────
function toggleMobileSidebar() {
  const sidebar  = document.getElementById('sidebar');
  const overlay  = document.getElementById('sidebarOverlay');
  const isOpen   = sidebar.classList.contains('mobile-open');
  sidebar.classList.toggle('mobile-open', !isOpen);
  overlay.classList.toggle('open', !isOpen);
}
function closeMobileSidebar() {
  document.getElementById('sidebar').classList.remove('mobile-open');
  document.getElementById('sidebarOverlay').classList.remove('open');
}

// ─── UTILS ────────────────────────────────────────────────────────────────────
function fmtDate(d) { return new Date(d).toLocaleDateString('fr-FR'); }
function fmtDateLong(d) { return new Date(d).toLocaleDateString('fr-FR',{day:'numeric',month:'long',year:'numeric'}).toUpperCase(); }
function escH(t) { const d=document.createElement('div'); d.textContent=t; return d.innerHTML.replace(/\n/g,'<br>'); }
function escJ(s) { return (s||'').replace(/'/g,"\\'").replace(/"/g,'\\"').replace(/\n/g,' '); }

