// ─── HOME NAVIGATION ──────────────────────────────────────────────────────────
function goHome() {
  if (!USER) return;
  if (USER.role === 'medecin' || USER.role === 'assistant') showView('dashboard-medecin');
  else if (USER.role === 'admin') showView('admin-dashboard');
  else showView('dashboard-patient');
}

// ─── APP INIT ─────────────────────────────────────────────────────────────────
function initApp() {
  const roleLabels = {medecin:'Médecin Ophtalmologiste',assistant:'Secrétaire Médicale',patient:'Espace Patient',admin:'Administrateur'};
  const roleIcons  = {medecin:'&#128065;', assistant:'&#128203;', patient:'&#128100;', admin:'&#9881;'};
  document.getElementById('topbarUser').textContent = USER.prenom + ' ' + USER.nom;
  document.getElementById('topbarRole').textContent = roleLabels[USER.role] || USER.role;
  document.getElementById('roleDot').className = 'role-dot ' + USER.role;
  document.getElementById('sidebarRole').textContent = roleLabels[USER.role] || USER.role;
  // Dynamic logo icon based on role
  const logoEl = document.getElementById('sidebarLogoIcon');
  if (logoEl) logoEl.innerHTML = roleIcons[USER.role] || '&#128065;';

  buildSidebar();
  loadNotifications();
  if (USER.role === 'medecin') {
    api('/api/medecins').then(list => { MEDECINS = list || []; });
    document.getElementById('globalSearchWrap').style.display = 'block';
  }

  if (USER.role === 'medecin') {
    showView('dashboard-medecin');
    _updateTodayBadge();
    setInterval(_updateTodayBadge, 60000);
  } else if (USER.role === 'admin') {
    showView('admin-dashboard');
  } else {
    showView('dashboard-patient');
  }

  setInterval(loadNotifications, 30000);
}

function buildSidebar() {
  let html = '';
  if (USER.role === 'medecin') {
    html = `
      <div class="nav-section">
        <div class="nav-section-label">Navigation</div>
        <button class="nav-btn" onclick="showView('dashboard-medecin')">📊 ${t('Tableau de bord')}</button>
        <button class="nav-btn" id="navToday" onclick="showView('today')">🏥 ${t("Salle d'attente")}</button>
        <button class="nav-btn" onclick="showView('agenda')">📅 ${t('Agenda & RDV')}</button>
        <button class="nav-btn" onclick="showView('questions-medecin')">💬 ${t('Questions patients')}</button>
        <button class="nav-btn" onclick="showView('ai-assistant')">🤖 ${t('Assistant IA')}</button>
        <button class="nav-btn" onclick="showView('statistiques')">📈 ${t('Statistiques')}</button>
        <button class="nav-btn" onclick="showView('unassigned-patients')">👥 ${t('Patients sans médecin')}</button>
      </div>
      <div class="nav-section">
        <div class="nav-section-label" style="display:flex;align-items:center;justify-content:space-between;padding-right:10px">
          ${t('Patients')}
          <div style="display:flex;gap:4px">
            <button class="btn btn-sm btn-ghost" style="padding:3px 8px;font-size:11px" onclick="openAddPatient()">+ ${t('Ajouter')}</button>
            <button class="btn btn-sm btn-ghost" style="padding:3px 8px;font-size:11px" onclick="openImport()">↑ ${t('Importer')}</button>
          </div>
        </div>
      </div>
      <div class="sidebar-patient-section">
        <div class="sidebar-patient-search">
          <input type="text" placeholder="${t('Rechercher un patient...')}" oninput="searchPatients(this.value)">
        </div>
        <div style="display:flex;gap:4px;padding:4px 8px 0">
          <button id="btnMesPatients" class="btn btn-sm btn-primary" style="flex:1;justify-content:center;font-size:11px" onclick="setSidebarFilter(false)">${t('Mes patients')}</button>
          <button id="btnTousPatients" class="btn btn-sm btn-ghost" style="flex:1;justify-content:center;font-size:11px" onclick="setSidebarFilter(true)">${t('Tous')}</button>
        </div>
        <div class="patient-list-scroll" id="patientListSidebar"></div>
      </div>`;
  } else if (USER.role === 'admin') {
    html = `
      <div class="nav-section">
        <div class="nav-section-label">${t('Administration')}</div>
        <button class="nav-btn" onclick="showView('admin-dashboard')">📊 ${t('Tableau de bord')}</button>
        <button class="nav-btn" id="navAdminPending" onclick="showView('admin-pending')">⏳ ${t('Comptes en attente')} <span id="pendingBadge" style="background:var(--amber);color:#000;border-radius:10px;padding:1px 7px;font-size:11px;margin-left:4px;display:none"></span></button>
        <button class="nav-btn" onclick="showView('admin-users')">👥 ${t('Tous les utilisateurs')}</button>
        <button class="nav-btn" onclick="showView('admin-create-medecin')">🩺 ${t('Créer un médecin')}</button>
        <button class="nav-btn" onclick="showView('admin-create-patient')">🧑 ${t('Créer un patient')}</button>
      </div>`;
  } else {
    html = `
      <div class="nav-section">
        <div class="nav-section-label">${t('Mon espace')}</div>
        <button class="nav-btn" onclick="showView('dashboard-patient')">🏠 Accueil</button>
        <button class="nav-btn" onclick="showView('mes-rdv')">📅 ${t('Mes rendez-vous')}</button>
        <button class="nav-btn" onclick="showView('mes-documents')">📎 ${t('Mes documents')}</button>
        <button class="nav-btn" onclick="showView('mes-questions')">💬 ${t('Questions au médecin')}</button>
      </div>`;
  }
  document.getElementById('sidebarNav').innerHTML = html;
  if (USER.role === 'medecin') loadPatientsSidebar();
  if (USER.role === 'admin') _updatePendingBadge();
  buildBottomNav();
}

