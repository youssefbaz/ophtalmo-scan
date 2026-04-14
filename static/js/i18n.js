// ─── I18N ─────────────────────────────────────────────────────────────────────
const TRANSLATIONS = {
  fr: {},
  en: {
    // Sidebar nav
    'Tableau de bord':'Dashboard','Patients':'Patients','Agenda & RDV':'Agenda & Appointments',
    'Questions patients':'Patient Questions','Assistant IA':'AI Assistant',
    'Statistiques':'Statistics',
    'Salle d\'attente':'Waiting Room','Paramètres':'Settings','Se déconnecter':'Log out',
    'Ajouter':'Add','Importer':'Import','Rechercher un patient...':'Search patient...',
    'Mes patients':'My patients','Tous':'All',
    'Administration':'Administration','Comptes en attente':'Pending accounts',
    'Tous les utilisateurs':'All users','Créer un médecin':'Create doctor','Créer un patient':'Create patient',
    'Mon espace':'My space','Mes rendez-vous':'My appointments',
    'Mes documents':'My documents','Questions au médecin':'Questions to doctor',
    // Topbar titles
    'Tableau de bord médecin':'Dashboard','Mon espace santé':'My health space',
    'Agenda & Rendez-vous':'Agenda & Appointments','Questions des patients':'Patient Questions',
    'Assistant IA Ophtalmologie':'Ophthalmology AI Assistant','Dossier patient':'Patient file',
    'Liste des patients':'Patient list',"Salle d'attente — Aujourd'hui":"Waiting Room — Today",
    'Tableau de bord — Administration':'Dashboard — Administration',
    'Comptes en attente de validation':'Pending accounts','Gestion des utilisateurs':'User management',
    'Créer un compte médecin':'Create doctor account','Créer un dossier patient':'Create patient file',
  },
  ar: {
    // Sidebar nav
    'Tableau de bord':'لوحة التحكم','Patients':'المرضى','Agenda & RDV':'الأجندة والمواعيد',
    'Questions patients':'أسئلة المرضى','Assistant IA':'مساعد الذكاء الاصطناعي',
    'Statistiques':'الإحصائيات',
    'Salle d\'attente':'غرفة الانتظار','Paramètres':'الإعدادات','Se déconnecter':'تسجيل الخروج',
    'Ajouter':'إضافة','Importer':'استيراد','Rechercher un patient...':'البحث عن مريض...',
    'Mes patients':'مرضاي','Tous':'الكل',
    'Administration':'الإدارة','Comptes en attente':'حسابات معلقة',
    'Tous les utilisateurs':'جميع المستخدمين','Créer un médecin':'إنشاء طبيب','Créer un patient':'إنشاء مريض',
    'Mon espace':'مساحتي','Mes rendez-vous':'مواعيدي',
    'Mes documents':'وثائقي','Questions au médecin':'أسئلة للطبيب',
    // Topbar titles
    'Tableau de bord médecin':'لوحة التحكم','Mon espace santé':'مساحتي الصحية',
    'Agenda & Rendez-vous':'الأجندة والمواعيد','Questions des patients':'أسئلة المرضى',
    'Assistant IA Ophtalmologie':'مساعد الذكاء الاصطناعي','Dossier patient':'ملف المريض',
    'Liste des patients':'قائمة المرضى',"Salle d'attente — Aujourd'hui":"غرفة الانتظار — اليوم",
    'Tableau de bord — Administration':'لوحة التحكم — الإدارة',
    'Comptes en attente de validation':'حسابات معلقة','Gestion des utilisateurs':'إدارة المستخدمين',
    'Créer un compte médecin':'إنشاء حساب طبيب','Créer un dossier patient':'إنشاء ملف مريض',
  }
};
let _currentLang = localStorage.getItem('ophtalmo_lang') || 'fr';

