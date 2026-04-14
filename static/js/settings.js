// ─── CHANGE PASSWORD ──────────────────────────────────────────────────────────

function openChangePassword() {
  closeUserMenu();
  showModal('Changer le mot de passe', `
    <div style="margin-bottom:12px">
      <label class="lbl">Mot de passe actuel</label>
      <input type="password" class="input" id="cpCurrent" placeholder="Votre mot de passe actuel">
    </div>
    <div style="margin-bottom:12px">
      <label class="lbl">Nouveau mot de passe</label>
      <input type="password" class="input" id="cpNew" placeholder="Au moins 6 caractères">
    </div>
    <div>
      <label class="lbl">Confirmer le nouveau mot de passe</label>
      <input type="password" class="input" id="cpConfirm" placeholder="Répétez le nouveau mot de passe">
    </div>
    <div id="cpError" style="color:#fca5a5;font-size:13px;margin-top:10px;display:none"></div>
  `, async () => {
    const current  = document.getElementById('cpCurrent').value;
    const newPw    = document.getElementById('cpNew').value;
    const confirm2 = document.getElementById('cpConfirm').value;
    const errEl    = document.getElementById('cpError');
    errEl.style.display = 'none';
    if (newPw !== confirm2) {
      errEl.textContent = 'Les deux mots de passe ne correspondent pas.';
      errEl.style.display = 'block'; return;
    }
    if (newPw.length < 6) {
      errEl.textContent = 'Le mot de passe doit faire au moins 6 caractères.';
      errEl.style.display = 'block'; return;
    }
    const res = await api('/api/change-password', 'POST', {current_password: current, new_password: newPw});
    if (res.ok) {
      closeModal();
      showModal('Mot de passe modifié ✓',
        '<div style="text-align:center;padding:10px"><div style="font-size:36px;margin-bottom:12px">✅</div><p style="color:var(--text2)">Votre mot de passe a été mis à jour avec succès.</p></div>',
        () => closeModal(), true
      );
    } else {
      errEl.textContent = res.error || 'Erreur';
      errEl.style.display = 'block';
    }
  });
}

// ─── USER MENU ────────────────────────────────────────────────────────────────

let _userMenuOpen = false;

function toggleUserMenu(e) {
  e.stopPropagation();
  _userMenuOpen = !_userMenuOpen;
  document.getElementById('userMenu').classList.toggle('open', _userMenuOpen);
}

function closeUserMenu() {
  _userMenuOpen = false;
  document.getElementById('userMenu').classList.remove('open');
}

document.addEventListener('click', e => {
  if (!e.target.closest('.user-menu') && !e.target.closest('.topbar-user')) closeUserMenu();
});

// ─── PDF ORDONNANCE DOWNLOAD ──────────────────────────────────────────────────

async function downloadOrdonnancePDF(pid, oid) {
  try {
    const resp = await fetch(`/api/patients/${pid}/ordonnances/${oid}/pdf`);
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      alert(err.error || `Erreur ${resp.status} lors du téléchargement.`);
      return;
    }
    const blob = await resp.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `ordonnance_${oid}.pdf`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch(e) {
    alert('Erreur lors du téléchargement du PDF.');
  }
}

// ─── AI CONSULTATION SUMMARY ──────────────────────────────────────────────────

async function generateConsultationSummary(pid) {
  // Show loading modal with proper close button
  showModal('Compte-rendu IA', `
    <div style="text-align:center;padding:20px">
      <div style="font-size:36px;margin-bottom:12px">🤖</div>
      <div id="summaryLoading" style="color:var(--text2);margin-bottom:16px">Génération du compte-rendu…</div>
      <div id="summaryResult" style="text-align:left;display:none;background:var(--bg2);border-radius:10px;padding:16px;font-size:13px;color:var(--text);white-space:pre-wrap;max-height:380px;overflow-y:auto"></div>
      <div id="summaryActions" style="display:none;margin-top:14px;display:none;gap:8px;justify-content:flex-end">
        <button class="btn btn-ghost btn-sm" id="summaryCopyBtn" onclick="summaryCopy()">📋 Copier</button>
        <button class="btn btn-primary btn-sm" onclick="summaryOpenPage()">🖨 Ouvrir / Imprimer</button>
        <button class="btn btn-ghost btn-sm" onclick="closeModal()">✕ Fermer</button>
      </div>
    </div>
  `);

  window._lastSummaryText = '';
  window._lastSummaryPid  = pid;

  const res = await api(`/api/patients/${pid}/consultation-summary`, 'POST', {});
  const loading = document.getElementById('summaryLoading');
  const el      = document.getElementById('summaryResult');
  const actions = document.getElementById('summaryActions');
  if (!el) return;

  if (loading) loading.style.display = 'none';

  if (res.ok && res.summary) {
    window._lastSummaryText = res.summary;
    el.textContent = res.summary;
    el.style.display = 'block';
    if (actions) { actions.style.display = 'flex'; }
  } else {
    el.textContent = res.error || 'Erreur lors de la génération.';
    el.style.color = 'var(--danger, #ef4444)';
    el.style.display = 'block';
    const btnDiv = document.createElement('div');
    btnDiv.style.cssText = 'margin-top:14px;display:flex;gap:8px;justify-content:flex-end';
    // Show Retry button when the failure is transient; Config button otherwise
    if (res.temporary !== false) {
      btnDiv.innerHTML = `
        <button class="btn btn-primary btn-sm" onclick="generateSummary('${pid}')">🔄 Réessayer</button>
        <button class="btn btn-ghost btn-sm" onclick="closeModal('modal')">✕ Fermer</button>`;
    } else {
      btnDiv.innerHTML = `
        <button class="btn btn-ghost btn-sm" onclick="showView('settings')">⚙ Paramètres API</button>
        <button class="btn btn-ghost btn-sm" onclick="closeModal('modal')">✕ Fermer</button>`;
    }
    el.parentElement.appendChild(btnDiv);
  }
}

function summaryCopy() {
  navigator.clipboard.writeText(window._lastSummaryText || '');
  const btn = document.getElementById('summaryCopyBtn');
  if (btn) { btn.textContent = '✓ Copié !'; setTimeout(() => { btn.textContent = '📋 Copier'; }, 2000); }
}

