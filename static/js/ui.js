// ─── TOAST / SNACKBAR ─────────────────────────────────────────────────────────
/**
 * showToast(message, type='info', duration=3500)
 * type: 'success' | 'error' | 'warning' | 'info'
 */
function showToast(message, type='info', duration=3500) {
  const icons = { success:'✅', error:'❌', warning:'⚠️', info:'ℹ️' };
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.innerHTML = `
    <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
    <span class="toast-msg">${message}</span>
    <button class="toast-close" onclick="this.closest('.toast').remove()">×</button>`;
  container.appendChild(t);
  if (duration > 0) {
    setTimeout(() => {
      t.classList.add('out');
      setTimeout(() => t.remove(), 280);
    }, duration);
  }
}

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
  const list = Array.isArray(patients) ? patients : [];

  // Populate quick-select dropdown
  const sel = document.getElementById('patientQuickSelect');
  if (sel) {
    sel.innerHTML = '<option value="">⚡ Accès rapide…</option>' +
      list.map(p => `<option value="${p.id}">${p.prenom} ${p.nom} (${p.id})</option>`).join('');
  }

  window._sidebarPatients = list;
  if (!window._selPats) window._selPats = [];

  const el = document.getElementById('patientListSidebar');
  if (!el) return;

  const selIds = new Set((window._selPats || []).map(p => p.id));
  el.innerHTML = list.map(p => {
    const dr = (_showAllPatients && p.medecin_id)
      ? MEDECINS.find(m => m.id === p.medecin_id) : null;
    const isChecked = selIds.has(p.id) ? 'checked' : '';
    const lastConsultBadge = _lastConsultBadge(p.last_consult);
    return `
      <div class="patient-mini ${currentPatientId===p.id?'active':''}" style="display:flex;align-items:center;gap:6px;padding-left:6px">
        <input type="checkbox" class="pat-check" id="patCheck_${p.id}" ${isChecked}
               style="width:14px;height:14px;accent-color:var(--teal);flex-shrink:0;cursor:pointer"
               onclick="event.stopPropagation();togglePatientSelection('${p.id}','${escJ(p.prenom+' '+p.nom)}')">
        <div style="flex:1;min-width:0" onclick="loadPatient('${p.id}')">
          <div class="pm-name">${p.prenom} ${p.nom}${p.linked?` <span style="font-size:9px;background:rgba(14,165,160,0.15);color:var(--teal2);padding:1px 5px;border-radius:6px;vertical-align:middle">RDV</span>`:''}</div>
          <div class="pm-id">${p.id}${dr?` · <span style="color:var(--teal2);font-size:10px">${dr.nom}</span>`:''}${lastConsultBadge}</div>
        </div>
        ${(p.nb_rdv_urgent||0)>0?`<span class="pm-badge">🚨 ${p.nb_rdv_urgent}</span>`:''}
      </div>`;
  }).join('') || '<div style="color:var(--text3);font-size:12px;padding:16px;text-align:center">Aucun patient</div>';
}

function _lastConsultBadge(isoDate) {
  if (!isoDate) return '';
  const d = new Date(isoDate);
  if (isNaN(d)) return '';
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  let txt, color;
  if (days <= 0)         { txt = "aujourd'hui"; color = 'var(--teal2)'; }
  else if (days === 1)   { txt = 'hier';        color = 'var(--teal2)'; }
  else if (days < 30)    { txt = `il y a ${days}j`; color = 'var(--teal2)'; }
  else if (days < 180)   { txt = `il y a ${Math.round(days/30)} mois`; color = 'var(--text3)'; }
  else                   { txt = `il y a ${Math.round(days/365)} an${days>=730?'s':''}`; color = 'var(--amber,#f59e0b)'; }
  return ` · <span style="color:${color};font-size:10px" title="Dernière consultation : ${isoDate}">${txt}</span>`;
}

function togglePatientSelection(pid, label) {
  if (!window._selPats) window._selPats = [];
  const idx = window._selPats.findIndex(p => p.id === pid);
  const cb = document.getElementById(`patCheck_${pid}`);
  if (cb?.checked) {
    if (idx === -1) window._selPats.push({ id: pid, label });
  } else {
    if (idx !== -1) window._selPats.splice(idx, 1);
  }
  _updatePatientActionBar();
}

function _updatePatientActionBar() {
  const count = (window._selPats || []).length;
  const bar = document.getElementById('patientActionBar');
  const lbl = document.getElementById('patActionLabel');
  const singles = document.querySelectorAll('.pat-action-single');
  if (bar) bar.style.display = count > 0 ? '' : 'none';
  if (lbl) lbl.textContent = `✔ ${count} sélectionné(s)`;
  singles.forEach(b => b.style.display = count === 1 ? '' : 'none');
  // Update select-all button label
  const btnSA = document.getElementById('btnSelectAll');
  if (btnSA) {
    const total = (window._sidebarPatients || []).length;
    btnSA.textContent = (count > 0 && count === total) ? '☑ Tout désélectionner' : '☐ Tout sélectionner';
  }
}

