// Chat page: messages, commands, voice input, attachments, specialists, TTS.

const messages = document.getElementById('messages');
const input = document.getElementById('input');
const composerStatus = document.getElementById('composer-status');
const sendButton = document.getElementById('send-btn');
const micButton = document.getElementById('mic-btn');
const attachSummary = document.getElementById('attach-summary');
const attachSummaryText = document.getElementById('attach-summary-text');
const attachSummaryButton = document.getElementById('attach-summary-btn');
const ttsSelect = document.getElementById('tts-engine');

// Control labels come from Python (core.ANSWER_CONTROLS); prompts never live in JS.
try {
  window.ANSWER_CONTROLS = JSON.parse(document.getElementById('answer-controls').textContent);
} catch (err) {
  window.ANSWER_CONTROLS = [];
}

let busy = false;
let ttsEngine = ttsSelect.value;
let lastRetry = null;

// ---------------------------------------------------------------- messages

// Header row: Solaris icon + name for replies, person icon + profile name for the user.
const USER_ICON = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="3.4"/><path d="M5.5 20a6.5 6.5 0 0113 0"/></svg>';
const SOLARIS_ICON = '<img src="/static/favicon/favicon.svg" alt="" width="16" height="16">';

function addMessage(kind, html, meta = '') {
  const wrapper = document.createElement('div');
  wrapper.className = `msg msg-${kind}`;
  const isUser = kind === 'user';
  const name = isUser ? (messages.dataset.profileName || 'You') : (kind === 'ai' ? 'Solaris' : '');
  if (name) {
    const tag = !isUser && meta && meta !== 'Solaris'
      ? `<span class="msg-head-tag">${escapeHtml(meta)}</span>` : '';
    const head = document.createElement('div');
    head.className = 'msg-head';
    head.innerHTML = `${isUser ? USER_ICON : SOLARIS_ICON}<span>${escapeHtml(name)}</span>${tag}`;
    wrapper.appendChild(head);
  }
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = html;
  wrapper.appendChild(bubble);
  messages.appendChild(wrapper);
  messages.scrollTop = messages.scrollHeight;
  return wrapper;
}

function addTyping() {
  const wrapper = addMessage('system', '<span class="typing">thinking</span>');
  return wrapper;
}

function setBusy(value, label = '') {
  busy = value;
  sendButton.disabled = value;
  input.disabled = value;
  composerStatus.textContent = label;
}

function plain(text) {
  return escapeHtml(text).replace(/\n/g, '<br>');
}

// ---------------------------------------------------------------- TTS

async function speak(text) {
  if (ttsEngine === 'off' || !text) return;
  try {
    const response = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, engine: ttsEngine }),
    });
    if (!response.ok) return;
    const blob = await response.blob();
    const audio = new Audio(URL.createObjectURL(blob));
    audio.play();
  } catch (err) {
    /* speech is best-effort */
  }
}

ttsSelect.addEventListener('change', async () => {
  ttsEngine = ttsSelect.value;
  await api('/api/tts/engine', { method: 'POST', body: JSON.stringify({ engine: ttsEngine }) });
  toast(`Voice replies: ${ttsEngine}`, 'ok');
});

// ---------------------------------------------------------------- payloads

function renderReply(payload, speakToo = true, question = '') {
  let html = payload.html || plain(payload.raw || '');
  if (payload.notes && payload.notes.length) {
    html += `<ul class="notes">${payload.notes.map((note) => `<li>${escapeHtml(note)}</li>`).join('')}</ul>`;
  }
  if (payload.sources && payload.sources.length) {
    html += `<ul class="sources">${payload.sources.map((source, index) =>
      `<li>[${index + 1}] <a href="${escapeHtml(source.url)}" target="_blank" rel="noopener">${escapeHtml(source.title || source.url)}</a>
       <span class="muted small">${escapeHtml(source.source || '')}</span></li>`).join('')}</ul>`;
  }
  const wrapper = addMessage('ai', html, payload.title || 'Solaris');
  attachAnswerSurface(wrapper, payload, question);
  if (payload.pulse) Shelf.renderRoute(payload.pulse);
  if (speakToo && payload.speak !== false) speak(payload.raw || '');
  return wrapper;
}

