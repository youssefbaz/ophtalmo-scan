// ─── MESSAGES (threaded conversations, text + audio) ────────────────────────

const _AUDIO_MAX_SEC = 180;

// ─── Audio recording helper (MediaRecorder, webm/opus) ──────────────────────
const _recorder = {
  media: null, chunks: [], stream: null, startedAt: 0,
  blob: null, url: null, timerId: null, durationSec: 0,
};

function _detectIosContext() {
  const ua = navigator.userAgent || '';
  const isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isAndroid = /Android/i.test(ua);
  const isStandalone = window.navigator.standalone === true ||
                       window.matchMedia('(display-mode: standalone)').matches;
  const isInAppBrowser = /FBAN|FBAV|Instagram|Line|Twitter|LinkedInApp|MicroMessenger|TikTok/i.test(ua);
  const isChromeIOS = /CriOS/.test(ua);
  const isFirefoxIOS = /FxiOS/.test(ua);
  const isEdgeIOS = /EdgiOS/.test(ua);
  const isSafari = /Safari/.test(ua) && !isChromeIOS && !isFirefoxIOS && !isEdgeIOS;
  let browserName = 'Safari';
  if (isChromeIOS) browserName = 'Chrome';
  else if (isFirefoxIOS) browserName = 'Firefox';
  else if (isEdgeIOS) browserName = 'Edge';
  else if (isAndroid && /Chrome/.test(ua)) browserName = 'Chrome';
  else if (isAndroid && /Firefox/.test(ua)) browserName = 'Firefox';
  else if (isAndroid && /SamsungBrowser/.test(ua)) browserName = 'Samsung Internet';
  // Best-effort private/incognito detection on iOS WKWebView: storage quota is
  // dramatically lower in private mode. Returns a Promise<boolean>.
  const isLikelyPrivate = async () => {
    if (!isIOS || !navigator.storage || !navigator.storage.estimate) return false;
    try {
      const { quota } = await navigator.storage.estimate();
      return typeof quota === 'number' && quota < 120 * 1024 * 1024;
    } catch { return false; }
  };
  return { isIOS, isAndroid, isStandalone, isInAppBrowser, isSafari, isChromeIOS, isFirefoxIOS, isEdgeIOS, browserName, isLikelyPrivate };
}

