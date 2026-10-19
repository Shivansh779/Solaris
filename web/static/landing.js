// Landing page: profile gallery, access states and profile security.

let PROFILES = [];
let CURRENT = null;

function profileCard(profile) {
  const isCurrent = profile.user_id === CURRENT;
  const locked = profile.state === 'inactive' || profile.visibility === 'private';
  const card = document.createElement('div');
  card.className = `profile-card ${isCurrent ? 'is-current' : ''} ${locked ? 'is-locked' : ''}`;
  card.innerHTML = `
    <div class="profile-card-head">
      <div style="display:flex; align-items:center; gap:10px">
        <span class="profile-visual" aria-hidden="true">${escapeHtml(profile.name.slice(0, 1).toUpperCase())}</span>
        <strong>${escapeHtml(profile.name)}</strong>
      </div>
      ${profileBadge(profile)}
    </div>
    <div class="muted small">id ${profile.user_id}${isCurrent ? ' · current session' : ''}</div>
    ${profile.locked_for ? `<div class="warn-line">Too many attempts — locked for ${profile.locked_for}s.</div>` : ''}
    <div class="profile-card-actions"></div>`;

  const actions = card.querySelector('.profile-card-actions');
  const add = (label, handler, primary = false) => {
    const button = document.createElement('button');
    button.className = `btn btn-small${primary ? ' btn-primary' : ''}`;
    button.textContent = label;
    button.addEventListener('click', handler);
    actions.appendChild(button);
  };

  if (locked) {
    add(profile.state === 'inactive' ? 'Reactivate' : 'Unlock', () => openProfileAccess(profile, () => window.location.reload()), true);
  } else if (!isCurrent) {
    add('Open', async () => {
      const result = await api('/api/profiles/select', { method: 'POST', body: JSON.stringify({ user_id: profile.user_id }) });
      if (result.ok) {
        toast('Profile opened.', 'ok');
        window.location.reload();
      } else {
        toast(result.error || 'Could not open that profile.', 'error');
      }
    }, true);
  } else {
    add('Open chat', () => { window.location.href = '/chat'; }, true);
  }

  add('Manage', () => openManage(profile));
  return card;
}

function paint() {
  const host = document.getElementById('profile-grid');
  if (!host) return;
  const hideLocked = document.getElementById('only-show-public').checked;
  host.innerHTML = '';
  const visible = PROFILES.filter((profile) => {
    if (!hideLocked) return true;
    return profile.state === 'active' && profile.visibility === 'public';
  });
  if (!visible.length) {
    host.innerHTML = '<p class="muted small">No profiles to show. Create one below.</p>';
    return;
  }
  visible.forEach((profile) => host.appendChild(profileCard(profile)));
}

async function loadProfiles() {
  const data = await api('/api/profiles');
  PROFILES = data.profiles || [];
  CURRENT = data.current;
  paint();
}

function revealCode(code, note) {
  openModal('Activation code', `
    <div class="code-reveal">
      <strong>Store this now</strong>
      <div class="code-value" id="modal-code">${escapeHtml(code)}</div>
      <p class="warn-line">${escapeHtml(note || 'Shown once — only its hash is stored. Without it this profile cannot be reopened after deactivation.')}</p>
      <button class="btn btn-small" id="modal-code-copy">Copy</button>
    </div>`);
  document.getElementById('modal-code-copy').addEventListener('click', () => {
    navigator.clipboard.writeText(code).then(
      () => toast('Activation code copied.', 'ok'),
      () => toast('Copy failed — write it down manually.', 'error'),
    );
  });
}

