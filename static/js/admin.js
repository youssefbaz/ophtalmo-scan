// ─── ADMIN: PENDING BADGE ─────────────────────────────────────────────────────
async function _updatePendingBadge() {
  const stats = await api('/api/admin/stats');
  const badge = document.getElementById('pendingBadge');
  if (!badge) return;
  if (stats && stats.pending > 0) {
    badge.textContent = stats.pending;
    badge.style.display = 'inline';
  } else {
    badge.style.display = 'none';
  }
}

// ─── ADMIN: DASHBOARD ─────────────────────────────────────────────────────────
async function renderAdminDashboard(c) {
  c.innerHTML = '<div style="color:var(--text3);padding:40px;text-align:center">Chargement…</div>';
  const [stats, smtp] = await Promise.all([api('/api/admin/stats'), api('/api/admin/smtp-status')]);
  c.innerHTML = `
    <div class="welcome-banner">
      <div class="welcome-avatar">🛡</div>
      <div>
        <div class="welcome-name">Administration — OphtalmoScan</div>
        <div class="welcome-sub">Gestion des comptes et des accès</div>
      </div>
    </div>
    <div class="grid-4" style="margin-bottom:28px">
      <div class="stat-card amber" style="cursor:pointer" onclick="showView('admin-pending')">
        <div class="stat-label">En attente</div>
        <div class="stat-value">${stats.pending}</div>
      </div>
      <div class="stat-card teal" style="cursor:pointer" onclick="showView('admin-users')">
        <div class="stat-label">Médecins actifs</div>
        <div class="stat-value">${stats.medecins}</div>
      </div>
      <div class="stat-card blue">
        <div class="stat-label">Patients</div>
        <div class="stat-value">${stats.patients}</div>
      </div>
      <div class="stat-card red">
        <div class="stat-label">Désactivés</div>
        <div class="stat-value">${stats.inactive}</div>
      </div>
    </div>
    ${stats.pending > 0 ? `
    <div style="background:var(--amber-dim);border:1px solid var(--amber);border-radius:var(--radius);padding:16px 20px;display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
      <div>
        <div style="font-weight:600;color:var(--amber);margin-bottom:2px">⏳ ${stats.pending} compte${stats.pending>1?'s':''} en attente de validation</div>
        <div style="font-size:13px;color:var(--text2)">Des médecins ont fait une demande de création de compte.</div>
      </div>
      <button class="btn btn-primary btn-sm" onclick="showView('admin-pending')">Voir les demandes</button>
    </div>` : ''}
    <div class="section-title" style="margin-bottom:14px">Actions rapides</div>
    <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px">
      <button class="btn btn-primary" onclick="showView('admin-pending')">⏳ Valider des comptes</button>
      <button class="btn btn-ghost" onclick="showView('admin-users')">👥 Gérer les utilisateurs</button>
      <button class="btn btn-ghost" onclick="showView('admin-create-medecin')">🩺 Créer un médecin</button>
      <button class="btn btn-ghost" onclick="showView('admin-create-patient')">🧑 Créer un patient</button>
    </div>
    <div class="section-title" style="margin-bottom:14px">Configuration email (SMTP)</div>
    <div class="card" style="padding:18px 20px;margin-bottom:0">
      <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
        <div style="font-size:22px">${smtp.configured ? '✅' : '❌'}</div>
        <div style="flex:1">
          <div style="font-weight:600;margin-bottom:4px">
            ${smtp.configured ? 'SMTP configuré' : 'SMTP non configuré'}
          </div>
          ${smtp.configured ? `
          <div style="font-size:12px;color:var(--text2);display:flex;flex-wrap:wrap;gap:12px">
            <span>Serveur : <strong>${smtp.host}:${smtp.port}</strong></span>
            <span>Compte : <strong>${smtp.user}</strong></span>
            <span>Expéditeur : <strong>${smtp.from}</strong></span>
          </div>` : `
          <div style="font-size:12px;color:var(--text2)">
            Définissez SMTP_HOST, SMTP_USER et SMTP_PASSWORD dans le fichier <code>.env</code>.
          </div>`}
        </div>
        ${smtp.configured ? `
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <input class="form-input" id="smtpTestTo" placeholder="email de test..." style="width:200px;padding:6px 10px;font-size:13px">
          <button class="btn btn-ghost btn-sm" onclick="adminTestSmtp()">Envoyer test</button>
        </div>` : ''}
      </div>
      <div id="smtpTestMsg" style="margin-top:10px"></div>
    </div>`;
}