function toggleSelectAllPatients() {
  const list = window._sidebarPatients || [];
  const count = (window._selPats || []).length;
  const allSelected = count === list.length && list.length > 0;
  if (allSelected) {
    window._selPats = [];
    document.querySelectorAll('.pat-check').forEach(c => c.checked = false);
  } else {
    window._selPats = list.map(p => ({ id: p.id, label: p.prenom + ' ' + p.nom }));
    document.querySelectorAll('.pat-check').forEach(c => c.checked = true);
  }
  _updatePatientActionBar();
}

async function deleteSelectedPatients() {
  const sel = window._selPats || [];
  if (!sel.length) return;
  const names = sel.map(p => p.label).join(', ');
  if (!confirm(`Supprimer ${sel.length} patient(s) ?\n${names}`)) return;
  for (const p of sel) {
    await api(`/api/patients/${p.id}`, 'DELETE');
  }
  window._selPats = [];
  _updatePatientActionBar();
  loadPatientsSidebar();
}

async function _sidebarEditPatient() {
  const p = (window._selPats || [])[0];
  if (!p) return;
  await loadPatient(p.id);
  openEditPatient(p.id);
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
  if (res.ok) {
    closeModal('modalRdv');
    showView(currentView);
    loadNotifications();
    if (res.date_changed) _showRdvChangedDialog(rdvId, res);
  } else {
    alert(res.error || 'Erreur');
  }
}

function _showRdvChangedDialog(rdvId, res) {
  const oldStr = res.old_date
    ? new Date(res.old_date).toLocaleDateString('fr-FR', {weekday:'long',day:'numeric',month:'long',year:'numeric'})
      + (res.old_heure ? ` à ${res.old_heure}` : '')
    : '';
  const newStr = new Date(res.new_date).toLocaleDateString('fr-FR', {weekday:'long',day:'numeric',month:'long',year:'numeric'})
    + (res.new_heure ? ` à ${res.new_heure}` : '');

  showModal('📅 RDV modifié', `
    <div style="text-align:center;margin-bottom:18px">
      <div style="font-size:36px;margin-bottom:8px">📅</div>
      <div style="font-size:14px;font-weight:600;color:var(--text);margin-bottom:4px">Le rendez-vous a été modifié</div>
      ${oldStr ? `<div style="font-size:12px;color:var(--text3);text-decoration:line-through;margin-bottom:4px">${escH(oldStr)}</div>` : ''}
      <div style="font-size:14px;font-weight:700;color:var(--teal2)">${escH(newStr)}</div>
    </div>
    <p style="font-size:13px;color:var(--text2);text-align:center;margin-bottom:0">
      Souhaitez-vous informer le patient par email ?
    </p>
  `, async () => {
    const btn = document.getElementById('modalDynConfirmBtn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Envoi…'; }
    const r = await api(`/api/rdv/${rdvId}/notify-change`, 'POST', {
      old_date: res.old_date, old_heure: res.old_heure
    });
    closeModal();
    if (r.ok) showToast(r.message || 'Email envoyé au patient', 'success');
    else showToast(r.error || 'Erreur lors de l\'envoi', 'error');
  });

  // Relabel the confirm button
  setTimeout(() => {
    const btn = document.getElementById('modalDynConfirmBtn');
    if (btn) btn.textContent = '✉ Envoyer un email';
    const cancel = document.querySelector('#modalDynFooter .btn-ghost');
    if (cancel) cancel.textContent = 'Ne pas notifier';
  }, 0);
}

async function validerRdv(rdvId, statut) {
  await api(`/api/rdv/${rdvId}/valider`,'POST',{statut});
  showView(currentView);
  loadNotifications();
}

