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
  if (!Array.isArray(users)) {
    const msg = (users && users.error) || 'Impossible de charger les comptes en attente.';
    c.innerHTML = `<div style="color:var(--red);padding:40px;text-align:center">⚠ ${escH(msg)}</div>`;
    return;
  }
  if (users.length === 0) {
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
  const nowSql    = new Date().toISOString().slice(0,19).replace('T',' ');
  const isLocked  = !!u.locked_until && u.locked_until > nowSql;
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
            ${isLocked ? `<span class="badge" style="background:var(--red-dim);color:var(--red);border:1px solid var(--red)" title="Verrouillé jusqu'à ${u.locked_until}">🔒 Verrouillé</span>` : ''}
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
            ${isLocked ? `<button class="btn btn-primary btn-sm" onclick="adminUnlock('${u.id}','${(u.prenom||'').replace(/'/g,"\\'")} ${(u.nom||'').replace(/'/g,"\\'")}')">🔓 Déverrouiller</button>` : ''}
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

async function adminUnlock(uid, name) {
  if (!confirm(`Déverrouiller le compte de ${name} maintenant ?`)) return;
  const res = await api(`/api/admin/users/${uid}/unlock`, 'POST');
  if (res.ok) { showView(currentView); }
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
  if (!Array.isArray(users)) {
    const msg = (users && users.error) || 'Impossible de charger la liste des utilisateurs.';
    c.innerHTML = `<div style="color:var(--red);padding:40px;text-align:center">⚠ ${escH(msg)}</div>`;
    return;
  }
  if (users.length === 0) {
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


// ─── ADMIN: PATIENT RECORDS MANAGEMENT ───────────────────────────────────────
async function renderAdminPatients(c) {
  c.innerHTML = '<div style="color:var(--text3);padding:40px;text-align:center">Chargement…</div>';
  // Pre-load médecins list for the assignment dropdowns
  const [patients, medRows] = await Promise.all([
    api('/api/admin/patients'),
    api('/api/admin/users?role=medecin'),
  ]);
  window._adminMedecins = Array.isArray(medRows)
    ? medRows.map(m => ({ id: m.id, label: `${m.prenom||''} ${m.nom||''}`.trim() || m.username }))
    : [];
  if (!Array.isArray(patients)) {
    c.innerHTML = '<div style="color:var(--red);padding:20px">Erreur de chargement.</div>';
    return;
  }

  c.innerHTML = `
    <div style="margin-bottom:16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <div style="font-size:15px;font-weight:700">🗂 Dossiers patients (${patients.length})</div>
      <input class="form-input" id="adminPatSearch" placeholder="Rechercher nom, prénom, ID…"
             style="flex:1;min-width:180px;max-width:300px;padding:6px 12px;font-size:13px"
             oninput="filterAdminPatients()">
    </div>
    <div style="font-size:12px;color:var(--amber);background:rgba(251,191,36,.1);border:1px solid rgba(251,191,36,.3);border-radius:8px;padding:10px 14px;margin-bottom:16px">
      ⚠️ Cette vue liste les <strong>dossiers patients</strong> (pas les comptes utilisateurs). Supprimer ici efface définitivement le dossier médical du patient.
    </div>
    <div id="adminPatList">
      ${patients.map(p => _renderAdminPatCard(p)).join('')}
    </div>`;
  window._adminPats = patients;
}

function _renderAdminPatCard(p) {
  const medLabel = p.medecin_label
    ? `<span style="color:var(--teal2);font-size:11px">🩺 ${escH(p.medecin_label)}</span>`
    : `<span style="color:var(--amber);font-size:11px">⚠ Sans médecin</span>`;
  const accLabel = p.patient_username
    ? `<span style="color:var(--teal2);font-size:11px">👤 ${escH(p.patient_username)}</span>`
    : `<span style="color:var(--text3);font-size:11px">Pas de compte</span>`;
  return `
    <div class="card" style="margin-bottom:10px;padding:14px 18px;flex-wrap:wrap;gap:12px" id="adminPatCard_${p.id}">
      <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
        <div style="width:38px;height:38px;border-radius:50%;background:var(--teal-dim);border:2px solid var(--teal);display:flex;align-items:center;justify-content:center;font-size:17px;flex-shrink:0">👤</div>
        <div style="flex:1;min-width:160px">
          <div style="font-weight:600;font-size:14px">${escH(p.prenom)} ${escH(p.nom)}</div>
          <div style="font-size:12px;color:var(--text2);margin-top:3px;display:flex;gap:10px;flex-wrap:wrap">
            <span style="color:var(--text3);font-family:monospace">${p.id}</span>
            ${medLabel}
            ${accLabel}
            <span style="color:var(--text3)">📅 ${p.created_at||'—'}</span>
          </div>
        </div>
        <div style="display:flex;gap:6px;flex-shrink:0">
          <button class="btn btn-ghost btn-sm" onclick="adminEditPatient('${p.id}')">✏️ Modifier</button>
          <button class="btn btn-sm" style="background:var(--red-dim);color:var(--red);border-color:rgba(239,68,68,.3)"
                  onclick="adminDeletePatientRecord('${p.id}','${(p.prenom+' '+p.nom).replace(/'/g,"\\'")}')">
            🗑️ Supprimer
          </button>
        </div>
      </div>
    </div>`;
}

function filterAdminPatients() {
  const q = (document.getElementById('adminPatSearch')?.value || '').toLowerCase();
  const filtered = (window._adminPats || []).filter(p =>
    !q || `${p.nom} ${p.prenom} ${p.id}`.toLowerCase().includes(q)
  );
  document.getElementById('adminPatList').innerHTML =
    filtered.length ? filtered.map(p => _renderAdminPatCard(p)).join('') :
    '<div style="color:var(--text3);padding:20px;text-align:center">Aucun résultat.</div>';
}

async function adminEditPatient(pid) {
  const medecins = window._adminMedecins || [];
  showModal('✏️ Modifier le patient', '<div style="color:var(--text3);text-align:center;padding:20px">Chargement…</div>');

  const p = await api(`/api/admin/patients/${pid}`);
  if (p.error) { showToast(p.error, 'error'); closeModal(); return; }

  const medOptions = medecins.map(m =>
    `<option value="${m.id}" ${m.id === p.medecin_id ? 'selected' : ''}>${escH(m.label)}</option>`
  ).join('');

  const body = document.getElementById('modalDynBody');
  if (!body) return;
  body.innerHTML = `
    <div style="margin-bottom:16px">
      <div style="font-size:14px;font-weight:700">${escH(p.prenom)} ${escH(p.nom)}</div>
      <div style="font-size:12px;color:var(--text3);font-family:monospace">${p.id}</div>
    </div>

    <div style="background:var(--bg2);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:16px">
      <div style="font-size:12px;font-weight:600;color:var(--text2);margin-bottom:10px">🩺 Médecin responsable</div>
      ${p.medecin_id
        ? `<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:12px">
             <div style="font-size:13px;color:var(--teal2);font-weight:600">${escH(p.medecin_label || p.medecin_id)}</div>
             <button class="btn btn-ghost btn-sm" style="color:var(--red);border-color:var(--red)"
                     onclick="adminDetachMedecin('${pid}','${escH(p.medecin_label)}',true)">
               ✕ Détacher ce médecin
             </button>
           </div>`
        : `<div style="font-size:12px;color:var(--amber);margin-bottom:10px">⚠ Aucun médecin affecté</div>`
      }

      <div class="form-group" style="margin-bottom:8px">
        <label class="form-label">${p.medecin_id ? 'Changer de médecin' : 'Affecter un médecin'}</label>
        <select class="form-input" id="adminPatMedSel">
          <option value="">— Sélectionner —</option>
          ${medOptions}
        </select>
      </div>
      <button class="btn btn-primary btn-sm" onclick="adminAssignMedecin('${pid}',true)">
        ✓ ${p.medecin_id ? 'Changer le médecin' : 'Affecter ce médecin'}
      </button>
    </div>
  `;
}

async function adminAssignMedecin(pid, fromModal = false) {
  const selId = fromModal ? 'adminPatMedSel' : `medSel_${pid}`;
  const sel   = document.getElementById(selId);
  const mid   = sel?.value || '';
  if (!mid) { showToast('Sélectionnez un médecin dans la liste.', 'warning'); return; }
  const res = await api(`/api/admin/patients/${pid}/medecin`, 'PUT', {medecin_id: mid});
  if (res.ok) {
    const med = (window._adminMedecins || []).find(m => m.id === mid);
    showToast(`Médecin affecté : Dr. ${escH(med?.label || mid)}`, 'success');
    if (fromModal) closeModal();
    renderAdminPatients(document.getElementById('viewContent'));
  } else {
    showToast(res.error || 'Erreur lors de l\'affectation', 'error');
  }
}

async function adminDetachMedecin(pid, medecinLabel, fromModal = false) {
  if (!confirm(`Détacher "${medecinLabel}" de ce patient ?\nLe patient n'apparaîtra plus dans la liste de ce médecin.`)) return;
  const res = await api(`/api/admin/patients/${pid}/medecin`, 'DELETE');
  if (res.ok) {
    showToast('Médecin détaché — le patient passe en liste non-affectée.', 'success');
    if (fromModal) closeModal();
    renderAdminPatients(document.getElementById('viewContent'));
  } else {
    showToast(res.error || 'Erreur lors du détachement', 'error');
  }
}

async function adminDeletePatientRecord(pid, name) {
  if (!confirm(`Supprimer le dossier patient de ${name} ?\n\nLe dossier sera masqué (soft-delete) et restaurable depuis la corbeille.`)) return;
  const res = await api(`/api/admin/patients/${pid}`, 'DELETE');
  if (res.ok) {
    const card = document.getElementById(`adminPatCard_${pid}`);
    if (card) card.remove();
    window._adminPats = (window._adminPats || []).filter(p => p.id !== pid);
    showUndoToast(`Dossier de ${name} supprimé`, async () => {
      const r = await api(`/api/admin/patients/${pid}/restore`, 'POST');
      if (r.ok) {
        showToast('Dossier restauré — rechargez la vue', 'success');
        renderAdminPatients(document.getElementById('viewContent'));
      } else {
        showToast(r.error || 'Restauration impossible', 'error');
      }
    });
  } else {
    alert(res.error || 'Erreur lors de la suppression.');
  }
}

// ─── ADMIN: TRASH VIEW (soft-deleted patients) ───────────────────────────────
async function renderAdminTrash(c) {
  c.innerHTML = '<div style="color:var(--text3);padding:40px;text-align:center">Chargement…</div>';
  const rows = await api('/api/admin/patients/deleted');
  if (!Array.isArray(rows)) {
    c.innerHTML = '<div style="color:var(--red);padding:20px">Erreur de chargement.</div>';
    return;
  }
  c.innerHTML = `
    <div style="margin-bottom:16px;display:flex;gap:10px;align-items:center;flex-wrap:wrap">
      <div style="font-size:15px;font-weight:700">🗑️ Corbeille — dossiers supprimés (${rows.length})</div>
    </div>
    <div style="font-size:12px;color:var(--text2);background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:10px 14px;margin-bottom:16px">
      Restaurez ici les patients supprimés par erreur. Les détails du journal d'audit restent anonymisés (RGPD) même après restauration.
    </div>
    <div id="adminTrashList">
      ${rows.length ? rows.map(p => _renderTrashCard(p)).join('')
                    : '<div style="color:var(--text3);padding:20px;text-align:center">Aucun dossier supprimé.</div>'}
    </div>`;
}

function _renderTrashCard(p) {
  return `
    <div class="card" style="margin-bottom:10px;padding:14px 18px;display:flex;align-items:center;gap:14px;flex-wrap:wrap" id="trashCard_${p.id}">
      <div style="width:38px;height:38px;border-radius:50%;background:var(--bg2);border:2px solid var(--border);display:flex;align-items:center;justify-content:center;font-size:17px;flex-shrink:0">🗑️</div>
      <div style="flex:1;min-width:160px">
        <div style="font-weight:600;font-size:14px">${escH(p.prenom)} ${escH(p.nom)}</div>
        <div style="font-size:12px;color:var(--text3);margin-top:3px">
          <span style="font-family:monospace">${p.id}</span> · Supprimé le ${p.deleted_at || '—'}
        </div>
      </div>
      <button class="btn btn-primary btn-sm" onclick="adminRestorePatient('${p.id}','${(p.prenom+' '+p.nom).replace(/'/g,"\\'")}')">
        ↶ Restaurer
      </button>
    </div>`;
}

// ─── ADMIN: SECURITY EVENTS DASHBOARD ────────────────────────────────────────
const _SEC_LABELS = {
  login_failed:                  { icon:'🔴', label:'Échec connexion' },
  login_totp_failed:             { icon:'🔴', label:'Échec 2FA' },
  login_backup_code_used:        { icon:'🟠', label:'Code de secours utilisé' },
  login_trusted_device:          { icon:'🟡', label:'Appareil de confiance' },
  totp_regen_failed:             { icon:'🟠', label:'Regen 2FA échoué' },
  totp_backup_codes_regenerated: { icon:'🟡', label:'Codes 2FA régénérés' },
  admin_password_reset:          { icon:'🟠', label:'Reset mdp par admin' },
  admin_user_deleted:            { icon:'🔴', label:'Utilisateur supprimé' },
  admin_account_deactivated:     { icon:'🟠', label:'Compte désactivé' },
  patient_deleted_gdpr:          { icon:'🟡', label:'Patient supprimé (RGPD)' },
  GDPR_PURGE:                    { icon:'🔴', label:'Purge RGPD définitive' },
  compte_verrouille:             { icon:'🔴', label:'Compte verrouillé' },
};

async function renderAdminSecurityEvents(c) {
  c.innerHTML = '<div style="color:var(--text3);padding:40px;text-align:center">Chargement…</div>';
  const events = await api('/api/admin/security-events?limit=200');
  if (!Array.isArray(events)) {
    c.innerHTML = '<div style="color:var(--red);padding:20px">Erreur de chargement.</div>';
    return;
  }

  const actionCounts = {};
  events.forEach(e => { actionCounts[e.action] = (actionCounts[e.action] || 0) + 1; });

  const summaryItems = Object.entries(actionCounts)
    .sort((a,b) => b[1] - a[1])
    .map(([action, count]) => {
      const {icon, label} = _SEC_LABELS[action] || {icon:'ℹ️', label: action};
      return `<div style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:10px 14px;min-width:140px;text-align:center">
        <div style="font-size:20px">${icon}</div>
        <div style="font-weight:700;font-size:18px;color:var(--text)">${count}</div>
        <div style="font-size:11px;color:var(--text3);margin-top:2px">${label}</div>
      </div>`;
    }).join('');

  const rows = events.map(e => {
    const {icon, label} = _SEC_LABELS[e.action] || {icon:'ℹ️', label: e.action};
    const when = new Date(e.created_at).toLocaleString('fr-FR', {day:'2-digit',month:'2-digit',year:'2-digit',hour:'2-digit',minute:'2-digit'});
    const ip = e.ip_address || '—';
    const severity = e.action.startsWith('login_failed') || e.action.includes('verrouill') || e.action.includes('PURGE')
      ? 'var(--red-dim)' : 'transparent';
    return `<tr style="background:${severity}">
      <td style="padding:8px 12px;font-size:12px;color:var(--text3)">${when}</td>
      <td style="padding:8px 12px;font-size:13px">${icon} ${label}</td>
      <td style="padding:8px 12px;font-size:12px;color:var(--text2)">${escH(e.actor||'—')}</td>
      <td style="padding:8px 12px;font-size:11px;font-family:monospace;color:var(--text3)">${escH(ip)}</td>
      <td style="padding:8px 12px;font-size:11px;color:var(--text3);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escH(e.detail||'')}">${escH(e.detail||'')}</td>
    </tr>`;
  }).join('');

  c.innerHTML = `
    <div style="margin-bottom:16px">
      <div style="font-size:15px;font-weight:700;margin-bottom:12px">🔐 Événements de sécurité (${events.length} derniers)</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px">${summaryItems}</div>
    </div>
    <div style="overflow-x:auto;border-radius:10px;border:1px solid var(--border)">
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="background:var(--bg2);border-bottom:2px solid var(--border)">
            <th style="padding:8px 12px;font-size:11px;text-align:left;color:var(--text3);text-transform:uppercase;letter-spacing:.5px">Date</th>
            <th style="padding:8px 12px;font-size:11px;text-align:left;color:var(--text3);text-transform:uppercase;letter-spacing:.5px">Événement</th>
            <th style="padding:8px 12px;font-size:11px;text-align:left;color:var(--text3);text-transform:uppercase;letter-spacing:.5px">Acteur</th>
            <th style="padding:8px 12px;font-size:11px;text-align:left;color:var(--text3);text-transform:uppercase;letter-spacing:.5px">IP</th>
            <th style="padding:8px 12px;font-size:11px;text-align:left;color:var(--text3);text-transform:uppercase;letter-spacing:.5px">Détail</th>
          </tr>
        </thead>
        <tbody>${rows || '<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text3)">Aucun événement.</td></tr>'}</tbody>
      </table>
    </div>`;
}

async function adminRestorePatient(pid, name) {
  const res = await api(`/api/admin/patients/${pid}/restore`, 'POST');
  if (res.ok) {
    const card = document.getElementById(`trashCard_${pid}`);
    if (card) card.remove();
    showToast(`${name} restauré`, 'success');
  } else {
    showToast(res.error || 'Erreur', 'error');
  }
}