async function adminTestSmtp() {
  const to    = document.getElementById('smtpTestTo')?.value.trim();
  const msgEl = document.getElementById('smtpTestMsg');
  if (!to || !to.includes('@')) {
    msgEl.innerHTML = '<div class="auth-msg auth-msg-error">Entrez une adresse email valide.</div>'; return;
  }
  msgEl.innerHTML = '<div style="color:var(--text3);font-size:13px">Envoi en cours…</div>';
  const res = await api('/api/admin/test-email', 'POST', {to});
  if (res.ok) {
    msgEl.innerHTML = `<div class="auth-msg auth-msg-success">${res.message}</div>`;
  } else {
    msgEl.innerHTML = `<div class="auth-msg auth-msg-error">${res.error || 'Erreur inconnue'}</div>`;
  }
}

// ─── ADMIN: PENDING ACCOUNTS ──────────────────────────────────────────────────
async function renderAdminPending(c) {
  c.innerHTML = '<div style="color:var(--text3);padding:40px;text-align:center">Chargement…</div>';
  const users = await api('/api/admin/users/pending');
  if (!users || users.length === 0) {
    c.innerHTML = `
      <div style="text-align:center;padding:60px 20px">
        <div style="font-size:48px;margin-bottom:12px">✅</div>
        <div style="font-size:18px;color:var(--text);margin-bottom:8px">Aucun compte en attente</div>
        <div style="color:var(--text3);font-size:14px">Toutes les demandes ont été traitées.</div>
      </div>`;
    return;
  }
  c.innerHTML = `
    <div id="pendingList">
      ${users.map(u => _renderAdminUserCard(u, true)).join('')}
    </div>`;
}

