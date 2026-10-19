// Study page: profile-scoped study trails.

let META = { stages: [], mastery: ['new', 'practicing', 'confident', 'revisit'] };
try {
  META = JSON.parse(document.getElementById('study-meta').textContent);
} catch (err) { /* defaults are fine */ }

const MASTERY_LABELS = {
  new: 'New',
  practicing: 'Practicing',
  confident: 'Confident',
  revisit: 'Revisit',
};

const STAGE_LABELS = {
  starting: 'Starting',
  learning: 'Learning',
  practicing: 'Practicing',
  reviewing: 'Reviewing',
  done: 'Wrapped up',
};

function trailCard(trail) {
  const card = document.createElement('article');
  card.className = 'trail';

  const counts = trail.mastery || {};
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  const segments = [];
  ['new', 'practicing', 'confident', 'revisit'].forEach((state) => {
    for (let i = 0; i < (counts[state] || 0); i += 1) {
      segments.push(`<span class="m-${state}" title="${MASTERY_LABELS[state]}"></span>`);
    }
  });
  for (let i = segments.length; i < 8; i += 1) segments.push('<span></span>');

  card.innerHTML = `
    <div class="trail-head">
      <div>
        <h2>${escapeHtml(trail.title)}</h2>
        <p class="muted">${escapeHtml(trail.description || 'No description yet.')}</p>
      </div>
      <div class="trail-actions"></div>
    </div>
    <div class="trail-progress" aria-hidden="true">${segments.join('')}</div>
    <div class="shelf-kv"><span>${total} ${total === 1 ? 'concept' : 'concepts'} · ${trail.quizzes_completed} quizzes</span>
      <span>${escapeHtml(STAGE_LABELS[trail.stage] || trail.stage)}${trail.next_review ? ` · review ${escapeHtml(trail.next_review)}` : ''}</span></div>`;

  const actions = card.querySelector('.trail-actions');
  actions.innerHTML = `
    <button class="btn btn-small" data-act="quiz">Generate quiz</button>
    <button class="btn btn-small" data-act="note">Add note</button>
    <button class="btn btn-small" data-act="edit">Edit</button>
    <button class="btn btn-small" data-act="delete">Delete</button>`;
  actions.querySelector('[data-act="quiz"]').addEventListener('click', () => {
    window.location.href = `/chat?prefill=${encodeURIComponent(`.QUIZ: ${trail.title}`)}`;
  });
  actions.querySelector('[data-act="note"]').addEventListener('click', () => openNote(trail));
  actions.querySelector('[data-act="edit"]').addEventListener('click', () => openTrail(null, trail));
  actions.querySelector('[data-act="delete"]').addEventListener('click', () => deleteTrail(trail));

  const concepts = document.createElement('ul');
  concepts.className = 'concept-list';
  const list = trail.concepts || [];
  if (!list.length) {
    concepts.innerHTML = '<li class="shelf-empty">No concepts yet — add one when a topic clicks.</li>';
  }
  list.forEach((concept) => {
    const item = document.createElement('li');
    item.className = 'concept';
    item.innerHTML = `<span class="concept-name">${escapeHtml(concept.name)}</span>
      <span class="mastery-group" role="group" aria-label="Mastery for ${escapeHtml(concept.name)}">
        ${META.mastery.map((state) => `<button type="button" data-mastery="${state}"
          aria-pressed="${concept.mastery === state}">${MASTERY_LABELS[state]}</button>`).join('')}
      </span>
      <button class="btn btn-small" data-act="drop">Remove</button>`;
    item.querySelectorAll('[data-mastery]').forEach((button) => {
      button.addEventListener('click', async () => {
        await api(`/api/study/concepts/${concept.id}/mastery`, {
          method: 'POST',
          body: JSON.stringify({ mastery: button.dataset.mastery }),
        });
        load();
      });
    });
    item.querySelector('[data-act="drop"]').addEventListener('click', async () => {
      await api(`/api/study/concepts/${concept.id}`, { method: 'DELETE' });
      load();
    });
    concepts.appendChild(item);
  });
  card.appendChild(concepts);

  const addRow = document.createElement('div');
  addRow.className = 'row';
  addRow.innerHTML = `<input type="text" placeholder="Add a concept (e.g. B-tree index)" aria-label="New concept">
    <button class="btn btn-small">Add</button>`;
  const addInput = addRow.querySelector('input');
  const submit = async () => {
    const name = addInput.value.trim();
    if (!name) return;
    const result = await api(`/api/study/trails/${trail.id}/concepts`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    });
    if (!result.ok) {
      toast(result.error || 'Could not add that concept.', 'error');
      return;
    }
    load();
  };
  addRow.querySelector('button').addEventListener('click', submit);
  addInput.addEventListener('keydown', (event) => { if (event.key === 'Enter') submit(); });
  card.appendChild(addRow);

  if ((trail.saved_notes || []).length) {
    const details = document.createElement('details');
    details.innerHTML = `<summary class="muted small">${trail.saved_notes.length} saved
      ${trail.saved_notes.length === 1 ? 'note' : 'notes'}</summary>
      <ul class="trail-notes">${trail.saved_notes.map((note) => `
        <li><strong>${escapeHtml(note.title || 'Note')}</strong>
          <span class="muted small"> ${escapeHtml(note.created_at)}</span>
          <pre>${escapeHtml(note.content)}</pre>
          <button class="btn btn-small" data-note="${note.id}">Remove</button></li>`).join('')}</ul>`;
    details.querySelectorAll('[data-note]').forEach((button) => {
      button.addEventListener('click', async () => {
        await api(`/api/study/notes/${button.dataset.note}`, { method: 'DELETE' });
        load();
      });
    });
    card.appendChild(details);
  }

  return card;
}