function handlePayload(payload, originalMessage) {
  switch (payload.type) {
    case 'reply':
      renderReply(payload, true, originalMessage);
      break;
    case 'info':
      addMessage('system', plain(payload.message));
      break;
    case 'error':
      addMessage('error', plain(payload.message || 'Something went wrong.'));
      break;
    case 'clear':
      messages.innerHTML = '';
      break;
    case 'session_end':
      addMessage('system', plain(payload.message));
      speak(payload.message);
      break;
    case 'profile_picker':
      openProfilePicker(payload.profiles, payload.current, reloadSoon);
      break;
    case 'attachments':
      openAttachments(payload.attachments);
      break;
    case 'attached':
      refreshAttachments(payload.attachments);
      addMessage('system', plain(payload.message + (payload.recommendation ? ` — ${payload.recommendation}` : '')));
      break;
    case 'detached':
      refreshAttachments(payload.attachments);
      addMessage('system', plain(payload.message));
      break;
    case 'better_open':
      openBetterModal(payload.prefill || '');
      break;
    case 'better_questions':
      renderBetterQuestions(payload);
      break;
    case 'better_draft':
      renderBetterDraft(payload);
      break;
    case 'need_keys':
      openKeyModal(payload, originalMessage);
      break;
    default:
      addMessage('system', plain(payload.message || JSON.stringify(payload)));
  }
}

// ---------------------------------------------------------------- sending

async function send(overrideText = null) {
  const text = overrideText != null ? overrideText : input.value.trim();
  if (!text || busy) return;

  if (overrideText == null) {
    input.value = '';
    input.style.height = 'auto';
    addMessage('user', plain(text));
  }

  const typing = addTyping();
  setBusy(true, '');
  try {
    const payload = await api('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message: text, input: lastInputMode }),
    });
    typing.remove();
    lastInputMode = 'text';
    handlePayload(payload, text);
  } catch (err) {
    typing.remove();
    addMessage('error', plain(`Request failed: ${err.message}`));
  } finally {
    setBusy(false, '');
    input.focus();
  }
}

sendButton.addEventListener('click', () => send());
input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    send();
  }
});
input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
});

// ---------------------------------------------------------------- voice input

const RECORD_SECONDS = 5;
let activeRecorder = null;
let lastInputMode = 'text';

micButton.addEventListener('click', async () => {
  if (busy) return;

  // Second click while recording = stop early.
  if (activeRecorder) {
    if (activeRecorder.state !== 'inactive') activeRecorder.stop();
    return;
  }

  if (!navigator.mediaDevices || !window.MediaRecorder) {
    toast('This browser cannot record audio.', 'error');
    return;
  }

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (err) {
    toast('Microphone permission denied.', 'error');
    return;
  }

  const chunks = [];
  const recorder = new MediaRecorder(stream);
  activeRecorder = recorder;
  recorder.ondataavailable = (event) => chunks.push(event.data);
  recorder.start();

  let remaining = RECORD_SECONDS;
  micButton.classList.add('recording');
  composerStatus.textContent = `Recording… ${remaining}s (click to stop early)`;

  const ticker = setInterval(() => {
    remaining -= 1;
    if (remaining > 0) composerStatus.textContent = `Recording… ${remaining}s (click to stop early)`;
  }, 1000);
  setTimeout(() => { if (recorder.state !== 'inactive') recorder.stop(); }, RECORD_SECONDS * 1000);

  recorder.onstop = async () => {
    clearInterval(ticker);
    activeRecorder = null;
    stream.getTracks().forEach((track) => track.stop());
    micButton.classList.remove('recording');
    composerStatus.textContent = 'Transcribing…';

    const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
    if (blob.size === 0) {
      composerStatus.textContent = '';
      toast('No audio captured.', 'error');
      return;
    }

    const form = new FormData();
    form.append('audio', blob, 'speech.webm');
    const result = await apiForm('/api/voice', form);
    composerStatus.textContent = '';
    if (result.ok && result.text) {
      input.value = result.text;
      lastInputMode = 'voice';
      input.focus();
      toast('Transcribed. Press Enter to send.', 'ok');
    } else {
      toast(result.error || 'Could not transcribe.', 'error');
    }
  };
});

// ---------------------------------------------------------------- attachments

const attachInput = document.getElementById('attach-input');
document.getElementById('attach-btn').addEventListener('click', () => attachInput.click());

attachInput.addEventListener('change', async () => {
  const file = attachInput.files[0];
  attachInput.value = '';
  if (!file) return;
  const form = new FormData();
  form.append('file', file);
  composerStatus.textContent = 'Attaching…';
  const payload = await apiForm('/api/attach', form);
  composerStatus.textContent = '';
  handlePayload(payload, '');
});

function updateAttachSummary(items) {
  const total = items.length;
  const selected = items.filter((item) => item.selected !== false).length;
  attachSummary.hidden = !total;
  if (!total) return;
  attachSummaryText.textContent = total === 1
    ? `${items[0].name} · ${selected ? 'included' : 'excluded'}`
    : `${total} files · ${selected} selected`;
  attachSummaryButton.setAttribute('aria-label',
    `${total} files attached, ${selected} included. Open the workspace to change them.`);
}

function refreshAttachments(items) {
  updateAttachSummary(items);
  if (window.Shelf) {
    if (Shelf.state) Shelf.state.attachments = items;
    Shelf.renderFiles(items);
  }
}