function _renderAdminUserCard(u, withActions) {
  const statusColor = {active:'badge-teal',pending:'badge-amber',inactive:'badge-red'}[u.status] || 'badge-amber';
  const isChecked = (window._selAdminUsers || []).some(s => s.id === u.id) ? 'checked' : '';
  return `
    <div class="card" style="margin-bottom:14px;padding:18px 20px;transition:border-color .15s${isChecked?';border-color:var(--teal)':''}" id="userCard_${u.id}">
      <div style="display:flex;align-items:flex-start;gap:14px;flex-wrap:wrap">
        <div style="display:flex;flex-direction:column;align-items:center;gap:8px;flex-shrink:0">
          <input type="checkbox" id="userCheck_${u.id}" class="user-check" ${isChecked}
                 style="width:16px;height:16px;accent-color:var(--teal);cursor:pointer"
                 onclick="toggleAdminUserSelection('${u.id}','${(u.prenom||'').replace(/'/g,"\\'")} ${(u.nom||'').replace(/'/g,"\\'")}')">
          <div style="width:44px;height:44px;border-radius:50%;background:var(--teal-dim);border:2px solid var(--teal);display:flex;align-items:center;justify-content:center;font-size:20px">
            ${u.role === 'medecin' ? '🩺' : '👤'}
          </div>
        </div>
        <div style="flex:1;min-width:200px">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px">
            <strong style="font-size:15px">${u.prenom || ''} ${u.nom || ''}</strong>
            <span class="badge ${statusColor}">${u.status}</span>
            <span class="badge badge-teal" style="background:var(--teal-dim);color:var(--teal2)">${u.role}</span>
          </div>
          <div style="font-size:13px;color:var(--text2);display:flex;flex-wrap:wrap;gap:12px">
            <span>👤 ${u.username}</span>
            ${u.role === 'medecin' && u.medecin_code ? `<span style="background:var(--teal-dim);color:var(--teal2);padding:1px 7px;border-radius:6px;font-weight:600">${u.medecin_code}</span>` : ''}
            ${u.email ? `<span>✉️ ${u.email}</span>` : ''}
            ${u.organisation ? `<span>🏥 ${u.organisation}</span>` : ''}
            ${u.date_naissance ? `<span>🎂 ${u.date_naissance}</span>` : ''}
          </div>
          <div style="font-size:11px;color:var(--text3);margin-top:4px">Créé le ${u.created_at ? u.created_at.slice(0,10) : '—'}</div>
        </div>
        <div style="display:flex;gap:8px;flex-shrink:0;align-items:center;flex-wrap:wrap">
          ${withActions ? `
            <button class="btn btn-primary btn-sm" onclick="adminValidate('${u.id}')">✅ Valider</button>
            <button class="btn btn-sm" style="background:var(--red-dim);color:var(--red);border-color:var(--red)" onclick="adminDeactivate('${u.id}','${u.prenom} ${u.nom}')">🔒 Désactiver</button>
          ` : `
            ${u.status === 'pending' ? `<button class="btn btn-primary btn-sm" onclick="adminValidate('${u.id}')">✅ Valider</button>` : ''}
            ${u.status === 'active' ? `<button class="btn btn-sm" style="background:var(--red-dim);color:var(--red);border-color:var(--red)" onclick="adminDeactivate('${u.id}','${u.prenom} ${u.nom}')">🔒 Désactiver</button>` : ''}
            ${u.status !== 'active' ? `<button class="btn btn-ghost btn-sm" onclick="adminActivate('${u.id}')">🔓 Activer</button>` : ''}
          `}
          <button class="btn btn-ghost btn-sm" onclick="adminOpenEditUser('${u.id}')">✏️ Modifier</button>
        </div>
      </div>
    </div>`;
}

async function adminValidate(uid) {
  const res = await api(`/api/admin/users/${uid}/validate`, 'POST');
  if (res.ok) { _updatePendingBadge(); showView(currentView); }
  else alert(res.error || 'Erreur');
}

async function adminDeactivate(uid, name) {
  if (!confirm(`Désactiver le compte de ${name} ?`)) return;
  const res = await api(`/api/admin/users/${uid}/deactivate`, 'POST');
  if (res.ok) { _updatePendingBadge(); showView(currentView); }
  else alert(res.error || 'Erreur');
}

async function adminActivate(uid) {
  const res = await api(`/api/admin/users/${uid}/activate`, 'POST');
  if (res.ok) { _updatePendingBadge(); showView(currentView); }
  else alert(res.error || 'Erreur');
}