function buildBottomNav() {
  const nav = document.getElementById('bottomNav');
  if (!nav) return;
  let items = [];
  if (USER.role === 'medecin') {
    items = [
      { view: 'dashboard-medecin', icon: '📊', label: t('Accueil') },
      { view: 'today',             icon: '🏥', label: t('Salle att.'), id: 'bniToday' },
      { view: 'agenda',            icon: '📅', label: t('Agenda') },
      { view: 'ai-assistant',      icon: '🤖', label: t('IA') },
      { view: 'settings',          icon: '⚙',  label: t('Réglages') },
    ];
  } else if (USER.role === 'admin') {
    items = [
      { view: 'admin-dashboard', icon: '📊', label: t('Accueil') },
      { view: 'admin-pending',   icon: '⏳', label: t('En attente'), id: 'bniPending' },
      { view: 'admin-users',     icon: '👥', label: t('Utilisateurs') },
      { view: 'settings',        icon: '⚙',  label: t('Réglages') },
    ];
  } else {
    items = [
      { view: 'dashboard-patient', icon: '🏠', label: t('Accueil') },
      { view: 'mes-rdv',           icon: '📅', label: t('RDV') },
      { view: 'mes-documents',     icon: '📎', label: t('Documents') },
      { view: 'mes-questions',     icon: '💬', label: t('Questions') },
      { view: 'settings',          icon: '⚙',  label: t('Réglages') },
    ];
  }
  nav.innerHTML = items.map(it => `
    <button class="bottom-nav-item" data-view="${it.view}"
            onclick="showView('${it.view}')"
            ${it.id ? `id="${it.id}"` : ''}>
      <span class="bni-icon">${it.icon}</span>
      <span class="bni-label">${it.label}</span>
      ${it.badge ? `<span class="bni-badge" id="${it.badge}"></span>` : ''}
    </button>`).join('');
}

// ─── VIEWS ROUTER ─────────────────────────────────────────────────────────────
function goBack() {
  if (_viewHistory.length < 2) return;
  _viewHistory.pop(); // remove current
  const prev = _viewHistory.pop(); // get previous
  if (prev) showView(prev.viewId, prev.title, true);
}

function showView(viewId, title, _fromBack) {
  closeMobileSidebar();
  if (!_fromBack) {
    // Push to history (max 20 entries, avoid duplicate consecutive)
    const last = _viewHistory[_viewHistory.length - 1];
    if (!last || last.viewId !== viewId) {
      _viewHistory.push({ viewId, title: title || null });
      if (_viewHistory.length > 20) _viewHistory.shift();
    }
  }
  currentView = viewId;
  const titles = {
    'dashboard-medecin':'Tableau de bord médecin',
    'dashboard-patient':'Mon espace santé','agenda':'Agenda & Rendez-vous',
    'questions-medecin':'Questions des patients','ai-assistant':'Assistant IA Ophtalmologie',
    'patient-profile':'Dossier patient','liste-patients-anon':'Liste des patients',
    'mes-rdv':'Mes rendez-vous','mes-documents':'Mes documents','mes-questions':'Questions au médecin',
    'today': "Salle d'attente — Aujourd'hui",
    'admin-dashboard':'Tableau de bord — Administration',
    'admin-pending':'Comptes en attente de validation',
    'admin-users':'Gestion des utilisateurs',
    'admin-create-medecin':'Créer un compte médecin',
    'admin-create-patient':'Créer un dossier patient',
    'settings':'Paramètres',
    'statistiques':'Statistiques',
    'unassigned-patients':'Patients sans médecin'
  };
  document.getElementById('topbarTitle').textContent = title || t(titles[viewId] || viewId);
  // Back button
  const backBtn = document.getElementById('topbarBackBtn');
  if (backBtn) backBtn.style.display = _viewHistory.length > 1 ? 'flex' : 'none';
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.bottom-nav-item').forEach(b => {
    b.classList.toggle('active', b.dataset.view === viewId);
  });

  // Render view
  const c = document.getElementById('mainContent');
  if (viewId === 'dashboard-medecin') renderDashboardMedecin(c);
  else if (viewId === 'dashboard-patient') renderDashboardPatient(c);
  else if (viewId === 'agenda') renderAgenda(c);
  else if (viewId === 'questions-medecin') renderQuestionsMedecin(c);
  else if (viewId === 'ai-assistant') renderAiAssistant(c);
  else if (viewId === 'patient-profile') renderPatientProfile(c, currentPatientId);
  else if (viewId === 'liste-patients-anon') renderListePatientsAnon(c);
  else if (viewId === 'mes-rdv') renderMesRdv(c);
  else if (viewId === 'mes-documents') renderMesDocuments(c);
  else if (viewId === 'mes-questions') renderMesQuestions(c);
  else if (viewId === 'today') renderTodayView(c);
  else if (viewId === 'admin-dashboard') renderAdminDashboard(c);
  else if (viewId === 'admin-pending') renderAdminPending(c);
  else if (viewId === 'admin-users') renderAdminUsers(c);
  else if (viewId === 'admin-create-medecin') renderAdminCreateMedecin(c);
  else if (viewId === 'admin-create-patient') renderAdminCreatePatient(c);
  else if (viewId === 'settings') renderSettings(c);
  else if (viewId === 'statistiques') renderStatistiques(c);
  else if (viewId === 'unassigned-patients') renderUnassignedPatients(c);
}