async function deleteRdv(rdvId) {
  if (!confirm('Supprimer ce rendez-vous ?')) return;
  const res = await api(`/api/rdv/${rdvId}`, 'DELETE');
  if (res && res.error) { alert(res.error); return; }
  showView(currentView);
  loadNotifications();
  showUndoToast('Rendez-vous supprimé.', async () => {
    await api(`/api/rdv/${rdvId}/restore`, 'POST');
    showView(currentView);
    loadNotifications();
  });
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

  // Badge unread message count on the patient Messages nav button
  if (USER && USER.role === 'patient') {
    const unreadMsgs = notifs.filter(n => !n.lu && n.type === 'message_medecin').length;
    const navBtn = document.getElementById('navMesMessages');
    if (navBtn) {
      const existing = navBtn.querySelector('.nb');
      if (unreadMsgs > 0) {
        if (existing) existing.textContent = unreadMsgs;
        else navBtn.insertAdjacentHTML('beforeend', `<span class="nb">${unreadMsgs}</span>`);
      } else if (existing) {
        existing.remove();
      }
    }
  }
  
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
    else if (type === 'message_medecin')           showView('mes-messages');
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

// ─── UNDO TOAST (for reversible deletes) ─────────────────────────────────────
/**
 * showUndoToast(message, onUndo, duration=8000)
 * Renders a toast with an "Annuler" button. If clicked within `duration` ms,
 * calls onUndo(). After the window expires the toast fades out.
 */
function showUndoToast(message, onUndo, duration = 8000) {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const t = document.createElement('div');
  t.className = 'toast toast-info';
  t.innerHTML = `
    <span class="toast-icon">↶</span>
    <span class="toast-msg" style="flex:1">${escH(message)}</span>
    <button class="btn btn-ghost btn-sm" style="padding:3px 10px;font-weight:600" data-undo>Annuler</button>
    <button class="toast-close" data-close>×</button>`;
  let called = false;
  const finish = () => {
    if (called) return; called = true;
    t.classList.add('out');
    setTimeout(() => t.remove(), 280);
  };
  t.querySelector('[data-undo]').addEventListener('click', async () => {
    if (called) return; called = true;
    try { await onUndo(); } catch(e) { console.error('undo failed', e); }
    t.classList.add('out');
    setTimeout(() => t.remove(), 280);
  });
  t.querySelector('[data-close]').addEventListener('click', finish);
  container.appendChild(t);
  setTimeout(finish, duration);
}

// ─── SESSION IDLE-TIMEOUT WARNING ────────────────────────────────────────────
// Shows a banner 2 min before the server-side session expires and lets the
// user extend by pinging /me. Reset on any meaningful user activity.
(function initSessionWarning() {
  let lastActivity = Date.now();
  let warningEl    = null;
  const WARN_BEFORE_MS = 2 * 60 * 1000;
  const markActive = () => { lastActivity = Date.now(); if (warningEl) dismissWarn(); };
  ['mousedown','keydown','scroll','touchstart'].forEach(ev =>
    document.addEventListener(ev, markActive, { passive: true })
  );
  function dismissWarn() {
    if (warningEl) { warningEl.remove(); warningEl = null; }
  }
  async function extendSession() {
    dismissWarn();
    lastActivity = Date.now();
    await api('/me');   // any authed response refreshes the server-side idle stamp
  }
  function showWarn(secondsLeft) {
    if (warningEl) return;
    warningEl = document.createElement('div');
    warningEl.style.cssText =
      'position:fixed;top:16px;left:50%;transform:translateX(-50%);' +
      'background:var(--amber-dim,#fff8e1);border:1px solid var(--amber,#f59e0b);' +
      'color:#92400e;padding:12px 18px;border-radius:10px;z-index:10000;' +
      'box-shadow:0 6px 20px rgba(0,0,0,.15);display:flex;gap:12px;align-items:center;font-size:13px';
    warningEl.setAttribute('role', 'alert');
    warningEl.innerHTML = `
      <span>⏱ Votre session expirera dans ${Math.ceil(secondsLeft/60)} min.</span>
      <button class="btn btn-primary btn-sm" id="sessionExtendBtn">Rester connecté</button>`;
    document.body.appendChild(warningEl);
    warningEl.querySelector('#sessionExtendBtn').onclick = extendSession;
  }
  setInterval(() => {
    if (typeof USER === 'undefined' || !USER || !USER.authenticated) return;
    const idleMin = Number(USER.session_idle_timeout || 60);
    const idleMs  = idleMin * 60 * 1000;
    const elapsed = Date.now() - lastActivity;
    const remaining = idleMs - elapsed;
    if (remaining <= 0) { dismissWarn(); return; }         // backend will clear
    if (remaining <= WARN_BEFORE_MS) showWarn(remaining / 1000);
  }, 15000);
})();

// ─── GLOBAL KEYBOARD SHORTCUTS (Ctrl/Cmd+K opens global search) ──────────────
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    const input = document.getElementById('globalSearchInput');
    const wrap  = document.getElementById('globalSearchWrap');
    if (input && wrap && wrap.style.display !== 'none') {
      e.preventDefault();
      input.focus();
      input.select();
    }
  }
});

// ─── UTILS ────────────────────────────────────────────────────────────────────
function fmtDate(d) { return new Date(d).toLocaleDateString('fr-FR'); }
function fmtDateLong(d) { return new Date(d).toLocaleDateString('fr-FR',{day:'numeric',month:'long',year:'numeric'}).toUpperCase(); }
function escH(t) { const d=document.createElement('div'); d.textContent=t; return d.innerHTML.replace(/\n/g,'<br>'); }
function escJ(s) { return (s||'').replace(/'/g,"\\'").replace(/"/g,'\\"').replace(/\n/g,' '); }

