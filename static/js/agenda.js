// ─── AGENDA ───────────────────────────────────────────────────────────────────
// ─── AGENDA / CALENDRIER ──────────────────────────────────────────────────────
let _calYear, _calMonth, _allRdvs = [];

async function renderAgenda(c) {
  _allRdvs = await api('/api/rdv');
  const now = new Date();
  _calYear  = now.getFullYear();
  _calMonth = now.getMonth();
  _renderCalendar(c);
}

function _renderCalendar(c) {
  const today   = new Date().toISOString().slice(0,10);
  const months  = ['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'];
  const days    = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'];

  // Build day map for current month
  const rdvMap  = {};
  _allRdvs.forEach(r => { if (!rdvMap[r.date]) rdvMap[r.date] = []; rdvMap[r.date].push(r); });

  // Stats for header
  const confirmed = _allRdvs.filter(r => r.statut === 'confirmé').length;
  const pending   = _allRdvs.filter(r => r.statut === 'en_attente').length;
  const urgent    = _allRdvs.filter(r => r.urgent).length;

  // Calendar grid
  const firstDay = new Date(_calYear, _calMonth, 1);
  const lastDay  = new Date(_calYear, _calMonth + 1, 0);
  // Monday-based: 0=Mon … 6=Sun
  let startDow = firstDay.getDay(); // 0=Sun
  startDow = (startDow === 0) ? 6 : startDow - 1;

  let cells = '';
  // Empty cells before first day
  for (let i = 0; i < startDow; i++) cells += `<div class="cal-cell cal-empty"></div>`;

  for (let d = 1; d <= lastDay.getDate(); d++) {
    const dateStr = `${_calYear}-${String(_calMonth+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
    const dayRdvs = rdvMap[dateStr] || [];
    const isToday = dateStr === today;
    const hasUrgent = dayRdvs.some(r => r.urgent);
    const dots = dayRdvs.slice(0,4).map(r => {
      const col = r.urgent ? 'var(--red)' : r.statut==='confirmé' ? 'var(--teal)' : 'var(--amber)';
      return `<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${col}"></span>`;
    }).join('');
    cells += `
      <div class="cal-cell ${isToday?'cal-today':''} ${dayRdvs.length?'cal-has-rdv':''} ${hasUrgent?'cal-urgent':''}"
           onclick="calSelectDay('${dateStr}')">
        <div class="cal-day-num">${d}</div>
        ${dayRdvs.length ? `<div style="display:flex;gap:2px;flex-wrap:wrap;margin-top:2px">${dots}</div>` : ''}
        ${dayRdvs.length ? `<div style="margin-top:3px"><span style="background:${dayRdvs.some(r=>r.urgent)?'var(--red)':'var(--teal)'};color:#fff;font-size:10px;font-weight:700;padding:1px 6px;border-radius:8px">${dayRdvs.length}</span></div>` : ''}
      </div>`;
  }

  // Upcoming: today + tomorrow only
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0,10);
  const upcomingToday    = _allRdvs.filter(r => r.date === today    && r.statut !== 'annulé').sort((a,b) => a.heure.localeCompare(b.heure));
  const upcomingTomorrow = _allRdvs.filter(r => r.date === tomorrow && r.statut !== 'annulé').sort((a,b) => a.heure.localeCompare(b.heure));
  const upcoming = [...upcomingToday, ...upcomingTomorrow];

  c.innerHTML = `
    <style>
      .cal-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:4px; }
      .cal-header-day { text-align:center; font-size:10px; text-transform:uppercase; letter-spacing:1px; color:var(--text3); padding:6px 0; }
      .cal-cell { min-height:64px; border-radius:8px; padding:6px; background:var(--card); border:1px solid var(--border); cursor:pointer; transition:border-color .15s; }
      .cal-cell:hover { border-color:var(--teal); }
      .cal-cell.cal-empty { background:transparent; border:none; cursor:default; }
      .cal-cell.cal-today { border-color:var(--teal); background:var(--teal-dim); }
      .cal-cell.cal-has-rdv { }
      .cal-cell.cal-urgent { border-color:rgba(239,68,68,.5); }
      .cal-cell.cal-selected { border-color:var(--teal); box-shadow:0 0 0 2px rgba(14,165,160,.3); }
      .cal-day-num { font-size:12px; font-weight:600; color:var(--text2); }
      .cal-cell.cal-today .cal-day-num { color:var(--teal2); }
      .cal-day-panel { background:var(--card); border:1px solid var(--border); border-radius:var(--radius); padding:16px; }
      .cal-month-btn { font-size:15px;font-weight:700;color:var(--text);background:none;border:none;cursor:pointer;padding:4px 10px;border-radius:6px;transition:background .15s; }
      .cal-month-btn:hover { background:var(--bg2); }
      .cal-picker { position:absolute;z-index:100;background:var(--card);border:1px solid var(--border);border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.2);padding:14px;min-width:240px; }
      .cal-picker-months { display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:10px; }
      .cal-picker-month { padding:6px 4px;border-radius:6px;border:1px solid transparent;cursor:pointer;font-size:12px;text-align:center;color:var(--text2);transition:all .15s; }
      .cal-picker-month:hover { border-color:var(--teal);color:var(--teal2); }
      .cal-picker-month.active { background:var(--teal);color:#fff;border-color:var(--teal); }
    </style>

    <!-- Header stats -->
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px">
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <span style="display:inline-flex;align-items:center;gap:6px;background:var(--teal-dim);border:1px solid var(--teal);color:var(--teal2);border-radius:10px;padding:5px 12px;font-size:13px;font-weight:700">
          <span style="font-size:16px;font-weight:900;color:var(--teal)">${confirmed}</span> confirmé${confirmed>1?'s':''}
        </span>
        <span style="display:inline-flex;align-items:center;gap:6px;background:var(--amber-dim);border:1px solid var(--amber);color:var(--amber);border-radius:10px;padding:5px 12px;font-size:13px;font-weight:700">
          <span style="font-size:16px;font-weight:900">${pending}</span> en attente
        </span>
        ${urgent ? `<span style="display:inline-flex;align-items:center;gap:6px;background:var(--red-dim);border:1px solid var(--red);color:var(--red);border-radius:10px;padding:5px 12px;font-size:13px;font-weight:700">
          <span style="font-size:16px;font-weight:900">${urgent}</span> urgent${urgent>1?'s':''}
        </span>` : ''}
      </div>
      ${USER.role==='medecin'?`<button class="btn btn-primary btn-sm" onclick="openAddRdv(null)">+ Nouveau RDV</button>`:''}
    </div>

    <div class="cal-layout-wrap" style="display:grid;grid-template-columns:1fr 300px;gap:20px;align-items:start">
      <!-- Calendar -->
      <div>
        <!-- Month nav -->
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;position:relative">
          <button class="btn btn-ghost btn-sm" onclick="calNav(-1)">‹ Précédent</button>
          <div style="position:relative">
            <button class="cal-month-btn" onclick="calTogglePicker(event)">${months[_calMonth]} ${_calYear} ▾</button>
            <div id="calPicker" class="cal-picker" style="display:none;top:calc(100% + 6px);left:50%;transform:translateX(-50%)">
              <div style="display:flex;align-items:center;justify-content:space-between">
                <button class="btn btn-ghost btn-sm" onclick="calPickerYear(-1)">‹</button>
                <span id="calPickerYear" style="font-size:14px;font-weight:700;color:var(--text)">${_calYear}</span>
                <button class="btn btn-ghost btn-sm" onclick="calPickerYear(1)">›</button>
              </div>
              <div class="cal-picker-months">
                ${months.map((m,i)=>`<div class="cal-picker-month${i===_calMonth?' active':''}" onclick="calPickerSelect(${i})">${m.slice(0,3)}</div>`).join('')}
              </div>
            </div>
          </div>
          <button class="btn btn-ghost btn-sm" onclick="calNav(1)">Suivant ›</button>
        </div>
        <!-- Day headers -->
        <div class="cal-grid" style="margin-bottom:4px">
          ${days.map(d=>`<div class="cal-header-day">${d}</div>`).join('')}
        </div>
        <!-- Day cells -->
        <div class="cal-grid">${cells}</div>
      </div>

      <!-- Side panel -->
      <div>
        <div id="calDayPanel" class="cal-day-panel">
          <div style="font-size:11px;font-weight:700;color:var(--teal2);letter-spacing:1px;text-transform:uppercase;margin-bottom:10px;display:flex;align-items:center;gap:8px">
            RDV Proches
            ${upcoming.length ? `<span style="background:var(--teal);color:#fff;font-size:11px;font-weight:700;padding:2px 8px;border-radius:12px">${upcoming.length}</span>` : ''}
          </div>
          ${upcomingToday.length ? `<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--teal2);margin-bottom:6px">Aujourd'hui <span style="background:var(--teal-dim);padding:1px 6px;border-radius:6px">${upcomingToday.length}</span></div>${upcomingToday.map(r=>_rdvMiniCard(r)).join('')}` : ''}
          ${upcomingTomorrow.length ? `<div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--text2);margin-top:10px;margin-bottom:6px">Demain <span style="background:var(--bg2);padding:1px 6px;border-radius:6px">${upcomingTomorrow.length}</span></div>${upcomingTomorrow.map(r=>_rdvMiniCard(r)).join('')}` : ''}
          ${!upcoming.length ? '<div style="color:var(--text3);font-size:13px">Aucun RDV aujourd\'hui ni demain</div>' : ''}
        </div>
      </div>
    </div>`;
}

function _rdvMiniCard(r) {
  const col = r.urgent ? 'var(--red)' : r.statut==='confirmé' ? 'var(--teal)' : 'var(--amber)';
  return `
    <div style="padding:10px;border-radius:8px;background:var(--bg2);border:1px solid var(--border);margin-bottom:8px;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
        <span style="width:8px;height:8px;border-radius:50%;background:${col};flex-shrink:0"></span>
        <span style="font-size:12px;font-weight:600;color:var(--text);flex:1;cursor:${USER.role==='medecin'?'pointer':'default'}"
              ${USER.role==='medecin'?`onclick="loadPatient('${r.patient_id}')"`:''}>${r.heure} · ${_normRdvType(r.type)}</span>
        ${USER.role==='medecin'?`<button class="btn btn-ghost btn-sm" style="font-size:10px;padding:2px 7px" onclick="event.stopPropagation();openEditRdvAgenda('${r.id}')">✏</button>`:''}
      </div>
      <div style="font-size:11px;color:var(--text2);margin-left:16px">${r.patient_prenom||''} ${r.patient_nom||''}</div>
      <div style="font-size:11px;color:var(--text3);margin-left:16px">${fmtDate(r.date)} · <span style="color:${col}">${r.statut}</span></div>
      ${USER.role==='medecin'?`
        <div style="display:flex;gap:6px;margin-top:6px;margin-left:16px;flex-wrap:wrap">
          ${r.statut==='en_attente'?`
            <button class="btn btn-primary btn-sm" style="font-size:10px" onclick="event.stopPropagation();validerRdv('${r.id}','confirmé')">✓ Confirmer</button>
            <button class="btn btn-ghost btn-sm" style="font-size:10px" onclick="event.stopPropagation();validerRdv('${r.id}','annulé')">✗ Annuler</button>
          `:''}
          <button class="btn btn-ghost btn-sm" style="font-size:10px" onclick="event.stopPropagation();openMessageModal('${r.patient_id}','${r.id}','${escJ(_normRdvType(r.type))} — ${escJ(r.date)} ${escJ(r.heure)}')">✉ Message</button>
        </div>`:''}
    </div>`;
}

async function openEditRdvAgenda(rid) {
  const rdv = _allRdvs.find(r => r.id === rid);
  if (!rdv) return;
  const statutOptions = ['programmé','confirmé','annulé','en_attente'].map(s =>
    `<option value="${s}"${rdv.statut===s?' selected':''}>${s}</option>`).join('');
  showModal('Modifier le rendez-vous', `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
      <div><label class="lbl">Type</label>
        <select class="input" id="agEditType">
          ${['Consultation','Contrôle','Suivi glaucome','IVT','Chirurgie cataracte','Bilan rétine','Urgence','Bilan orthoptique','Laser','Pré-opératoire','Autre']
            .map(t=>`<option value="${t}"${rdv.type===t?' selected':''}>${t}</option>`).join('')}
        </select>
      </div>
      <div><label class="lbl">Statut</label><select class="input" id="agEditStatut">${statutOptions}</select></div>
      <div><label class="lbl">Date</label><input type="date" class="input" id="agEditDate" value="${rdv.date}"></div>
      <div><label class="lbl">Heure</label><input type="time" class="input" id="agEditHeure" value="${rdv.heure}"></div>
    </div>
    <div style="margin-bottom:12px"><label class="lbl">Notes</label>
      <textarea class="input" id="agEditNotes" rows="2">${escH(rdv.notes||'')}</textarea>
    </div>
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">
      <input type="checkbox" id="agEditUrgent" ${rdv.urgent?'checked':''}>
      <label for="agEditUrgent" style="font-size:13px;color:var(--text2)">Urgence</label>
    </div>
    <div style="display:flex;gap:8px;margin-top:16px">
      <button class="btn btn-primary" onclick="submitEditRdvAgenda('${rid}')">✓ Enregistrer</button>
      <button class="btn btn-ghost" onclick="closeModal()">Annuler</button>
    </div>
  `);
}

async function submitEditRdvAgenda(rid) {
  const body = {
    type:   document.getElementById('agEditType').value,
    statut: document.getElementById('agEditStatut').value,
    date:   document.getElementById('agEditDate').value,
    heure:  document.getElementById('agEditHeure').value,
    notes:  document.getElementById('agEditNotes').value,
    urgent: document.getElementById('agEditUrgent').checked ? 1 : 0,
  };
  const res = await api(`/api/rdv/${rid}`, 'PUT', body);
  if (res.ok) {
    closeModal();
    // Refresh
    _allRdvs = await api('/api/rdv');
    _renderCalendar(document.getElementById('mainContent'));
  } else {
    alert(res.error || 'Erreur lors de la mise à jour');
  }
}

function calNav(dir) {
  _calMonth += dir;
  if (_calMonth > 11) { _calMonth = 0; _calYear++; }
  if (_calMonth < 0)  { _calMonth = 11; _calYear--; }
  _renderCalendar(document.getElementById('mainContent'));
}

let _calPickerYear = null;
function calTogglePicker(e) {
  e.stopPropagation();
  const p = document.getElementById('calPicker');
  if (!p) return;
  const open = p.style.display !== 'none';
  p.style.display = open ? 'none' : 'block';
  if (!open) {
    _calPickerYear = _calYear;
    document.getElementById('calPickerYear').textContent = _calPickerYear;
    if (!_calPickerCloseHandler) {
      _calPickerCloseHandler = () => { const pp = document.getElementById('calPicker'); if (pp) pp.style.display = 'none'; };
      document.addEventListener('click', _calPickerCloseHandler);
    }
  }
}
let _calPickerCloseHandler = null;

function calPickerYear(dir) {
  _calPickerYear = (_calPickerYear || _calYear) + dir;
  const el = document.getElementById('calPickerYear');
  if (el) el.textContent = _calPickerYear;
}

function calPickerSelect(monthIdx) {
  _calMonth = monthIdx;
  _calYear = _calPickerYear || _calYear;
  const p = document.getElementById('calPicker');
  if (p) p.style.display = 'none';
  _renderCalendar(document.getElementById('mainContent'));
}

function calSelectDay(dateStr) {
  // Highlight selected cell
  document.querySelectorAll('.cal-cell').forEach(el => el.classList.remove('cal-selected'));
  event.currentTarget.classList.add('cal-selected');

  const panel = document.getElementById('calDayPanel');
  const dayRdvs = _allRdvs.filter(r => r.date === dateStr).sort((a,b) => a.heure.localeCompare(b.heure));
  panel.innerHTML = `
    <div style="font-size:12px;font-weight:600;color:var(--teal2);margin-bottom:12px">${fmtDateLong(dateStr).toUpperCase()}</div>
    ${dayRdvs.length ? dayRdvs.map(r => _rdvMiniCard(r)).join('') :
      '<div style="color:var(--text3);font-size:13px">Aucun rendez-vous ce jour</div>'}`;
}

// ─── QUESTIONS MÉDECIN ────────────────────────────────────────────────────────
async function renderQuestionsMedecin(c) {
  const questions_all = [];
  const patients = await api('/api/patients');
  const patientsMap = Object.fromEntries(patients.map(p => [p.id, p]));

  for (const pid of Object.keys(patientsMap)) {
    const qs = await api(`/api/patients/${pid}/questions`);
    if (!Array.isArray(qs)) continue;
    const p = patientsMap[pid];
    qs.forEach(q => questions_all.push({...q, patient_id: pid, patient_nom: `${p.prenom} ${p.nom}`}));
  }
  const pending = questions_all.filter(q => q.statut === 'en_attente');

  c.innerHTML = `
    <div style="margin-bottom:14px">
      <span class="badge badge-amber">${pending.length} en attente</span>
      <span class="badge badge-green" style="margin-left:6px">${questions_all.length - pending.length} répondues</span>
    </div>
    ${questions_all.length === 0 ? '<div style="color:var(--text3);text-align:center;padding:40px">Aucune question</div>' :
      questions_all.sort((a,b)=>a.statut==='en_attente'?-1:1).map(q=>`
        <div class="question-card ${q.statut==='en_attente'?'pending':'answered'}">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
            <div style="font-size:12px;color:var(--teal2);font-weight:600;cursor:pointer" onclick="loadPatient('${q.patient_id}')">👤 ${q.patient_nom} →</div>
            <span class="badge ${q.statut==='en_attente'?'badge-amber':'badge-green'}">${q.statut}</span>
          </div>
          <div class="q-text">❓ ${q.question}</div>
          <div class="q-date">${q.date}</div>
          ${q.reponse_ia?`<div class="ai-draft"><div class="ai-draft-label">🤖 Suggestion IA</div><div class="ai-draft-text">${q.reponse_ia}</div></div>`:''}
          ${q.statut==='en_attente'?`
            <div class="answer-area">
              <textarea class="input" id="rep-${q.id}" rows="3">${q.reponse_ia||''}</textarea>
              <div style="margin-top:8px;display:flex;gap:8px">
                <button class="btn btn-primary btn-sm" onclick="sendReponse('${q.patient_id}','${q.id}')">✓ Envoyer</button>
                <button class="btn btn-ghost btn-sm" onclick="sendReponseIA('${q.patient_id}','${q.id}')">✓ Valider IA</button>
              </div>
            </div>` :
            `<div style="margin-top:8px;display:flex;align-items:flex-start;gap:8px">
              <div style="flex:1;background:var(--green-dim);border-radius:8px;padding:8px 12px;font-size:12px;color:var(--text2)">✅ ${q.reponse}</div>
              <button class="btn btn-ghost btn-sm" style="color:var(--red);flex-shrink:0" title="Archiver" onclick="softDeleteQuestion('${q.patient_id}','${q.id}',this)">🗑</button>
            </div>`}
        </div>
      `).join('')}`;
}

// ─── LISTE PATIENTS ANONYMISÉE (ASSISTANT) ────────────────────────────────────
async function renderListePatientsAnon(c) {
  const patients = await api('/api/patients');
  c.innerHTML = `
    <div style="margin-bottom:14px;font-size:13px;color:var(--text2)">Vue anonymisée — ${patients.length} patients</div>
    ${patients.map(p=>`
      <div class="anon-card">
        <div class="anon-id">${p.code}</div>
        <div class="anon-info">
          <div style="font-size:13px;color:var(--text)">${p.sexe==='F'?'♀':'♂'} ${p.age} ans</div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:4px">
            ${p.antecedents.map(a=>`<span class="badge badge-teal" style="font-size:10px">${a}</span>`).join('')}
          </div>
        </div>
        <div style="font-size:12px;color:var(--text3);text-align:right">
          <div>${p.nb_rdv} RDV</div>
          <div>${p.nb_imagerie} images</div>
        </div>
      </div>
    `).join('')}`;
}