async function adminOpenEditUser(uid) {
  const content = document.getElementById('modalAdminEditUserContent');
  content.innerHTML = '<div style="color:var(--text3);padding:30px;text-align:center">Chargement…</div>';
  openModal('modalAdminEditUser');

  const u = await api(`/api/admin/users/${uid}`);
  if (u.error) {
    content.innerHTML = `<div style="color:var(--red);padding:20px">${u.error}</div>`;
    return;
  }

  const isMedecin = u.role === 'medecin';
  const esc = v => (v || '').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  content.innerHTML = `
    <div id="adminEditMsg" style="margin-bottom:10px"></div>
    <input type="hidden" id="adminEditUid" value="${esc(u.id)}">
    <div style="display:flex;gap:12px">
      <div class="form-group" style="flex:1">
        <label class="form-label">Nom *</label>
        <input class="form-input" id="adminEditNom" value="${esc(u.nom)}">
      </div>
      <div class="form-group" style="flex:1">
        <label class="form-label">Prénom *</label>
        <input class="form-input" id="adminEditPrenom" value="${esc(u.prenom)}">
      </div>
    </div>
    <div class="form-group">
      <label class="form-label">Email</label>
      <input class="form-input" id="adminEditEmail" type="email" value="${esc(u.email)}">
    </div>
    ${isMedecin ? `
    <div class="form-group">
      <label class="form-label">Organisation / Clinique</label>
      <input class="form-input" id="adminEditOrg" value="${esc(u.organisation)}">
    </div>` : `
    <div class="form-group">
      <label class="form-label">Date de naissance</label>
      <input class="form-input" id="adminEditDdn" type="date" value="${esc(u.date_naissance)}">
    </div>`}
    <div class="form-group">
      <label class="form-label">Statut</label>
      <select class="form-input" id="adminEditStatus">
        <option value="active"   ${u.status==='active'   ?'selected':''}>Actif</option>
        <option value="inactive" ${u.status==='inactive' ?'selected':''}>Inactif (désactivé)</option>
        <option value="pending"  ${u.status==='pending'  ?'selected':''}>En attente</option>
      </select>
    </div>
    <div style="display:flex;gap:10px;margin-top:18px">
      <button class="btn btn-primary" onclick="adminSaveEditUser()">💾 Enregistrer</button>
      <button class="btn btn-ghost" onclick="closeModal('modalAdminEditUser')">Annuler</button>
    </div>
    <hr style="border-color:var(--border);margin:22px 0">
    <div style="font-size:13px;font-weight:600;color:var(--text2);margin-bottom:10px">🔑 Réinitialiser le mot de passe</div>
    <div style="display:flex;gap:10px;align-items:flex-end">
      <div class="form-group" style="flex:1;margin-bottom:0">
        <label class="form-label">Nouveau mot de passe (12+ car., maj, chiffre, spécial)</label>
        <input class="form-input" id="adminEditNewPw" type="password" placeholder="Nouveau mot de passe" autocomplete="new-password">
      </div>
      <button class="btn btn-ghost btn-sm" style="flex-shrink:0;margin-bottom:1px" onclick="adminResetUserPassword()">Appliquer</button>
    </div>
    <div id="adminEditPwMsg" style="margin-top:6px;font-size:12px"></div>
    <hr style="border-color:var(--border);margin:22px 0">
    <div style="font-size:13px;font-weight:600;color:var(--red);margin-bottom:10px">⚠️ Zone de danger</div>
    <button class="btn btn-sm" style="background:var(--red-dim);color:var(--red);border-color:var(--red)"
            onclick="adminDeleteUser('${esc(u.id)}','${esc(u.prenom)} ${esc(u.nom)}')">
      🗑️ Supprimer ce compte
    </button>
  `;
}

async function adminSaveEditUser() {
  const uid    = document.getElementById('adminEditUid').value;
  const nom    = document.getElementById('adminEditNom').value.trim();
  const prenom = document.getElementById('adminEditPrenom').value.trim();
  const email  = document.getElementById('adminEditEmail').value.trim();
  const status = document.getElementById('adminEditStatus').value;
  const org    = document.getElementById('adminEditOrg')?.value.trim() || '';
  const ddn    = document.getElementById('adminEditDdn')?.value.trim() || '';
  const msgEl  = document.getElementById('adminEditMsg');

  if (!nom || !prenom) {
    msgEl.innerHTML = '<span style="color:var(--red)">Nom et prénom requis.</span>';
    return;
  }
  const res = await api(`/api/admin/users/${uid}`, 'PUT', {
    nom, prenom, email, status, organisation: org, date_naissance: ddn
  });
  if (res.ok) {
    msgEl.innerHTML = '<span style="color:var(--teal2)">✅ Modifications enregistrées.</span>';
    _updatePendingBadge();
    setTimeout(() => { closeModal('modalAdminEditUser'); showView(currentView); }, 800);
  } else {
    msgEl.innerHTML = `<span style="color:var(--red)">${res.error || 'Erreur'}</span>`;
  }
}

