// Living Workspace shelf, privacy pulse and the refinement dial.
// Shared by the chat page; reads every value from server payloads.

const PULSE_LABELS = {
  local: 'Local',
  cloud: 'Cloud',
  hybrid: 'Hybrid',
  unknown: 'Unknown',
};

const ICONS = {
  shorter: '<path d="M4 8h16M4 16h9"/>',
  deeper: '<path d="M12 4v16M6 10l6-6 6 6"/>',
  challenge: '<path d="M12 3l8 5v8l-8 5-8-5V8z"/><path d="M12 9v4M12 16h.01"/>',
  plan: '<path d="M8 6h12M8 12h12M8 18h12M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
  notes: '<path d="M6 3h9l4 4v14H6z"/><path d="M9 11h7M9 15h7"/>',
  beginner: '<circle cx="12" cy="9" r="5"/><path d="M12 14v7M8 21h8"/>',
  examples: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M4 10h16"/>',
  regenerate: '<path d="M20 11a8 8 0 00-14.3-4.6M4 13a8 8 0 0014.3 4.6"/><path d="M4 4v6h6M20 20v-6h-6"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V5a2 2 0 012-2h10"/>',
};

function pulseIcon(name) {
  return ICONS[name] || ICONS.notes;
}

function fileGlyph(type) {
  if (type === 'pdf') return 'PDF';
  if (type === 'markdown') return 'MD';
  if (type === 'jpeg' || type === 'png') return 'IMG';
  return (type || 'FILE').slice(0, 3).toUpperCase();
}

// ---------------------------------------------------------------- privacy pulse

function renderPulse(payload) {
  const pulse = payload.pulse;
  if (!pulse) return null;

  const box = document.createElement('div');
  box.className = 'pulse';

  const classification = pulse.classification || 'unknown';
  const pill = document.createElement('button');
  pill.type = 'button';
  pill.className = `pulse-pill pulse-${escapeHtml(classification)}`;
  pill.setAttribute('aria-expanded', 'false');
  const where = pulse.provider ? `${providerLabel(pulse.provider)}${pulse.model ? ` · ${pulse.model}` : ''}` : '';
  pill.innerHTML = `<span class="pulse-dot" aria-hidden="true"></span>
    <span>${escapeHtml(PULSE_LABELS[classification] || 'Unknown')}</span>
    <span class="muted">${escapeHtml(where)}</span>`;

  const trace = document.createElement('div');
  trace.className = 'pulse-trace';
  trace.hidden = true;
  trace.innerHTML = buildTrace(pulse);

  pill.addEventListener('click', () => {
    trace.hidden = !trace.hidden;
    pill.setAttribute('aria-expanded', String(!trace.hidden));
  });

  box.appendChild(pill);

  if (pulse.memories > 0) {
    const details = document.createElement('details');
    details.className = 'memory-uses';
    details.innerHTML = `<summary>Used ${pulse.memories} workspace ${pulse.memories === 1 ? 'memory' : 'memories'}</summary>
      <ul>${(pulse.memory_items || []).map((item) =>
        `<li>${escapeHtml(item.title)} <span class="muted">· ${escapeHtml(item.category)}</span></li>`).join('')}</ul>`;
    box.appendChild(details);
  }

  box.appendChild(trace);
  return box;
}

function buildTrace(pulse) {
  const rows = [
    ['Route', escapeHtml(pulse.classification || 'unknown')],
    ['Provider', escapeHtml(pulse.provider ? providerLabel(pulse.provider) : 'not recorded')],
    ['Model', escapeHtml(pulse.model || 'not recorded')],
    ['Web search', pulse.web_search ? 'yes' : 'no'],
    ['Files', pulse.files_total ? `${pulse.files_selected} of ${pulse.files_total} selected` : 'none'],
    ['Skills', (pulse.skills || []).length ? pulse.skills.map(escapeHtml).join(', ') : 'none'],
    ['Workspace memory', String(pulse.memories || 0)],
  ];
  if (pulse.latency_ms != null && pulse.latency_ms > 0) {
    rows.push(['Latency', `${(pulse.latency_ms / 1000).toFixed(1)}s`]);
  }
  const reasons = (pulse.fallbacks || []).filter(Boolean);
  const steps = (pulse.steps || []).filter((step) => step.provider);
  return `
    <dl>${rows.map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join('')}</dl>
    ${steps.length ? `<ul>${steps.map((step) =>
      `<li>${escapeHtml(providerLabel(step.provider))}${step.model ? ` · ${escapeHtml(step.model)}` : ''} — ${step.ok ? 'answered' : `failed${step.reason ? `: ${escapeHtml(step.reason)}` : ''}`}</li>`).join('')}</ul>` : ''}
    ${reasons.length ? `<p class="muted small">${reasons.map(escapeHtml).join(' ')}</p>` : ''}`;
}