function summaryOpenPage() {
  const text = window._lastSummaryText;
  const patient = window._currentPatient;
  const patientName = patient ? `${patient.prenom} ${patient.nom}` : 'Patient';
  const w = window.open('', '_blank', 'width=800,height=900');
  w.document.write(`<!DOCTYPE html><html><head><meta charset="UTF-8">
  <title>Compte-rendu IA — ${patientName}</title>
  <style>
    body{font-family:Georgia,serif;padding:40px 60px;color:#111;font-size:14px;line-height:1.8;max-width:750px;margin:0 auto}
    h1{font-size:20px;border-bottom:2px solid #333;padding-bottom:8px;margin-bottom:20px}
    .meta{font-size:12px;color:#666;margin-bottom:24px}
    .content{white-space:pre-wrap;font-size:13.5px;line-height:1.9}
    .footer{margin-top:40px;font-size:11px;color:#999;border-top:1px solid #ddd;padding-top:10px}
    .no-print{display:flex;gap:10px;margin-bottom:28px}
    @media print{.no-print{display:none!important}body{padding:20mm 25mm}}
    button{padding:8px 20px;border-radius:6px;border:1px solid #ccc;cursor:pointer;font-size:13px}
    button.primary{background:#0e7a76;color:#fff;border-color:#0e7a76}
  </style>
  </head><body>
  <div class="no-print">
    <button class="primary" onclick="window.print()">🖨 Imprimer</button>
    <button onclick="window.close()">✕ Fermer</button>
  </div>
  <h1>Compte-rendu de consultation — ${patientName}</h1>
  <div class="meta">Généré le ${new Date().toLocaleDateString('fr-FR', {weekday:'long',year:'numeric',month:'long',day:'numeric'})} — OphtalmoScan</div>
  <div class="content">${text.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</div>
  <div class="footer">Document généré automatiquement par OphtalmoScan · À valider par le médecin</div>
  </body></html>`);
  w.document.close();
}

// ─── STATISTIQUES DASHBOARD ───────────────────────────────────────────────────

let _statsCharts = {};

function _destroyStatsCharts() {
  Object.values(_statsCharts).forEach(c => { try { c.destroy(); } catch(e){} });
  _statsCharts = {};
}

function _statsChart(id, config) {
  const ctx = document.getElementById(id);
  if (!ctx) return;
  if (_statsCharts[id]) _statsCharts[id].destroy();
  _statsCharts[id] = new Chart(ctx, config);
}

const STAT_COLORS = [
  '#0e9a94','#f59e0b','#ef4444','#6366f1','#10b981',
  '#f97316','#8b5cf6','#06b6d4','#84cc16','#ec4899'
];

function _shortMonth(ym) {
  const [y, m] = ym.split('-');
  const months = ['Jan','Fév','Mar','Avr','Mai','Juin','Juil','Aoû','Sep','Oct','Nov','Déc'];
  return months[parseInt(m) - 1] + (y !== String(new Date().getFullYear()) ? ' '+y.slice(2) : '');
}

async function renderUnassignedPatients(c) {
  c.innerHTML = '<div style="color:var(--text3);padding:30px;text-align:center">Chargement…</div>';
  const patients = await api('/api/patients/unassigned');
  if (!Array.isArray(patients)) { c.innerHTML = '<div style="color:var(--red);padding:20px">Erreur de chargement.</div>'; return; }

  if (patients.length === 0) {
    c.innerHTML = `<div style="text-align:center;padding:48px;color:var(--text3)">
      <div style="font-size:40px;margin-bottom:12px">👥</div>
      <div style="font-size:16px;font-weight:600;margin-bottom:6px">Aucun patient sans médecin</div>
      <div style="font-size:13px">Tous les patients inscrits ont déjà un médecin assigné.</div>
    </div>`;
    return;
  }

  c.innerHTML = `
    <div style="margin-bottom:20px">
      <div style="font-size:13px;color:var(--text2)">
        ${patients.length} patient(s) inscrit(s) sans médecin assigné.
        Cliquez sur <strong>Ajouter à ma liste</strong> pour les rattacher à votre base.
      </div>
    </div>
    <div id="unassignedList">
      ${patients.map(p => `
        <div class="card" style="margin-bottom:12px;padding:16px 18px;display:flex;align-items:center;gap:14px;flex-wrap:wrap" id="ucard_${p.id}">
          <div style="width:40px;height:40px;border-radius:50%;background:var(--teal-dim);border:2px solid var(--teal);display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0">👤</div>
          <div style="flex:1;min-width:160px">
            <div style="font-weight:600;font-size:14px">${p.prenom || ''} ${p.nom || ''}</div>
            <div style="font-size:12px;color:var(--text2);margin-top:2px">
              ${p.ddn ? '🎂 ' + p.ddn : ''}
              ${p.has_account ? '<span style="color:var(--teal2);margin-left:8px">✓ Compte actif ('+p.username+')</span>' : '<span style="color:var(--text3);margin-left:8px">Pas encore de compte</span>'}
            </div>
          </div>
          <button class="btn btn-primary btn-sm" onclick="claimPatient('${p.id}')">+ Ajouter à ma liste</button>
        </div>`).join('')}
    </div>`;
}

async function claimPatient(pid) {
  const res = await api(`/api/patients/${pid}/claim`, 'POST');
  if (res.ok) {
    const card = document.getElementById(`ucard_${pid}`);
    if (card) {
      card.style.opacity = '0.5';
      card.innerHTML += '<span style="color:var(--teal2);font-size:13px;margin-left:8px">✅ Ajouté</span>';
      setTimeout(() => card.remove(), 1200);
    }
    loadPatientsSidebar();
  } else {
    alert(res.error || 'Erreur');
  }
}