function _showMicHelpModal(reason) {
  // reason: 'denied' | 'private' | 'standalone' | 'inapp' | 'insecure' | 'unsupported' | 'notfound' | 'busy' | 'unknown'
  const ctx = _detectIosContext();
  const browser = ctx.browserName;

  const iosSteps = `
    <div style="font-weight:600;margin:12px 0 6px;color:var(--teal2)">📱 Sur iPhone / iPad</div>
    <ol style="padding-left:20px;line-height:1.7;font-size:13px;color:var(--text2)">
      <li>Ouvrez l'application <b>Réglages</b> de l'iPhone</li>
      <li>Faites défiler jusqu'à <b>${browser}</b> et tapez dessus</li>
      <li>Tapez sur <b>Microphone</b></li>
      <li>Choisissez <b>Demander</b> ou <b>Autoriser</b> (pas Refuser)</li>
      <li>Revenez sur la page et <b>rechargez</b> (tirez vers le bas)</li>
    </ol>
    <div style="font-size:12px;color:var(--text3);margin-top:6px">
      Si la boîte de dialogue d'autorisation ne s'affiche toujours pas, supprimez les données du site dans
      <b>Réglages → ${browser}</b>, puis rechargez.
      L'enregistrement n'est pas disponible en navigation privée ni depuis "Sur l'écran d'accueil".
    </div>`;

  const androidSteps = `
    <div style="font-weight:600;margin:12px 0 6px;color:var(--teal2)">🤖 Sur Android</div>
    <ol style="padding-left:20px;line-height:1.7;font-size:13px;color:var(--text2)">
      <li>Tapez sur l'icône <b>🔒</b> (ou ⓘ) à gauche de l'adresse du site</li>
      <li>Tapez sur <b>Autorisations</b> ou <b>Paramètres du site</b></li>
      <li>Activez <b>Microphone</b> → <b>Autoriser</b></li>
      <li>Rechargez la page</li>
    </ol>
    <div style="font-size:12px;color:var(--text3);margin-top:6px">
      Sinon : <b>Paramètres Android → Applications → ${browser} → Autorisations → Microphone → Autoriser</b>.
    </div>`;

  let headline = "Microphone bloqué";
  let lead = "L'enregistrement audio n'est pas autorisé. Suivez les étapes ci-dessous pour activer le microphone, puis réessayez.";
  if (reason === 'private') {
    headline = "Navigation privée détectée";
    lead = "L'enregistrement audio est désactivé en navigation privée. Ouvrez le site dans un onglet normal de " + browser + ".";
  } else if (reason === 'standalone') {
    headline = "Mode application détecté";
    lead = "L'enregistrement audio n'est pas disponible quand le site est lancé depuis l'écran d'accueil. Ouvrez l'URL directement dans " + browser + ".";
  } else if (reason === 'inapp') {
    headline = "Navigateur intégré détecté";
    lead = "Ce navigateur intégré (Instagram, Facebook, etc.) ne permet pas l'enregistrement audio. Ouvrez le lien dans " + (ctx.isIOS ? "Safari" : "Chrome") + " (menu ⋯ → Ouvrir dans le navigateur).";
  } else if (reason === 'insecure') {
    headline = "Connexion non sécurisée";
    lead = "L'enregistrement audio nécessite une connexion HTTPS. Demandez à votre administrateur d'activer HTTPS sur le site.";
  } else if (reason === 'unsupported') {
    headline = "Navigateur incompatible";
    lead = "Votre navigateur ne supporte pas l'enregistrement audio. Essayez avec Safari (iOS) ou Chrome (Android).";
  } else if (reason === 'notfound') {
    headline = "Aucun microphone";
    lead = "Aucun microphone n'a été détecté sur votre appareil.";
  } else if (reason === 'busy') {
    headline = "Microphone occupé";
    lead = "Une autre application utilise déjà le microphone. Fermez-la puis réessayez.";
  }

  const showSteps = ['denied', 'unknown'].includes(reason);

  const overlay = document.createElement('div');
  overlay.id = 'micHelpModal';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.style.cssText = `
    position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:10000;
    display:flex;align-items:center;justify-content:center;padding:16px;
    backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px);`;
  overlay.innerHTML = `
    <div style="background:var(--bg);color:var(--text);max-width:480px;width:100%;
                border-radius:16px;border:1px solid var(--border);
                padding:22px 20px calc(20px + env(safe-area-inset-bottom, 0px));
                max-height:90dvh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.4)">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <div style="font-size:24px">🎤</div>
        <div style="font-size:17px;font-weight:700;flex:1">${headline}</div>
        <button type="button" id="micHelpClose" aria-label="Fermer"
          style="background:none;border:none;font-size:22px;color:var(--text2);cursor:pointer;width:36px;height:36px">×</button>
      </div>
      <div style="font-size:13px;color:var(--text);line-height:1.5">${lead}</div>
      ${showSteps ? (ctx.isIOS ? iosSteps : ctx.isAndroid ? androidSteps : iosSteps + androidSteps) : ''}
      <div style="margin-top:18px;display:flex;gap:8px;justify-content:flex-end">
        <button type="button" id="micHelpOk" class="btn btn-primary btn-sm">J'ai compris</button>
      </div>
    </div>`;
  const close = () => { try { document.body.removeChild(overlay); } catch {} };
  overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
  document.body.appendChild(overlay);
  document.getElementById('micHelpClose').addEventListener('click', close);
  document.getElementById('micHelpOk').addEventListener('click', close);
}

