import builtins
import re

import pytest

import _log


@pytest.fixture
def fake_log_file(tmp_path, monkeypatch):
    real_open = builtins.open

    def fake_open(path, *args, **kwargs):
        if str(path) == "System_Logs.txt":
            path = str(tmp_path / "System_Logs.txt")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    return tmp_path / "System_Logs.txt"


def test_current_time_format():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", _log.current_time())


def test_current_time_is_str():
    assert isinstance(_log.current_time(), str)


def test_system_log_writes_line(fake_log_file, monkeypatch):
    monkeypatch.setattr(_log, "current_time", lambda: "2026-09-12 10:00:00")
    _log.system_log("DATABASE", "INFO", "hello world")
    lines = fake_log_file.read_text().splitlines()
    assert lines == ["[INFO] [DATABASE] [2026-09-12 10:00:00]: hello world"]


def test_system_log_appends(fake_log_file, monkeypatch):
    monkeypatch.setattr(_log, "current_time", lambda: "2026-09-12 10:00:00")
    _log.system_log("A", "WARN", "first")
    _log.system_log("B", "ERROR", "second")
    assert len(fake_log_file.read_text().splitlines()) == 2