async function renderStatistiques(c) {
  _destroyStatsCharts();
  c.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
      <div style="font-size:13px;color:var(--text3)">Chargement des statistiques…</div>
    </div>
    <div style="text-align:center;padding:60px;color:var(--text3)">
      <div style="font-size:40px;margin-bottom:12px">📊</div>
      <div>Calcul en cours…</div>
    </div>`;

  const s = await api('/api/stats');
  if (!s || s.error) {
    c.innerHTML = `<div style="color:var(--red);padding:40px;text-align:center">Erreur de chargement des statistiques.</div>`;
    return;
  }

  // ── Helper: mini stat card ─────────────────────────────────────────────────
  const statCard = (icon, label, value, sub='', color='var(--teal)') => `
    <div class="stat-card" style="background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px 20px;display:flex;flex-direction:column;gap:4px">
      <div style="display:flex;align-items:center;gap:8px">
        <span style="font-size:20px">${icon}</span>
        <span style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--text3)">${label}</span>
      </div>
      <div style="font-size:32px;font-weight:800;color:${color};line-height:1.1">${value}</div>
      ${sub ? `<div style="font-size:11px;color:var(--text3)">${sub}</div>` : ''}
    </div>`;

  // ── Helper: chart card ─────────────────────────────────────────────────────
  const chartCard = (title, id, height=200) => `
    <div class="card" style="padding:20px">
      <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--teal2);margin-bottom:14px">${title}</div>
      <canvas id="${id}" style="max-height:${height}px"></canvas>
    </div>`;

  // ── Stat grid ──────────────────────────────────────────────────────────────
  const surgeryPct = s.total_patients ? Math.round(s.patients_with_surgery / s.total_patients * 100) : 0;

  c.innerHTML = `
    <style>
      .stats-section-title {
        font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;
        color:var(--teal2);margin:28px 0 14px;display:flex;align-items:center;gap:8px;
      }
      .stats-section-title::after {
        content:'';flex:1;height:1px;background:var(--border);
      }
      .stats-kpi-grid { display:grid;grid-template-columns:repeat(auto-fill,minmax(175px,1fr));gap:12px;margin-bottom:8px }
      .stats-chart-2 { display:grid;grid-template-columns:1fr 1fr;gap:16px }
      .stats-chart-3 { display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px }
      @media(max-width:900px){ .stats-chart-3{grid-template-columns:1fr 1fr} }
      @media(max-width:600px){ .stats-chart-2,.stats-chart-3{grid-template-columns:1fr} }
    </style>

    <!-- ── PATIENTS ──────────────────────────────────────────────────────── -->
    <div class="stats-section-title">👥 Patients</div>
    <div class="stats-kpi-grid">
      ${statCard('👥','Total patients', s.total_patients, 'Tous enregistrés')}
      ${statCard('🆕','Ce mois-ci', s.new_this_month, 'Nouveaux patients', 'var(--amber)')}
      ${statCard('📅','Cette année', s.new_this_year, 'Nouveaux en '+new Date().getFullYear(), 'var(--teal)')}
      ${statCard('⚧','Femmes', s.sex_dist['F']||0, `Hommes : ${s.sex_dist['M']||0}`, '#ec4899')}
      ${statCard('🔬','Consultations moy.', s.avg_consults, 'par patient', 'var(--teal)')}
      ${statCard('✂','Chirurgies', s.patients_with_surgery, surgeryPct+'% des patients', '#6366f1')}
      ${statCard('💉','Injections IVT', s.total_ivt, 'Total IVT réalisées', 'var(--amber)')}
    </div>

    <div class="stats-chart-2" style="margin-top:14px">
      ${chartCard('Nouveaux patients / mois (12 derniers mois)', 'statsPatientMonth', 200)}
      ${chartCard('Répartition par âge', 'statsAgeBands', 200)}
    </div>
    <div class="stats-chart-2" style="margin-top:14px">
      ${chartCard('Répartition par sexe', 'statsSexDist', 180)}
      ${chartCard('Patients / année', 'statsPatientYear', 180)}
    </div>

    <!-- ── RDV ────────────────────────────────────────────────────────────── -->
    <div class="stats-section-title">📅 Rendez-vous</div>
    <div class="stats-kpi-grid">
      ${statCard('📅','Total RDV', s.total_rdv, 'Tous les RDV')}
      ${statCard('✅','Confirmés', s.rdv_confirmed, Math.round(s.rdv_confirmed/Math.max(s.total_rdv,1)*100)+'%', 'var(--teal)')}
      ${statCard('⏳','En attente', s.rdv_pending, 'À valider', 'var(--amber)')}
      ${statCard('❌','Annulés', s.rdv_cancelled, Math.round(s.rdv_cancelled/Math.max(s.total_rdv,1)*100)+'%', 'var(--red)')}
      ${statCard('🚨','Urgents', s.rdv_urgent, 'Total urgences', 'var(--red)')}
      ${statCard('📆','Aujourd\'hui', s.rdv_today, 'RDV prévus', 'var(--teal)')}
      ${statCard('🗓','Cette semaine', s.rdv_week, 'RDV cette semaine')}
      ${statCard('📊','Ce mois', s.rdv_month, 'RDV ce mois')}
    </div>

    <div class="stats-chart-2" style="margin-top:14px">
      ${chartCard('RDV / mois (12 derniers mois)', 'statsRdvMonth', 200)}
      ${chartCard('Activité par jour de la semaine', 'statsRdvWeekday', 200)}
    </div>
    <div class="stats-chart-2" style="margin-top:14px">
      ${chartCard('Répartition par type de RDV', 'statsRdvType', 220)}
      ${chartCard('Statut des RDV', 'statsRdvStatut', 220)}
    </div>

    <!-- ── CONSULTATIONS ──────────────────────────────────────────────────── -->
    <div class="stats-section-title">📋 Consultations & Clinique</div>
    <div class="stats-kpi-grid">
      ${statCard('📋','Consultations', s.total_consults, 'Total enregistrées')}
      ${statCard('📈','Moy. / patient', s.avg_consults, 'consultations', 'var(--teal)')}
    </div>

    <div class="stats-chart-2" style="margin-top:14px">
      ${chartCard('Consultations / mois', 'statsConsultMonth', 200)}
      ${chartCard('Top 10 diagnostics', 'statsDiag', 260)}
    </div>
    <div class="stats-chart-2" style="margin-top:14px">
      ${chartCard('Top 10 motifs de consultation', 'statsMotif', 260)}
      ${chartCard('Top antécédents patients', 'statsAntecedents', 260)}
    </div>
    <div class="stats-chart-2" style="margin-top:14px">
      ${s.surgery_types.length ? chartCard('Types de chirurgie', 'statsSurgery', 220) : ''}
      ${s.ivt_by_med.length ? chartCard('Médicaments IVT utilisés', 'statsIvtMed', 220) : ''}
    </div>

    <div style="height:40px"></div>`;

  // ── Render all charts after DOM is ready ───────────────────────────────────
  requestAnimationFrame(() => {
    const chartDefaults = {
      plugins: { legend: { labels: { color: 'var(--text2)', font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: 'var(--text3)', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' } },
        y: { ticks: { color: 'var(--text3)', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.05)' }, beginAtZero: true }
      }
    };
    const noScales = { plugins: { legend: { labels: { color: 'var(--text2)', font: { size: 11 } } } } };

    // Patients per month
    _statsChart('statsPatientMonth', {
      type: 'bar',
      data: {
        labels: s.patients_per_month.map(d => _shortMonth(d.month)),
        datasets: [{ label: 'Nouveaux patients', data: s.patients_per_month.map(d => d.count),
          backgroundColor: 'rgba(14,154,148,0.7)', borderColor: 'var(--teal)', borderWidth: 1, borderRadius: 4 }]
      },
      options: { ...chartDefaults, plugins: { ...chartDefaults.plugins, legend: { display: false } } }
    });

    // Age bands
    _statsChart('statsAgeBands', {
      type: 'bar',
      data: {
        labels: Object.keys(s.age_bands),
        datasets: [{ label: 'Patients', data: Object.values(s.age_bands),
          backgroundColor: STAT_COLORS, borderRadius: 4 }]
      },
      options: { ...chartDefaults, plugins: { ...chartDefaults.plugins, legend: { display: false } } }
    });

    // Sex distribution (doughnut)
    // Build in a fixed order (M, F, other) with explicit key→colour mapping
    // so the chart is never wrong regardless of dict insertion order.
    const _sexColorMap = { 'M': '#6366f1', 'F': '#ec4899' };
    const _sexLabelMap = { 'M': 'Hommes',  'F': 'Femmes'  };
    const _sexOrder    = ['M', 'F', ...Object.keys(s.sex_dist).filter(k => k !== 'M' && k !== 'F')];
    const _sexFiltered = _sexOrder.filter(k => s.sex_dist[k] !== undefined);
    _statsChart('statsSexDist', {
      type: 'doughnut',
      data: {
        labels:   _sexFiltered.map(k => _sexLabelMap[k] || 'N/R'),
        datasets: [{ data: _sexFiltered.map(k => s.sex_dist[k]), backgroundColor: _sexFiltered.map(k => _sexColorMap[k] || '#94a3b8'), borderWidth: 0 }]
      },
      options: { ...noScales, cutout: '65%' }
    });

    // Patients per year
    _statsChart('statsPatientYear', {
      type: 'bar',
      data: {
        labels: s.patients_per_year.map(d => d.year),
        datasets: [{ label: 'Patients', data: s.patients_per_year.map(d => d.count),
          backgroundColor: 'rgba(99,102,241,0.7)', borderColor: '#6366f1', borderWidth: 1, borderRadius: 4 }]
      },
      options: { ...chartDefaults, plugins: { ...chartDefaults.plugins, legend: { display: false } } }
    });

    // RDV per month
    _statsChart('statsRdvMonth', {
      type: 'line',
      data: {
        labels: s.rdv_per_month.map(d => _shortMonth(d.month)),
        datasets: [{ label: 'RDV', data: s.rdv_per_month.map(d => d.count),
          borderColor: 'var(--teal)', backgroundColor: 'rgba(14,154,148,0.12)',
          fill: true, tension: 0.35, pointRadius: 3, pointBackgroundColor: 'var(--teal)' }]
      },
      options: { ...chartDefaults, plugins: { ...chartDefaults.plugins, legend: { display: false } } }
    });

    // RDV per weekday
    _statsChart('statsRdvWeekday', {
      type: 'bar',
      data: {
        labels: s.rdv_per_weekday.map(d => d.day),
        datasets: [{ label: 'RDV', data: s.rdv_per_weekday.map(d => d.count),
          backgroundColor: s.rdv_per_weekday.map((d,i) => STAT_COLORS[i % STAT_COLORS.length]),
          borderRadius: 4 }]
      },
      options: { ...chartDefaults, plugins: { ...chartDefaults.plugins, legend: { display: false } } }
    });

    // RDV by type (horizontal bar)
    _statsChart('statsRdvType', {
      type: 'bar',
      data: {
        labels: s.rdv_by_type.map(d => d.type),
        datasets: [{ label: 'RDV', data: s.rdv_by_type.map(d => d.count),
          backgroundColor: 'rgba(245,158,11,0.75)', borderColor: 'var(--amber)', borderWidth: 1, borderRadius: 4 }]
      },
      options: {
        indexAxis: 'y',
        ...chartDefaults,
        plugins: { ...chartDefaults.plugins, legend: { display: false } }
      }
    });

    // RDV statut (pie)
    _statsChart('statsRdvStatut', {
      type: 'pie',
      data: {
        labels: ['Confirmés', 'En attente', 'Annulés'],
        datasets: [{ data: [s.rdv_confirmed, s.rdv_pending, s.rdv_cancelled],
          backgroundColor: ['#0e9a94','#f59e0b','#ef4444'], borderWidth: 0 }]
      },
      options: noScales
    });

    // Consultations per month
    _statsChart('statsConsultMonth', {
      type: 'line',
      data: {
        labels: s.consults_per_month.map(d => _shortMonth(d.month)),
        datasets: [{ label: 'Consultations', data: s.consults_per_month.map(d => d.count),
          borderColor: '#6366f1', backgroundColor: 'rgba(99,102,241,0.12)',
          fill: true, tension: 0.35, pointRadius: 3, pointBackgroundColor: '#6366f1' }]
      },
      options: { ...chartDefaults, plugins: { ...chartDefaults.plugins, legend: { display: false } } }
    });

    // Top diagnostics (horizontal bar)
    if (s.top_diagnostics.length) {
      _statsChart('statsDiag', {
        type: 'bar',
        data: {
          labels: s.top_diagnostics.map(d => d.label.length > 35 ? d.label.slice(0,35)+'…' : d.label),
          datasets: [{ label: 'Cas', data: s.top_diagnostics.map(d => d.count),
            backgroundColor: STAT_COLORS, borderRadius: 4 }]
        },
        options: {
          indexAxis: 'y',
          ...chartDefaults,
          plugins: { ...chartDefaults.plugins, legend: { display: false } }
        }
      });
    }

    // Top motifs
    if (s.top_motifs.length) {
      _statsChart('statsMotif', {
        type: 'bar',
        data: {
          labels: s.top_motifs.map(d => d.label.length > 35 ? d.label.slice(0,35)+'…' : d.label),
          datasets: [{ label: 'Consultations', data: s.top_motifs.map(d => d.count),
            backgroundColor: 'rgba(6,182,212,0.75)', borderColor: '#06b6d4', borderWidth: 1, borderRadius: 4 }]
        },
        options: {
          indexAxis: 'y',
          ...chartDefaults,
          plugins: { ...chartDefaults.plugins, legend: { display: false } }
        }
      });
    }

    // Top antécédents
    if (s.top_antecedents.length) {
      _statsChart('statsAntecedents', {
        type: 'bar',
        data: {
          labels: s.top_antecedents.map(d => d.label.length > 32 ? d.label.slice(0,32)+'…' : d.label),
          datasets: [{ label: 'Patients', data: s.top_antecedents.map(d => d.count),
            backgroundColor: 'rgba(139,92,246,0.75)', borderColor: '#8b5cf6', borderWidth: 1, borderRadius: 4 }]
        },
        options: {
          indexAxis: 'y',
          ...chartDefaults,
          plugins: { ...chartDefaults.plugins, legend: { display: false } }
        }
      });
    }

    // Surgery types
    if (s.surgery_types.length) {
      _statsChart('statsSurgery', {
        type: 'bar',
        data: {
          labels: s.surgery_types.map(d => d.label.length > 30 ? d.label.slice(0,30)+'…' : d.label),
          datasets: [{ label: 'Patients', data: s.surgery_types.map(d => d.count),
            backgroundColor: STAT_COLORS, borderRadius: 4 }]
        },
        options: {
          indexAxis: 'y',
          ...chartDefaults,
          plugins: { ...chartDefaults.plugins, legend: { display: false } }
        }
      });
    }

    // IVT medications
    if (s.ivt_by_med.length) {
      _statsChart('statsIvtMed', {
        type: 'doughnut',
        data: {
          labels: s.ivt_by_med.map(d => d.label),
          datasets: [{ data: s.ivt_by_med.map(d => d.count), backgroundColor: STAT_COLORS, borderWidth: 0 }]
        },
        options: { ...noScales, cutout: '55%' }
      });
    }
  });
}

// ─── CSV EXPORT ───────────────────────────────────────────────────────────────

function exportPatientsCSV() {
  const a = document.createElement('a');
  a.href = '/api/patients/export-csv';
  a.download = `patients_${new Date().toISOString().slice(0,10)}.csv`;
  a.click();
}

// ─── IVT TIMELINE CHART ───────────────────────────────────────────────────────

function renderIVTChart(ivtList, pid) {
  const canvas = document.getElementById(`chart-ivt-${pid}`);
  if (!canvas || !ivtList.length) return;
  const ctx = canvas.getContext('2d');
  const sorted = [...ivtList].sort((a,b) => a.date.localeCompare(b.date));
  const odData = sorted.filter(i => i.oeil === 'OD');
  const ogData = sorted.filter(i => i.oeil === 'OG');
  const allDates = [...new Set(sorted.map(i => i.date))];

  if (window[`_ivtChart_${pid}`]) window[`_ivtChart_${pid}`].destroy();
  window[`_ivtChart_${pid}`] = new Chart(ctx, {
    type: 'scatter',
    data: {
      datasets: [
        {
          label: 'OD', data: odData.map(i => ({x: i.date, y: 1, num: i.numero, med: i.medicament})),
          backgroundColor: 'rgba(14,165,160,0.8)', pointRadius: 8, pointHoverRadius: 10
        },
        {
          label: 'OG', data: ogData.map(i => ({x: i.date, y: 0, num: i.numero, med: i.medicament})),
          backgroundColor: 'rgba(245,158,11,0.8)', pointRadius: 8, pointHoverRadius: 10
        }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: true,
      plugins: {
        legend: { labels: { color: '#7fa8be', font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const d = ctx.raw;
              return `${ctx.dataset.label} #${d.num} — ${d.med} (${d.x})`;
            }
          }
        }
      },
      scales: {
        x: { type: 'category', labels: allDates, ticks: { color: '#3d6a82', font: { size: 9 } }, grid: { color: 'rgba(21,48,69,0.5)' } },
        y: {
          ticks: { color: '#3d6a82', callback: v => v === 1 ? 'OD' : 'OG', font: { size: 10 } },
          grid: { color: 'rgba(21,48,69,0.5)' }, min: -0.5, max: 1.5, stepSize: 1
        }
      }
    }
  });
}