async function adminResetUserPassword() {
  const uid   = document.getElementById('adminEditUid').value;
  const pw    = document.getElementById('adminEditNewPw').value;
  const msgEl = document.getElementById('adminEditPwMsg');
  const res   = await api(`/api/admin/users/${uid}/reset-password`, 'POST', { new_password: pw });
  if (res.ok) {
    msgEl.innerHTML = '<span style="color:var(--teal2)">✅ Mot de passe réinitialisé.</span>';
    document.getElementById('adminEditNewPw').value = '';
  } else {
    msgEl.innerHTML = `<span style="color:var(--red)">${res.error || 'Erreur'}</span>`;
  }
}

async function adminDeleteUser(uid, name) {
  if (!confirm(`Supprimer définitivement le compte de ${name} ?\n\nCette action est irréversible.`)) return;
  const res = await api(`/api/admin/users/${uid}`, 'DELETE');
  if (res.ok) {
    closeModal('modalAdminEditUser');
    _updatePendingBadge();
    showView(currentView);
  } else {
    alert(res.error || 'Erreur lors de la suppression.');
  }
}

function toggleAdminUserSelection(uid, label) {
  if (!window._selAdminUsers) window._selAdminUsers = [];
  const checkbox = document.getElementById(`userCheck_${uid}`);
  const card     = document.getElementById(`userCard_${uid}`);
  if (checkbox?.checked) {
    if (!window._selAdminUsers.find(u => u.id === uid)) window._selAdminUsers.push({ id: uid, label });
    if (card) card.style.borderColor = 'var(--teal)';
  } else {
    window._selAdminUsers = window._selAdminUsers.filter(u => u.id !== uid);
    if (card) card.style.borderColor = '';
  }
  _updateAdminActionBar();
}

function _updateAdminActionBar() {
  const bar = document.getElementById('adminUserActionBar');
  if (!bar) return;
  const sel = window._selAdminUsers || [];
  if (sel.length === 0) { bar.style.display = 'none'; return; }
  bar.style.display = 'flex';
  const countEl  = bar.querySelector('.sel-count');
  const modifyBtn = bar.querySelector('.admin-modify-btn');
  if (countEl)  countEl.textContent = sel.length === 1 ? sel[0].label : `${sel.length} utilisateurs sélectionnés`;
  if (modifyBtn) modifyBtn.style.display = sel.length === 1 ? '' : 'none';
}

async function adminDeleteSelected() {
  const sel = window._selAdminUsers || [];
  if (!sel.length) return;
  const names = sel.map(u => u.label).join(', ');
  const msg = sel.length === 1
    ? `Supprimer définitivement le compte de ${names} ?`
    : `Supprimer définitivement ces ${sel.length} comptes ?\n${names}`;
  if (!confirm(msg + '\n\nCette action est irréversible.')) return;
  for (const u of sel) await api(`/api/admin/users/${u.id}`, 'DELETE');
  window._selAdminUsers = [];
  _updatePendingBadge();
  showView(currentView);
}

