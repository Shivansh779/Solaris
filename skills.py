"""Markdown skills for Solaris.

A skill is one Markdown file with optional YAML frontmatter:

    ---
    name: Code Review
    description: Reviews attached code for correctness and security.
    short-description: Find bugs before they ship
    default-prompt: Review the selected files and list findings by severity.
    icon: "◇"
    brand-color: "#b7f04a"
    ---
    Instructions the model should follow while this skill is active.

Discovery reads two scopes, project first:

    Skills/                (next to this module, versioned with the app)
    ~/.solaris/skills/     (personal, survives moving the project)

A user-scope skill overrides a project-scope skill with the same name.
Files are data only — nothing in a skill is ever executed.

Active skills live in memory for the session, exactly like attachments; they
are never written to the database. Only active skills are assembled into the
prompt block returned by get_context().
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

PROJECT_DIR = Path(__file__).resolve().parent / "Skills"
USER_DIR = Path.home() / ".solaris" / "skills"

SKILL_LIMIT = 64 * 1024        # skip files larger than 64 KiB
BODY_LIMIT = 6_000             # characters of one skill body sent to a model
CONTEXT_LIMIT = 24_000         # characters of all active skills combined

_COLOR = re.compile(r"^#[0-9a-fA-F]{3,8}$")

_active: set[str] = set()


# ------------------------------------------------------------------ parsing


def _text(value, limit=0):
    if value is None:
        return ""
    value = str(value).strip()
    return value[:limit].strip() if limit else value


def _first_line(body: str) -> str:
    for line in body.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line
    return ""


def _title(stem: str) -> str:
    return stem.replace("-", " ").replace("_", " ").strip().title()


def _parse(path: Path, scope: str) -> Optional[Dict[str, Any]]:
    try:
        if path.stat().st_size > SKILL_LIMIT:
            return None
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    meta: Dict[str, Any] = {}
    body = raw
    if raw.startswith("---"):
        lines = raw.splitlines()
        for index, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                try:
                    loaded = yaml.safe_load("\n".join(lines[1:index]))
                except yaml.YAMLError:
                    loaded = None
                if isinstance(loaded, dict):
                    meta = loaded
                body = "\n".join(lines[index + 1:])
                break

    body = body.strip()
    name = _text(meta.get("name")) or _title(path.stem)
    description = _text(meta.get("description")) or _first_line(body)
    short = _text(meta.get("short-description")) or description[:70]
    icon = _text(meta.get("icon"), 8)
    color = _text(meta.get("brand-color"))
    if not _COLOR.match(color):
        color = ""

    skill_id = f"{scope}:{path.name}"
    return {
        "id": skill_id,
        "name": name,
        "description": description,
        "short": short,
        "default_prompt": _text(meta.get("default-prompt")),
        "icon": icon,
        "color": color,
        "body": body,
        "scope": scope,
        "path": str(path),
        "active": skill_id in _active,
    }


def _root(scope: str) -> Path:
    return PROJECT_DIR if scope == "project" else USER_DIR


def discover() -> List[Dict[str, Any]]:
    """Every skill file, project scope first, user scope overriding by name."""
    found: Dict[str, Dict[str, Any]] = {}
    for scope in ("project", "user"):
        root = _root(scope)
        if not root.is_dir():
            continue
        try:
            candidates = sorted(root.glob("*.md"), key=lambda item: item.name.casefold())
        except OSError:
            continue
        for path in candidates:
            if path.name.startswith(".") or not path.is_file():
                continue
            skill = _parse(path, scope)
            if skill is None:
                continue
            found[skill["name"].casefold()] = skill
    return sorted(found.values(), key=lambda item: item["name"].casefold())


def get(skill_id: str) -> Optional[Dict[str, Any]]:
    return next((item for item in discover() if item["id"] == skill_id), None)


# ------------------------------------------------------------------ activation


def set_active(skill_id: str, active: bool) -> bool:
    """Turn one known skill on or off. False when the id is unknown."""
    if get(skill_id) is None:
        return False
    if active:
        _active.add(skill_id)
    else:
        _active.discard(skill_id)
    return True


def clear_active() -> None:
    _active.clear()


def get_context() -> str:
    """Labelled block for the prompt. Empty when no skill is active."""
    chosen = [item for item in discover() if item["id"] in _active]
    if not chosen:
        return ""

    parts = ["=== ACTIVE SKILLS ==="]
    used = 0
    for skill in chosen:
        body = skill["body"]
        if len(body) > BODY_LIMIT:
            body = body[:BODY_LIMIT].rstrip() + "\n… (skill truncated)"
        if used + len(body) > CONTEXT_LIMIT:
            parts.append("\n… (more active skills omitted to keep the prompt bounded)")
            break
        used += len(body)
        parts.append(f"\n--- {skill['name']} ({skill['scope']}) ---")
        parts.append(body)
    parts.append("\n=== END ACTIVE SKILLS ===")
    return "\n".join(parts)


def payload() -> Dict[str, Any]:
    """JSON-safe view for the workspace shelf. Prompt text stays server-side."""
    items = []
    for skill in discover():
        items.append({
            "id": skill["id"],
            "name": skill["name"],
            "description": skill["description"],
            "short": skill["short"],
            "icon": skill["icon"],
            "color": skill["color"],
            "scope": skill["scope"],
            "active": skill["id"] in _active,
            "can_run": bool(skill["default_prompt"]),
        })
    active = [item["name"] for item in items if item["active"]]
    return {"skills": items, "active": active, "total": len(items),
            "active_count": len(active)}


def invoke_prompt(skill_id: str) -> Optional[str]:
    """The visible message a Run click sends, or None when there is none."""
    skill = get(skill_id)
    if skill is None or not skill["default_prompt"]:
        return None
    return skill["default_prompt"]
