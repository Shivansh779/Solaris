"""Workspace API: Constellation Memory, Study Trails, session workspace, answer controls.

Every route here is profile-scoped and guarded server-side by web.access —
a locked (inactive or private-unlocked) profile can never read or write this
data through guessed ids.
"""

from flask import Blueprint, jsonify, request

import core
import main_db
import memory_db
import skills
import study_db
import vec_db
import web.access as access
import web.jobs as jobs
import workspace_db

bp = Blueprint("workspace", __name__)

# ------------------------------------------------------------------ guards


def _guard():
    """(user_id, error_response) for the selected profile."""
    ok, body, status = access.require_selected()
    if not ok:
        return None, (jsonify(body), status)
    return core.session.user_id, None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bad(message, status=400):
    return jsonify({"ok": False, "error": message}), status


# ------------------------------------------------------------------ workspace


@bp.get("/api/workspace")
def workspace_state():
    user_id, error = _guard()
    if error:
        return error
    profile_access = main_db.get_access(user_id) or {}
    return jsonify({
        "ok": True,
        "task": workspace_db.get_task(user_id),
        "checkpoint": workspace_db.get_checkpoint(user_id),
        "attachments": core.attachments_payload(),
        "skills": skills.payload(),
        "memory": memory_db.counts(user_id),
        "study": study_db.summary(user_id),
        "route": core.session.last_route,
        "profile": {
            "user_id": user_id,
            "name": core.session.name,
            "visibility": profile_access.get("visibility"),
            "state": profile_access.get("state"),
        },
    })


@bp.post("/api/workspace/task")
def workspace_task():
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    task = data.get("task")
    if task is None:
        return _bad("Send a task string (empty clears it).")
    return jsonify({"ok": True, "task": workspace_db.set_task(user_id, task)})


@bp.post("/api/workspace/checkpoint")
def workspace_checkpoint():
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    checkpoint = workspace_db.save_checkpoint(
        user_id,
        goal=data.get("goal", ""),
        decisions=data.get("decisions", ""),
        questions=data.get("questions", ""),
        next_step=data.get("next_step", ""),
    )
    return jsonify({"ok": True, "checkpoint": checkpoint})


# ------------------------------------------------------------------ memory


@bp.get("/api/memory")
def memory_list():
    user_id, error = _guard()
    if error:
        return error
    return jsonify({
        "ok": True,
        "active": memory_db.list_memories(user_id, status="active"),
        "suggested": memory_db.list_memories(user_id, status="suggested"),
        "archived": memory_db.list_memories(user_id, status="archived"),
        "counts": memory_db.counts(user_id),
        "categories": [
            {"key": key, "label": memory_db.CATEGORY_LABELS[key]}
            for key in memory_db.CATEGORIES
        ],
    })


@bp.post("/api/memory")
def memory_add():
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    try:
        memory_id = memory_db.add_memory(
            user_id,
            data.get("category", "custom"),
            data.get("title", ""),
            data.get("detail", ""),
            source="user",
            status="active",
        )
    except ValueError as e:
        return _bad(str(e))
    return jsonify({"ok": True, "id": memory_id, "counts": memory_db.counts(user_id)})


@bp.post("/api/memory/<int:memory_id>")
def memory_edit(memory_id):
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    try:
        changed = memory_db.update_memory(
            user_id, memory_id,
            category=data.get("category"),
            title=data.get("title"),
            detail=data.get("detail"),
        )
    except ValueError as e:
        return _bad(str(e))
    if not changed:
        return _bad("Memory not found.", 404)
    return jsonify({"ok": True, "memory": memory_db.get_memory(user_id, memory_id)})


@bp.post("/api/memory/<int:memory_id>/status")
def memory_status(memory_id):
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    try:
        changed = memory_db.set_status(user_id, memory_id, data.get("status", ""))
    except ValueError as e:
        return _bad(str(e))
    if not changed:
        return _bad("Memory not found.", 404)
    return jsonify({"ok": True, "counts": memory_db.counts(user_id)})


@bp.delete("/api/memory/<int:memory_id>")
def memory_forget(memory_id):
    user_id, error = _guard()
    if error:
        return error
    if not memory_db.delete_memory(user_id, memory_id):
        return _bad("Memory not found.", 404)
    return jsonify({"ok": True, "counts": memory_db.counts(user_id)})


