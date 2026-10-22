// Settings page: models, specialists, API keys (password gated) and password rotation.

const SPECIALIST_ROLES = [
  { key: 'coding', label: '💻 The Programmer' },
  { key: 'writing', label: '✍️ The Writer' },
  { key: 'reasoning', label: '🧠 The Strategist' },
  { key: 'study', label: '📚 Study' },
];

let settingsData = null;

// ---------------------------------------------------------------- tabs

document.querySelectorAll('.tab').forEach((tab) => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((item) => item.classList.remove('active'));
    tab.classList.add('active');
    document.querySelectorAll('.tab-panel').forEach((panel) => { panel.hidden = true; });
    document.getElementById(`tab-${tab.dataset.tab}`).hidden = false;
  });
});

function openTab(name) {
  const tab = document.querySelector(`.tab[data-tab="${name}"]`);
  if (tab) tab.click();
}
if (window.location.hash === '#password') openTab('password');
if (window.location.hash === '#keys') openTab('keys');

// ---------------------------------------------------------------- models

function specialistCard(role, spec) {
  const primary = spec.primary || {};
  const secondary = spec.secondary || {};
  return `
    <div class="card">
      <h3>${role.label}</h3>
      <label>Primary model <input type="text" data-spec="${role.key}" data-part="primary-name" value="${escapeHtml(primary.name || '')}"></label>
      <label>Primary provider <select data-spec="${role.key}" data-part="primary-provider">${providerOptions(primary.provider)}</select></label>
      <label>Secondary model <input type="text" data-spec="${role.key}" data-part="secondary-name" value="${escapeHtml(secondary.name || '')}"></label>
      <label>Secondary provider <select data-spec="${role.key}" data-part="secondary-provider">${providerOptions(secondary.provider)}</select></label>
    </div>`;
}

function fillModels() {
  const config = settingsData.config || {};
  const vision = config.vision_model || {};
  const depths = (config.web || {}).depths || {};
  const settings = settingsData.settings || {};
  const response = settings.response || {};
  const personality = settings.personality || {};

  document.getElementById('m-gemini').value = config.gemini || '';
  document.getElementById('m-openrouter').value = (config.openrouter || []).join('\n');
  document.getElementById('m-local').value = config.local || '';
  document.getElementById('m-assist').value = config.or_assist || '';

  document.getElementById('m-depth-quick').value = depths.quick || 3;
  document.getElementById('m-depth-standard').value = depths.standard || 5;
  document.getElementById('m-depth-deep').value = depths.deep || 8;

  document.getElementById('m-vision-p-model').value = (vision.primary || {}).model || '';
  document.getElementById('m-vision-p-provider').innerHTML = providerOptions((vision.primary || {}).provider);
  document.getElementById('m-vision-s-model').value = (vision.secondary || {}).model || '';
  document.getElementById('m-vision-s-provider').innerHTML = providerOptions((vision.secondary || {}).provider);

  document.getElementById('specialist-grid').innerHTML = SPECIALIST_ROLES
    .map((role) => specialistCard(role, (config.specialist || {})[role.key] || {}))
    .join('');

  document.getElementById('s-max-length').value = response.maximum_length || 8;
  document.getElementById('s-emoji').value = response.emoji_density || 'Moderate';
  document.getElementById('s-warmth').value = (personality.warmth || 'moderate').toLowerCase();
  document.getElementById('s-humor').value = (personality.humor || 'low').toLowerCase();
  document.getElementById('s-creativity').value = personality.creativity || 0.9;
}

function collectModels() {
  const base = settingsData.settings || {};
  const specialists = {};
  SPECIALIST_ROLES.forEach((role) => {
    const get = (part) => document.querySelector(`[data-spec="${role.key}"][data-part="${part}"]`).value.trim();
    specialists[role.key] = {
      primary: { name: get('primary-name'), role: role.key === 'coding' ? 'coder' : role.key, provider: get('primary-provider') },
      secondary: { name: get('secondary-name'), role: role.key === 'coding' ? 'coder' : role.key, provider: get('secondary-provider') },
    };
  });

  return {
    config: {
      gemini: document.getElementById('m-gemini').value.trim(),
      openrouter: document.getElementById('m-openrouter').value.split('\n').map((line) => line.trim()).filter(Boolean),
      local: document.getElementById('m-local').value.trim(),
      or_assist: document.getElementById('m-assist').value.trim(),
      web: {
        depths: {
          quick: parseInt(document.getElementById('m-depth-quick').value, 10) || 3,
          standard: parseInt(document.getElementById('m-depth-standard').value, 10) || 5,
          deep: parseInt(document.getElementById('m-depth-deep').value, 10) || 8,
        },
      },
      vision_model: {
        primary: {
          model: document.getElementById('m-vision-p-model').value.trim(),
          provider: document.getElementById('m-vision-p-provider').value,
        },
        secondary: {
          model: document.getElementById('m-vision-s-model').value.trim(),
          provider: document.getElementById('m-vision-s-provider').value,
        },
      },
      specialist: specialists,
    },
    settings: {
      response: {
        maximum_length: parseInt(document.getElementById('s-max-length').value, 10) || 8,
        emoji_density: document.getElementById('s-emoji').value,
        thinking_level: (base.response || {}).thinking_level || {},
        temperature: (base.response || {}).temperature || {},
        detail: (base.response || {}).detail || {},
      },
      personality: {
        warmth: document.getElementById('s-warmth').value,
        humor: document.getElementById('s-humor').value,
        creativity: String(document.getElementById('s-creativity').value) || '0.9',
      },
    },
  };
}