async function load() {
  const data = await api('/api/study/trails');
  if (!data.ok) {
    toast(data.error || 'Study trails are unavailable for this profile.', 'error');
    return;
  }
  META.stages = data.stages || META.stages;
  META.mastery = data.mastery || META.mastery;

  const host = document.getElementById('trails');
  host.innerHTML = '';
  const trails = data.trails || [];
  if (!trails.length) {
    host.innerHTML = `<section class="card"><h2>No trails yet</h2>
      <p class="muted small">Create one when you start learning something — or save an answer to a trail straight
      from chat with the dial under any reply.</p></section>`;
    return;
  }
  trails.forEach((trail) => host.appendChild(trailCard(trail)));
}

function openTrail(_unused, trail) {
  const editing = Boolean(trail);
  openModal(editing ? 'Edit trail' : 'New study trail', `
    <label>Topic <input id="trail-title" type="text" maxlength="160"
      value="${editing ? escapeHtml(trail.title) : ''}" placeholder="SQLite indexing"></label>
    <label>What are you aiming for? <textarea id="trail-description" rows="2"
      placeholder="Understand query plans well enough to tune slowly">${editing ? escapeHtml(trail.description || '') : ''}</textarea></label>
    ${editing ? `<label>Stage
      <select id="trail-stage">${META.stages.map((stage) => `<option value="${stage.key}"
        ${trail.stage === stage.key ? 'selected' : ''}>${escapeHtml(stage.label || stage.key)}</option>`).join('')}</select></label>
      <label>Next review <input id="trail-review" type="text"
        value="${escapeHtml(trail.next_review || '')}" placeholder="e.g. next week, or 2026-11-02"></label>` : ''}
    <div class="actions">
      <button class="btn btn-primary" id="trail-save">${editing ? 'Save' : 'Create trail'}</button>
      <span class="muted small" id="trail-status"></span>
    </div>`);

  document.getElementById('trail-save').addEventListener('click', async () => {
    const title = document.getElementById('trail-title').value.trim();
    if (!title) {
      document.getElementById('trail-status').textContent = 'Give the trail a topic.';
      return;
    }
    const payload = {
      title,
      description: document.getElementById('trail-description').value,
    };
    if (editing) {
      payload.stage = document.getElementById('trail-stage').value;
      payload.next_review = document.getElementById('trail-review').value;
    }
    const path = editing ? `/api/study/trails/${trail.id}` : '/api/study/trails';
    const result = await api(path, { method: 'POST', body: JSON.stringify(payload) });
    if (!result.ok) {
      document.getElementById('trail-status').textContent = result.error || 'Could not save.';
      return;
    }
    closeModal();
    toast(editing ? 'Trail updated.' : 'Trail created.', 'ok');
    load();
  });
}

function openNote(trail) {
  openModal(`Add a note — ${trail.title}`, `
    <label>Title <input id="note-title" type="text" placeholder="Base cases"></label>
    <label>Note <textarea id="note-content" rows="6" placeholder="Anything worth keeping"></textarea></label>
    <div class="actions"><button class="btn btn-primary" id="note-save">Save note</button>
      <span class="muted small" id="note-status"></span></div>`);
  document.getElementById('note-save').addEventListener('click', async () => {
    const result = await api(`/api/study/trails/${trail.id}/notes`, {
      method: 'POST',
      body: JSON.stringify({
        title: document.getElementById('note-title').value,
        content: document.getElementById('note-content').value,
      }),
    });
    if (!result.ok) {
      document.getElementById('note-status').textContent = result.error || 'Could not save.';
      return;
    }
    closeModal();
    toast('Note saved.', 'ok');
    load();
  });
}

async function deleteTrail(trail) {
  if (!window.confirm(`Delete “${trail.title}” with its concepts and notes?`)) return;
  const result = await api(`/api/study/trails/${trail.id}`, { method: 'DELETE' });
  if (!result.ok) {
    toast(result.error || 'Could not delete that trail.', 'error');
    return;
  }
  toast('Trail deleted.', 'ok');
  load();
}

document.getElementById('trail-new').addEventListener('click', () => openTrail(null, null));
load();