async function _startRecording(statusEl, timerEl, stopBtn, sendBtn) {
  const ctx = _detectIosContext();

  if (ctx.isInAppBrowser) {
    _showMicHelpModal('inapp');
    return false;
  }
  if (ctx.isIOS && ctx.isStandalone) {
    _showMicHelpModal('standalone');
    return false;
  }

  const secure = window.isSecureContext || ['localhost','127.0.0.1','[::1]'].includes(location.hostname);
  if (!secure) {
    _showMicHelpModal('insecure');
    return false;
  }
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    _showMicHelpModal('unsupported');
    return false;
  }
  try {
    _recorder.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    const name = e && e.name;
    if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
      const likelyPrivate = await ctx.isLikelyPrivate();
      _showMicHelpModal(likelyPrivate ? 'private' : 'denied');
    } else if (name === 'NotFoundError' || name === 'OverconstrainedError') {
      _showMicHelpModal('notfound');
    } else if (name === 'NotReadableError') {
      _showMicHelpModal('busy');
    } else {
      _showMicHelpModal('unknown');
    }
    return false;
  }
  let mime = '';
  if (window.MediaRecorder) {
    for (const m of ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']) {
      if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) { mime = m; break; }
    }
  } else {
    showToast("L'enregistrement audio n'est pas supporté par ce navigateur.", 'error');
    return false;
  }
  _recorder.chunks = [];
  _recorder.media  = new MediaRecorder(_recorder.stream, mime ? { mimeType: mime } : undefined);
  _recorder.media.ondataavailable = (e) => { if (e.data && e.data.size) _recorder.chunks.push(e.data); };
  _recorder.media.onstop = () => {
    const type = _recorder.media.mimeType || 'audio/webm';
    _recorder.blob = new Blob(_recorder.chunks, { type });
    _recorder.url  = URL.createObjectURL(_recorder.blob);
    _recorder.durationSec = Math.round((Date.now() - _recorder.startedAt) / 1000);
    if (_recorder.stream) _recorder.stream.getTracks().forEach(t => t.stop());
    _recorder.stream = null;
    if (_recorder.timerId) { clearInterval(_recorder.timerId); _recorder.timerId = null; }
    const preview = document.getElementById('audioPreview');
    if (preview) {
      preview.innerHTML = `
        <div style="display:flex;align-items:center;gap:8px;padding:8px 10px;background:var(--teal-dim);border:1px solid var(--teal-border);border-radius:8px">
          <audio controls src="${_recorder.url}" style="flex:1;height:32px"></audio>
          <span style="font-size:11px;color:var(--teal2)">${_recorder.durationSec}s</span>
          <button type="button" class="btn btn-ghost btn-sm" onclick="_discardRecording()" title="Supprimer">🗑</button>
        </div>`;
      preview.style.display = 'block';
    }
    if (sendBtn) sendBtn.disabled = false;
  };
  _recorder.startedAt = Date.now();
  _recorder.media.start();
  if (stopBtn) stopBtn.style.display = 'inline-flex';
  if (statusEl) statusEl.textContent = '● Enregistrement…';
  _recorder.timerId = setInterval(() => {
    const s = Math.floor((Date.now() - _recorder.startedAt) / 1000);
    if (timerEl) timerEl.textContent = `${s}s / ${_AUDIO_MAX_SEC}s`;
    if (s >= _AUDIO_MAX_SEC) _stopRecording();
  }, 250);
  return true;
}

function _stopRecording() {
  if (_recorder.media && _recorder.media.state !== 'inactive') {
    _recorder.media.stop();
  }
  const statusEl = document.getElementById('audioStatus');
  if (statusEl) statusEl.textContent = '';
  const stopBtn = document.getElementById('audioStopBtn');
  if (stopBtn) stopBtn.style.display = 'none';
}

function _discardRecording() {
  _recorder.blob = null;
  if (_recorder.url) { URL.revokeObjectURL(_recorder.url); _recorder.url = null; }
  _recorder.durationSec = 0;
  const preview = document.getElementById('audioPreview');
  if (preview) { preview.innerHTML = ''; preview.style.display = 'none'; }
}

