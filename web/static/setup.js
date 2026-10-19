// Setup wizard: environment → local AI → web → providers → models → profile → password.

const STEP_ORDER = ['env', 'local', 'web', 'providers', 'models', 'profile', 'finish'];
const PROVIDER_ORDER = ['gemini', 'openrouter', 'openrouter-assist', 'nvidia', 'groq', 'ollama-cloud'];
const PROVIDER_NOTES = {
  gemini: 'Primary chat model (Google AI Studio key).',
  openrouter: 'Fallback chain — free models available.',
  'openrouter-assist': 'Optional second OpenRouter key used for summaries.',
  nvidia: 'NVIDIA NIM — good for vision models.',
  groq: 'Fast inference for smaller models.',
  'ollama-cloud': 'Hosted Ollama models (specialists in the default config).',
};
const SPECIALIST_ROLES = [
  { key: 'coding', label: '💻 The Programmer' },
  { key: 'writing', label: '✍️ The Writer' },
  { key: 'reasoning', label: '🧠 The Strategist' },
  { key: 'study', label: '📚 Study' },
];

let wizard = null;
let currentStep = 0;

// ---------------------------------------------------------------- helpers

function goToStep(index) {
  currentStep = Math.max(0, Math.min(index, STEP_ORDER.length - 1));
  STEP_ORDER.forEach((step, i) => {
    document.querySelector(`.step-panel[data-step="${step}"]`).hidden = i !== currentStep;
    const nav = document.querySelector(`.steps li[data-step="${step}"]`);
    nav.classList.toggle('active', i === currentStep);
    nav.classList.toggle('done', i < currentStep);
  });
  document.getElementById('prev-step').disabled = currentStep === 0;
  document.getElementById('next-step').disabled = currentStep === STEP_ORDER.length - 1;
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

document.getElementById('prev-step').addEventListener('click', () => goToStep(currentStep - 1));
document.getElementById('next-step').addEventListener('click', () => goToStep(currentStep + 1));

async function runJob(path, body, logElement, button) {
  button.disabled = true;
  logElement.hidden = false;
  logElement.textContent = '';
  const started = await api(path, { method: 'POST', body: JSON.stringify(body || {}) });
  if (!started.job) throw new Error(started.error || 'Could not start the job.');

  let error = null;
  let result = null;
  for (;;) {
    await new Promise((resolve) => setTimeout(resolve, 900));
    const job = await api(`/api/jobs/${started.job}`);
    logElement.textContent = (job.log || []).join('\n');
    logElement.scrollTop = logElement.scrollHeight;
    if (job.status === 'done') { result = job.result; break; }
    if (job.status === 'error') { error = job.error; break; }
  }
  button.disabled = false;
  if (error) throw new Error(error);
  return result;
}

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

// ---------------------------------------------------------------- load state

async function loadWizard() {
  wizard = await api('/api/wizard/status');
  const config = wizard.config || {};

  document.getElementById('env-python').textContent = wizard.python;
  const missing = wizard.missing_imports || [];
  document.getElementById('env-missing').textContent = missing.length
    ? `Missing packages: ${missing.join(', ')}`
    : 'All required packages are installed.';
  document.getElementById('whichllm-command').textContent = wizard.whichllm_command
    ? `available: ${wizard.whichllm_command}`
    : 'whichllm not found yet';

  document.getElementById('local-model').value = config.local || '';
  document.getElementById('w-gemini').value = config.gemini || '';
  document.getElementById('w-openrouter').value = (config.openrouter || []).join('\n');
  document.getElementById('w-local').value = config.local || '';
  document.getElementById('w-assist').value = config.or_assist || '';

  const vision = config.vision_model || {};
  document.getElementById('w-vision-p-model').value = (vision.primary || {}).model || '';
  document.getElementById('w-vision-p-provider').innerHTML = providerOptions((vision.primary || {}).provider);
  document.getElementById('w-vision-s-model').value = (vision.secondary || {}).model || '';
  document.getElementById('w-vision-s-provider').innerHTML = providerOptions((vision.secondary || {}).provider);
  document.getElementById('w-specialist-grid').innerHTML = SPECIALIST_ROLES
    .map((role) => specialistCard(role, (config.specialist || {})[role.key] || {}))
    .join('');

  const rows = PROVIDER_ORDER.map((name) => {
    const hasKey = (wizard.provider_keys || {})[name];
    const label = (wizard.provider_labels || {})[name] || name;
    return `
      <div class="provider-row">
        <input type="checkbox" id="prov-${name}" ${hasKey ? 'checked' : ''}>
        <label for="prov-${name}" style="margin:0">${escapeHtml(label)}</label>
        <input type="password" data-provider="${name}" placeholder="${hasKey ? 'key already set — paste to replace' : 'paste API key'}" autocomplete="off">
        <div class="provider-meta">${escapeHtml(PROVIDER_NOTES[name] || '')}</div>
      </div>`;
  });
  document.getElementById('provider-list').innerHTML = rows.join('');

  if (wizard.password_set) {
    document.getElementById('finish-btn').textContent = 'Password already set';
    document.getElementById('finish-btn').disabled = true;
  }
}

// ---------------------------------------------------------------- step 1: env

document.getElementById('env-install').addEventListener('click', async () => {
  const log = document.getElementById('env-log');
  try {
    await runJob('/api/wizard/install-requirements', {}, log, document.getElementById('env-install'));
    toast('Dependencies installed.', 'ok');
    await loadWizard();
  } catch (err) {
    toast(`Install failed: ${err.message}`, 'error');
  }
});

// ---------------------------------------------------------------- step 2: local AI

document.getElementById('whichllm-install').addEventListener('click', async () => {
  const log = document.getElementById('whichllm-log');
  try {
    await runJob('/api/wizard/whichllm/install', {}, log, document.getElementById('whichllm-install'));
    toast('whichllm installed.', 'ok');
    await loadWizard();
  } catch (err) {
    toast(`Install failed: ${err.message}`, 'error');
  }
});

document.getElementById('whichllm-run').addEventListener('click', async () => {
  const log = document.getElementById('whichllm-log');
  const table = document.getElementById('whichllm-table');
  const body = table.querySelector('tbody');
  try {
    const result = await runJob('/api/wizard/whichllm/run', { top: 10 }, log, document.getElementById('whichllm-run'));
    const hardware = result.hardware || {};
    const gpu = (hardware.gpus || [])[0] || {};
    document.getElementById('hw-info').textContent = [
      gpu.name ? `GPU: ${gpu.name}` : null,
      gpu.memory_bandwidth_gbps ? `BW ${Math.round(gpu.memory_bandwidth_gbps)} GB/s` : null,
      hardware.ram_bytes ? `RAM ${Math.round(hardware.ram_bytes / 1e9)} GB` : null,
      hardware.cpu ? `CPU: ${hardware.cpu}` : null,
    ].filter(Boolean).join(' · ');

    body.innerHTML = (result.models || []).map((model) => {
      const speed = model.estimated_tok_per_sec ? `${model.estimated_tok_per_sec.toFixed(1)} tok/s` : '—';
      const range = model.speed_range_tok_per_sec ? `(${model.speed_range_tok_per_sec.map((v) => v.toFixed(1)).join('–')})` : '';
      return `<tr data-model="${escapeHtml(model.model_id)}">
        <td>${model.rank}</td>
        <td>${escapeHtml(model.model_id)}</td>
        <td>${escapeHtml(model.quant_type || '')}</td>
        <td>${speed} <span class="muted small">${range}</span></td>
        <td>${escapeHtml(model.fit_type || '')}</td>
        <td>${model.quality_score ? model.quality_score.toFixed(1) : '—'}</td>
        <td>${escapeHtml(model.license || '')}</td>
      </tr>`;
    }).join('');
    table.hidden = false;

    body.querySelectorAll('tr').forEach((row) => {
      row.addEventListener('click', () => {
        body.querySelectorAll('tr').forEach((other) => other.classList.remove('selected'));
        row.classList.add('selected');
        document.getElementById('local-model').value = row.dataset.model;
        document.getElementById('ollama-hint').textContent = `ollama run ${row.dataset.model}`;
      });
    });
    if ((result.models || []).length) {
      body.querySelector('tr').click();
    }
    toast(`whichllm picked ${(result.models || []).length} models.`, 'ok');
  } catch (err) {
    toast(`whichllm failed: ${err.message}`, 'error');
  }
});

document.getElementById('save-local').addEventListener('click', async () => {
  const name = document.getElementById('local-model').value.trim();
  const status = document.getElementById('local-status');
  if (!name) {
    toast('Pick a model or type one in.', 'error');
    return;
  }
  const data = await api('/api/wizard/local', { method: 'POST', body: JSON.stringify({ name }) });
  if (data.ok) {
    status.textContent = `Saved: ${name}`;
    document.getElementById('w-local').value = name;
    document.getElementById('ollama-hint').textContent = `ollama run ${name}`;
    toast('Local model saved to config.json.', 'ok');
  } else {
    toast(data.error || 'Could not save.', 'error');
  }
});

// ---------------------------------------------------------------- step 3: web

document.querySelectorAll('input[name="web-choice"]').forEach((radio) => {
  radio.addEventListener('change', () => {
    const wantsWeb = document.querySelector('input[name="web-choice"]:checked').value === 'yes';
    document.getElementById('web-fields').hidden = !wantsWeb;
  });
});

document.getElementById('save-web').addEventListener('click', async () => {
  const wantsWeb = document.querySelector('input[name="web-choice"]:checked').value === 'yes';
  const status = document.getElementById('web-status');
  if (!wantsWeb) {
    status.textContent = 'Skipped — .WEB will ask for keys when you first use it.';
    return;
  }
  const tavily = document.getElementById('tavily-key').value.trim();
  const firecrawl = document.getElementById('firecrawl-key').value.trim();
  if (!tavily && !firecrawl) {
    toast('Enter at least one key, or choose "No".', 'error');
    return;
  }
  const data = await api('/api/wizard/web-keys', { method: 'POST', body: JSON.stringify({ tavily, firecrawl }) });
  if (data.ok) {
    status.textContent = `Saved: ${data.saved.join(', ')}`;
    toast('Web keys written to .env.', 'ok');
  } else {
    toast(data.error || 'Could not save web keys.', 'error');
  }
});

// ---------------------------------------------------------------- step 4: providers

document.getElementById('save-providers').addEventListener('click', async () => {
  const keys = {};
  document.querySelectorAll('[data-provider]').forEach((field) => {
    const value = field.value.trim();
    const checkbox = document.getElementById(`prov-${field.dataset.provider}`);
    if (value && (!checkbox || checkbox.checked)) keys[field.dataset.provider] = value;
  });
  if (!Object.keys(keys).length) {
    toast('Tick a provider and paste its key first.', 'error');
    return;
  }
  const data = await api('/api/wizard/provider-keys', { method: 'POST', body: JSON.stringify({ keys }) });
  if (data.ok) {
    document.getElementById('providers-status').textContent = `Saved: ${data.saved.join(', ')}`;
    toast('Provider keys written to .env.', 'ok');
    await loadWizard();
  } else {
    toast(data.error || 'Could not save provider keys.', 'error');
  }
});

// ---------------------------------------------------------------- step 5: models

function collectModels() {
  const specialists = {};
  SPECIALIST_ROLES.forEach((role) => {
    const get = (part) => document.querySelector(`[data-spec="${role.key}"][data-part="${part}"]`).value.trim();
    specialists[role.key] = {
      primary: { name: get('primary-name'), role: role.key === 'coding' ? 'coder' : role.key, provider: get('primary-provider') },
      secondary: { name: get('secondary-name'), role: role.key === 'coding' ? 'coder' : role.key, provider: get('secondary-provider') },
    };
  });
  return {
    gemini: document.getElementById('w-gemini').value.trim(),
    openrouter: document.getElementById('w-openrouter').value.split('\n').map((line) => line.trim()).filter(Boolean),
    local: document.getElementById('w-local').value.trim(),
    or_assist: document.getElementById('w-assist').value.trim(),
    vision_model: {
      primary: {
        model: document.getElementById('w-vision-p-model').value.trim(),
        provider: document.getElementById('w-vision-p-provider').value,
      },
      secondary: {
        model: document.getElementById('w-vision-s-model').value.trim(),
        provider: document.getElementById('w-vision-s-provider').value,
      },
    },
    specialist: specialists,
  };
}

document.getElementById('save-models').addEventListener('click', async () => {
  const status = document.getElementById('models-status');
  status.textContent = 'Saving…';
  const data = await api('/api/wizard/config', { method: 'POST', body: JSON.stringify({ config: collectModels() }) });
  status.textContent = '';
  if (data.ok) {
    toast('Models saved to config.json.', 'ok');
    await loadWizard();
  } else {
    toast(data.error || 'Could not save models.', 'error');
  }
});

// ---------------------------------------------------------------- step 6: profile

document.getElementById('save-profile').addEventListener('click', async () => {
  const name = document.getElementById('p-name').value.trim();
  const preference = document.getElementById('p-preference').value.trim();
  const about = document.getElementById('p-about').value.trim();
  if (!name || !preference) {
    toast('Name and behaviour preference are required.', 'error');
    return;
  }
  const status = document.getElementById('profile-status');
  status.textContent = 'Creating (Solaris summarises your answers first)…';
  const data = await api('/api/wizard/profile', {
    method: 'POST',
    body: JSON.stringify({ name, preference, about }),
  });
  status.textContent = '';
  if (data.ok) {
    toast('Profile created.', 'ok');
  } else {
    toast(data.error || 'Could not create profile.', 'error');
  }
});

// ---------------------------------------------------------------- step 7: password

document.getElementById('finish-btn').addEventListener('click', async () => {
  const data = await api('/api/wizard/finish', { method: 'POST', body: '{}' });
  if (!data.ok) {
    toast(data.error || 'Could not generate the password.', 'error');
    return;
  }
  if (data.already_set) {
    toast('A password is already set — rotate it in Settings → Password.', 'ok');
    return;
  }
  const box = document.getElementById('password-result');
  box.hidden = false;
  box.innerHTML = `
    <p><strong>Your 6-character API password</strong></p>
    <div class="password-value">${escapeHtml(data.password)}</div>
    <p class="muted small">Needed for any API key change — including web keys added later from chat. Store it somewhere safe; it is shown only once.</p>
    <button class="btn btn-small" id="copy-password">Copy</button>`;
  document.getElementById('copy-password').addEventListener('click', () => {
    navigator.clipboard.writeText(data.password);
    toast('Copied.', 'ok');
  });
  document.getElementById('finish-btn').disabled = true;
  document.getElementById('finish-btn').textContent = 'Password already set';
});

// ---------------------------------------------------------------- boot

loadWizard().then(() => goToStep(0));