attachSummaryButton.addEventListener('click', () => Shelf.reveal('files-section'));

async function loadAttachments() {
  const data = await api('/api/attachments');
  refreshAttachments(data.attachments || []);
}

function openAttachments(items) {
  if (!items.length) {
    addMessage('system', 'No files attached currently.');
    return;
  }
  openModal('Attached files', `
    <p class="muted small">Only included files are processed and sent to the model. Toggle them here
    or as boxes in the workspace shelf.</p>
    <div class="form-grid">${items.map((item) =>
      `<div class="row"><code>${escapeHtml(item.name)}</code><span class="muted small">${escapeHtml(item.type)}</span>
       <button class="btn btn-small" data-include="${item.index}">${item.selected === false ? 'Include' : 'Exclude'}</button>
       <button class="btn btn-small" data-remove="${item.index}">Remove</button></div>`).join('')}</div>`);
  document.querySelectorAll('[data-remove]').forEach((button) => {
    button.addEventListener('click', async () => {
      const payload = await api('/api/attachments/remove', {
        method: 'POST',
        body: JSON.stringify({ index: button.dataset.remove }),
      });
      handlePayload(payload, '');
      closeModal();
    });
  });
  document.querySelectorAll('[data-include]').forEach((button) => {
    button.addEventListener('click', async () => {
      const item = items.find((entry) => String(entry.index) === button.dataset.include) || {};
      const payload = await api('/api/attachments/select', {
        method: 'POST',
        body: JSON.stringify({ index: button.dataset.include, selected: item.selected === false }),
      });
      refreshAttachments(payload.attachments || []);
      openAttachments(payload.attachments || []);
    });
  });
}

// ---------------------------------------------------------------- profiles
// openProfilePicker / openProfileAccess live in app.js — the landing page and
// this page walk the same activation-code and password flows.

const reloadSoon = () => setTimeout(() => window.location.reload(), 400);

document.getElementById('profile-switch-btn').addEventListener('click', async () => {
  const data = await api('/api/profiles');
  openProfilePicker(data.profiles || [], data.current, reloadSoon);
});

document.getElementById('end-session').addEventListener('click', async () => {
  const data = await api('/api/session/end', { method: 'POST', body: '{}' });
  addMessage('system', plain(data.message || 'Session ended.'));
});

// ---------------------------------------------------------------- specialists

function openBetterModal(prefill) {
  openModal('Ask a specialist', `
    <label>Specialist
      <select id="better-specialist">
        <option value="writer">✍️ The Writer — essays, editing, creative</option>
        <option value="coder">💻 The Programmer — code, debugging, design</option>
        <option value="strategist">🧠 The Strategist — reasoning, plans, PRDs</option>
      </select>
    </label>
    <label>Your request
      <textarea id="better-question" rows="4" placeholder="Describe what you need">${escapeHtml(prefill)}</textarea>
    </label>
    <label class="inline"><input type="checkbox" id="better-attachments" checked> Include attached files</label>
    <div class="actions"><button class="btn btn-primary" id="better-go">Ask</button></div>
  `);

  document.getElementById('better-go').addEventListener('click', async () => {
    const specialist = document.getElementById('better-specialist').value;
    const question = document.getElementById('better-question').value.trim();
    if (!question) {
      toast('Describe your request first.', 'error');
      return;
    }
    const useAttachments = document.getElementById('better-attachments').checked;
    closeModal();
    addMessage('user', plain(`${specialist === 'coder' ? '💻' : specialist === 'writer' ? '✍️' : '🧠'} ${question}`));
    const typing = addTyping();
    const payload = await api('/api/better', {
      method: 'POST',
      body: JSON.stringify({ specialist, question, use_attachments: useAttachments }),
    });
    typing.remove();
    handlePayload(payload, '');
  });
}

function renderBetterQuestions(payload) {
  addMessage('ai', payload.html, payload.title || 'Strategist');
  const questions = Array.isArray(payload.questions) ? payload.questions : [];
  if (questions.length < 2) {
    openBetterAnswerBox();
    return;
  }
  const fields = questions.map((question, index) => `
    <div class="better-q">
      <label for="better-q-${index}">${index + 1}. ${escapeHtml(question)}</label>
      <textarea id="better-q-${index}" rows="2" placeholder="N/A"></textarea>
    </div>`).join('');
  openModal('Answer the strategist', `
    <p class="muted small">Answer each question below — leave a field empty for N/A.</p>
    <form id="better-form">
      ${fields}
      <div class="actions"><button class="btn btn-primary" type="submit">Send answers</button></div>
    </form>
  `);
  document.getElementById('better-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const answers = questions.map((_, index) => {
      const field = document.getElementById(`better-q-${index}`);
      return (field.value || '').trim() || 'N/A';
    }).map((answer, index) => `${index + 1}. ${answer}`).join('\n');
    closeModal();
    addMessage('user', plain(answers));
    const typing = addTyping();
    const reply = await api('/api/better/answers', {
      method: 'POST',
      body: JSON.stringify({ answers }),
    });
    typing.remove();
    handlePayload(reply, '');
  });
}