// ─── SETTINGS ─────────────────────────────────────────────────────────────────
async function renderSettings(c) {
  closeUserMenu();
  const profile    = await api('/api/settings/profile');
  const storedTheme = localStorage.getItem('ophtalmo_theme') || 'dark';
  const lang        = localStorage.getItem('ophtalmo_lang') || 'fr';
  const canEdit     = USER.role === 'medecin' || USER.role === 'admin';
  const isMedecin   = USER.role === 'medecin' || USER.role === 'admin';

  const L = {
    profile:    {fr:'👤 Mon profil',         en:'👤 My profile',       ar:'👤 ملفي الشخصي'},
    nom:        {fr:'Nom',                   en:'Last name',           ar:'اللقب'},
    prenom:     {fr:'Prénom',               en:'First name',          ar:'الاسم'},
    username:   {fr:'Identifiant',          en:'Username',            ar:'اسم المستخدم'},
    email:      {fr:'Email',                en:'Email',               ar:'البريد الإلكتروني'},
    code:       {fr:'Code médecin',         en:'Doctor code',         ar:'كود الطبيب'},
    readOnly:   {fr:'Contactez l\'administrateur pour modifier vos informations.', en:'Contact the administrator to update your information.', ar:'تواصل مع المشرف لتعديل معلوماتك.'},
    password:   {fr:'🔑 Mot de passe',      en:'🔑 Password',         ar:'🔑 كلمة المرور'},
    pwDesc:     {fr:'Entrez l\'adresse email associée à votre compte. Si elle correspond, vous recevrez un lien de réinitialisation valable 2 heures.', en:'Enter the email address linked to your account. If it matches, you will receive a reset link valid for 2 hours.', ar:'أدخل البريد الإلكتروني المرتبط بحسابك. إذا تطابق، ستتلقى رابط إعادة تعيين صالحاً لمدة ساعتين.'},
    pwBtn:      {fr:'Envoyer le lien',      en:'Send reset link',     ar:'إرسال الرابط'},
    theme:      {fr:'🎨 Thème',             en:'🎨 Theme',            ar:'🎨 المظهر'},
    lang:       {fr:'🌐 Langue',            en:'🌐 Language',         ar:'🌐 اللغة'},
    export:     {fr:'📤 Export des données',en:'📤 Data export',      ar:'📤 تصدير البيانات'},
    exportBtn:  {fr:'⬇ Exporter tous les patients (CSV)', en:'⬇ Export all patients (CSV)', ar:'⬇ تصدير جميع المرضى (CSV)'},
    exportHint: {fr:'Pour un patient individuel, ouvrez son dossier et utilisez ⬇.', en:'For a single patient, open their file and use ⬇.', ar:'لمريض واحد، افتح ملفه واستخدم ⬇.'},
    apply:      {fr:'✓ Appliquer les modifications', en:'✓ Apply changes', ar:'✓ تطبيق التغييرات'},
    themes: {
      dark:     {fr:'Sombre',    en:'Dark',     ar:'داكن'},
      light:    {fr:'Clair',     en:'Light',    ar:'فاتح'},
      clinical: {fr:'Clinique',  en:'Clinical', ar:'سريري'},
      contrast: {fr:'Contraste', en:'Contrast', ar:'تباين'},
    },
  };
  const lx = l => (L[l] || {})[lang] || (L[l] || {})[lang] || (L[l] || {}).fr || l;

  c.innerHTML = `
  <div style="max-width:680px;display:flex;flex-direction:column;gap:20px">

    <!-- PROFILE -->
    <div class="card" style="padding:24px">
      <div class="section-title" style="margin-bottom:16px">${lx('profile')}
        ${profile.medecin_code ? `<span style="margin-left:10px;font-size:12px;background:var(--teal-dim);color:var(--teal2);padding:2px 10px;border-radius:8px;font-weight:700">${profile.medecin_code}</span>` : ''}
      </div>
      ${canEdit ? `
      <div style="display:flex;gap:14px">
        <div class="form-group" style="flex:1">
          <label class="form-label">${lx('nom')} *</label>
          <input class="form-input" id="sNom" value="${profile.nom || ''}" placeholder="${lx('nom')}">
        </div>
        <div class="form-group" style="flex:1">
          <label class="form-label">${lx('prenom')} *</label>
          <input class="form-input" id="sPrenom" value="${profile.prenom || ''}" placeholder="${lx('prenom')}">
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">${lx('username')} *</label>
        <input class="form-input" id="sUsername" value="${profile.username || ''}" placeholder="${lx('username')}" autocomplete="off">
      </div>
      <div class="form-group">
        <label class="form-label">${lx('email')}</label>
        <input class="form-input" type="email" id="sEmail" value="${profile.email || ''}" placeholder="${lx('email')}">
      </div>
      <div id="settingsProfileMsg" style="margin-bottom:4px"></div>
      ` : `
      <div style="display:flex;gap:14px">
        <div class="form-group" style="flex:1">
          <label class="form-label">${lx('nom')}</label>
          <div class="form-input" style="opacity:.6">${profile.nom || '—'}</div>
        </div>
        <div class="form-group" style="flex:1">
          <label class="form-label">${lx('prenom')}</label>
          <div class="form-input" style="opacity:.6">${profile.prenom || '—'}</div>
        </div>
      </div>
      <div class="form-group">
        <label class="form-label">${lx('username')}</label>
        <div class="form-input" style="opacity:.6;font-family:monospace">${profile.username || '—'}</div>
      </div>
      <div style="font-size:12px;color:var(--text3)">${lx('readOnly')}</div>
      `}
    </div>

    <!-- PASSWORD -->
    <div class="card" style="padding:24px">
      <div class="section-title" style="margin-bottom:12px">${lx('password')}</div>
      <p style="font-size:13px;color:var(--text2);margin-bottom:14px;line-height:1.6">${lx('pwDesc')}</p>
      <div class="form-group">
        <label class="form-label">${lx('email')}</label>
        <input class="form-input" type="email" id="settingsPwEmail" placeholder="votre@email.com" value="${profile.email || ''}">
      </div>
      <div id="settingsPwMsg" style="margin-bottom:10px"></div>
      <button class="btn btn-ghost btn-sm" onclick="settingsSendPwReset()">${lx('pwBtn')}</button>
    </div>

    <!-- THEME -->
    <div class="card" style="padding:24px">
      <div class="section-title" style="margin-bottom:16px">${lx('theme')}</div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px">
        ${[
          {id:'dark',    preview:'#06111a', text:'#dff0f5', accent:'#0ea5a0'},
          {id:'light',   preview:'#f0f4f8', text:'#0a2233', accent:'#0ea5a0'},
          {id:'clinical',preview:'#f5f7fa', text:'#1a2940', accent:'#0077cc'},
          {id:'contrast',preview:'#000000', text:'#ffffff', accent:'#00ffcc'},
        ].map(th=>`
          <div onclick="applyTheme('${th.id}');document.querySelectorAll('.theme-opt').forEach(e=>{e.style.borderColor='var(--border)';e.classList.remove('selected')});this.style.borderColor='var(--teal)';this.classList.add('selected')"
               class="theme-opt${storedTheme===th.id?' selected':''}"
               style="cursor:pointer;border-radius:10px;overflow:hidden;border:2px solid ${storedTheme===th.id?'var(--teal)':'var(--border)'};transition:border-color .15s">
            <div style="height:48px;background:${th.preview};display:flex;align-items:center;justify-content:center;gap:6px">
              <div style="width:20px;height:20px;border-radius:50%;background:${th.accent}"></div>
              <div style="width:40px;height:8px;border-radius:4px;background:${th.text};opacity:.4"></div>
            </div>
            <div style="padding:6px 10px;font-size:12px;font-weight:600;background:var(--card);color:var(--text)">${(L.themes[th.id]||{})[lang]||th.id}</div>
          </div>
        `).join('')}
      </div>
    </div>

    <!-- LANGUAGE -->
    <div class="card" style="padding:24px">
      <div class="section-title" style="margin-bottom:16px">${lx('lang')}</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        ${[
          {code:'fr', label:'Français', flag:'🇫🇷'},
          {code:'en', label:'English',  flag:'🇬🇧'},
          {code:'ar', label:'العربية',  flag:'🇲🇦'},
        ].map(l=>`
          <button onclick="applyLang('${l.code}')"
                  class="btn lang-btn ${lang===l.code?'btn-primary':'btn-ghost'}" style="font-size:15px;gap:6px">
            ${l.flag} ${l.label}
          </button>
        `).join('')}
      </div>
    </div>

    <!-- 2FA / TOTP -->
    <div class="card" style="padding:24px">
      <div class="section-title" style="margin-bottom:12px">🔐 Authentification à deux facteurs (2FA)</div>
      ${profile.totp_enabled ? `
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
        <span style="background:rgba(14,165,160,.15);color:var(--teal2);padding:3px 12px;border-radius:99px;font-size:12px;font-weight:700">ACTIVÉE</span>
        <span style="font-size:13px;color:var(--text2)">Votre compte est protégé par une application d'authentification.</span>
      </div>
      <div id="totpSettingsMsg" style="margin-bottom:10px"></div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start">
        <div style="flex:1;min-width:200px">
          <label class="form-label">Mot de passe actuel</label>
          <input class="form-input" type="password" id="totpDisablePw" placeholder="Mot de passe" autocomplete="current-password">
        </div>
        <div style="flex:1;min-width:140px">
          <label class="form-label">Code 2FA actuel</label>
          <input class="form-input" id="totpDisableToken" placeholder="000000" maxlength="6" inputmode="numeric">
        </div>
      </div>
      <button class="btn btn-ghost btn-sm" style="color:var(--red);border-color:var(--red);margin-top:8px" onclick="settingsDisableTotp()">
        Désactiver la 2FA
      </button>
      ` : `
      <p style="font-size:13px;color:var(--text2);margin-bottom:16px;line-height:1.6">
        Protégez votre compte avec une application d'authentification (Google Authenticator, Authy, etc.).<br>
        Une fois activée, un code à 6 chiffres vous sera demandé à chaque connexion.
      </p>
      <div id="totpSettingsMsg" style="margin-bottom:10px"></div>
      <div id="totpQrArea" style="display:none;margin-bottom:16px">
        <div style="margin-bottom:12px">
          <img id="totpQrImg" src="" alt="QR Code 2FA" style="border-radius:10px;border:3px solid var(--teal);max-width:200px;display:block">
        </div>
        <p style="font-size:12px;color:var(--text3);margin-bottom:10px">Scannez ce QR code avec votre application, puis entrez le code généré pour confirmer l'activation.</p>
        <div style="display:flex;gap:10px;align-items:flex-end">
          <div class="form-group" style="flex:1;margin:0">
            <label class="form-label">Code de vérification</label>
            <input class="form-input" id="totpVerifyToken" placeholder="000000" maxlength="6" inputmode="numeric" style="letter-spacing:6px;font-size:18px;font-weight:700">
          </div>
          <button class="btn btn-primary" onclick="settingsVerifyTotp()">Activer</button>
        </div>
      </div>
      <button class="btn btn-ghost btn-sm" id="totpSetupBtn" onclick="settingsSetupTotp()">
        Configurer la 2FA →
      </button>
      `}
    </div>

    <!-- CHANGE PASSWORD -->
    <div class="card" style="padding:24px">
      <div class="section-title" style="margin-bottom:12px">🔑 Changer le mot de passe</div>
      <p style="font-size:12px;color:var(--text3);margin-bottom:14px">
        Minimum 12 caractères, avec majuscule, minuscule, chiffre et caractère spécial.
      </p>
      <div class="form-group">
        <label class="form-label">Mot de passe actuel</label>
        <input class="form-input" type="password" id="changePwCurrent" placeholder="••••••••••••" autocomplete="current-password">
      </div>
      <div class="form-group">
        <label class="form-label">Nouveau mot de passe</label>
        <input class="form-input" type="password" id="changePwNew" placeholder="••••••••••••" autocomplete="new-password">
      </div>
      <div class="form-group">
        <label class="form-label">Confirmer le nouveau mot de passe</label>
        <input class="form-input" type="password" id="changePwNew2" placeholder="••••••••••••" autocomplete="new-password">
      </div>
      <div id="changePwMsg" style="margin-bottom:10px"></div>
      <button class="btn btn-ghost btn-sm" onclick="settingsChangePassword()">Changer le mot de passe</button>
    </div>

    <!-- EXPORT (médecin/admin only) -->
    ${isMedecin ? `
    <div class="card" style="padding:24px">
      <div class="section-title" style="margin-bottom:16px">${lx('export')}</div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <button class="btn btn-ghost" onclick="exportPatientsCSV()">${lx('exportBtn')}</button>
      </div>
      <div style="font-size:12px;color:var(--text3);margin-top:10px">${lx('exportHint')}</div>
    </div>` : ''}

    <!-- APPLY BUTTON -->
    ${canEdit ? `
    <div style="display:flex;gap:12px;align-items:center;padding-bottom:32px">
      <button class="btn btn-primary" style="min-width:220px;justify-content:center" onclick="settingsApply()">${lx('apply')}</button>
      <div id="settingsApplyMsg" style="font-size:13px"></div>
    </div>` : ''}

  </div>`;
}