function openManage(profile) {
  const isPrivate = profile.visibility === 'private';
  openModal(`Manage — ${profile.name}`, `
    <p class="muted small">id ${profile.user_id} · ${profileStateLabel(profile)} profile.
      ${isPrivate ? 'The password opens it; the activation code reopens it after deactivation.' : ''}</p>

    <div class="card" style="margin:0 0 12px">
      <h3>Visibility</h3>
      <p class="muted small">Private profiles ask for a password before anything is shown.</p>
      <div class="row">
        <button class="btn btn-small" id="vis-toggle">${isPrivate ? 'Make public' : 'Make private…'}</button>
        <button class="btn btn-small" id="pw-change">${isPrivate ? 'Change password…' : 'Set password…'}</button>
        ${isPrivate ? '<button class="btn btn-small" id="vis-lock">Lock now</button>' : ''}
      </div>
    </div>

    <div class="card" style="margin:0 0 12px">
      <h3>Activation code</h3>
      <p class="muted small">Needed to reopen this profile after it is deactivated.
        ${profile.has_activation_code ? 'A code is already stored (only as a hash).' : 'No code stored yet.'}</p>
      <div class="row">
        <button class="btn btn-small" id="code-regen">Regenerate code…</button>
      </div>
    </div>

    <div class="card" style="margin:0">
      <h3>Deactivate</h3>
      <p class="muted small">Closes this profile everywhere: chat history, memory, study trails and preferences stay
        stored but become unreachable until the activation code is entered again.</p>
      <div class="row">
        <button class="btn btn-small" id="deactivate">Deactivate profile…</button>
      </div>
    </div>

    <div class="actions"><button class="btn" id="manage-close">Close</button>
      <span class="muted small" id="manage-status"></span></div>`);

  document.getElementById('manage-close').addEventListener('click', closeModal);

  document.getElementById('vis-toggle').addEventListener('click', () => {
    if (isPrivate) {
      api('/api/profiles/visibility', {
        method: 'POST',
        body: JSON.stringify({ user_id: profile.user_id, visibility: 'public' }),
      }).then((result) => {
        if (!result.ok) { toast(result.error || 'Could not change visibility.', 'error'); return; }
        toast('Profile is public now.', 'ok');
        closeModal();
        loadProfiles();
      });
      return;
    }
    openModal('Make this profile private', `
      <p class="muted small">Choose a password. It is required every time this profile is opened in a new browser
        session, and only a PBKDF2 hash is stored.</p>
      <label>Profile password <input id="vis-password" type="password" autocomplete="new-password"></label>
      <label>Repeat password <input id="vis-password-2" type="password" autocomplete="new-password"></label>
      <div class="actions"><button class="btn btn-primary" id="vis-save">Save</button>
        <span class="muted small" id="vis-status"></span></div>`);
    document.getElementById('vis-save').addEventListener('click', async () => {
      const first = document.getElementById('vis-password').value;
      const second = document.getElementById('vis-password-2').value;
      if (first.length < 4) { document.getElementById('vis-status').textContent = 'At least 4 characters.'; return; }
      if (first !== second) { document.getElementById('vis-status').textContent = 'The passwords differ.'; return; }
      const result = await api('/api/profiles/visibility', {
        method: 'POST',
        body: JSON.stringify({ user_id: profile.user_id, visibility: 'private', password: first }),
      });
      if (!result.ok) {
        document.getElementById('vis-status').textContent = result.error || 'Could not save.';
        return;
      }
      toast('Profile is private now.', 'ok');
      closeModal();
      loadProfiles();
    });
  });

  document.getElementById('pw-change').addEventListener('click', () => {
    openModal('Profile password', `
      <p class="muted small">${profile.has_password ? 'Enter the current password, then the new one.' : 'Set the password for this profile.'}</p>
      ${profile.has_password ? '<label>Current password <input id="pw-current" type="password" autocomplete="off"></label>' : ''}
      <label>New password <input id="pw-new" type="password" autocomplete="new-password"></label>
      <div class="actions"><button class="btn btn-primary" id="pw-save">Save</button>
        <span class="muted small" id="pw-status"></span></div>`);
    document.getElementById('pw-save').addEventListener('click', async () => {
      const payload = { user_id: profile.user_id, password: document.getElementById('pw-new').value };
      const current = document.getElementById('pw-current');
      if (current) payload.current = current.value;
      const result = await api('/api/profiles/password/set', { method: 'POST', body: JSON.stringify(payload) });
      if (!result.ok) {
        document.getElementById('pw-status').textContent = result.error || 'Could not save.';
        return;
      }
      toast('Profile password saved.', 'ok');
      closeModal();
      loadProfiles();
    });
  });

  const lock = document.getElementById('vis-lock');
  if (lock) {
    lock.addEventListener('click', async () => {
      await api('/api/profiles/lock', { method: 'POST', body: JSON.stringify({ user_id: profile.user_id }) });
      toast('Locked for this browser session.', 'ok');
      window.location.reload();
    });
  }

  document.getElementById('code-regen').addEventListener('click', () => {
    openModal('Regenerate activation code', `
      <p class="muted small">The previous code stops working immediately. A new one is shown once.</p>
      ${profile.visibility === 'private' ? '<label>Profile password <input id="regen-password" type="password" autocomplete="off"></label>' : ''}
      <div class="actions"><button class="btn btn-primary" id="regen-go">Regenerate</button>
        <span class="muted small" id="regen-status"></span></div>`);
    document.getElementById('regen-go').addEventListener('click', async () => {
      const payload = { user_id: profile.user_id };
      const password = document.getElementById('regen-password');
      if (password) payload.password = password.value;
      const result = await api('/api/profiles/activation-code/regenerate', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      if (!result.ok) {
        document.getElementById('regen-status').textContent = result.error || 'Could not regenerate.';
        return;
      }
      revealCode(result.activation_code, result.warning);
      loadProfiles();
    });
  });

  document.getElementById('deactivate').addEventListener('click', () => {
    openModal('Deactivate profile', `
      <p>Deactivating <strong>${escapeHtml(profile.name)}</strong> hides its chat history, memory and study trails until
        its activation code is entered again. Make sure you have that code.</p>
      <label>Type DEACTIVATE to confirm <input id="deactivate-confirm" type="text" autocomplete="off"></label>
      <div class="actions"><button class="btn" id="deactivate-go">Deactivate</button>
        <span class="muted small" id="deactivate-status"></span></div>`);
    document.getElementById('deactivate-go').addEventListener('click', async () => {
      const result = await api('/api/profiles/deactivate', {
        method: 'POST',
        body: JSON.stringify({
          user_id: profile.user_id,
          confirm: document.getElementById('deactivate-confirm').value.trim(),
        }),
      });
      if (!result.ok) {
        document.getElementById('deactivate-status').textContent = result.error || 'Not deactivated.';
        return;
      }
      toast('Profile deactivated.', 'ok');
      closeModal();
      loadProfiles();
    });
  });
}

document.getElementById('only-show-public').addEventListener('change', paint);

document.getElementById('profile-create').addEventListener('click', async () => {
  const status = document.getElementById('create-status');
  const name = document.getElementById('new-name').value.trim();
  const preference = document.getElementById('new-preference').value.trim();
  const about = document.getElementById('new-about').value.trim();
  if (!name || !preference) {
    status.textContent = 'Name and behaviour preference are required.';
    return;
  }
  status.textContent = 'Creating…';
  const result = await api('/api/profiles', {
    method: 'POST',
    body: JSON.stringify({ name, preference, about }),
  });
  if (!result.ok) {
    status.textContent = result.error || 'Could not create the profile.';
    return;
  }
  status.textContent = 'Profile created.';
  document.getElementById('code-value').textContent = result.activation_code;
  document.getElementById('code-reveal').hidden = false;
  document.getElementById('code-copy').onclick = () => {
    navigator.clipboard.writeText(result.activation_code).then(
      () => toast('Activation code copied.', 'ok'),
      () => toast('Copy failed — write it down manually.', 'error'),
    );
  };
  document.getElementById('new-name').value = '';
  document.getElementById('new-preference').value = '';
  document.getElementById('new-about').value = '';
  toast('Profile created — store its activation code.', 'ok');
  await loadProfiles();
});

loadProfiles();
