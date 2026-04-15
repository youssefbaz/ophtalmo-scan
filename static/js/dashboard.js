// ─── DASHBOARD MÉDECIN ────────────────────────────────────────────────────────
async function renderDashboardMedecin(c) {
  const [patients, rdvs, notifs] = await Promise.all([
    api('/api/patients'), api('/api/rdv'), api('/api/notifications')
  ]);
  const urgents = rdvs.filter(r => r.urgent && r.statut === 'en_attente');
  const today    = new Date().toISOString().slice(0,10);
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0,10);
  const todayRdvs    = rdvs.filter(r => r.date === today).sort((a,b) => a.heure.localeCompare(b.heure));
  const tomorrowRdvs = rdvs.filter(r => r.date === tomorrow && r.statut !== 'annulé').sort((a,b) => a.heure.localeCompare(b.heure));
  const upcoming = [...todayRdvs, ...tomorrowRdvs];
  const now = new Date().toTimeString().slice(0,5);

  c.innerHTML = `
    <div class="grid-4" style="margin-bottom:20px">
      <div class="stat-card teal"><div class="stat-label">Patients</div><div class="stat-value">${patients.length}</div><div class="stat-sub">Total enregistrés</div></div>
      <div class="stat-card amber"><div class="stat-label">Aujourd'hui</div><div class="stat-value">${todayRdvs.length}</div><div class="stat-sub">RDV du jour</div></div>
      <div class="stat-card red"><div class="stat-label">RDV Urgents</div><div class="stat-value">${urgents.length}</div><div class="stat-sub">En attente validation</div></div>
      <div class="stat-card blue"><div class="stat-label">Questions</div><div class="stat-value">${notifs.filter(n=>n.type==='question').length}</div><div class="stat-sub">En attente réponse</div></div>
    </div>

    ${urgents.length ? `
    <div style="margin-bottom:20px">
      <div class="section-title">🚨 RDV Urgents — Validation requise</div>
      ${urgents.map(r => `
        <div class="rdv-card urgent">
          <div class="rdv-date-block urgent"><div class="rdv-day urgent">${new Date(r.date).getDate()}</div><div class="rdv-month">${new Date(r.date).toLocaleString('fr-FR',{month:'short'})}</div></div>
          <div class="rdv-info">
            <div class="rdv-type">🚨 ${r.patient_prenom} ${r.patient_nom}</div>
            <div class="rdv-meta">${_normRdvType(r.type)} · ${r.heure} · <span style="color:var(--color-red)">Urgent</span></div>
          </div>
          <div style="display:flex;gap:8px">
            <button class="btn btn-amber btn-sm" onclick="modifierRdv('${r.id}','${r.date}','${r.heure}')">✏ Modifier</button>
            <button class="btn btn-primary btn-sm" onclick="validerRdv('${r.id}','confirmé')">✓ Confirmer</button>
            <button class="btn btn-ghost btn-sm" onclick="validerRdv('${r.id}','annulé')">✗ Refuser</button>
            <button class="btn btn-red btn-sm" onclick="deleteRdv('${r.id}')">🗑</button>
          </div>
        </div>
      `).join('')}
    </div>` : ''}

    <div style="margin-bottom:24px">
      <div class="section-title">📅 Planning du jour — ${new Date().toLocaleDateString('fr-FR',{weekday:'long',day:'numeric',month:'long'})}</div>
      ${todayRdvs.length ? `
        <div style="display:flex;flex-direction:column;gap:8px">
          ${todayRdvs.map(r => {
            const isPast = r.heure < now;
            const isCurrent = r.heure <= now && now <= r.heure.replace(/(\d+):(\d+)/, (_, h, m) => `${String(+h + 1).padStart(2,'0')}:${m}`);
            return `
            <div class="rdv-card" style="cursor:pointer;${isCurrent ? 'border-color:var(--teal);box-shadow:0 0 0 2px rgba(14,165,160,0.2)' : isPast ? 'opacity:0.5' : ''}" onclick="loadPatient('${r.patient_id}')">
              <div class="rdv-date-block ${r.urgent?'urgent':''}">
                <div class="rdv-day ${r.urgent?'urgent':''}" style="font-size:18px">${r.heure}</div>
              </div>
              <div class="rdv-info">
                <div class="rdv-type">${r.urgent?'🚨 ':''} ${r.patient_prenom} ${r.patient_nom}</div>
                <div class="rdv-meta">${_normRdvType(r.type)} · ${r.medecin}</div>
              </div>
              <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">
                <span class="badge ${r.statut==='confirmé'?'badge-teal':r.statut==='en_attente'?'badge-amber':'badge-red'}">${r.statut}</span>
                ${isCurrent ? '<span style="font-size:10px;color:var(--teal2)">● En cours</span>' : ''}
                ${isPast && !isCurrent ? '<span style="font-size:10px;color:var(--text3)">Passé</span>' : ''}
              </div>
            </div>`;
          }).join('')}
        </div>` : 
        '<div style="color:var(--text3);font-size:13px;padding:20px;text-align:center;background:var(--card);border-radius:var(--radius);border:1px solid var(--border)">Aucun rendez-vous aujourd\'hui</div>'
      }
    </div>

    <!-- Post-op gaps alert -->
    <div id="postopGapsPanel" style="margin-bottom:24px;display:none">
      <div class="section-title">⚠️ Suivis post-opératoires en retard</div>
      <div id="postopGapsList"></div>
    </div>

    <!-- Notes rapides -->
    <div style="margin-bottom:24px">
      <div class="section-title">📝 Notes rapides</div>
      <div style="display:flex;gap:8px;margin-bottom:10px">
        <input class="input" id="noteInput" placeholder="Ajouter une note…" style="flex:1;padding:8px 12px"
               onkeydown="if(event.key==='Enter')addNote()">
        <button class="btn btn-primary btn-sm" onclick="addNote()">+</button>
      </div>
      <div id="notesList" style="display:flex;flex-direction:column;gap:6px">${renderNotesList()}</div>
    </div>

    <div class="grid-2">
      <div>
        <div class="section-title" style="display:flex;align-items:center;gap:8px">
          Prochains rendez-vous
          ${upcoming.length ? `<span style="background:var(--teal);color:#fff;font-size:11px;font-weight:700;padding:2px 8px;border-radius:12px">${upcoming.length}</span>` : ''}
        </div>
        ${todayRdvs.length ? `<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--teal2);margin-bottom:6px">Aujourd'hui · <span style="background:var(--teal-dim);color:var(--teal2);padding:1px 7px;border-radius:8px">${todayRdvs.length} RDV</span></div>` : ''}
        ${todayRdvs.map(r => `
          <div class="rdv-card" style="cursor:pointer" onclick="loadPatient('${r.patient_id}')">
            <div class="rdv-date-block"><div class="rdv-day" style="font-size:16px">${r.heure}</div></div>
            <div class="rdv-info">
              <div class="rdv-type">${r.patient_prenom} ${r.patient_nom}</div>
              <div class="rdv-meta">${_normRdvType(r.type)}</div>
            </div>
            <span class="badge ${r.statut==='confirmé'?'badge-teal':r.statut==='en_attente'?'badge-amber':'badge-red'}">${r.statut}</span>
          </div>
        `).join('')}
        ${tomorrowRdvs.length ? `<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:var(--text2);margin-top:10px;margin-bottom:6px">Demain · <span style="background:var(--bg2);color:var(--text2);padding:1px 7px;border-radius:8px">${tomorrowRdvs.length} RDV</span></div>` : ''}
        ${tomorrowRdvs.map(r => `
          <div class="rdv-card" style="cursor:pointer" onclick="loadPatient('${r.patient_id}')">
            <div class="rdv-date-block"><div class="rdv-day" style="font-size:16px">${r.heure}</div></div>
            <div class="rdv-info">
              <div class="rdv-type">${r.patient_prenom} ${r.patient_nom}</div>
              <div class="rdv-meta">${_normRdvType(r.type)}</div>
            </div>
            <span class="badge ${r.statut==='confirmé'?'badge-teal':r.statut==='en_attente'?'badge-amber':'badge-red'}">${r.statut}</span>
          </div>
        `).join('')}
        ${!upcoming.length ? '<div style="color:var(--text3);font-size:13px;padding:20px;text-align:center;background:var(--card);border-radius:var(--radius);border:1px solid var(--border)">Aucun RDV aujourd\'hui ni demain</div>' : ''}
      </div>
      <div>
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
          <div class="section-title" style="margin-bottom:0">Activité récente</div>
          ${notifs.length ? `<button class="btn btn-ghost btn-sm" style="font-size:11px;opacity:.7" onclick="clearActivite()">🗑 Effacer tout</button>` : ''}
        </div>
        ${notifs.slice(0,6).map(n => `
          <div class="notif-item ${n.lu?'':'unread'}" style="border-radius:10px;margin-bottom:6px;border:1px solid var(--border);cursor:pointer" onclick="handleNotifClick('${n.id}','${n.type}','${n.patient_id||''}')">
            <div class="notif-msg">${n.message}</div>
            <div class="notif-time">${n.date}</div>
          </div>
        `).join('') || '<div style="color:var(--text3);font-size:13px;padding:20px;text-align:center">Aucune activité</div>'}
      </div>
    </div>`;
  // Load post-op gaps asynchronously after render
  _loadPostopGaps();
}

async function _loadPostopGaps() {
  const gaps = await api('/api/postop-gaps');
  const panel = document.getElementById('postopGapsPanel');
  const list  = document.getElementById('postopGapsList');
  if (!panel || !list || !Array.isArray(gaps) || !gaps.length) {
    if (panel) panel.style.display = 'none';
    return;
  }
  panel.style.display = 'block';
  list.innerHTML = gaps.slice(0, 8).map(g => {
    const days = Math.round((new Date() - new Date(g.date_prevue)) / 86400000);
    return `
    <div style="display:flex;align-items:center;gap:12px;padding:10px 14px;background:var(--red-dim);border:1px solid rgba(239,68,68,0.3);border-radius:10px;margin-bottom:6px;cursor:pointer" onclick="loadPatient('${g.patient_id}')">
      <span style="font-size:20px">⚠️</span>
      <div style="flex:1">
        <div style="font-size:13px;font-weight:600;color:var(--text)">${g.prenom} ${g.nom}</div>
        <div style="font-size:11px;color:var(--text2)">Étape ${g.etape} — prévu le ${new Date(g.date_prevue).toLocaleDateString('fr-FR')} (${days}j de retard)</div>
      </div>
      <span class="badge badge-red">${days}j</span>
    </div>`;
  }).join('');
}

// ─── DASHBOARD PATIENT ────────────────────────────────────────────────────────
async function renderDashboardPatient(c) {
  const pid = USER.patient_id;
  const [patient, rdvs] = await Promise.all([api(`/api/patients/${pid}`), api('/api/rdv')]);
  const today = new Date().toISOString().slice(0,10);
  const prochains = rdvs.filter(r => r.date >= today).sort((a,b) => a.date.localeCompare(b.date) || a.heure.localeCompare(b.heure));
  const nextRdv = prochains[0] || null;
  const age = new Date().getFullYear() - new Date(patient.ddn).getFullYear();

  // Days until next RDV
  const daysUntil = nextRdv ? Math.round((new Date(nextRdv.date) - new Date(today)) / 86400000) : null;

  c.innerHTML = `
    <div class="welcome-banner">
      <div class="welcome-avatar">👤</div>
      <div>
        <div class="welcome-name">Bonjour, ${patient.prenom} ${patient.nom}</div>
        <div class="welcome-sub">${age} ans · ${patient.antecedents.join(' · ')}</div>
      </div>
      <div style="margin-left:auto;display:flex;gap:10px">
        <button class="btn btn-red btn-sm" onclick="openRdvUrgent()">🚨 RDV Urgent</button>
        <button class="btn btn-primary btn-sm" onclick="showView('mes-rdv')">📅 Prendre RDV</button>
      </div>
    </div>

    ${nextRdv ? `
    <div style="margin-bottom:20px;background:linear-gradient(135deg,#102840,var(--bg2));border:1px solid var(--teal);border-radius:18px;padding:20px 24px;display:flex;align-items:center;gap:20px">
      <div style="background:var(--teal);border-radius:14px;padding:14px 18px;text-align:center;min-width:70px">
        <div style="font-family:'Playfair Display',serif;font-size:28px;color:white;line-height:1">${new Date(nextRdv.date).getDate()}</div>
        <div style="font-size:11px;text-transform:uppercase;color:rgba(255,255,255,0.8);letter-spacing:1px">${new Date(nextRdv.date).toLocaleString('fr-FR',{month:'short'})}</div>
      </div>
      <div style="flex:1">
        <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:var(--teal2);margin-bottom:4px">Prochain rendez-vous</div>
        <div style="font-family:'Playfair Display',serif;font-size:18px;color:var(--text)">${nextRdv.type}</div>
        <div style="font-size:13px;color:var(--text2);margin-top:4px">⏰ ${nextRdv.heure} · ${nextRdv.medecin}</div>
      </div>
      <div style="text-align:center">
        <div style="font-family:'Playfair Display',serif;font-size:32px;color:var(--teal2)">${daysUntil === 0 ? "Auj." : daysUntil + 'j'}</div>
        <div style="font-size:11px;color:var(--text3)">${daysUntil === 0 ? "Aujourd'hui !" : 'restants'}</div>
        <span class="badge ${nextRdv.statut==='confirmé'?'badge-teal':'badge-amber'}" style="margin-top:6px">${nextRdv.statut}</span>
      </div>
    </div>` : `
    <div style="margin-bottom:20px;background:var(--card);border:1px dashed var(--border);border-radius:18px;padding:24px;text-align:center">
      <div style="font-size:32px;margin-bottom:8px">📅</div>
      <div style="color:var(--text2);font-size:14px;margin-bottom:12px">Aucun rendez-vous programmé</div>
      <button class="btn btn-primary btn-sm" onclick="showView('mes-rdv')">Prendre un rendez-vous</button>
    </div>`}

    <div class="grid-3" style="margin-bottom:20px">
      <div class="stat-card teal"><div class="stat-label">RDV à venir</div><div class="stat-value">${prochains.length}</div></div>
      <div class="stat-card blue"><div class="stat-label">Consultations</div><div class="stat-value">${patient.historique.length}</div></div>
      <div class="stat-card amber"><div class="stat-label">Documents</div><div class="stat-value">${(patient.documents||[]).length}</div></div>
    </div>

    <div class="grid-2">
      <div>
        <div class="section-title">Tous mes rendez-vous</div>
        ${prochains.slice(0,4).map((r,i) => `
          <div class="rdv-card" style="${i===0?'border-color:var(--teal)':''}">
            <div class="rdv-date-block"><div class="rdv-day">${new Date(r.date).getDate()}</div><div class="rdv-month">${new Date(r.date).toLocaleString('fr-FR',{month:'short'})}</div></div>
            <div class="rdv-info"><div class="rdv-type">${_normRdvType(r.type)}</div><div class="rdv-meta">⏰ ${r.heure} · ${r.medecin}</div></div>
            <span class="badge ${r.statut==='confirmé'?'badge-teal':'badge-amber'}">${r.statut}</span>
          </div>
        `).join('') || '<div style="color:var(--text3);font-size:13px;padding:16px;text-align:center">Aucun RDV programmé</div>'}
        <button class="btn btn-ghost btn-sm" style="margin-top:8px" onclick="showView('mes-rdv')">Voir tous →</button>
      </div>
      <div>
        <div class="section-title">Dernières consultations</div>
        ${patient.historique.slice(0,3).map(h=>`
          <div class="tl-item" style="margin-bottom:10px">
            <div class="tl-date">${fmtDate(h.date)}</div>
            <div class="tl-title">${h.motif}</div>
            <div class="tl-field-value" style="font-size:12px;color:var(--text2)">${h.traitement || ''}</div>
          </div>
        `).join('')}
      </div>
    </div>`;
}