function _resetRecorder() {
  try { if (_recorder.media && _recorder.media.state !== 'inactive') _recorder.media.stop(); } catch {}
  if (_recorder.stream) { try { _recorder.stream.getTracks().forEach(t => t.stop()); } catch {} }
  if (_recorder.timerId) clearInterval(_recorder.timerId);
  if (_recorder.url) URL.revokeObjectURL(_recorder.url);
  _recorder.media = null; _recorder.stream = null; _recorder.chunks = [];
  _recorder.blob = null; _recorder.url = null; _recorder.durationSec = 0; _recorder.timerId = null;
}

// ─── Shared composer HTML (text + 🎤 mic + preview) ─────────────────────────
function _composerHTML() {
  return `
    <textarea class="input" id="msgContenu" rows="4"
      placeholder="Écrivez votre message (ou enregistrez un audio)…"
      style="resize:vertical"></textarea>
    <div style="display:flex;align-items:center;gap:8px;margin-top:8px;flex-wrap:wrap">
      <button type="button" class="btn btn-ghost btn-sm" id="audioRecBtn" onclick="_toggleRecord()">🎤 Enregistrer</button>
      <button type="button" class="btn btn-ghost btn-sm" id="audioStopBtn" style="display:none;color:var(--red)" onclick="_stopRecording()">⏹ Arrêter</button>
      <span id="audioStatus" style="font-size:12px;color:var(--text2)"></span>
      <span id="audioTimer"  style="font-size:12px;color:var(--text3);margin-left:auto"></span>
    </div>
    <div id="audioPreview" style="display:none;margin-top:8px"></div>`;
}

async function _toggleRecord() {
  const btn = document.getElementById('audioRecBtn');
  if (_recorder.media && _recorder.media.state === 'recording') {
    _stopRecording();
    return;
  }
  _discardRecording();
  const statusEl = document.getElementById('audioStatus');
  const timerEl  = document.getElementById('audioTimer');
  const stopBtn  = document.getElementById('audioStopBtn');
  const ok = await _startRecording(statusEl, timerEl, stopBtn, null);
  if (!ok && btn) btn.disabled = false;
}

