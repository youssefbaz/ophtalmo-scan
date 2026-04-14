// ─── CREDENTIALS DISPLAY HELPER ──────────────────────────────────────────────
function _showCredentialsModal(fullName, creds, pid) {
  const emailNote = creds.email_sent
    ? '<div style="background:var(--teal-dim);border:1px solid var(--teal);border-radius:8px;padding:10px 14px;font-size:12px;color:var(--teal2);margin-top:12px">✉️ Les identifiants ont été envoyés par email au patient.</div>'
    : '<div style="background:var(--amber-dim);border:1px solid var(--amber);border-radius:8px;padding:10px 14px;font-size:12px;color:var(--amber);margin-top:12px">⚠️ Aucun email envoyé (pas d\'adresse email ou SMTP non configuré). Communiquez ces identifiants manuellement.</div>';
  showModal('Compte patient créé ✓', `
    <div style="text-align:center;padding:8px 0 14px">
      <div style="font-size:40px;margin-bottom:8px">✅</div>
      <p style="color:var(--text2);font-size:13px;margin-bottom:16px">Compte créé pour <b>${fullName}</b></p>
    </div>
    <div style="background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:16px;font-size:14px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <span style="color:var(--text3)">Identifiant</span>
        <span style="font-family:monospace;font-weight:600">${creds.username}</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
        <span style="color:var(--text3)">Mot de passe</span>
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-family:monospace;font-weight:600" id="credPwDisplay">${creds.password}</span>
          <button class="btn btn-ghost btn-sm" style="padding:3px 8px;font-size:11px"
            onclick="navigator.clipboard.writeText('${creds.password}');this.textContent='✓'">📋</button>
        </div>
      </div>
    </div>
    ${emailNote}
  `, () => { closeModal(); if(pid) loadPatient(pid); }, true);
}

// ─── PATIENT ACCOUNT CREATION ──────────────────────────────────────────────

async function sendPatientInvite(pid) {
  const res = await api(`/api/patients/${pid}/send-invite`, 'POST');
  if (res.ok) {
    alert('📧 Lien d\'inscription envoyé par email.');
  } else {
    alert(res.error || 'Erreur lors de l\'envoi du lien.');
  }
}

async function openCreateAccount(pid, fullName, patientEmail) {
  const sugUser = 'patient.' + fullName.toLowerCase().replace(/\s+/g,'.').replace(/[^a-z0-9.]/g,'');
  const sugPass = Math.random().toString(36).slice(2,10) + Math.random().toString(36).slice(2,6);
  showModal('Créer un compte patient', `
    <p style="font-size:13px;color:var(--text2);margin-bottom:14px">
      Un compte permettra à <b>${fullName}</b> de consulter ses données et poser des questions depuis l'application.
    </p>
    <div class="form-group">
      <label class="lbl">Email * <span style="font-size:11px;color:var(--text2)">(les identifiants seront envoyés à cette adresse)</span></label>
      <input id="acc-email" class="input" type="email" placeholder="patient@email.com" value="${escH(patientEmail||'')}" required>
    </div>
    <div class="form-group">
      <label class="lbl">Nom d'utilisateur</label>
      <input id="acc-user" class="input" value="${sugUser}">
    </div>
    <div class="form-group">
      <label class="lbl">Mot de passe</label>
      <div style="display:flex;gap:8px">
        <input id="acc-pass" class="input" value="${sugPass}">
        <button class="btn btn-ghost btn-sm" onclick="document.getElementById('acc-pass').select();document.execCommand('copy');this.textContent='✓ Copié'" style="white-space:nowrap">📋 Copier</button>
      </div>
    </div>
  `, async () => {
    const email = document.getElementById('acc-email').value.trim();
    if (!email || !email.includes('@')) {
      showToast('L\'adresse email est obligatoire.', 'error'); return false;
    }
    const res = await api(`/api/patients/${pid}/create-account`, 'POST', {
      username: document.getElementById('acc-user').value.trim(),
      password: document.getElementById('acc-pass').value.trim(),
      email
    });
    if (res.ok) {
      closeModal();
      _showCredentialsModal(fullName, res, pid);
    } else {
      showToast(res.error || 'Erreur création compte', 'error');
    }
  });
}

// ─── SMS REMINDERS ─────────────────────────────────────────────────────────


async function triggerEmailReminders() {
  if (!confirm('Envoyer les rappels email pour les RDV de demain ?')) return;
  const res = await api('/api/email/send-reminders', 'POST');
  if (res.ok) alert(`${res.sent} rappel(s) email envoyé(s).`);
  else alert(res.error || 'Erreur envoi email');
}

// ─── TODAY / SALLE D'ATTENTE ──────────────────────────────────────────────────

async function _updateTodayBadge() {
  const rdvs = await api('/api/rdv');
  const today = new Date().toISOString().slice(0,10);
  const count = rdvs.filter(r => r.date === today && r.statut !== 'annulé').length;
  const btn   = document.getElementById('navToday');
  if (!btn) return;
  const existing = btn.querySelector('.nb');
  if (existing) existing.remove();
  if (count > 0) {
    const badge = document.createElement('span');
    badge.className = 'nb amber';
    badge.textContent = count;
    btn.appendChild(badge);
  }
}