@bp.post("/api/memory/clear")
def memory_clear():
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    if (data.get("confirm") or "").strip().upper() != "FORGET":
        return _bad("Type FORGET to confirm clearing every memory node for this profile.")
    removed = memory_db.clear_profile(user_id)
    return jsonify({"ok": True, "removed": removed, "counts": memory_db.counts(user_id)})


# ------------------------------------------------------------------ study


@bp.get("/api/study/trails")
def study_trails():
    user_id, error = _guard()
    if error:
        return error
    return jsonify({
        "ok": True,
        "trails": study_db.list_trails(user_id),
        "stages": [{"key": key, "label": study_db.STAGE_LABELS[key]} for key in study_db.STAGES],
        "mastery": list(study_db.MASTERY),
        "summary": study_db.summary(user_id),
    })


@bp.post("/api/study/trails")
def study_create():
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    try:
        trail_id = study_db.create_trail(user_id, data.get("title", ""), data.get("description", ""))
    except ValueError as e:
        return _bad(str(e))
    return jsonify({"ok": True, "trail": study_db.get_trail(user_id, trail_id)})


@bp.get("/api/study/trails/<int:trail_id>")
def study_trail(trail_id):
    user_id, error = _guard()
    if error:
        return error
    trail = study_db.get_trail(user_id, trail_id)
    if trail is None:
        return _bad("Study trail not found.", 404)
    return jsonify({"ok": True, "trail": trail})


@bp.post("/api/study/trails/<int:trail_id>")
def study_update(trail_id):
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    try:
        changed = study_db.update_trail(
            user_id, trail_id,
            title=data.get("title"),
            description=data.get("description"),
            stage=data.get("stage"),
            next_review=data.get("next_review"),
        )
    except ValueError as e:
        return _bad(str(e))
    if not changed:
        return _bad("Study trail not found.", 404)
    return jsonify({"ok": True, "trail": study_db.get_trail(user_id, trail_id)})


@bp.delete("/api/study/trails/<int:trail_id>")
def study_delete(trail_id):
    user_id, error = _guard()
    if error:
        return error
    if not study_db.delete_trail(user_id, trail_id):
        return _bad("Study trail not found.", 404)
    return jsonify({"ok": True, "summary": study_db.summary(user_id)})


@bp.post("/api/study/trails/<int:trail_id>/concepts")
def study_add_concept(trail_id):
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    try:
        study_db.add_concept(user_id, trail_id, data.get("name", ""), data.get("mastery", "new"))
    except ValueError as e:
        return _bad(str(e))
    return jsonify({"ok": True, "trail": study_db.get_trail(user_id, trail_id)})


@bp.post("/api/study/concepts/<int:concept_id>/mastery")
def study_mastery(concept_id):
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    try:
        changed = study_db.set_mastery(user_id, concept_id, data.get("mastery", ""))
    except ValueError as e:
        return _bad(str(e))
    if not changed:
        return _bad("Concept not found.", 404)
    return jsonify({"ok": True})


@bp.delete("/api/study/concepts/<int:concept_id>")
def study_delete_concept(concept_id):
    user_id, error = _guard()
    if error:
        return error
    if not study_db.delete_concept(user_id, concept_id):
        return _bad("Concept not found.", 404)
    return jsonify({"ok": True})


@bp.post("/api/study/trails/<int:trail_id>/notes")
def study_add_note(trail_id):
    """Save an answer (or anything) into a trail."""
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    try:
        study_db.add_note(user_id, trail_id, data.get("title", ""), data.get("content", ""))
    except ValueError as e:
        return _bad(str(e))
    return jsonify({"ok": True, "trail": study_db.get_trail(user_id, trail_id)})


@bp.delete("/api/study/notes/<int:note_id>")
def study_delete_note(note_id):
    user_id, error = _guard()
    if error:
        return error
    if not study_db.delete_note(user_id, note_id):
        return _bad("Note not found.", 404)
    return jsonify({"ok": True})


@bp.post("/api/study/trails/<int:trail_id>/quiz")
def study_quiz_done(trail_id):
    """Record that a quiz was completed for this trail."""
    user_id, error = _guard()
    if error:
        return error
    if not study_db.register_quiz(user_id, trail_id):
        return _bad("Study trail not found.", 404)
    return jsonify({"ok": True, "trail": study_db.get_trail(user_id, trail_id)})


