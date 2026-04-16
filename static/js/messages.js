// ─── MESSAGES (Doctor → Patient) ─────────────────────────────────────────────

// ─── DOCTOR: Open compose modal ──────────────────────────────────────────────
function openMessageModal(pid, rdvId, rdvLabel) {
  const rdvSection = rdvId ? `
    <div style="margin-bottom:12px;padding:10px 14px;background:var(--teal-dim);border:1px solid var(--teal-border);border-radius:8px;font-size:12px;color:var(--teal2)">
      📅 Réponse au RDV : <strong>${escH(rdvLabel || rdvId)}</strong>
      <input type="hidden" id="msgRdvId" value="${escH(rdvId)}">
    </div>` : `<input type="hidden" id="msgRdvId" value="">`;

  showModal('✉ Envoyer un message', `
    ${rdvSection}
    <div style="margin-bottom:12px">
      <label class="lbl">Message au patient</label>
      <textarea class="input" id="msgContenu" rows="5"
        placeholder="Écrivez votre message ici…"
        style="resize:vertical"></textarea>
    </div>
    <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--bg2);border-radius:8px;font-size:12px;color:var(--text2)">
      <span>📧</span>
      <span>Le patient recevra également une notification par email.</span>
    </div>
    <div id="msgError" style="color:var(--color-red);font-size:13px;margin-top:8px;display:none"></div>
    <div style="margin-top:16px;display:flex;gap:8px">
      <button class="btn btn-primary" id="msgSendBtn" onclick="submitMessage('${pid}')">✉ Envoyer</button>
      <button class="btn btn-ghost" onclick="closeModal()">Annuler</button>
    </div>
  `);
  setTimeout(() => {
    const ta = document.getElementById('msgContenu');
    if (ta) ta.focus();
  }, 80);
}

async function submitMessage(pid) {
  const contenu = (document.getElementById('msgContenu')?.value || '').trim();
  const rdvId   = document.getElementById('msgRdvId')?.value || '';
  const errEl   = document.getElementById('msgError');
  const btn     = document.getElementById('msgSendBtn');
  if (!contenu) {
    errEl.textContent = 'Le message ne peut pas être vide.';
    errEl.style.display = 'block';
    return;
  }
  btn.disabled = true;
  btn.textContent = 'Envoi…';
  errEl.style.display = 'none';
  const res = await api(`/api/patients/${pid}/messages`, 'POST', { contenu, rdv_id: rdvId });
  if (res.ok) {
    closeModal();
    showToast('Message envoyé avec succès', 'success');
  } else {
    errEl.textContent = res.error || 'Erreur lors de l\'envoi';
    errEl.style.display = 'block';
    btn.disabled = false;
    btn.textContent = '✉ Envoyer';
  }
}

// ─── PATIENT: Render Messages View ───────────────────────────────────────────
async function renderMesMessages(c) {
  const pid = USER.patient_id;
  const messages = await api(`/api/patients/${pid}/messages`);

  // Mark all unread as read
  if (Array.isArray(messages)) {
    for (const m of messages) {
      if (!m.lu) {
        api(`/api/messages/${m.id}/lu`, 'POST').catch(() => {});
        m.lu = true;
      }
    }
  }

  const list = Array.isArray(messages) ? messages : [];

  c.innerHTML = `
    <div style="margin-bottom:18px">
      <div style="font-size:13px;color:var(--text2);margin-bottom:4px">
        Messages envoyés par votre médecin.
      </div>
    </div>

    <div id="msgListPatient">
      ${list.length === 0
        ? '<div style="color:var(--text3);text-align:center;padding:40px 20px">Aucun message pour le moment</div>'
        : list.map(m => _patientMsgCard(m)).join('')
      }
    </div>`;
}

function _patientMsgCard(m) {
  const rdvBlock = m.rdv_info
    ? `<div style="margin-top:8px;padding:8px 12px;background:var(--bg2);border-radius:6px;font-size:12px;color:var(--text2)">
         📅 Concerne votre RDV du ${fmtDate(m.rdv_info.date)} à ${m.rdv_info.heure} — ${escH(m.rdv_info.type)}
       </div>`
    : '';

  return `
    <div class="question-card answered" id="msg-card-${m.id}"
         style="position:relative">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <div style="font-size:12px;font-weight:600;color:var(--teal2)">✉ ${escH(m.medecin_nom || 'Votre médecin')}</div>
        <div style="display:flex;align-items:center;gap:6px">
          <span style="font-size:11px;color:var(--text3)">${m.date}</span>
          <button class="btn btn-ghost btn-sm"
                  style="color:var(--red);font-size:11px;padding:2px 7px"
                  title="Supprimer"
                  onclick="deletePatientMessage('${m.id}','${USER.patient_id}',this)">🗑</button>
        </div>
      </div>
      <div style="font-size:14px;line-height:1.6;color:var(--text);white-space:pre-wrap">${escH(m.contenu)}</div>
      ${rdvBlock}
    </div>`;
}

async function deletePatientMessage(mid, pid, btn) {
  if (!confirm('Supprimer ce message ?')) return;
  btn.disabled = true;
  const res = await api(`/api/messages/${mid}`, 'DELETE');
  if (res.ok) {
    const card = document.getElementById(`msg-card-${mid}`);
    if (card) card.remove();
    showToast('Message supprimé', 'info');
    // Show empty state if no cards left
    const listEl = document.getElementById('msgListPatient');
    if (listEl && !listEl.querySelector('.question-card')) {
      listEl.innerHTML = '<div style="color:var(--text3);text-align:center;padding:40px 20px">Aucun message pour le moment</div>';
    }
  } else {
    showToast(res.error || 'Erreur lors de la suppression', 'error');
    btn.disabled = false;
  }
}