// ─── ADMIN: ALL USERS ─────────────────────────────────────────────────────────
async function renderAdminUsers(c) {
  c.innerHTML = '<div style="color:var(--text3);padding:40px;text-align:center">Chargement…</div>';
  const users = await api('/api/admin/users');
  if (!users || users.length === 0) {
    c.innerHTML = '<div style="color:var(--text3);padding:40px;text-align:center">Aucun utilisateur.</div>';
    return;
  }
  window._selAdminUsers = [];
  const roles = ['tous','medecin','patient'];
  const roleLabels = {tous:'Tous',medecin:'Médecins',patient:'Patients'};
  c.innerHTML = `
    <div id="adminUserActionBar" style="display:none;position:sticky;top:0;z-index:10;background:var(--teal-dim);border:1px solid var(--teal-border);border-radius:10px;padding:12px 16px;margin-bottom:14px;align-items:center;gap:12px;flex-wrap:wrap">
      <span style="font-size:13px;font-weight:600;color:var(--teal2)">✔ <span class="sel-count"></span></span>
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-left:auto">
        <button class="btn btn-primary btn-sm admin-modify-btn" onclick="adminOpenEditUser(window._selAdminUsers?.[0]?.id)">✏️ Modifier</button>
        <button class="btn btn-sm" style="background:var(--red-dim);color:var(--red);border-color:var(--red)"
                onclick="adminDeleteSelected()">🗑️ Supprimer</button>
      </div>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap">
      ${roles.map(r => `
        <button class="btn ${r==='tous'?'btn-primary':'btn-ghost'} btn-sm" id="filterBtn_${r}"
                onclick="filterAdminUsers('${r}')" style="font-size:12px">${roleLabels[r]}</button>
      `).join('')}
      <input class="form-input" id="adminUserSearch" placeholder="Rechercher…"
             style="flex:1;min-width:180px;max-width:280px;padding:6px 12px;font-size:13px"
             oninput="filterAdminUsers(window._adminFilter||'tous')">
    </div>
    <div id="adminUserList">
      ${users.map(u => _renderAdminUserCard(u, false)).join('')}
    </div>`;
  window._adminUsers = users;
  window._adminFilter = 'tous';
}

function filterAdminUsers(role) {
  window._adminFilter = role;
  const q = (document.getElementById('adminUserSearch')?.value || '').toLowerCase();
  document.querySelectorAll('[id^="filterBtn_"]').forEach(b => {
    b.className = 'btn btn-sm ' + (b.id === 'filterBtn_' + role ? 'btn-primary' : 'btn-ghost');
    b.style.fontSize = '12px';
  });
  const filtered = (window._adminUsers || []).filter(u =>
    (role === 'tous' || u.role === role) &&
    (!q || `${u.nom} ${u.prenom} ${u.username} ${u.email||''} ${u.organisation||''}`.toLowerCase().includes(q))
  );
  document.getElementById('adminUserList').innerHTML =
    filtered.length ? filtered.map(u => _renderAdminUserCard(u, false)).join('') :
    '<div style="color:var(--text3);padding:20px;text-align:center">Aucun résultat.</div>';
  // Re-highlight all selected cards still visible after filtering
  (window._selAdminUsers || []).forEach(s => {
    const card = document.getElementById(`userCard_${s.id}`);
    if (card) card.style.borderColor = 'var(--teal)';
  });
  _updateAdminActionBar();
}

// ─── ADMIN: CREATE MÉDECIN ────────────────────────────────────────────────────
function renderAdminCreateMedecin(c) {
  c.innerHTML = `
    <div class="card" style="max-width:580px;padding:28px 32px">
      <div class="section-title" style="margin-bottom:20px">➕ Créer un compte médecin</div>
      <div style="display:flex;gap:14px">
        <div class="form-group" style="flex:1">
          <label class="form-label">Nom *</label>
          <input class="form-input" id="cmNom" placeholder="Nom de famille" autocomplete="family-name">
        </div>
        <div class="form-group" style="flex:1">
          <label class="form-label">Prénom *</label>
          <input class="form-input" id="cmPrenom" placeholder="Prénom" autocomplete="given-name">
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">Identifiant de connexion *</label>
        <input class="form-input" id="cmUsername" placeholder="Ex : dr.dupont" autocomplete="off">
      </div>
      <div class="form-group">
        <label class="form-label">Mot de passe * <span style="color:var(--text3);font-weight:400">(min. 8 caractères)</span></label>
        <input class="form-input" type="password" id="cmPassword" placeholder="••••••••" autocomplete="new-password">
      </div>
      <div class="form-group">
        <label class="form-label">Email</label>
        <input class="form-input" type="email" id="cmEmail" placeholder="medecin@clinique.fr" autocomplete="email">
      </div>
      <div class="form-group">
        <label class="form-label">Établissement / Organisation</label>
        <input class="form-input" id="cmOrganisation" placeholder="Clinique, hôpital, cabinet..." autocomplete="organization">
      </div>
      <div class="form-group">
        <label class="form-label">Date de naissance</label>
        <input class="form-input" type="date" id="cmDateNaissance">
      </div>
      <div id="cmMsg" style="margin-bottom:14px"></div>
      <div style="display:flex;gap:10px">
        <button class="btn btn-primary" style="flex:1;justify-content:center" onclick="adminSubmitCreateMedecin()">Créer le compte médecin</button>
        <button class="btn btn-ghost" onclick="showView('admin-dashboard')">Annuler</button>
      </div>
    </div>`;
  initPasswordToggles();
}

