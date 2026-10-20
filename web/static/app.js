// Shared helpers for every Solaris page.

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  let data = {};
  try {
    data = await response.json();
  } catch (err) {
    data = { ok: false, error: `Server returned ${response.status}` };
  }
  if (!response.ok && !data.error) {
    data.error = `Request failed (${response.status})`;
  }
  data._status = response.status;
  return data;
}

async function apiForm(path, formData) {
  const response = await fetch(path, { method: 'POST', body: formData });
  let data = {};
  try {
    data = await response.json();
  } catch (err) {
    data = { ok: false, error: `Server returned ${response.status}` };
  }
  data._status = response.status;
  return data;
}

let toastTimer = null;
function toast(message, kind = '') {
  const box = document.getElementById('toast');
  if (!box) return;
  box.textContent = message;
  box.className = `toast ${kind}`;
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, 3600);
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text == null ? '' : String(text);
  // Quotes too: the result is also used inside HTML attributes.
  return div.innerHTML.replace(/"/g, '&quot;');
}

function openModal(title, bodyHtml) {
  const modal = document.getElementById('modal');
  if (!modal) return;
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = bodyHtml;
  modal.hidden = false;
}

function closeModal() {
  const modal = document.getElementById('modal');
  if (modal) modal.hidden = true;
}

const PROVIDER_LABELS = {
  gemini: 'Google Gemini',
  openrouter: 'OpenRouter',
  'openrouter-assist': 'OpenRouter (Assistant)',
  nvidia: 'NVIDIA NIM',
  groq: 'Groq',
  'ollama-cloud': 'Ollama Cloud',
  google: 'Google Gemini',
};

function providerLabel(name) {
  return PROVIDER_LABELS[name] || name;
}

function providerOptions(selected) {
  const names = ['gemini', 'openrouter', 'ollama-cloud', 'nvidia', 'groq'];
  return names.map((name) => {
    const isSelected = selected === name || (selected === 'google' && name === 'gemini') ? ' selected' : '';
    return `<option value="${name}"${isSelected}>${providerLabel(name)}</option>`;
  }).join('');
}

// ---------------------------------------------------------------- profile access
// Shared by the landing page and the chat page. The server decides what is
// allowed; these helpers only walk the user through the two credentials:
// an activation code (inactive profile) and a profile password (private one).

function profileStateLabel(profile) {
  if (profile.state === 'inactive') return 'inactive';
  return profile.visibility === 'private' ? 'private' : 'public';
}

function profileBadge(profile) {
  if (profile.state === 'inactive') return '<span class="badge">inactive</span>';
  if (profile.visibility === 'private') return '<span class="badge badge-private">private</span>';
  return '<span class="badge badge-local">public</span>';
}

function openProfileAccess(profile, onSuccess) {
  const needsActivation = profile.state === 'inactive';

  const body = `
    <p class="muted small">${escapeHtml(profile.name)} · ${profileStateLabel(profile)} profile</p>
    <label>${needsActivation ? 'Activation code' : 'Profile password'}
      <input id="profile-secret" type="${needsActivation ? 'text' : 'password'}" autocomplete="off"
             placeholder="${needsActivation ? 'ABCD-EFGH' : ''}">
    </label>
    <div class="actions">
      <button class="btn btn-primary" id="profile-go">${needsActivation ? 'Reactivate' : 'Unlock'}</button>
      <span class="muted small" id="profile-status"></span>
    </div>
    <p class="muted small">${needsActivation
      ? 'Inactive profiles stay closed until this code is entered. Store it somewhere safe.'
      : 'The unlock lasts for this browser session only.'}</p>`;
  openModal(needsActivation ? 'Reactivate profile' : 'Unlock profile', body);

  const status = document.getElementById('profile-status');
  const secret = document.getElementById('profile-secret');
  secret.focus();

  document.getElementById('profile-go').addEventListener('click', async () => {
    const value = secret.value.trim();
    if (!value) {
      status.textContent = 'Enter the value first.';
      return;
    }
    status.textContent = 'Checking…';
    const path = needsActivation ? '/api/profiles/activate' : '/api/profiles/unlock';
    const payload = needsActivation ? { user_id: profile.user_id, code: value } : { user_id: profile.user_id, password: value };
    const result = await api(path, { method: 'POST', body: JSON.stringify(payload) });

    if (!result.ok) {
      status.textContent = result.error || 'That did not work.';
      secret.select();
      return;
    }
    if (needsActivation && result.needs_password) {
      // Activated; now the private password is still required.
      closeModal();
      openProfileAccess({ ...profile, state: 'active', visibility: 'private' }, onSuccess);
      return;
    }
    closeModal();
    toast(needsActivation ? 'Profile reactivated.' : 'Profile unlocked.', 'ok');
    if (onSuccess) onSuccess();
  });

  secret.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') document.getElementById('profile-go').click();
  });
}

function openProfilePicker(profiles, currentId, onSwitched) {
  const rows = profiles.map((profile) => {
    const current = profile.user_id === currentId;
    const locked = profile.state === 'inactive' || profile.visibility === 'private';
    const action = profile.state === 'inactive' ? 'Reactivate' : locked ? 'Unlock' : 'Open';
    return `
      <div class="profile-card ${current ? 'is-current' : ''} ${locked ? 'is-locked' : ''}">
        <div class="profile-card-head">
          <strong>${escapeHtml(profile.name)}</strong>
          ${profileBadge(profile)}
        </div>
        <div class="muted small">id ${profile.user_id}${current ? ' · current' : ''}</div>
        ${profile.locked_for ? `<div class="warn-line">Locked — try again in ${profile.locked_for}s.</div>` : ''}
        <div class="profile-card-actions">
          <button class="btn btn-small ${locked ? '' : 'btn-primary'}" data-open="${profile.user_id}">${action}</button>
        </div>
      </div>`;
  }).join('');

  openModal('Profiles', `<div class="profile-grid">${rows}</div>
    <p class="muted small">Public profiles open directly. Private profiles need their password; inactive profiles need
    their activation code first. “Public” means visible inside this local app only.</p>`);

  document.querySelectorAll('[data-open]').forEach((button) => {
    button.addEventListener('click', async () => {
      const id = Number(button.dataset.open);
      const profile = profiles.find((item) => item.user_id === id);
      const result = await api('/api/profiles/select', { method: 'POST', body: JSON.stringify({ user_id: id }) });
      if (result.ok) {
        closeModal();
        toast('Profile opened.', 'ok');
        if (onSwitched) onSwitched();
        return;
      }
      if (result.needs === 'activation' || result.needs === 'password') {
        closeModal();
        openProfileAccess(profile, onSwitched);
        return;
      }
      toast(result.error || 'Could not open that profile.', 'error');
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const close = document.getElementById('modal-close');
  if (close) close.addEventListener('click', closeModal);
  const modal = document.getElementById('modal');
  if (modal) {
    modal.addEventListener('click', (event) => { if (event.target === modal) closeModal(); });
  }
});