async function settingsApply() {
  const nom      = document.getElementById('sNom')?.value.trim();
  const prenom   = document.getElementById('sPrenom')?.value.trim();
  const username = document.getElementById('sUsername')?.value.trim();
  const email    = document.getElementById('sEmail')?.value.trim();
  const msgEl    = document.getElementById('settingsApplyMsg');
  const profileMsg = document.getElementById('settingsProfileMsg');

  if (!nom || !prenom || !username) {
    if (profileMsg) profileMsg.innerHTML = '<div class="auth-msg auth-msg-error">Nom, prénom et identifiant sont requis.</div>';
    return;
  }
  const res = await api('/api/settings/profile', 'PUT', {nom, prenom, email, username});
  if (res.ok) {
    // Update in-memory USER object
    USER.nom    = nom;
    USER.prenom = prenom;
    document.getElementById('topbarUser').textContent = prenom + ' ' + nom;
    if (profileMsg) profileMsg.innerHTML = '';
    msgEl.innerHTML = `<span style="color:var(--green)">✓ ${res.warning ? res.warning : 'Modifications enregistrées'}</span>`;
    if (res.warning) msgEl.innerHTML = `<span style="color:var(--amber)">⚠ ${res.warning}</span>`;
  } else {
    if (profileMsg) profileMsg.innerHTML = `<div class="auth-msg auth-msg-error">${res.error || 'Erreur'}</div>`;
    msgEl.innerHTML = '';
  }
}