// Fallback for a questionnaire the parser could not split: one free-text box.
function openBetterAnswerBox() {
  openModal('Answer the strategist', `
    <p class="muted small">Answer the questions above — N/A is fine for anything you don't care about.</p>
    <textarea id="better-answers" rows="6" placeholder="1. …&#10;2. …"></textarea>
    <div class="actions"><button class="btn btn-primary" id="better-send-answers">Send answers</button></div>
  `);
  document.getElementById('better-send-answers').addEventListener('click', async () => {
    const answers = document.getElementById('better-answers').value.trim();
    closeModal();
    addMessage('user', plain(answers || 'N/A'));
    const typing = addTyping();
    const payload = await api('/api/better/answers', {
      method: 'POST',
      body: JSON.stringify({ answers }),
    });
    typing.remove();
    handlePayload(payload, '');
  });
}

// The pending draft decision: only one is live, so the row is replaced when a
// new draft arrives.
let draftActions = null;

function renderBetterDraft(payload) {
  const wrapper = renderReply(payload, false);
  if (draftActions) {
    draftActions.remove();
    draftActions = null;
  }
  const row = document.createElement('div');
  row.className = 'actions';
  row.innerHTML = `
    <button class="btn btn-primary" id="draft-approve">Approve</button>
    <button class="btn" id="draft-reject">Ask the Secondary Model</button>`;
  wrapper.appendChild(row);
  draftActions = row;

  document.getElementById('draft-approve').addEventListener('click', async () => {
    const typing = addTyping();
    const reply = await api('/api/better/decision', { method: 'POST', body: JSON.stringify({ approve: true }) });
    typing.remove();
    if (reply && reply.type === 'error') {
      addMessage('error', plain(reply.message || 'Could not approve the draft.'));
      return;
    }
    // The approved draft is already on screen; the server sends it back as a
    // reply, so only the confirmation is added.
    row.remove();
    if (draftActions === row) draftActions = null;
    addMessage('system', plain('Draft approved.'));
    if (reply && reply.type === 'reply') speak(reply.raw || '');
  });
  document.getElementById('draft-reject').addEventListener('click', async () => {
    const typing = addTyping();
    const reply = await api('/api/better/decision', { method: 'POST', body: JSON.stringify({ approve: false }) });
    typing.remove();
    handlePayload(reply, '');
  });
}

// ---------------------------------------------------------------- web keys

function openKeyModal(payload, originalMessage) {
  lastRetry = originalMessage;
  openModal('Web search setup', `
    <p class="muted small">Live web search needs a Tavily and/or Firecrawl key. Saving a key requires your API password.</p>
    <label>Tavily API key <input id="key-tavily" type="password" placeholder="tvly-…"></label>
    <label>Firecrawl API key <input id="key-firecrawl" type="password" placeholder="fc-…"></label>
    <label>API password <input id="key-password" type="password" autocomplete="off"></label>
    <div class="actions">
      <button class="btn btn-primary" id="key-save">Save & retry</button>
      <span class="muted small" id="key-status"></span>
    </div>
    <p class="muted small">No password yet? Create one in <a href="/settings#password">Settings → Password</a>.</p>
  `);

  document.getElementById('key-save').addEventListener('click', async () => {
    const values = {};
    const tavily = document.getElementById('key-tavily').value.trim();
    const firecrawl = document.getElementById('key-firecrawl').value.trim();
    if (tavily) values.TAVILY_API_KEY = tavily;
    if (firecrawl) values.FIRECRAWL_API_KEY = firecrawl;
    if (!Object.keys(values).length) {
      document.getElementById('key-status').textContent = 'Enter at least one key.';
      return;
    }
    const password = document.getElementById('key-password').value;
    const result = await api('/api/settings/keys', {
      method: 'POST',
      body: JSON.stringify({ password, values }),
    });
    if (!result.ok) {
      document.getElementById('key-status').textContent = result.error || 'Could not save.';
      return;
    }
    closeModal();
    addMessage('system', 'Web keys saved. Retrying…');
    if (lastRetry) send(lastRetry);
  });
}

// ---------------------------------------------------------------- boot

loadAttachments();
workspaceInit();

// The study page hands off a pre-filled command (e.g. .QUIZ: SQLite indexing).
const prefill = new URLSearchParams(window.location.search).get('prefill');
if (prefill) {
  input.value = prefill;
  input.focus();
}

input.focus();
