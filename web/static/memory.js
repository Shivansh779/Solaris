// Memory page: the profile's constellation of memory nodes.

let categories = [];
let nodes = { active: [], suggested: [], archived: [] };

function nodeMeta(node) {
  const parts = [`source: ${node.source}`];
  if (node.confidence != null) parts.push(`confidence ${Math.round(node.confidence * 100)}%`);
  parts.push(`updated ${node.updated_at}`);
  return parts.join(' · ');
}

function renderNode(node, options = {}) {
  const item = document.createElement('li');
  item.className = `memory-node ${options.className || ''}`;
  item.innerHTML = `
    <span class="memory-orbit" aria-hidden="true"></span>
    <div>
      <h3>${escapeHtml(node.title)}</h3>
      ${node.detail ? `<p>${escapeHtml(node.detail)}</p>` : ''}
      <div class="memory-node-meta">${escapeHtml(nodeMeta(node))}</div>
    </div>
    <div class="memory-node-actions"></div>`;

  const actions = item.querySelector('.memory-node-actions');
  (options.actions || []).forEach((action) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = action.label;
    button.addEventListener('click', () => action.run(node));
    actions.appendChild(button);
  });
  return item;
}

function paint() {
  // Suggested
  const suggested = nodes.suggested || [];
  document.getElementById('suggested-card').hidden = suggested.length === 0;
  document.getElementById('suggested-count').textContent = String(suggested.length);
  const suggestedList = document.getElementById('suggested-list');
  suggestedList.innerHTML = '';
  suggested.forEach((node) => {
    suggestedList.appendChild(renderNode(node, {
      className: 'is-suggested',
      actions: [
        { label: 'Approve', run: (item) => setStatus(item, 'active', 'Memory approved.') },
        { label: 'Edit', run: (item) => openEditor(item) },
        { label: 'Forget', run: (item) => forget(item) },
      ],
    }));
  });

  // Active, grouped by category
  const groups = document.getElementById('memory-groups');
  groups.innerHTML = '';
  categories.forEach((category) => {
    const members = nodes.active.filter((node) => node.category === category.key);
    if (!members.length) return;
    const section = document.createElement('section');
    section.className = 'memory-group';
    section.innerHTML = `<div class="memory-group-head">
        <h2>${escapeHtml(category.label)}</h2>
        <span class="hint">${members.length} ${members.length === 1 ? 'node' : 'nodes'}</span>
      </div>
      <ul class="memory-list"></ul>`;
    const list = section.querySelector('.memory-list');
    members.forEach((node) => {
      list.appendChild(renderNode(node, {
        actions: [
          { label: 'Edit', run: (item) => openEditor(item) },
          { label: 'Archive', run: (item) => setStatus(item, 'archived', 'Memory archived.') },
          { label: 'Forget', run: (item) => forget(item) },
        ],
      }));
    });
    groups.appendChild(section);
  });

  if (!nodes.active.length && !suggested.length) {
    const empty = document.createElement('section');
    empty.className = 'memory-group';
    empty.innerHTML = `<h2>No memory yet</h2>
      <p class="muted small">Add a preference, a project, or something you are learning. Solaris uses at most
      ${8} relevant nodes per answer and tells you when it did.</p>`;
    groups.appendChild(empty);
  }

  // Archived
  const archived = nodes.archived || [];
  document.getElementById('archived-card').hidden = archived.length === 0;
  document.getElementById('archived-count').textContent = String(archived.length);
  const archivedList = document.getElementById('archived-list');
  archivedList.innerHTML = '';
  archived.forEach((node) => {
    archivedList.appendChild(renderNode(node, {
      className: 'is-archived',
      actions: [
        { label: 'Restore', run: (item) => setStatus(item, 'active', 'Memory restored.') },
        { label: 'Forget', run: (item) => forget(item) },
      ],
    }));
  });
}

async function load() {
  const data = await api('/api/memory');
  if (!data.ok) {
    toast(data.error || 'Memory is unavailable for this profile.', 'error');
    return;
  }
  categories = data.categories || [];
  nodes = { active: data.active, suggested: data.suggested, archived: data.archived };
  paint();
}

async function setStatus(node, status, message) {
  const result = await api(`/api/memory/${node.id}/status`, {
    method: 'POST',
    body: JSON.stringify({ status }),
  });
  if (!result.ok) {
    toast(result.error || 'Could not update that node.', 'error');
    return;
  }
  toast(message, 'ok');
  load();
}

async function forget(node) {
  const confirmed = window.confirm(`Forget “${node.title}” permanently? This cannot be undone.`);
  if (!confirmed) return;
  const result = await api(`/api/memory/${node.id}`, { method: 'DELETE' });
  if (!result.ok) {
    toast(result.error || 'Could not forget that node.', 'error');
    return;
  }
  toast('Forgotten.', 'ok');
  load();
}

function openEditor(node) {
  const editing = Boolean(node);
  openModal(editing ? 'Edit memory' : 'Add memory', `
    <label>Category
      <select id="mem-category">
        ${categories.map((category) => `<option value="${category.key}"
          ${editing && node.category === category.key ? 'selected' : ''}>${escapeHtml(category.label)}</option>`).join('')}
      </select>
    </label>
    <label>Memory <input id="mem-title" type="text" maxlength="200"
      value="${editing ? escapeHtml(node.title) : ''}" placeholder="Prefers concise answers"></label>
    <label>Supporting detail (optional) <textarea id="mem-detail" rows="2"
      placeholder="Anything that makes this precise">${editing ? escapeHtml(node.detail || '') : ''}</textarea></label>
    <div class="actions">
      <button class="btn btn-primary" id="mem-save">${editing ? 'Save changes' : 'Add memory'}</button>
      <span class="muted small" id="mem-status"></span>
    </div>`);

  document.getElementById('mem-save').addEventListener('click', async () => {
    const payload = {
      category: document.getElementById('mem-category').value,
      title: document.getElementById('mem-title').value.trim(),
      detail: document.getElementById('mem-detail').value.trim(),
    };
    let result;
    if (editing) {
      result = await api(`/api/memory/${node.id}`, { method: 'POST', body: JSON.stringify(payload) });
    } else {
      result = await api('/api/memory', { method: 'POST', body: JSON.stringify(payload) });
    }
    if (!result.ok) {
      document.getElementById('mem-status').textContent = result.error || 'Could not save.';
      return;
    }
    closeModal();
    toast(editing ? 'Memory updated.' : 'Memory added.', 'ok');
    load();
  });
}

document.getElementById('memory-add').addEventListener('click', () => openEditor(null));

document.getElementById('memory-clear').addEventListener('click', () => {
  openModal('Clear all profile memories', `
    <p>This permanently deletes <strong>every</strong> memory node for this profile — active, suggested and archived.
      Chat history and study trails are not touched.</p>
    <label>Type FORGET to confirm <input id="clear-confirm" type="text" autocomplete="off"></label>
    <div class="actions">
      <button class="btn" id="clear-go">Clear all memories</button>
      <span class="muted small" id="clear-status"></span>
    </div>`);
  document.getElementById('clear-go').addEventListener('click', async () => {
    const value = document.getElementById('clear-confirm').value.trim();
    const result = await api('/api/memory/clear', { method: 'POST', body: JSON.stringify({ confirm: value }) });
    if (!result.ok) {
      document.getElementById('clear-status').textContent = result.error || 'Not cleared.';
      return;
    }
    closeModal();
    toast(`Cleared ${result.removed} ${result.removed === 1 ? 'node' : 'nodes'}.`, 'ok');
    load();
  });
});

load();