async function settingsSendPwReset() {
  const email = document.getElementById('settingsPwEmail').value.trim();
  const msgEl = document.getElementById('settingsPwMsg');
  if (!email || !email.includes('@')) {
    msgEl.innerHTML = '<div class="auth-msg auth-msg-error">Entrez une adresse email valide.</div>'; return;
  }
  const res = await api('/api/settings/request-pw-reset', 'POST', {email});
  if (res.ok) {
    msgEl.innerHTML = `<div class="auth-msg auth-msg-success">${res.message}</div>`;
  } else {
    msgEl.innerHTML = `<div class="auth-msg auth-msg-error">${res.error || 'Erreur'}</div>`;
  }
}

async function settingsSetupTotp() {
  const msgEl  = document.getElementById('totpSettingsMsg');
  const btn    = document.getElementById('totpSetupBtn');
  if (btn) btn.disabled = true;
  msgEl.innerHTML = '<span style="color:var(--text3)">Génération du QR code...</span>';
  const res = await api('/api/totp/setup', 'POST', {});
  if (res.ok) {
    msgEl.innerHTML = '';
    const qrArea = document.getElementById('totpQrArea');
    const qrImg  = document.getElementById('totpQrImg');
    if (qrArea && qrImg) { qrImg.src = res.qr; qrArea.style.display = ''; }
    if (btn) btn.style.display = 'none';
  } else {
    msgEl.innerHTML = `<div class="auth-msg auth-msg-error">${res.error || 'Erreur lors de la configuration'}</div>`;
    if (btn) btn.disabled = false;
  }
}

