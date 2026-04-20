// ─── AI ASSISTANT ─────────────────────────────────────────────────────────────
function renderAiAssistant(c) {
  c.innerHTML = `
    <div class="ai-panel card" style="padding:0">
      <div class="ai-header">
        <div class="ai-dot"></div>
        <div>
          <div style="font-family:'Playfair Display',serif;font-size:16px">Assistant IA Ophtalmologie</div>
          <div style="font-size:12px;color:var(--text2)">Spécialisé en pathologies et imagerie oculaires</div>
        </div>
        ${currentPatientId?`<span class="badge badge-teal" style="margin-left:auto">Contexte: Patient chargé</span>`:''}
      </div>
      <div class="ai-messages" id="aiMessages">
        <div class="msg msg-ai">
          <div class="msg-sender">🤖 IA OPHTHALMO</div>
          <div class="msg-bubble">Bonjour Docteur. Je suis votre assistant spécialisé ophtalmologie.\n\nJe peux vous aider à:\n• Répondre aux questions cliniques ophtalmologiques\n• Proposer des diagnostics différentiels\n• Donner des recommandations thérapeutiques\n\nPosez votre question ou chargez le contexte d'un patient.</div>
        </div>
      </div>
      <div class="quick-qs">
        <button class="quick-q" onclick="sendQuickQ('Critères retraitement anti-VEGF DMLA exsudative ?')">DMLA anti-VEGF</button>
        <button class="quick-q" onclick="sendQuickQ('Interpréter rapport C/D 0.7 glaucome ?')">Rapport C/D</button>
        <button class="quick-q" onclick="sendQuickQ('Kératocône grade II : cross-linking indiqué ?')">Kératocône</button>
        <button class="quick-q" onclick="sendQuickQ('Rétinopathie diabétique stades et traitement ?')">Rétinopathie DT</button>
        <button class="quick-q" onclick="sendQuickQ('Expliquer cataracte au patient simplement')">Expliquer cataracte</button>
      </div>
      <div class="ai-input-area">
        <textarea id="aiInput" placeholder="Question ophtalmologique..." rows="1"
          onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendAiMsg()}"
          oninput="this.style.height='auto';this.style.height=this.scrollHeight+'px'"></textarea>
        <button class="send-btn" id="sendAiBtn" onclick="sendAiMsg()">
          <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"/></svg>
        </button>
      </div>
    </div>`;
}

// ─── AI FUNCTIONS ─────────────────────────────────────────────────────────────
function sendQuickQ(q) { document.getElementById('aiInput').value=q; sendAiMsg(); }

async function sendAiMsg() {
  const inp = document.getElementById('aiInput');
  const q = inp.value.trim(); if(!q) return;
  inp.value=''; inp.style.height='auto';
  addMsg('user',q);
  const btn = document.getElementById('sendAiBtn'); btn.disabled=true;
  const lid='l'+Date.now();
  document.getElementById('aiMessages').innerHTML+=`<div class="msg msg-ai" id="${lid}"><div class="msg-sender">🤖</div><div class="msg-bubble"><span class="loading-dots"><span></span><span></span><span></span></span></div></div>`;
  scrollAi();
  const res = await api('/api/ai/question','POST',{question:q,context:aiContext,patient_id:aiContextPid});
  document.getElementById(lid)?.remove();
  addMsg('ai', res.answer||res.error||'Erreur');
  btn.disabled=false;
}

function addMsg(role,text) {
  const d=document.getElementById('aiMessages');
  d.innerHTML+=`<div class="msg msg-${role==='user'?'user':'ai'}"><div class="msg-sender">${role==='user'?'👨‍⚕️ MÉDECIN':'🤖 IA OPHTHALMO'}</div><div class="msg-bubble">${escH(text)}</div></div>`;
  scrollAi();
}
function scrollAi(){const d=document.getElementById('aiMessages');if(d)d.scrollTop=d.scrollHeight;}

async function startAiContext(pid) {
  const p = await api(`/api/patients/${pid}`);
  aiContext = `Patient: ${p.prenom} ${p.nom}, ${new Date().getFullYear()-new Date(p.ddn).getFullYear()} ans. Antécédents: ${p.antecedents.join(', ')}. Dernier traitement: ${p.historique[0]?.traitement||'NC'}`;
  aiContextPid = pid;
  showView('ai-assistant');
  setTimeout(()=>addMsg('ai',`Contexte chargé pour ${p.prenom} ${p.nom}.\nAntécédents: ${p.antecedents.join(', ')}\nDernier traitement: ${p.historique[0]?.traitement||'NC'}\n\nQuelle est votre question ?`),100);
}

async function softDeleteDoc(pid, docId, type) {
  if (!confirm(`Supprimer "${type}" de la vue active ?\nL'image reste conservée dans l'historique.`)) return;
  const res = await api(`/api/patients/${pid}/documents/${docId}`, 'DELETE');
  if (res.ok) loadPatient(pid);
  else alert(res.error || 'Erreur');
}

async function restoreDoc(pid, docId, btn) {
  btn.disabled = true;
  const res = await api(`/api/patients/${pid}/documents/${docId}/restore`, 'POST');
  if (res.ok) loadPatient(pid);
  else { alert(res.error || 'Erreur'); btn.disabled = false; }
}