function applyLang(lang) {
  _currentLang = lang;
  localStorage.setItem('ophtalmo_lang', lang);
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
  // Rebuild sidebar to translate nav labels (only when logged in)
  if (typeof buildSidebar === 'function' && typeof USER !== 'undefined' && USER) buildSidebar();
  // Update static translated elements
  const sBtn = document.getElementById('sidebarSettingsBtn');
  if (sBtn) sBtn.textContent = '⚙ ' + t('Paramètres');
  const uSettings = document.getElementById('userMenuSettings');
  if (uSettings) uSettings.textContent = '⚙ ' + t('Paramètres');
  const uLogout = document.getElementById('userMenuLogout');
  if (uLogout) uLogout.textContent = '↩ ' + t('Se déconnecter');
  // Re-render current view if it's settings (language buttons are inside it)
  if (typeof currentView !== 'undefined' && currentView === 'settings') {
    const c = document.getElementById('mainContent');
    if (c && typeof renderSettings === 'function') renderSettings(c);
  }
  // Refresh topbar title with new language
  if (typeof currentView !== 'undefined' && USER && currentView) {
    const titles = {
      'dashboard-medecin':'Tableau de bord médecin','dashboard-patient':'Mon espace santé',
      'agenda':'Agenda & Rendez-vous','questions-medecin':'Questions des patients',
      'ai-assistant':'Assistant IA Ophtalmologie','patient-profile':'Dossier patient',
      'liste-patients-anon':'Liste des patients','mes-rdv':'Mes rendez-vous',
      'mes-documents':'Mes documents','mes-questions':'Questions au médecin',
      'today':"Salle d'attente — Aujourd'hui",'admin-dashboard':'Tableau de bord — Administration',
      'admin-pending':'Comptes en attente de validation','admin-users':'Gestion des utilisateurs',
      'admin-create-medecin':'Créer un compte médecin','admin-create-patient':'Créer un dossier patient',
      'settings':'Paramètres',
    'statistiques':'Statistiques'
    };
    const titleEl = document.getElementById('topbarTitle');
    if (titleEl && titles[currentView]) titleEl.textContent = t(titles[currentView]);
  }
}

function t(key) {
  if (_currentLang === 'fr' || !TRANSLATIONS[_currentLang]) return key;
  return TRANSLATIONS[_currentLang][key] || key;
}

function applyTheme(theme) {
  document.body.classList.remove('theme-light','theme-clinical','theme-contrast');
  if (theme !== 'dark') document.body.classList.add('theme-' + theme);
  localStorage.setItem('ophtalmo_theme', theme);
}

// ─── PAGE LOAD: check for password reset token in URL ─────────────────────────
(async function checkResetToken() {
  initPasswordToggles(); // wire up eye-toggles on all static auth panels

  applyLang(_currentLang);
  const storedTheme = localStorage.getItem('ophtalmo_theme') || 'dark';
  applyTheme(storedTheme);

  // Pre-select role based on URL path (/medecin or /patient)
  const path = window.location.pathname.replace(/\/$/, '');
  if (path === '/medecin' || path === '/patient') {
    const role = path === '/medecin' ? 'medecin' : 'patient';
    const tabs  = document.querySelectorAll('.role-tab');
    tabs.forEach(t => {
      const isTarget = t.getAttribute('onclick').includes(`'${role}'`);
      t.classList.toggle('active', isTarget);
    });
    // Hide the role-tabs switcher — the URL already communicates the role
    const tabsContainer = document.querySelector('.role-tabs');
    if (tabsContainer) tabsContainer.style.display = 'none';
    // Update demo-creds hint
    document.getElementById('demoCreds').innerHTML = DEMO[role].hint;
    // Update subtitle
    document.getElementById('loginSubtitle').textContent =
      role === 'medecin' ? 'Espace médecin' : 'Espace patient';
    // On médecin portal: hide self-registration link (admin creates médecin accounts)
    // On patient portal: hide the médecin register tab in the register panel
    const authLinks = document.querySelector('#panelLogin .auth-links');
    if (role === 'medecin' && authLinks) {
      authLinks.innerHTML = '<a class="auth-link" onclick="showAuthPanel(\'forgot\')">Mot de passe oublié ?</a>';
    }
  }

  const params      = new URLSearchParams(window.location.search);
  const token       = params.get('token');
  const inviteToken = params.get('invite');
  if (token) {
    document.getElementById('resetToken').value = token;
    showAuthPanel('reset');
    return; // don't attempt auto-login
  }
  if (inviteToken) {
    showAuthPanel('register');
    setRegRole('patient');
    setPatientRegMethod('invite');
    setTimeout(() => {
      const el = document.getElementById('regInviteToken');
      if (el) { el.value = inviteToken; debounceCheckInvite(inviteToken); }
    }, 50);
    window.history.replaceState({}, '', '/');
    return;
  }
  // Auto-restore session if already logged in
  const me = await api('/me');
  if (me && me.authenticated) {
    USER = me;
    document.getElementById('loginScreen').style.display = 'none';
    document.getElementById('mainApp').style.display = 'flex';
    initApp();
  }
})();