document.getElementById('save-models').addEventListener('click', async () => {
  const status = document.getElementById('models-status');
  status.textContent = 'Saving…';
  const payload = collectModels();
  const data = await api('/api/settings/models', { method: 'POST', body: JSON.stringify(payload) });
  if (data.ok) {
    settingsData.config = data.config;
    status.textContent = '';
    toast('Models saved (backup written to _backups/).', 'ok');
  } else {
    status.textContent = '';
    toast(data.error || 'Could not save models.', 'error');
  }
});

// ---------------------------------------------------------------- keys

function fillKeys() {
  const body = document.querySelector('#keys-table tbody');
  body.innerHTML = '';
  (settingsData.keys || []).forEach((key) => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${escapeHtml(key.label)}${key.url ? `<br><a class="small" href="${key.url}" target="_blank" rel="noopener">get a key</a>` : ''}</td>
      <td>${key.set ? '<span class="chip chip-ok">set</span>' : '<span class="chip chip-muted">not set</span>'}</td>
      <td><input type="password" data-env="${key.env}" placeholder="${key.set ? 'replace / blank to keep' : 'paste key'}" autocomplete="off"></td>`;
    body.appendChild(row);
  });
}

document.getElementById('save-keys').addEventListener('click', async () => {
  const status = document.getElementById('keys-status');
  const values = {};
  document.querySelectorAll('#keys-table input[data-env]').forEach((field) => {
    const value = field.value.trim();
    if (value) values[field.dataset.env] = value;
  });
  if (!Object.keys(values).length) {
    toast('Nothing new to save.', 'error');
    return;
  }
  const password = document.getElementById('keys-password').value;
  status.textContent = 'Saving…';
  const data = await api('/api/settings/keys', {
    method: 'POST',
    body: JSON.stringify({ password, values }),
  });
  status.textContent = '';
  if (data.ok) {
    document.querySelectorAll('#keys-table input[data-env]').forEach((field) => { field.value = ''; });
    document.getElementById('keys-password').value = '';
    toast(`Updated: ${data.updated.join(', ')}`, 'ok');
    await loadSettings();
  } else {
    toast(data.error || 'Could not update keys.', 'error');
  }
});

// ---------------------------------------------------------------- password

function fillPassword() {
  const state = document.getElementById('password-state');
  const label = document.getElementById('current-password-label');
  if (settingsData.password_set) {
    state.textContent = 'A password is set. Generating a new one requires the current password.';
    label.hidden = false;
  } else {
    state.textContent = 'No password set yet. Create one now — you will need it for any API key change.';
    label.hidden = true;
  }
}

document.getElementById('rotate-password').addEventListener('click', async () => {
  const current = document.getElementById('current-password').value;
  const data = await api('/api/settings/password', {
    method: 'POST',
    body: JSON.stringify({ current }),
  });
  if (!data.ok) {
    toast(data.error || 'Could not set password.', 'error');
    return;
  }
  const box = document.getElementById('password-result');
  box.hidden = false;
  box.innerHTML = `
    <p><strong>Your new API password</strong> — write it down, it is shown only this once.</p>
    <div class="password-value">${escapeHtml(data.password)}</div>
    <button class="btn btn-small" id="copy-password">Copy</button>`;
  document.getElementById('copy-password').addEventListener('click', () => {
    navigator.clipboard.writeText(data.password);
    toast('Copied.', 'ok');
  });
  document.getElementById('current-password').value = '';
  await loadSettings();
});

// ---------------------------------------------------------------- boot

async function loadSettings() {
  settingsData = await api('/api/settings');
  fillModels();
  fillKeys();
  fillPassword();
  fillVector();
}

loadSettings();

// ---------------------------------------------------------------- vector index

function fillVector() {
  const vector = settingsData.vector || {};
  const grid = document.getElementById('vector-grid');
  if (!grid) return;
  const state = vector.state || 'empty';
  const stateLabel = { empty: 'not built', ready: 'ready', stale: 'stale' }[state] || state;
  grid.innerHTML = `
    <div class="chip ${vector.available && vector.ollama ? 'chip-ok' : 'chip-muted'}">
      ${vector.available ? 'extension loaded' : 'extension unavailable'}
    </div>
    <div class="chip ${vector.ollama ? 'chip-ok' : 'chip-muted'}">
      ${vector.ollama ? 'model resident' : 'model not resident'}
    </div>
    <div class="chip chip-muted">${vector.chunks || 0} chunks</div>
    <div class="chip chip-muted">${escapeHtml(vector.model || '—')}</div>
    <div class="chip chip-muted">${vector.dimension || '—'} dims</div>
    <div class="chip chip-muted">${stateLabel}</div>
`;

document.getElementById('vector-rebuild').addEventListener('click', async () => {
  const status = document.getElementById('vector-status');
  const btn = document.getElementById('vector-rebuild');
  btn.disabled = true;
  status.textContent = 'Rebuilding…';
  const data = await api('/api/vector/rebuild', { method: 'POST' });
  btn.disabled = false;
  status.textContent = '';
  if (data.ok) {
    settingsData.vector = data.vector;
    fillVector();
    toast('Index rebuilt.', 'ok');
  } else {
    toast(data.error || 'Rebuild failed.', 'error');
  }
});