async function adminSubmitCreateMedecin() {
  const nom            = document.getElementById('cmNom').value.trim();
  const prenom         = document.getElementById('cmPrenom').value.trim();
  const username       = document.getElementById('cmUsername').value.trim();
  const password       = document.getElementById('cmPassword').value;
  const email          = document.getElementById('cmEmail').value.trim();
  const organisation   = document.getElementById('cmOrganisation').value.trim();
  const date_naissance = document.getElementById('cmDateNaissance').value;
  const msgEl = document.getElementById('cmMsg');

  if (!nom || !prenom || !username || !password) {
    msgEl.innerHTML = '<div class="auth-msg auth-msg-error">Nom, prénom, identifiant et mot de passe sont requis.</div>'; return;
  }
  if (password.length < 8) {
    msgEl.innerHTML = '<div class="auth-msg auth-msg-error">Le mot de passe doit contenir au moins 8 caractères.</div>'; return;
  }
  const res = await api('/api/admin/medecins','POST',{nom,prenom,username,password,email,organisation,date_naissance});
  if (res.ok) {
    msgEl.innerHTML = `<div class="auth-msg auth-msg-success">Compte médecin créé — ID : <strong>${res.medecin_code}</strong></div>`;
    ['cmNom','cmPrenom','cmUsername','cmPassword','cmEmail','cmOrganisation','cmDateNaissance'].forEach(id => {
      document.getElementById(id).value = '';
    });
  } else {
    msgEl.innerHTML = `<div class="auth-msg auth-msg-error">${res.error || 'Erreur lors de la création.'}</div>`;
  }
}

// ─── ADMIN: CREATE PATIENT ────────────────────────────────────────────────────