// ---------------------------------------------------------------- refinement dial

function attachAnswerSurface(wrapper, payload, question) {
  if (payload.type !== 'reply' || !payload.raw) return;
  const pulse = renderPulse(payload);
  if (pulse) wrapper.appendChild(pulse);
  const manifest = renderManifest(payload, question, wrapper);
  if (manifest) wrapper.appendChild(manifest);
  wrapper.appendChild(buildDial(payload, question));
}

// ---------------------------------------------------------------- context manifest

// One quiet row per source that went into the answer. Server text is only ever
// set as text — never as HTML.
function renderManifest(payload, question, wrapper) {
  const items = Array.isArray(payload.context) ? payload.context : [];
  if (!items.length) return null;

  const details = document.createElement('details');
  details.className = 'context-manifest';

  const summary = document.createElement('summary');
  summary.textContent = `What went into this answer · ${items.length} source${items.length === 1 ? '' : 's'}`;
  details.appendChild(summary);

  const list = document.createElement('div');
  list.className = 'manifest-list';

  items.forEach((item) => {
    const row = document.createElement('div');
    row.className = 'manifest-item';

    const kind = document.createElement('span');
    kind.className = 'manifest-kind';
    kind.textContent = item.kind;

    const label = document.createElement('span');
    label.className = 'manifest-label';
    label.textContent = item.label || item.id;
    if (item.detail) label.title = item.detail;

    const size = document.createElement('span');
    size.className = 'manifest-size muted small';
    size.textContent = `${item.size || 0} chars`;

    const drop = document.createElement('button');
    drop.type = 'button';
    drop.className = 'manifest-drop';
    drop.textContent = 'without this';
    drop.addEventListener('click', () => reaskWithout(drop, item.id, question, payload, wrapper));

    row.append(kind, label, size, drop);
    list.appendChild(row);
  });

  details.appendChild(list);
  return details;
}

// Re-ask the same question without one source; the new reply lands right below
// the current one.
async function reaskWithout(button, id, question, payload, wrapper) {
  button.disabled = true;
  const working = document.createElement('span');
  working.className = 'manifest-working muted small';
  working.textContent = 'asking again…';
  button.parentNode.appendChild(working);
  try {
    const result = await api('/api/context/reask', {
      method: 'POST',
      body: JSON.stringify({
        question: question || '',
        answer: payload.raw || '',
        exclude: [id],
      }),
    });
    if (result.type === 'reply') {
      const fresh = renderReply(result, true, question);
      if (fresh && wrapper) wrapper.after(fresh);
      toast('Answered again without that source.', 'ok');
    } else {
      toast(result.message || result.error || 'The re-ask failed.', 'error');
    }
  } catch (err) {
    toast(`The re-ask failed: ${err.message}`, 'error');
  } finally {
    working.remove();
    button.disabled = false;
  }
}