async function settingsVerifyTotp() {
  const token = document.getElementById('totpVerifyToken')?.value.trim();
  const msgEl = document.getElementById('totpSettingsMsg');
  if (!token || token.length < 6) {
    msgEl.innerHTML = '<div class="auth-msg auth-msg-error">Entrez le code à 6 chiffres.</div>'; return;
  }
  const res = await api('/api/totp/verify', 'POST', {token});
  if (res.ok) {
    msgEl.innerHTML = `<div class="auth-msg auth-msg-success">${res.message}</div>`;
    setTimeout(() => renderSettings(document.getElementById('viewContent')), 1500);
  } else {
    msgEl.innerHTML = `<div class="auth-msg auth-msg-error">${res.error || 'Code invalide'}</div>`;
  }
}

async function settingsDisableTotp() {
  const password = document.getElementById('totpDisablePw')?.value;
  const token    = document.getElementById('totpDisableToken')?.value.trim();
  const msgEl    = document.getElementById('totpSettingsMsg');
  if (!password || !token) {
    msgEl.innerHTML = '<div class="auth-msg auth-msg-error">Mot de passe et code 2FA requis.</div>'; return;
  }
  const res = await api('/api/totp/disable', 'POST', {password, token});
  if (res.ok) {
    msgEl.innerHTML = `<div class="auth-msg auth-msg-success">${res.message}</div>`;
    setTimeout(() => renderSettings(document.getElementById('viewContent')), 1500);
  } else {
    msgEl.innerHTML = `<div class="auth-msg auth-msg-error">${res.error || 'Erreur'}</div>`;
  }
}

async function settingsChangePassword() {
  const current = document.getElementById('changePwCurrent')?.value;
  const newPw   = document.getElementById('changePwNew')?.value;
  const newPw2  = document.getElementById('changePwNew2')?.value;
  const msgEl   = document.getElementById('changePwMsg');
  if (!current || !newPw || !newPw2) {
    msgEl.innerHTML = '<div class="auth-msg auth-msg-error">Tous les champs sont requis.</div>'; return;
  }
  if (newPw !== newPw2) {
    msgEl.innerHTML = '<div class="auth-msg auth-msg-error">Les mots de passe ne correspondent pas.</div>'; return;
  }
  const res = await api('/api/change-password', 'POST', {current_password: current, new_password: newPw});
  if (res.ok) {
    msgEl.innerHTML = '<div class="auth-msg auth-msg-success">Mot de passe modifié avec succès.</div>';
    document.getElementById('changePwCurrent').value = '';
    document.getElementById('changePwNew').value = '';
    document.getElementById('changePwNew2').value = '';
  } else {
    msgEl.innerHTML = `<div class="auth-msg auth-msg-error">${res.error || 'Erreur'}</div>`;
  }
}

