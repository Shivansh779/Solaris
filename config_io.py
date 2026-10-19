"""Safe read/write access to Solaris' JSON config files.

Every write snapshots the previous file into _backups/ so a bad edit can
always be recovered by hand.
"""

import json
import os
import shutil
from datetime import datetime

CONFIG_PATH = "config.json"
SETTINGS_PATH = "settings.json"

BACKUP_DIR = "_backups"
KEEP_BACKUPS = 10


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_config():
    return _load(CONFIG_PATH)


def load_settings():
    return _load(SETTINGS_PATH)


def save_config(data):
    _save(CONFIG_PATH, data)


def save_settings(data):
    _save(SETTINGS_PATH, data)


def update_config(partial):
    """Deep-merge a partial config into config.json and save it."""
    data = load_config()
    _merge(data, partial)
    save_config(data)
    return data


def _merge(base, partial):
    for key, value in partial.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value


def _save(path, data):
    _backup(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        f.write("\n")


def _backup(path):
    if not os.path.exists(path):
        return
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, os.path.join(BACKUP_DIR, f"{stem}_{stamp}.json"))

    old = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith(f"{stem}_"))
    for name in old[:-KEEP_BACKUPS]:
        try:
            os.remove(os.path.join(BACKUP_DIR, name))
        except OSError:
            pass
