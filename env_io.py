"""Read and update the .env file while preserving its comments and ordering.

Also keeps os.environ in sync so changes apply without a process restart.
"""

import os

ENV_PATH = ".env"


def read_env():
    """Return a dict of the keys currently in .env."""
    values = {}
    if not os.path.exists(ENV_PATH):
        return values
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def set_env(updates):
    """Add or update keys in .env. An empty/None value removes the key.

    Returns the keys that were changed.
    """
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

    remaining = {k: v for k, v in updates.items() if v is not None}
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in remaining:
                value = remaining.pop(key)
                if value == "":
                    continue
                out.append(f"{key}={value}")
                continue
        out.append(line)

    if remaining:
        if out and out[-1].strip():
            out.append("")
        for key, value in remaining.items():
            if value:
                out.append(f"{key}={value}")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip("\n") + "\n")

    for key, value in updates.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)

    return sorted(updates.keys())


def is_set(*keys):
    """True when every given environment key has a value."""
    return all(os.getenv(key) for key in keys)