async function renderAdminCreatePatient(c) {
  const medecins = await api('/api/admin/users?role=medecin');
  const medecinOptions = Array.isArray(medecins)
    ? medecins.filter(m => m.status === 'active').map(m =>
        `<option value="${m.id}">${m.nom} ${m.prenom}${m.medecin_code ? ' ('+m.medecin_code+')' : ''}</option>`
      ).join('')
    : '';
  c.innerHTML = `
    <div class="card" style="max-width:620px;padding:28px 32px">
      <div class="section-title" style="margin-bottom:20px">🧑 Créer un dossier patient</div>
      <div style="display:flex;gap:14px">
        <div class="form-group" style="flex:1">
          <label class="form-label">Nom *</label>
          <input class="form-input" id="apNom" placeholder="Nom de famille">
        </div>
        <div class="form-group" style="flex:1">
          <label class="form-label">Prénom *</label>
          <input class="form-input" id="apPrenom" placeholder="Prénom">
        </div>
      </div>
      <div style="display:flex;gap:14px">
        <div class="form-group" style="flex:1">
          <label class="form-label">Date de naissance</label>
          <input class="form-input" type="date" id="apDdn">
        </div>
        <div class="form-group" style="flex:1">
          <label class="form-label">Sexe</label>
          <select class="form-input" id="apSexe">
            <option value="">-- Choisir --</option>
            <option value="M">Masculin</option>
            <option value="F">Féminin</option>
          </select>
        </div>
      </div>
      <div style="display:flex;gap:14px">
        <div class="form-group" style="flex:1">
          <label class="form-label">Téléphone</label>
          <input class="form-input" id="apTel" placeholder="06 xx xx xx xx">
        </div>
        <div class="form-group" style="flex:1">
          <label class="form-label">Email *</label>
          <input class="form-input" type="email" id="apEmail" placeholder="patient@email.com" required>
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">Médecin référent</label>
        <select class="form-input" id="apMedecinId">${medecinOptions}</select>
      </div>
      <div class="form-group">
        <label class="form-label">Antécédents <span style="color:var(--text3);font-weight:400">(séparés par virgule)</span></label>
        <input class="form-input" id="apAnt" placeholder="Ex: Glaucome, Diabète...">
      </div>
      <div class="form-group">
        <label class="form-label">Allergies <span style="color:var(--text3);font-weight:400">(séparées par virgule)</span></label>
        <input class="form-input" id="apAllerg" placeholder="Ex: Pénicilline...">
      </div>
      <div class="form-group" style="display:flex;align-items:center;gap:10px;margin-bottom:8px">
        <input type="checkbox" id="apSendEmail" checked style="width:16px;height:16px;cursor:pointer">
        <label for="apSendEmail" style="font-size:13px;cursor:pointer">Envoyer les identifiants par email au patient</label>
      </div>
      <div id="apMsg" style="margin-bottom:14px"></div>
      <div style="display:flex;gap:10px">
        <button class="btn btn-primary" style="flex:1;justify-content:center" onclick="adminSubmitCreatePatient()">Créer le dossier patient</button>
        <button class="btn btn-ghost" onclick="showView('admin-dashboard')">Annuler</button>
      </div>
    </div>`;
}

async function adminSubmitCreatePatient() {
  const nom        = document.getElementById('apNom').value.trim();
  const prenom     = document.getElementById('apPrenom').value.trim();
  const ddn        = document.getElementById('apDdn').value;
  const sexe       = document.getElementById('apSexe').value;
  const telephone  = document.getElementById('apTel').value.trim();
  const email      = document.getElementById('apEmail').value.trim();
  const medecin_id = document.getElementById('apMedecinId')?.value || '';
  const send_email = document.getElementById('apSendEmail').checked;
  const antecedents = document.getElementById('apAnt').value.split(',').map(s=>s.trim()).filter(Boolean);
  const allergies   = document.getElementById('apAllerg').value.split(',').map(s=>s.trim()).filter(Boolean);
  const msgEl = document.getElementById('apMsg');

  if (!nom || !prenom) {
    msgEl.innerHTML = '<div class="auth-msg auth-msg-error">Nom et prénom sont requis.</div>'; return;
  }
  if (!email || !email.includes('@')) {
    msgEl.innerHTML = '<div class="auth-msg auth-msg-error">L\'adresse email est obligatoire.</div>'; return;
  }
  const res = await api('/api/admin/patients','POST',{nom,prenom,ddn,sexe,telephone,email,medecin_id,send_email,antecedents,allergies});
  if (res.ok) {
    let msg = `<div class="auth-msg auth-msg-success">Patient créé — ID : <strong>${res.id}</strong>`;
    if (res.credentials) {
      msg += `<br>Identifiant : <strong>${res.credentials.username}</strong> · Mot de passe : <strong>${res.credentials.password}</strong>`;
      if (res.credentials.email_sent) msg += ' · Email envoyé ✓';
    }
    msg += '</div>';
    msgEl.innerHTML = msg;
    ['apNom','apPrenom','apDdn','apTel','apEmail','apAnt','apAllerg'].forEach(id => {
      const el = document.getElementById(id); if (el) el.value = '';
    });
    document.getElementById('apSendEmail').checked = true;
  } else {
    msgEl.innerHTML = `<div class="auth-msg auth-msg-error">${res.error || 'Erreur lors de la création.'}</div>`;
  }
}

