// ─── AUTH ─────────────────────────────────────────────────────────────────────
const DEMO = {
  medecin: {user:'dr.martin', pass:'medecin123', hint:'🩺 Médecin: dr.martin / medecin123'},
  patient: {user:'patient.marie', pass:'patient123', hint:'🧑 Patient 1: patient.marie / patient123<br>🧑 Patient 2: patient.jp / patient123'}
};

// ── Panel switcher ──
function initPasswordToggles() {
  document.querySelectorAll('input[type="password"]:not([data-pw-init])').forEach(input => {
    input.dataset.pwInit = '1';
    const wrap = document.createElement('div');
    wrap.className = 'pw-wrap';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'pw-eye';
    btn.title = 'Afficher / masquer le mot de passe';
    btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
    btn.addEventListener('click', () => {
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.innerHTML = show
        ? `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`
        : `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
    });
    wrap.appendChild(btn);
  });
}

function showAuthPanel(panel) {
  const panels = ['Login','Register','Forgot','Reset','Totp'];
  panels.forEach(p => {
    const el = document.getElementById('panel' + p);
    if (el) el.style.display = (p.toLowerCase() === panel) ? '' : 'none';
  });
  const subtitles = {
    login:    'Système de gestion ophtalmologique',
    register: 'Créer un compte',
    forgot:   'Réinitialisation du mot de passe',
    reset:    'Choisir un nouveau mot de passe',
    totp:     'Authentification à deux facteurs'
  };
  document.getElementById('loginSubtitle').textContent = subtitles[panel] || '';
  // Clear all messages when switching
  document.querySelectorAll('.auth-msg').forEach(el => { el.style.display = 'none'; el.textContent = ''; });
  // Reset register role tab when opening register panel
  if (panel === 'register') { setRegRole('patient'); setPatientRegMethod('free'); }
  // Focus TOTP input
  if (panel === 'totp') setTimeout(() => { const el = document.getElementById('totpCode'); if (el) el.focus(); }, 80);
}

function _authMsg(elId, type, text) {
  const el = document.getElementById(elId);
  el.className = 'auth-msg auth-msg-' + type;
  el.textContent = text;
  el.style.display = 'block';
}

function _validatePasswordFrontend(pw) {
  if (!pw || pw.length < 12) return 'Le mot de passe doit contenir au moins 12 caractères.';
  if (!/[A-Z]/.test(pw))     return 'Le mot de passe doit contenir au moins une majuscule.';
  if (!/[a-z]/.test(pw))     return 'Le mot de passe doit contenir au moins une minuscule.';
  if (!/\d/.test(pw))        return 'Le mot de passe doit contenir au moins un chiffre.';
  if (!/[!@#$%^&*()\-_=+\[\]{};:\'",.<>/?`~\\|]/.test(pw))
                             return 'Le mot de passe doit contenir au moins un caractère spécial.';
  return null; // valid
}

function setLoginRole(role, btn) {
  document.querySelectorAll('.role-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('demoCreds').innerHTML = DEMO[role].hint;
}

// Store credentials temporarily during 2FA step
let _pendingLoginCredentials = null;

async function doLogin() {
  const u   = document.getElementById('loginUser').value.trim();
  const p   = document.getElementById('loginPass').value;
  if (!u || !p) { _authMsg('loginError','error','Veuillez remplir tous les champs.'); return; }
  const activeTab = document.querySelector('.role-tab.active');
  const role = activeTab ? activeTab.dataset.role : 'medecin';
  const res = await api('/login','POST',{username:u, password:p, role});
  if (res.ok) {
    const me = await api('/me');
    USER = {...res, ...me};
    if (res.force_password_change || me.force_password_change) {
      _showForcePasswordChange();
      return;
    }
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('mainApp').style.display = 'flex';
    initApp();
  } else if (res.totp_required) {
    // Server confirmed password OK but 2FA is needed — store creds and show TOTP panel
    _pendingLoginCredentials = {username: u, password: p, role};
    showAuthPanel('totp');
  } else {
    _authMsg('loginError','error', res.error || 'Identifiants incorrects.');
  }
}

function _showForcePasswordChange() {
  // Replace login screen with a mandatory password change form
  document.getElementById('loginScreen').innerHTML = `
    <div class="auth-card" style="max-width:420px;width:100%">
      <div class="auth-logo">🔒 Changement de mot de passe requis</div>
      <p style="color:var(--text-2);font-size:13px;margin-bottom:20px;text-align:center">
        Ce compte utilise un mot de passe temporaire. Vous devez en choisir un nouveau avant de continuer.
      </p>
      <div id="forcePwMsg"></div>
      <div class="form-group">
        <label class="form-label">Mot de passe actuel</label>
        <input class="form-input" type="password" id="forcePwCurrent" placeholder="Mot de passe temporaire">
      </div>
      <div class="form-group">
        <label class="form-label">Nouveau mot de passe</label>
        <input class="form-input" type="password" id="forcePwNew" placeholder="12 caractères minimum">
      </div>
      <div class="form-group">
        <label class="form-label">Confirmer le nouveau mot de passe</label>
        <input class="form-input" type="password" id="forcePwConfirm" placeholder="Répétez le nouveau mot de passe">
      </div>
      <button class="btn btn-primary" style="width:100%" onclick="doForcePasswordChange()">Changer le mot de passe</button>
    </div>`;
  document.getElementById('loginScreen').style.display = 'flex';
}

async function doForcePasswordChange() {
  const current = document.getElementById('forcePwCurrent').value;
  const newPw   = document.getElementById('forcePwNew').value;
  const confirm = document.getElementById('forcePwConfirm').value;
  const msg     = document.getElementById('forcePwMsg');
  if (newPw !== confirm) {
    msg.innerHTML = '<div class="auth-msg auth-msg-error">Les mots de passe ne correspondent pas.</div>'; return;
  }
  const res = await api('/api/change-password','POST',{current_password: current, new_password: newPw});
  if (res.ok) {
    msg.innerHTML = '<div class="auth-msg auth-msg-success">Mot de passe changé. Connexion en cours…</div>';
    setTimeout(() => {
      document.getElementById('loginScreen').style.display = 'none';
      document.getElementById('mainApp').style.display = 'flex';
      initApp();
    }, 1000);
  } else {
    msg.innerHTML = `<div class="auth-msg auth-msg-error">${res.error || 'Erreur lors du changement.'}</div>`;
  }
}

async function doLoginTotp() {
  if (!_pendingLoginCredentials) { showAuthPanel('login'); return; }
  const token = document.getElementById('totpCode').value.trim();
  if (!token || token.length < 6) { _authMsg('totpError','error','Veuillez entrer le code à 6 chiffres.'); return; }
  const res = await api('/login','POST',{..._pendingLoginCredentials, totp_token: token});
  if (res.ok) {
    _pendingLoginCredentials = null;
    const me = await api('/me');
    USER = {...res, ...me};
    if (res.force_password_change || me.force_password_change) {
      _showForcePasswordChange();
      return;
    }
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('mainApp').style.display = 'flex';
    initApp();
  } else {
    _authMsg('totpError','error', res.error || 'Code invalide.');
    document.getElementById('totpCode').value = '';
    document.getElementById('totpCode').focus();
  }
}

let _regRole = 'patient';
let _patientRegMethod = 'invite';

function setRegRole(role) {
  _regRole = role;
  document.getElementById('regPatientFields').style.display  = role === 'patient' ? '' : 'none';
  document.getElementById('regMedecinFields').style.display  = role === 'medecin' ? '' : 'none';
  document.getElementById('regTabPatient').className = 'btn ' + (role === 'patient' ? 'btn-primary' : 'btn-ghost');
  document.getElementById('regTabMedecin').className = 'btn ' + (role === 'medecin' ? 'btn-primary' : 'btn-ghost');
  document.getElementById('regTabPatient').style.flex = document.getElementById('regTabMedecin').style.flex = '1';
  document.getElementById('regTabPatient').style.justifyContent = document.getElementById('regTabMedecin').style.justifyContent = 'center';
  document.getElementById('regTabPatient').style.fontSize = document.getElementById('regTabMedecin').style.fontSize = '13px';
  document.getElementById('registerMsg').innerHTML = '';
}

function setPatientRegMethod(method) {
  _patientRegMethod = method;
  document.getElementById('regFreeFields').style.display   = method === 'free'   ? '' : 'none';
  document.getElementById('regInviteFields').style.display = method === 'invite' ? '' : 'none';
  const btnFree   = document.getElementById('regPatSubFree');
  const btnInvite = document.getElementById('regPatSubInvite');
  if (btnFree)   { btnFree.className   = 'btn ' + (method === 'free'   ? 'btn-primary' : 'btn-ghost'); btnFree.style.cssText   += ';flex:1;justify-content:center;font-size:12px;border-radius:0;border:none'; }
  if (btnInvite) { btnInvite.className = 'btn ' + (method === 'invite' ? 'btn-primary' : 'btn-ghost'); btnInvite.style.cssText += ';flex:1;justify-content:center;font-size:12px;border-radius:0;border:none;border-left:1px solid var(--border)'; }
  document.getElementById('registerMsg').innerHTML = '';
}

// Doctor search for registration
let _doctorSearchDebounce = null;
let _selectedDoctorId = null;

function debounceSearchDoctor(val) {
  clearTimeout(_doctorSearchDebounce);
  const dd = document.getElementById('regDoctorDropdown');
  if (!val || val.length < 2) { dd.style.display = 'none'; return; }
  _doctorSearchDebounce = setTimeout(async () => {
    const doctors = await api(`/api/doctors/search?q=${encodeURIComponent(val)}`);
    if (!Array.isArray(doctors) || doctors.length === 0) { dd.style.display = 'none'; return; }
    dd.innerHTML = doctors.map(d =>
      `<div onclick="selectDoctor('${d.id}','${(d.prenom+' '+d.nom).replace(/'/g,"\\'")}','${d.medecin_code}')"
            style="padding:10px 14px;cursor:pointer;font-size:13px;border-bottom:1px solid var(--border)"
            onmouseover="this.style.background='var(--teal-dim)'" onmouseout="this.style.background=''">
        🩺 Dr. ${d.prenom} ${d.nom} <span style="color:var(--teal2);font-size:11px">${d.medecin_code}</span>
      </div>`
    ).join('');
    dd.style.display = '';
  }, 350);
}

function selectDoctor(id, name, code) {
  _selectedDoctorId = id;
  document.getElementById('regDoctorId').value = id;
  document.getElementById('regDoctorSearch').value = '';
  document.getElementById('regDoctorDropdown').style.display = 'none';
  document.getElementById('regDoctorSelectedName').textContent = `🩺 Dr. ${name} (${code})`;
  document.getElementById('regDoctorSelected').style.display = 'flex';
}

function clearDoctorSelection() {
  _selectedDoctorId = null;
  document.getElementById('regDoctorId').value = '';
  document.getElementById('regDoctorSearch').value = '';
  document.getElementById('regDoctorSelected').style.display = 'none';
}

let _inviteDebounce = null;
function debounceCheckInvite(val) {
  clearTimeout(_inviteDebounce);
  const msgEl = document.getElementById('regInviteMsg');
  const infoEl = document.getElementById('regInviteInfo');
  if (!val.trim()) { msgEl.innerHTML = ''; infoEl.style.display='none'; return; }
  _inviteDebounce = setTimeout(async () => {
    const res = await api(`/api/invite/${encodeURIComponent(val.trim())}`, 'GET');
    if (res.ok) {
      infoEl.textContent = `✅ Bonjour ${res.prenom} ${res.nom} — lien valide.`;
      infoEl.style.display = '';
      msgEl.innerHTML = '';
    } else {
      infoEl.style.display = 'none';
      msgEl.innerHTML = `<span style="color:var(--red)">${res.error || 'Lien invalide.'}</span>`;
    }
  }, 600);
}

async function doRegister() {
  const username  = document.getElementById('regUsername').value.trim();
  const password  = document.getElementById('regPassword').value;
  const password2 = document.getElementById('regPassword2').value;
  if (!username || !password) {
    _authMsg('registerMsg','error','Tous les champs sont requis.'); return;
  }
  const _pwErr = _validatePasswordFrontend(password);
  if (_pwErr) { _authMsg('registerMsg','error', _pwErr); return; }
  if (password !== password2) {
    _authMsg('registerMsg','error','Les mots de passe ne correspondent pas.'); return;
  }

  if (_regRole === 'patient') {
    if (_patientRegMethod === 'invite') {
      const token = document.getElementById('regInviteToken').value.trim();
      if (!token) { _authMsg('registerMsg','error','Veuillez coller votre token d\'invitation.'); return; }
      const res = await api('/api/patient-register','POST',{invite_token:token,username,password});
      if (res.ok) {
        _authMsg('registerMsg','success','Compte créé avec succès ! Vous pouvez vous connecter.');
        setTimeout(() => showAuthPanel('login'), 2200);
      } else {
        _authMsg('registerMsg','error', res.error || 'Erreur lors de la création du compte.');
      }
    } else {
      // free registration
      const nom        = document.getElementById('regPatNom').value.trim();
      const prenom     = document.getElementById('regPatPrenom').value.trim();
      const ddn        = document.getElementById('regPatDdn').value;
      const email      = document.getElementById('regPatEmail').value.trim();
      const medecin_id = document.getElementById('regDoctorId').value || '';
      if (!nom || !prenom || !ddn) {
        _authMsg('registerMsg','error','Nom, prénom et date de naissance sont requis.'); return;
      }
      if (!email || !email.includes('@')) {
        _authMsg('registerMsg','error','L\'adresse email est obligatoire.'); return;
      }
      const res = await api('/api/patient-register','POST',{nom,prenom,ddn,email,medecin_id,username,password});
      if (res.ok) {
        _authMsg('registerMsg','success','Compte créé avec succès ! Vous pouvez vous connecter.');
        setTimeout(() => showAuthPanel('login'), 2200);
      } else {
        _authMsg('registerMsg','error', res.error || 'Erreur lors de la création du compte.');
      }
    }
  } else {
    const nom            = document.getElementById('regNom').value.trim();
    const prenom         = document.getElementById('regPrenom').value.trim();
    const email          = document.getElementById('regEmail').value.trim();
    const organisation   = document.getElementById('regOrganisation').value.trim();
    const date_naissance = document.getElementById('regDateNaissance').value;
    if (!nom || !prenom) { _authMsg('registerMsg','error','Nom et prénom sont requis.'); return; }
    if (!email) { _authMsg('registerMsg','error','L\'adresse email est obligatoire.'); return; }
    const res = await api('/api/register-medecin','POST',{username,password,nom,prenom,email,organisation,date_naissance});
    if (res.ok) {
      _authMsg('registerMsg','success', res.message || 'Demande envoyée ! Un administrateur validera votre compte.');
      setTimeout(() => showAuthPanel('login'), 3000);
    } else {
      _authMsg('registerMsg','error', res.error || 'Erreur lors de la création du compte.');
    }
  }
}

async function doForgotPassword() {
  const username = document.getElementById('forgotUsername').value.trim();
  if (!username) { _authMsg('forgotMsg','error','Veuillez entrer votre identifiant.'); return; }
  const res = await api('/api/forgot-password','POST',{username});
  _authMsg('forgotMsg', res.ok ? 'success' : 'error',
    res.message || (res.ok ? 'Email envoyé si le compte existe.' : res.error));
}

async function doResetPassword() {
  const token     = document.getElementById('resetToken').value;
  const password  = document.getElementById('resetPassword').value;
  const password2 = document.getElementById('resetPassword2').value;
  const _pwErr2 = _validatePasswordFrontend(password);
  if (_pwErr2) { _authMsg('resetMsg','error', _pwErr2); return; }
  if (password !== password2) {
    _authMsg('resetMsg','error','Les mots de passe ne correspondent pas.'); return;
  }
  const res = await api('/api/reset-password','POST',{token, new_password: password});
  if (res.ok) {
    _authMsg('resetMsg','success','Mot de passe réinitialisé ! Vous pouvez vous connecter.');
    setTimeout(() => {
      window.history.replaceState({},'','/');
      showAuthPanel('login');
    }, 2200);
  } else {
    _authMsg('resetMsg','error', res.error || 'Lien invalide ou expiré.');
  }
}

async function doLogout() {
  await api('/logout','POST');
  USER = null; currentPatientId = null;
  document.getElementById('loginScreen').style.display = 'flex';
  document.getElementById('mainApp').style.display = 'none';
  showAuthPanel('login');
}