async function _postMessageWithPayload(url, contenu, rdvId, extra = {}) {
  // Use multipart when audio is present, JSON otherwise
  if (_recorder.blob) {
    const fd = new FormData();
    if (contenu) fd.append('contenu', contenu);
    if (rdvId)   fd.append('rdv_id', rdvId);
    const t = (_recorder.blob.type || '').toLowerCase();
    const n = (_recorder.blob.name || '').toLowerCase();
    const ext = t.includes('mp4') || t.includes('aac') || t.includes('m4a') || n.endsWith('.m4a') || n.endsWith('.mp4') || n.endsWith('.aac') ? 'm4a'
              : t.includes('ogg') || n.endsWith('.ogg') ? 'ogg'
              : t.includes('wav') || n.endsWith('.wav') ? 'wav'
              : 'webm';
    fd.append('audio', _recorder.blob, `message.${ext}`);
    fd.append('audio_duration_sec', String(_recorder.durationSec || 0));
    for (const [k, v] of Object.entries(extra)) fd.append(k, String(v));
    try {
      const r = await fetch(url, { method: 'POST', body: fd, credentials: 'include',
        headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (r.status === 429) return { error: 'Trop de tentatives. Réessayez dans une minute.' };
      return await r.json();
    } catch (e) { return { error: e.message }; }
  }
  return api(url, 'POST', { contenu, rdv_id: rdvId, ...extra });
}

// ─── DOCTOR: Open compose / thread modal ────────────────────────────────────
async function openMessageModal(pid, rdvId, rdvLabel) {
  _resetRecorder();
  const rdvSection = rdvId ? `
    <div style="margin-bottom:10px;padding:8px 12px;background:var(--teal-dim);border:1px solid var(--teal-border);border-radius:8px;font-size:12px;color:var(--teal2)">
      📅 Lié au RDV : <strong>${escH(rdvLabel || rdvId)}</strong>
      <input type="hidden" id="msgRdvId" value="${escH(rdvId)}">
    </div>` : `<input type="hidden" id="msgRdvId" value="">`;

  // Load conversations so the doctor sees the existing thread (if any)
  const convs = await api(`/api/patients/${pid}/conversations`);
  const openConv = Array.isArray(convs) ? convs.find(c => c.status === 'open') : null;

  let threadHTML = '';
  if (openConv) {
    const data = await api(`/api/conversations/${openConv.id}/messages`);
    const msgs = (data && data.messages) || [];
    threadHTML = `
      <div style="margin-bottom:10px;max-height:260px;overflow-y:auto;background:var(--bg2);border-radius:8px;padding:10px;display:flex;flex-direction:column;gap:8px">
        ${msgs.map(m => _threadBubble(m, 'medecin')).join('') || '<div style="color:var(--text3);font-size:12px;text-align:center">Aucun message</div>'}
      </div>
      <div style="display:flex;justify-content:flex-end;margin-bottom:8px">
        <button class="btn btn-ghost btn-sm" style="color:var(--red);font-size:11px"
          onclick="closeConversationFromModal('${openConv.id}','${pid}')">⏹ Terminer la conversation</button>
      </div>
    `;
  }

  showModal('✉ Message', `
    ${rdvSection}
    ${threadHTML}
    <div style="margin-bottom:8px">
      <label class="lbl">${openConv ? 'Votre réponse' : 'Nouveau message'}</label>
      ${_composerHTML()}
    </div>
    <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--bg2);border-radius:8px;font-size:12px;color:var(--text2)">
      <span>📧</span>
      <span>Le patient recevra une notification par email.</span>
    </div>
    <div id="msgError" style="color:var(--color-red);font-size:13px;margin-top:8px;display:none"></div>
    <div style="margin-top:14px;display:flex;gap:8px">
      <button class="btn btn-primary" id="msgSendBtn" onclick="submitMessage('${pid}')">✉ Envoyer</button>
      <button class="btn btn-ghost" onclick="closeModal();_resetRecorder()">Annuler</button>
    </div>
  `);
  setTimeout(() => { const ta = document.getElementById('msgContenu'); if (ta) ta.focus(); }, 80);
}

async function closeConversationFromModal(cid, pid) {
  if (!confirm('Terminer cette conversation ? Le patient devra en démarrer une nouvelle.')) return;
  const res = await api(`/api/conversations/${cid}/close`, 'POST');
  if (res.ok) {
    showToast('Conversation terminée', 'info');
    closeModal();
    _resetRecorder();
  } else {
    showToast(res.error || 'Erreur', 'error');
  }
}

async function submitMessage(pid) {
  const contenu = (document.getElementById('msgContenu')?.value || '').trim();
  const rdvId   = document.getElementById('msgRdvId')?.value || '';
  const errEl   = document.getElementById('msgError');
  const btn     = document.getElementById('msgSendBtn');
  if (!contenu && !_recorder.blob) {
    errEl.textContent = 'Message vide : écrivez un texte ou enregistrez un audio.';
    errEl.style.display = 'block';
    return;
  }
  btn.disabled = true; btn.textContent = 'Envoi…'; errEl.style.display = 'none';
  const res = await _postMessageWithPayload(`/api/patients/${pid}/messages`, contenu, rdvId);
  if (res.ok) {
    closeModal(); _resetRecorder();
    showToast('Message envoyé', 'success');
  } else {
    errEl.textContent = res.error || "Erreur lors de l'envoi";
    errEl.style.display = 'block';
    btn.disabled = false; btn.textContent = '✉ Envoyer';
  }
}

// ─── Shared thread bubble renderer ──────────────────────────────────────────
function _threadBubble(m, viewerRole) {
  const mine  = m.sender_role === viewerRole;
  const align = mine ? 'flex-end' : 'flex-start';
  const bg    = mine ? 'var(--teal-dim)' : 'var(--card)';
  const border= mine ? '1px solid var(--teal-border)' : '1px solid var(--border)';
  const audio = m.has_audio
    ? `<audio controls preload="none" src="/api/messages/${m.id}/audio" style="max-width:260px;margin-top:6px;height:32px"></audio>`
    : '';
  const text = m.contenu ? `<div style="white-space:pre-wrap;font-size:13px;line-height:1.5">${escH(m.contenu)}</div>` : '';
  return `
    <div style="display:flex;justify-content:${align}">
      <div style="max-width:80%;background:${bg};border:${border};border-radius:10px;padding:8px 10px">
        ${text}
        ${audio}
        <div style="font-size:10px;color:var(--text3);margin-top:4px;text-align:right">${escH(m.date)}</div>
      </div>
    </div>`;
}

// ─── PATIENT: Conversation list view ────────────────────────────────────────
async function renderMesMessages(c) {
  _resetRecorder();
  const pid = USER.patient_id;
  const convs = await api(`/api/patients/${pid}/conversations`);
  const list = Array.isArray(convs) ? convs : [];

  c.innerHTML = `
    <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap">
      <button class="btn btn-primary btn-sm" onclick="openPatientNewMessage(true)">➕ Nouvelle question</button>
    </div>
    <div id="convList">
      ${list.length ? list.map(_convCard).join('')
        : '<div style="color:var(--text3);text-align:center;padding:40px 20px">Aucune conversation pour le moment</div>'}
    </div>`;
}

function _convCard(cv) {
  const statusBadge = cv.status === 'open'
    ? '<span class="badge badge-teal" style="font-size:10px">Ouverte</span>'
    : '<span class="badge" style="background:var(--bg2);color:var(--text2);font-size:10px">Terminée</span>';
  const unread = cv.unread > 0
    ? `<span style="background:var(--red);color:#fff;font-size:10px;font-weight:700;padding:2px 7px;border-radius:10px;margin-left:6px">${cv.unread}</span>`
    : '';
  const preview = cv.last_preview || cv.subject || '(aucun message)';
  return `
    <div class="question-card" style="cursor:pointer" onclick="openConversationThread('${cv.id}')">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <div style="font-size:12px;font-weight:600;color:var(--teal2)">✉ ${escH(cv.medecin_nom || 'Médecin')} ${unread}</div>
        <div style="display:flex;align-items:center;gap:6px">
          ${statusBadge}
          <span style="font-size:11px;color:var(--text3)">${escH(cv.last_message_at || cv.created_at || '')}</span>
        </div>
      </div>
      <div style="font-size:13px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escH(preview)}</div>
    </div>`;
}

async function openConversationThread(cid) {
  const data = await api(`/api/conversations/${cid}/messages`);
  if (!data || data.error) { showToast(data?.error || 'Erreur', 'error'); return; }
  const conv = data.conversation || {};
  const msgs = data.messages || [];
  const isOpen = conv.status === 'open';
  const viewerRole = USER.role === 'patient' ? 'patient' : 'medecin';

  const composer = isOpen ? `
    <div style="border-top:1px solid var(--border);padding-top:10px;margin-top:10px">
      <label class="lbl">${viewerRole === 'patient' ? 'Votre réponse' : 'Répondre au patient'}</label>
      ${_composerHTML()}
      <div id="threadError" style="color:var(--color-red);font-size:13px;margin-top:8px;display:none"></div>
      <div style="margin-top:10px;display:flex;gap:8px">
        <button class="btn btn-primary" id="threadSendBtn" onclick="submitThreadReply('${cid}','${conv.patient_id}')">✉ Envoyer</button>
        ${viewerRole === 'medecin'
          ? `<button class="btn btn-ghost" style="color:var(--red)" onclick="closeConversationFromModal('${cid}','${conv.patient_id}')">⏹ Terminer</button>`
          : ''}
        <button class="btn btn-ghost" onclick="closeModal();_resetRecorder()">Fermer</button>
      </div>
    </div>` : `
    <div style="margin-top:10px;padding:10px;background:var(--bg2);border-radius:8px;font-size:12px;color:var(--text2);text-align:center">
      Conversation terminée le ${escH(conv.closed_at || '')}.
      ${viewerRole === 'patient'
        ? '<div style="margin-top:8px"><button class="btn btn-ghost btn-sm" onclick="closeModal();openPatientNewMessage(true)">Poser une nouvelle question</button></div>'
        : ''}
    </div>`;

  showModal(`✉ ${escH(viewerRole === 'patient' ? conv.medecin_nom : conv.patient_nom || 'Patient')}`, `
    <div id="threadMsgs" style="max-height:340px;overflow-y:auto;background:var(--bg2);border-radius:8px;padding:10px;display:flex;flex-direction:column;gap:8px">
      ${msgs.map(m => _threadBubble(m, viewerRole)).join('') || '<div style="color:var(--text3);font-size:12px;text-align:center">Aucun message</div>'}
    </div>
    ${composer}`);
  // scroll to bottom
  setTimeout(() => {
    const el = document.getElementById('threadMsgs');
    if (el) el.scrollTop = el.scrollHeight;
  }, 50);
}

async function submitThreadReply(cid, pid) {
  const contenu = (document.getElementById('msgContenu')?.value || '').trim();
  const errEl   = document.getElementById('threadError');
  const btn     = document.getElementById('threadSendBtn');
  if (!contenu && !_recorder.blob) {
    errEl.textContent = 'Message vide : écrivez un texte ou enregistrez un audio.';
    errEl.style.display = 'block';
    return;
  }
  btn.disabled = true; btn.textContent = 'Envoi…'; errEl.style.display = 'none';

  const url = USER.role === 'patient'
    ? `/api/patients/${pid}/messages/patient`
    : `/api/patients/${pid}/messages`;
  const res = await _postMessageWithPayload(url, contenu, '');
  if (res.ok) {
    _resetRecorder();
    // re-open thread to refresh
    await openConversationThread(cid);
    showToast('Envoyé', 'success');
  } else {
    errEl.textContent = res.error || "Erreur lors de l'envoi";
    errEl.style.display = 'block';
    btn.disabled = false; btn.textContent = '✉ Envoyer';
  }
}

async function openPatientNewMessage(newConv = false) {
  _resetRecorder();
  const pid = USER.patient_id;
  showModal('✉ Nouveau message', `
    <div style="margin-bottom:8px;font-size:12px;color:var(--text2)">
      Posez votre question à votre médecin. Vous pouvez écrire un message ou enregistrer un audio.
    </div>
    ${_composerHTML()}
    <div id="newMsgError" style="color:var(--color-red);font-size:13px;margin-top:8px;display:none"></div>
    <div style="margin-top:14px;display:flex;gap:8px">
      <button class="btn btn-primary" id="newMsgSendBtn" onclick="submitPatientNewMessage('${pid}',${newConv ? 'true' : 'false'})">✉ Envoyer</button>
      <button class="btn btn-ghost" onclick="closeModal();_resetRecorder()">Annuler</button>
    </div>`);
  setTimeout(() => { const ta = document.getElementById('msgContenu'); if (ta) ta.focus(); }, 80);
}

async function submitPatientNewMessage(pid, newConv) {
  const contenu = (document.getElementById('msgContenu')?.value || '').trim();
  const errEl   = document.getElementById('newMsgError');
  const btn     = document.getElementById('newMsgSendBtn');
  if (!contenu && !_recorder.blob) {
    errEl.textContent = 'Message vide : écrivez un texte ou enregistrez un audio.';
    errEl.style.display = 'block';
    return;
  }
  btn.disabled = true; btn.textContent = 'Envoi…'; errEl.style.display = 'none';
  const res = await _postMessageWithPayload(
    `/api/patients/${pid}/messages/patient`, contenu, '',
    newConv ? { new_conversation: '1' } : {}
  );
  if (res.ok) {
    closeModal(); _resetRecorder();
    showToast('Message envoyé', 'success');
    // refresh the list view
    const c = document.getElementById('mainContent');
    if (c && typeof renderMesMessages === 'function') renderMesMessages(c);
  } else {
    errEl.textContent = res.error || "Erreur lors de l'envoi";
    errEl.style.display = 'block';
    btn.disabled = false; btn.textContent = '✉ Envoyer';
  }
}