async function toggleDeletedDocs(pid, btn) {
  const panel = document.getElementById(`deleted-docs-${pid}`);
  if (panel.style.display !== 'none') {
    panel.style.display = 'none';
    btn.textContent = '🗂 Voir l\'historique des documents supprimés';
    return;
  }
  btn.textContent = '⏳ Chargement…';
  const deleted = await api(`/api/patients/${pid}/documents/deleted`);
  if (!deleted.length) {
    panel.innerHTML = '<div style="color:var(--text3);font-size:13px;padding:10px 0">Aucun document supprimé.</div>';
  } else {
    panel.innerHTML = `
      <div style="font-size:11px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:1px;margin-bottom:10px">
        Historique — ${deleted.length} document(s) supprimé(s)
      </div>
      <div style="display:flex;flex-direction:column;gap:8px">
        ${deleted.map(d => `
          <div style="display:flex;align-items:center;gap:12px;padding:10px 14px;background:var(--card);border:1px solid var(--border);border-radius:10px;opacity:.75">
            <span style="font-size:22px">${d.has_image ? '🖼️' : '📎'}</span>
            <div style="flex:1;min-width:0">
              <div style="font-size:13px;font-weight:600;color:var(--text)">${d.type}</div>
              <div style="font-size:11px;color:var(--text3)">Uploadé le ${fmtDate(d.date)} · Supprimé le ${fmtDate(d.deleted_at)}</div>
              ${d.analyse_ia ? `<div style="font-size:11px;color:var(--teal2);margin-top:2px">✓ Analyse IA disponible</div>` : ''}
            </div>
            <div style="display:flex;gap:6px;flex-shrink:0">
              ${d.has_image ? `<button class="btn btn-ghost btn-sm" style="font-size:11px" onclick="openImageViewer('${d.id}','${pid}','${escJ(d.type)}','','','')">👁</button>` : ''}
              <button class="btn btn-ghost btn-sm" style="font-size:11px;color:var(--teal2)" onclick="restoreDoc('${pid}','${d.id}',this)">↩ Restaurer</button>
            </div>
          </div>`).join('')}
      </div>`;
  }
  panel.style.display = 'block';
  btn.textContent = '🗂 Masquer l\'historique';
}

async function analyzeDocAI(pid, docId, type) {
  const el = event.target;
  const origText = el.textContent;
  el.textContent = '⏳…'; el.disabled = true;
  const res = await api(`/api/patients/${pid}/documents/${docId}/analyze`, 'POST', {});
  el.textContent = origText; el.disabled = false;
  if (res.ok) {
    // Show result in the image viewer
    window._pendingTab = 'media';
    await loadPatient(pid);
    openImageViewer(docId, pid, type, '', '', '');
  } else {
    alert('Erreur analyse IA : ' + (res.error || 'inconnue'));
  }
}

async function openImageViewer(imgId, pid, type, notes, patientName, antecedents) {
  document.getElementById('modalImageTitle').textContent = type;
  document.getElementById('modalImageContent').innerHTML = `
    <div style="text-align:center;padding:30px;color:var(--text3)">⏳ Chargement…</div>`;
  openModal('modalImage');

  const doc = await api(`/api/patients/${pid}/documents/${imgId}`);
  const imgHtml = doc.image_b64
    ? `<img src="data:image/jpeg;base64,${doc.image_b64}" style="max-width:100%;max-height:62vh;border-radius:10px;object-fit:contain;display:block;margin:0 auto">`
    : `<div style="background:var(--bg2);border-radius:12px;min-height:160px;display:flex;align-items:center;justify-content:center;font-size:48px">🔬</div>`;

  const existingAnalysis = doc.analyse_ia
    ? `<div style="margin-top:12px;background:var(--teal-dim);border:1px solid rgba(14,165,160,0.2);border-radius:10px;padding:14px;font-size:13px;color:var(--text2);white-space:pre-wrap;line-height:1.6"><div style="font-size:11px;color:var(--teal2);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px">🤖 Analyse IA</div>${doc.analyse_ia}</div>`
    : '';

  document.getElementById('modalImageContent').innerHTML = `
    ${imgHtml}
    ${notes ? `<div style="margin-top:10px;font-size:12px;color:var(--text3)">${notes}</div>` : ''}
    <div id="aiAnalysisBox" style="margin-top:12px;background:var(--teal-dim);border:1px solid rgba(14,165,160,0.2);border-radius:10px;padding:14px;display:none">
      <div style="font-size:11px;color:var(--teal2);margin-bottom:6px;text-transform:uppercase;letter-spacing:.5px">🤖 Analyse IA</div>
      <div id="aiAnalysisText" style="font-size:13px;color:var(--text2);white-space:pre-wrap;line-height:1.6"></div>
    </div>
    ${existingAnalysis}
    <div style="margin-top:14px;display:flex;gap:10px;flex-wrap:wrap">
      <button class="btn btn-ghost" onclick="closeModal('modalImage')">Fermer</button>
    </div>`;
}