function buildDial(payload, question) {
  const dial = document.createElement('div');
  dial.className = 'dial';
  dial.setAttribute('role', 'group');
  dial.setAttribute('aria-label', 'Refine this answer');

  const label = document.createElement('span');
  label.className = 'dial-label';
  label.textContent = 'Refine';
  dial.appendChild(label);

  (window.ANSWER_CONTROLS || []).forEach((control) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'dial-btn';
    button.title = control.hint || control.label;
    button.dataset.action = control.key;
    button.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${pulseIcon(control.key)}</svg>
      <span>${escapeHtml(control.label)}</span>`;
    button.addEventListener('click', () => runFollowUp(button, dial, control, payload, question));
    dial.appendChild(button);
  });

  // Keeping actions: these write to the workspace, not to the model.
  dial.appendChild(saveTrailButton(payload, question));
  dial.appendChild(saveCheckpointButton(payload));
  dial.appendChild(saveSkillButton(payload, question));
  dial.appendChild(copyButton(payload));
  return dial;
}

function copyButton(payload) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'dial-btn';
  button.title = 'Copy this answer';
  button.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS.copy}</svg><span>Copy</span>`;
  button.addEventListener('click', () => {
    navigator.clipboard.writeText(payload.raw || '').then(
      () => toast('Answer copied.', 'ok'),
      () => toast('Copy failed — select the text instead.', 'error'),
    );
  });
  return button;
}

function plainDialButton(label, onClick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'dial-btn';
  button.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
    <span>${escapeHtml(label)}</span>`;
  button.addEventListener('click', () => onClick(button));
  return button;
}

function saveTrailButton(payload, question) {
  return plainDialButton('Save to study trail', async () => {
    const data = await api('/api/study/trails');
    if (!data.ok) {
      toast(data.error || 'No profile is open.', 'error');
      return;
    }
    const trails = data.trails || [];
    openModal('Save to a study trail', `
      <p class="muted small">The answer is stored with the trail as notes. Nothing is sent to a model.</p>
      ${trails.length ? `<label>Existing trail
        <select id="trail-pick"><option value="">— new trail —</option>
        ${trails.map((trail) => `<option value="${trail.id}">${escapeHtml(trail.title)}</option>`).join('')}
        </select></label>` : ''}
      <label>New trail topic <input id="trail-title" type="text" placeholder="${escapeHtml(question || 'Topic')}"></label>
      <div class="actions"><button class="btn btn-primary" id="trail-save">Save</button>
        <span class="muted small" id="trail-status"></span></div>`);

    document.getElementById('trail-save').addEventListener('click', async () => {
      const status = document.getElementById('trail-status');
      const pick = document.getElementById('trail-pick');
      const title = document.getElementById('trail-title').value.trim();
      const note = payload.raw || '';
      const summary = (question || title || 'Saved answer').slice(0, 80);

      if (pick && pick.value) {
        const result = await api(`/api/study/trails/${pick.value}/notes`, {
          method: 'POST',
          body: JSON.stringify({ title: summary, content: note }),
        });
        if (!result.ok) { status.textContent = result.error || 'Could not save.'; return; }
      } else {
        if (!title) { status.textContent = 'Name the topic first.'; return; }
        const result = await api('/api/study/from-answer', {
          method: 'POST',
          body: JSON.stringify({ title, content: note }),
        });
        if (!result.ok) { status.textContent = result.error || 'Could not save.'; return; }
      }
      closeModal();
      toast('Saved to your study trail.', 'ok');
      Shelf.refresh();
    });
  });
}

function saveCheckpointButton(payload) {
  return plainDialButton('Save as checkpoint', async () => {
    const data = await api('/api/workspace');
    const checkpoint = (data.checkpoint) || {};
    const gist = (payload.raw || '').split('\n').filter(Boolean).slice(0, 3).join(' ').slice(0, 400);
    openModal('Save a session checkpoint', `
      <p class="muted small">Only this form writes a checkpoint — your own wording is never overwritten silently.</p>
      <label>Goal <input id="cp2-goal" type="text" value="${escapeHtml(checkpoint.goal || (data.task && data.task.task) || '')}"></label>
      <label>Decisions made <textarea id="cp2-decisions" rows="3">${escapeHtml(checkpoint.decisions || '')}</textarea></label>
      <label>Open questions <textarea id="cp2-questions" rows="2">${escapeHtml(checkpoint.questions || '')}</textarea></label>
      <label>Suggested next step <textarea id="cp2-next" rows="2">${escapeHtml(checkpoint.next_step || gist)}</textarea></label>
      <div class="actions"><button class="btn btn-primary" id="cp2-save">Save checkpoint</button>
        <span class="muted small" id="cp2-status"></span></div>`);

    document.getElementById('cp2-save').addEventListener('click', async () => {
      const result = await api('/api/workspace/checkpoint', {
        method: 'POST',
        body: JSON.stringify({
          goal: document.getElementById('cp2-goal').value,
          decisions: document.getElementById('cp2-decisions').value,
          questions: document.getElementById('cp2-questions').value,
          next_step: document.getElementById('cp2-next').value,
        }),
      });
      if (!result.ok) {
        document.getElementById('cp2-status').textContent = result.error || 'Could not save.';
        return;
      }
      closeModal();
      toast('Checkpoint saved.', 'ok');
      Shelf.refresh();
    });
  });
}

// Turn this thread into a Markdown skill: the model drafts it, the user edits
// the draft, the server writes the file the skill loader picks up.
function saveSkillButton(payload, question) {
  return plainDialButton('Save as skill', async () => {
    const result = await api('/api/skills/draft', { method: 'POST', body: '{}' });
    const draft = result.draft || {};
    openModal('Save this thread as a skill', `
      <p class="muted small">The draft comes from this conversation. Edit it before it is written.</p>
      <label>Title <input id="skill-title" type="text" value="${escapeHtml(draft.title || question || 'New skill')}"></label>
      <label>Description <input id="skill-desc" type="text" value="${escapeHtml(draft.description || '')}"></label>
      <label>Default prompt <input id="skill-prompt" type="text" value="${escapeHtml(draft.default_prompt || '')}"></label>
      <label>Instructions <textarea id="skill-body" rows="8">${escapeHtml(draft.body || payload.raw || '')}</textarea></label>
      <label>Scope <select id="skill-scope">
        <option value="project">Project — shared with this repo</option>
        <option value="user">Personal — only this machine</option></select></label>
      <div class="actions"><button class="btn btn-primary" id="skill-save">Save skill</button>
        <span class="muted small" id="skill-status"></span></div>`);

    document.getElementById('skill-save').addEventListener('click', async () => {
      const saved = await api('/api/skills/save', {
        method: 'POST',
        body: JSON.stringify({
          title: document.getElementById('skill-title').value,
          description: document.getElementById('skill-desc').value,
          default_prompt: document.getElementById('skill-prompt').value,
          body: document.getElementById('skill-body').value,
          scope: document.getElementById('skill-scope').value,
        }),
      });
      if (!saved.ok) {
        document.getElementById('skill-status').textContent = saved.error || 'Could not save.';
        return;
      }
      closeModal();
      toast(saved.skill ? `Skill saved: ${saved.skill.name}` : 'Skill saved.', 'ok');
      Shelf.refresh();
    });
  });
}

async function runFollowUp(button, dial, control, payload, question) {
  const buttons = dial.querySelectorAll('.dial-btn');
  buttons.forEach((item) => { item.disabled = true; });
  const status = document.createElement('span');
  status.className = 'dial-working';
  status.setAttribute('role', 'status');
  status.textContent = `${control.label}…`;
  dial.appendChild(status);

  try {
    const result = await api('/api/answer-control', {
      method: 'POST',
      body: JSON.stringify({ action: control.key, question: question || '', answer: payload.raw }),
    });
    status.remove();
    if (result.type === 'reply') {
      renderReply(result, true, question);
    } else {
      const error = document.createElement('span');
      error.className = 'dial-error';
      error.textContent = result.message || result.error || 'The refinement failed.';
      dial.appendChild(error);
    }
  } catch (err) {
    status.remove();
    const error = document.createElement('span');
    error.className = 'dial-error';
    error.textContent = `The refinement failed: ${err.message}`;
    dial.appendChild(error);
  } finally {
    buttons.forEach((item) => { item.disabled = false; });
  }
}

// ---------------------------------------------------------------- workspace shelf

const Shelf = {
  open: true,
  state: null,

  key: 'solaris.shelfOpen',

  init() {
    const wrapper = document.getElementById('workspace-layout');
    if (!wrapper) return;
    const stored = window.localStorage.getItem(this.key);
    this.open = stored === null ? true : stored === '1';
    this.apply();

    const toggle = document.getElementById('shelf-toggle');
    const close = document.getElementById('shelf-close');
    const backdrop = document.getElementById('shelf-backdrop');
    if (toggle) toggle.addEventListener('click', () => this.set(!this.open));
    if (close) close.addEventListener('click', () => this.set(false));
    if (backdrop) backdrop.addEventListener('click', () => this.set(false));

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') this.set(false, false);
    });

    this.wireTask();
    this.wireCheckpoint();
    this.wireFiles();
    this.refresh();
  },

  set(open, remember = true) {
    this.open = open;
    if (remember) window.localStorage.setItem(this.key, open ? '1' : '0');
    this.apply();
  },

  apply() {
    const wrapper = document.getElementById('workspace-layout');
    const shelf = document.getElementById('shelf');
    const toggle = document.getElementById('shelf-toggle');
    if (!wrapper || !shelf) return;
    wrapper.classList.toggle('has-shelf', this.open);
    shelf.hidden = !this.open;
    document.body.classList.toggle('shelf-open', this.open && window.innerWidth <= 1000);
    if (toggle) toggle.setAttribute('aria-expanded', String(this.open));
  },

  wireTask() {
    const form = document.getElementById('task-form');
    const view = document.getElementById('task-view');
    const input = document.getElementById('task-input');
    const edit = document.getElementById('task-edit');
    const cancel = document.getElementById('task-cancel');
    if (!form || !edit) return;

    edit.addEventListener('click', () => {
      input.value = (this.state && this.state.task.task) || '';
      view.hidden = true;
      form.hidden = false;
      input.focus();
    });
    cancel.addEventListener('click', () => {
      form.hidden = true;
      view.hidden = false;
    });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const result = await api('/api/workspace/task', {
        method: 'POST',
        body: JSON.stringify({ task: input.value }),
      });
      if (!result.ok) {
        toast(result.error || 'Could not save the task.', 'error');
        return;
      }
      form.hidden = true;
      view.hidden = false;
      toast('Task saved.', 'ok');
      this.refresh();
    });
  },

  wireCheckpoint() {
    const form = document.getElementById('checkpoint-form');
    const view = document.getElementById('checkpoint-view');
    const edit = document.getElementById('checkpoint-edit');
    const cancel = document.getElementById('checkpoint-cancel');
    if (!form || !edit) return;

    const fields = ['goal', 'decisions', 'questions', 'next_step'];
    edit.addEventListener('click', () => {
      const checkpoint = (this.state && this.state.checkpoint) || {};
      fields.forEach((name) => {
        const el = document.getElementById(name === 'next_step' ? 'cp-next' : `cp-${name}`);
        if (el) el.value = checkpoint[name] || '';
      });
      view.hidden = true;
      form.hidden = false;
    });
    cancel.addEventListener('click', () => {
      form.hidden = true;
      view.hidden = false;
    });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const result = await api('/api/workspace/checkpoint', {
        method: 'POST',
        body: JSON.stringify({
          goal: document.getElementById('cp-goal').value,
          decisions: document.getElementById('cp-decisions').value,
          questions: document.getElementById('cp-questions').value,
          next_step: document.getElementById('cp-next').value,
        }),
      });
      if (!result.ok) {
        toast(result.error || 'Could not save the checkpoint.', 'error');
        return;
      }
      form.hidden = true;
      view.hidden = false;
      toast('Checkpoint saved.', 'ok');
      this.refresh();
    });
  },

  wireFiles() {
    const all = document.getElementById('files-select-all');
    const none = document.getElementById('files-select-none');
    if (all) all.addEventListener('click', () => this.setAll(true));
    if (none) none.addEventListener('click', () => this.setAll(false));
  },

  async setSelected(index, selected) {
    const data = await api('/api/attachments/select', {
      method: 'POST',
      body: JSON.stringify({ index, selected }),
    });
    if (!data.attachments) {
      toast(data.message || data.error || 'Could not update the file.', 'error');
      return;
    }
    refreshAttachments(data.attachments);
  },

  async setAll(selected) {
    const items = (this.state && this.state.attachments) || [];
    const pending = items.filter((item) => (item.selected !== false) !== selected);
    if (!pending.length) return;
    let payload = null;
    for (const item of pending) {
      // Sequential on purpose: each response is a full snapshot of the list.
      payload = await api('/api/attachments/select', {
        method: 'POST',
        body: JSON.stringify({ index: item.index, selected }),
      });
    }
    if (!payload || !payload.attachments) {
      toast('Could not update the files.', 'error');
      this.refresh();
      return;
    }
    refreshAttachments(payload.attachments);
  },

  reveal(id) {
    this.set(true);
    const node = document.getElementById(id);
    if (!node) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    node.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'nearest' });
    node.classList.remove('is-flash');
    void node.offsetWidth;
    node.classList.add('is-flash');
    window.setTimeout(() => node.classList.remove('is-flash'), 1200);
  },

  async refresh() {
    const data = await api('/api/workspace');
    if (!data.ok) return;
    this.state = data;
    this.render();
  },

  render() {
    const state = this.state;
    if (!state) return;

    const taskText = document.getElementById('task-text');
    const taskUpdated = document.getElementById('task-updated');
    if (taskText) taskText.textContent = state.task.task || 'No task set for this session.';
    if (taskUpdated) taskUpdated.textContent = state.task.updated_at ? `Updated ${state.task.updated_at}` : '';

    document.getElementById('ctx-profile').textContent =
      `${state.profile.name || '—'} · ${state.profile.visibility || 'public'}`;
    const items = state.attachments || [];
    this.renderFiles(items);
    if (window.updateAttachSummary) updateAttachSummary(items);
    this.renderSkills(state.skills || { skills: [], active: [] });
    document.getElementById('ctx-memories').textContent = String(state.memory.active || 0);
    document.getElementById('ctx-trails').textContent = String(state.study.trails || 0);

    const checkpoint = state.checkpoint;
    const hasCheckpoint = Boolean(checkpoint.goal || checkpoint.decisions || checkpoint.questions || checkpoint.next_step);
    document.getElementById('checkpoint-empty').hidden = hasCheckpoint;
    document.getElementById('checkpoint-fields').hidden = !hasCheckpoint;
    document.getElementById('checkpoint-updated').textContent =
      hasCheckpoint && checkpoint.updated_at ? `Saved ${checkpoint.updated_at}` : '';
    if (hasCheckpoint) {
      document.querySelectorAll('[data-field]').forEach((node) => {
        node.textContent = checkpoint[node.dataset.field] || '—';
      });
    }

    this.renderStudy(state.study);
    this.renderRoute(state.route);
  },

  renderFiles(items) {
    const grid = document.getElementById('file-grid');
    if (!grid) return;

    const total = items.length;
    const selected = items.filter((item) => item.selected !== false).length;
    const count = document.getElementById('files-count');
    if (count) {
      count.hidden = !total;
      count.textContent = total ? `${selected}/${total}` : '';
    }
    const empty = document.getElementById('files-empty');
    if (empty) empty.hidden = total > 0;
    const actions = document.getElementById('files-actions');
    if (actions) actions.hidden = total < 2;
    const context = document.getElementById('ctx-attachments');
    if (context) context.textContent = total ? `${selected} of ${total} selected` : 'none';

    grid.innerHTML = '';
    items.forEach((item) => {
      const box = document.createElement('div');
      box.className = `file-box${item.selected === false ? '' : ' is-selected'}`;

      const main = document.createElement('button');
      main.type = 'button';
      main.className = 'file-main';
      main.setAttribute('aria-pressed', String(item.selected !== false));
      main.title = item.summary || item.name;
      main.innerHTML = `
        <span class="file-icon" aria-hidden="true">${escapeHtml(fileGlyph(item.type))}</span>
        <span class="file-name">${escapeHtml(item.name)}</span>
        <span class="file-meta">${escapeHtml(item.detail || (item.type || '').toUpperCase())}</span>
        <span class="file-check" aria-hidden="true">✓</span>`;
      main.addEventListener('click', () => this.setSelected(item.index, item.selected === false));

      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'file-remove';
      remove.title = `Remove ${item.name}`;
      remove.setAttribute('aria-label', `Remove ${item.name}`);
      remove.textContent = '✕';
      remove.addEventListener('click', async () => {
        const payload = await api('/api/attachments/remove', {
          method: 'POST',
          body: JSON.stringify({ index: item.index }),
        });
        handlePayload(payload, '');
      });

      const study = document.createElement('button');
      study.type = 'button';
      study.className = 'shelf-link';
      study.textContent = 'Study';
      study.title = `Create a study trail from ${item.name}`;
      study.setAttribute('aria-label', `Create a study trail from ${item.name}`);
      study.addEventListener('click', async () => {
        const payload = await api('/api/study/from-attachment', {
          method: 'POST',
          body: JSON.stringify({ index: item.index }),
        });
        if (!payload.ok) {
          toast(payload.error || 'Could not create the study trail.', 'error');
          return;
        }
        const trail = payload.trail || {};
        toast(`Study trail ready: ${trail.title || item.name}`, 'ok');
        this.refresh();
      });

      box.append(main, remove, study);
      grid.appendChild(box);
    });
  },

  renderSkills(payload) {
    const grid = document.getElementById('skill-grid');
    if (!grid) return;

    const list = (payload && payload.skills) || [];
    const active = (payload && payload.active) || [];
    const summary = document.getElementById('skills-summary-text');
    if (summary) {
      summary.textContent = active.length
        ? `${active.length} active · ${active.join(', ')}`
        : 'No skill active';
      summary.title = active.join(', ');
    }
    const count = document.getElementById('skills-count');
    if (count) {
      count.hidden = !list.length;
      count.textContent = list.length ? `${active.length}/${list.length}` : '';
    }
    const empty = document.getElementById('skills-empty');
    if (empty) empty.hidden = list.length > 0;

    grid.innerHTML = '';
    list.forEach((skill) => {
      const card = document.createElement('div');
      card.className = `skill-card${skill.active ? ' is-selected' : ''}`;
      if (skill.color) card.style.setProperty('--skill-color', skill.color);

      const main = document.createElement('button');
      main.type = 'button';
      main.className = 'skill-main';
      main.setAttribute('aria-pressed', String(Boolean(skill.active)));
      main.title = skill.description || skill.name;
      main.innerHTML = `
        <span class="skill-tile" aria-hidden="true">${escapeHtml(skill.icon || (skill.name || '?').slice(0, 1))}</span>
        <span class="skill-name">${escapeHtml(skill.name)}</span>
        <span class="skill-desc">${escapeHtml(skill.short || '')}</span>
        <span class="skill-check" aria-hidden="true">✓</span>`;
      main.addEventListener('click', () => this.toggleSkill(skill.id, !skill.active));
      card.appendChild(main);

      if (skill.can_run) {
        const run = document.createElement('button');
        run.type = 'button';
        run.className = 'skill-run';
        run.title = `Run ${skill.name}`;
        run.setAttribute('aria-label', `Run ${skill.name}`);
        run.innerHTML = '<svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor" aria-hidden="true"><path d="M8 5l11 7-11 7z"/></svg>';
        run.addEventListener('click', () => this.runSkill(skill));
        card.appendChild(run);
      }

      grid.appendChild(card);
    });
  },

  async toggleSkill(id, active) {
    const data = await api('/api/skills/toggle', {
      method: 'POST',
      body: JSON.stringify({ id, active }),
    });
    if (!data.ok) {
      toast(data.error || 'Could not update the skill.', 'error');
      return;
    }
    if (this.state) this.state.skills = data;
    this.renderSkills(data);
  },

  async runSkill(skill) {
    const data = await api('/api/skills/invoke', {
      method: 'POST',
      body: JSON.stringify({ id: skill.id }),
    });
    if (!data.ok) {
      toast(data.error || 'This skill has nothing to run.', 'error');
      return;
    }
    input.value = data.prompt;
    input.dispatchEvent(new Event('input'));
    send();
  },

  renderStudy(study) {
    const body = document.getElementById('study-body');
    if (!body) return;
    if (!study || !study.active) {
      body.innerHTML = '<p class="shelf-empty">No study trails yet. <a href="/study">Start one</a>.</p>';
      return;
    }
    const trail = study.active;
    body.innerHTML = `
      <div class="shelf-kv"><span>${escapeHtml(trail.title)}</span><span>${escapeHtml(trail.stage)}</span></div>
      <div class="shelf-kv"><span>Quizzes</span><span>${trail.quizzes_completed}</span></div>
      ${study.weak_spots.length ? `<p class="shelf-empty">Revisit: ${study.weak_spots.map((spot) => escapeHtml(spot.concept)).join(', ')}</p>` : ''}
      ${study.next_review ? `<p class="shelf-empty">Next review: ${escapeHtml(study.next_review)}</p>` : ''}`;
  },

  renderRoute(route) {
    const body = document.getElementById('route-body');
    if (!body) return;
    if (!route) {
      body.innerHTML = '<p class="shelf-empty">No reply yet this session.</p>';
      return;
    }
    body.innerHTML = `
      <div class="shelf-kv"><span>Last route</span><span>${escapeHtml(route.classification || 'unknown')}</span></div>
      <div class="shelf-kv"><span>Provider</span><span>${escapeHtml(route.provider ? providerLabel(route.provider) : 'not recorded')}</span></div>
      <div class="shelf-kv"><span>Model</span><span>${escapeHtml(route.model || '—')}</span></div>
      <div class="shelf-kv"><span>Latency</span><span>${route.latency_ms != null ? `${(route.latency_ms / 1000).toFixed(1)}s` : '—'}</span></div>
      ${route.web_search ? '<div class="shelf-kv"><span>Web search</span><span>used</span></div>' : ''}
      ${(route.fallbacks || []).length ? `<p class="shelf-empty">${route.fallbacks.map(escapeHtml).join(' ')}</p>` : ''}`;
  },
};

// Classic scripts share one global scope, but `const` does not create a
// window property — chat.js talks to the shelf through this explicit handle.
window.Shelf = Shelf;

function workspaceInit() {
  Shelf.init();
}