async function renderTodayView(c) {
  const rdvs = await api('/api/rdv');
  const today = new Date().toISOString().slice(0,10);
  const now   = new Date().toTimeString().slice(0,5);
  const todayRdvs = rdvs.filter(r => r.date === today).sort((a,b) => a.heure.localeCompare(b.heure));

  const done      = todayRdvs.filter(r => r.statut === 'terminé').length;
  const enCours   = todayRdvs.filter(r => r.statut === 'en_cours').length;
  const arrive    = todayRdvs.filter(r => r.statut === 'arrivé').length;
  const restants  = todayRdvs.filter(r => !['terminé','annulé'].includes(r.statut)).length;

  const statutBadge = s => {
    const map = {
      'confirmé':  ['badge-teal',  'Confirmé'],
      'programmé': ['badge-teal',  'Programmé'],
      'en_attente':['badge-amber', 'En attente'],
      'arrivé':    ['', 'Arrivé'],
      'en_cours':  ['badge-amber', 'En consultation'],
      'terminé':   ['badge-green', 'Terminé'],
      'annulé':    ['badge-red',   'Annulé'],
    };
    const [cls, label] = map[s] || ['', s];
    return `<span class="badge ${cls}" style="${s==='arrivé'?'background:rgba(59,130,246,.15);color:#93c5fd;border-color:rgba(59,130,246,.3)':''}">${label}</span>`;
  };

  const checkinButtons = r => {
    const btns = [];
    if (!['terminé','annulé'].includes(r.statut)) {
      if (r.statut !== 'arrivé'   && r.statut !== 'en_cours') btns.push(`<button class="btn btn-ghost btn-sm" style="font-size:11px;color:#93c5fd" onclick="setCheckin('${r.id}','arrivé')">✓ Arrivé</button>`);
      if (r.statut !== 'en_cours' && r.statut !== 'terminé')   btns.push(`<button class="btn btn-amber btn-sm" style="font-size:11px" onclick="setCheckin('${r.id}','en_cours')">▶ En cours</button>`);
      btns.push(`<button class="btn btn-primary btn-sm" style="font-size:11px" onclick="setCheckin('${r.id}','terminé')">✓ Terminé</button>`);
    }
    btns.push(`<button class="btn btn-ghost btn-sm" style="font-size:11px" onclick="openEditRdvModal('${r.id}')">✏</button>`);
    btns.push(`<button class="btn btn-ghost btn-sm" style="font-size:11px;opacity:.5" onclick="deleteRdv('${r.id}')">🗑</button>`);
    return btns.join('');
  };

  const cardClass = r => {
    if (r.statut === 'terminé') return 'checkin-card statut-termine';
    if (r.statut === 'en_cours') return 'checkin-card statut-en_cours';
    if (r.statut === 'arrivé') return 'checkin-card statut-arrive';
    if (r.statut === 'annulé') return 'checkin-card statut-annule';
    return 'checkin-card';
  };

  c.innerHTML = `
    <div style="margin-bottom:18px">
      <div style="font-size:13px;color:var(--text2);margin-bottom:12px">
        ${new Date().toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long',year:'numeric'}).toUpperCase()}
      </div>
      <div class="grid-4" style="margin-bottom:0">
        <div class="stat-card teal"><div class="stat-label">Total aujourd'hui</div><div class="stat-value">${todayRdvs.length}</div></div>
        <div class="stat-card blue"><div class="stat-label">Restants</div><div class="stat-value">${restants}</div></div>
        <div class="stat-card amber"><div class="stat-label">En cours</div><div class="stat-value">${enCours + arrive}</div></div>
        <div class="stat-card" style="--teal:var(--green)"><div class="stat-label">Terminés</div><div class="stat-value" style="color:var(--green)">${done}</div></div>
      </div>
    </div>

    <div style="display:flex;gap:8px;margin-bottom:18px;flex-wrap:wrap">
      <button class="btn btn-primary btn-sm" onclick="openAddRdv(null)">+ Nouveau RDV</button>
      <button class="btn btn-ghost btn-sm" onclick="triggerEmailReminders()" title="Rappels email demain">📧 Email demain</button>
      <button class="btn btn-ghost btn-sm" onclick="renderTodayView(document.getElementById('mainContent'))" title="Actualiser">↺ Actualiser</button>
    </div>

    ${todayRdvs.length === 0 ?
      '<div style="color:var(--text3);text-align:center;padding:60px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius)"><div style="font-size:40px;margin-bottom:12px">🏥</div><div>Aucun rendez-vous aujourd\'hui</div></div>' :
      todayRdvs.map(r => {
        const isPast = r.heure < now && !['terminé','en_cours'].includes(r.statut);
        return `
        <div class="${cardClass(r)}">
          <div class="checkin-time ${r.heure < now ? 'past' : ''}">${r.heure}</div>
          <div style="flex:1;min-width:0;cursor:pointer" onclick="loadPatient('${r.patient_id}')">
            <div style="font-size:14px;font-weight:600;color:var(--text)">${r.urgent?'🚨 ':''}${r.patient_prenom||''} ${r.patient_nom||''}</div>
            <div style="font-size:12px;color:var(--text2);margin-top:2px">${_normRdvType(r.type)} · ${r.medecin}</div>
            ${r.notes ? `<div style="font-size:11px;color:var(--text3);margin-top:2px">📝 ${escH(r.notes)}</div>` : ''}
          </div>
          <div style="display:flex;flex-direction:column;align-items:flex-end;gap:6px">
            ${statutBadge(r.statut)}
            ${isPast && r.statut !== 'terminé' ? '<span style="font-size:10px;color:var(--amber)">⚠ En retard</span>' : ''}
            <div style="display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end">${checkinButtons(r)}</div>
          </div>
        </div>`;
      }).join('')
    }`;
}

async function setCheckin(rdvId, statut) {
  const res = await api(`/api/rdv/${rdvId}`, 'PUT', {statut});
  if (res.ok) {
    renderTodayView(document.getElementById('mainContent'));
    _updateTodayBadge();
  }
}