@bp.post("/api/study/from-answer")
def study_from_answer():
    """Create a trail from a chat answer in one step (trail + note)."""
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    content = (data.get("content") or "").strip()
    if not title:
        return _bad("Give the trail a topic first.")
    trail_id = study_db.create_trail(user_id, title, data.get("description", ""))
    if content:
        study_db.add_note(user_id, trail_id, title, content)
    return jsonify({"ok": True, "trail": study_db.get_trail(user_id, trail_id)})


@bp.post("/api/study/from-attachment")
def study_from_attachment():
    """Create a trail from an attached file (trail + concepts + a note)."""
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    index = _int(data.get("index"))
    if index is None:
        return _bad("Send the attachment index.")
    try:
        trail = core.trail_from_attachment(index)
    except ValueError as e:
        return _bad(str(e))
    except Exception:
        return _bad("Could not build the study trail.", 500)
    return jsonify({"ok": True, "trail": trail})


# ------------------------------------------------------------------ answer controls


@bp.get("/api/answer-controls")
def answer_controls():
    return jsonify({"ok": True, "controls": core.answer_controls()})


@bp.post("/api/answer-control")
def answer_control():
    user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    payload = core.follow_up(
        data.get("action", ""),
        data.get("question", ""),
        data.get("answer", ""),
    )
    return jsonify(payload)


# ------------------------------------------------------------------ context manifest


@bp.post("/api/context/reask")
def context_reask():
    """Re-ask the same question with one context source removed.

    The previous answer is never handed to the model: it was written with the
    very source we are removing. The reply is an ordinary reply payload, so the
    UI renders it like any other answer — with its own manifest.
    """
    _user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return _bad("Send the question again.")
    exclude = data.get("exclude") or []
    if not isinstance(exclude, list):
        return _bad("`exclude` must be a list of context ids.")
    return jsonify(core.send(
        question,
        exclude_ids=exclude,
        record=False,
        previous_answer=str(data.get("answer") or ""),
    ))


# ------------------------------------------------------------------ skills


@bp.get("/api/skills")
def skills_list():
    _user_id, error = _guard()
    if error:
        return error
    return jsonify({"ok": True, **skills.payload()})


@bp.post("/api/skills/toggle")
def skills_toggle():
    _user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    skill_id = str(data.get("id") or "")
    if not skills.set_active(skill_id, bool(data.get("active"))):
        return _bad("Unknown skill.")
    return jsonify({"ok": True, **skills.payload()})


@bp.post("/api/skills/invoke")
def skills_invoke():
    _user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    skill_id = str(data.get("id") or "")
    prompt = skills.invoke_prompt(skill_id)
    if prompt is None:
        return _bad("This skill has no default prompt to run.")
    return jsonify({"ok": True, "id": skill_id, "prompt": prompt})


@bp.post("/api/skills/draft")
def skills_draft():
    """Draft a skill from the current thread. The user edits it before saving."""
    _user_id, error = _guard()
    if error:
        return error
    return jsonify({"ok": True, "draft": core.draft_skill_from_thread()})


@bp.post("/api/skills/save")
def skills_save():
    """Write the edited draft as a Markdown skill the loader picks up."""
    _user_id, error = _guard()
    if error:
        return error
    data = request.get_json(force=True) or {}
    title = str(data.get("title") or "").strip()
    if not title:
        return _bad("Give the skill a title.")
    scope = str(data.get("scope") or "project").strip().lower()
    if scope not in ("project", "user"):
        return _bad("Unknown scope.")
    try:
        skill = skills.save_skill(
            title,
            str(data.get("body") or "").strip(),
            description=str(data.get("description") or "").strip(),
            default_prompt=str(data.get("default_prompt") or "").strip(),
            scope=scope,
        )
    except ValueError as e:
        return _bad(str(e))
    return jsonify({"ok": True, "skill": skill})


# ------------------------------------------------------------------ vector

@bp.get("/api/vector/status")
def vector_status():
    """The state of the semantic index."""
    _user_id, error = _guard()
    if error:
        return error
    return jsonify({"ok": True, "vector": vec_db.stats()})


@bp.post("/api/vector/rebuild")
def vector_rebuild():
    """Rebuild the semantic index from the stored memories and summaries.

    The index is derived data, so this is always safe to run. It runs in the
    background because every chunk has to be embedded by the local model.
    """
    _user_id, error = _guard()
    if error:
        return error
    if not vec_db.available():
        return _bad("The sqlite-vec extension is not available on this machine.", 503)
    job_id = jobs.start(vec_db.rebuild)
    return jsonify({"ok": True, "job": job_id, "vector": vec_db.stats()})
