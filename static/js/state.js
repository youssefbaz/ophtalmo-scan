// ─── STATE ────────────────────────────────────────────────────────────────────
let USER = null;
let MEDECINS = [];
let currentPatientId = null;
let currentView = null;
let _viewHistory = [];   // navigation stack for back button
let aiContext = '';
let aiContextPid = '';
let notifOpen = false;

