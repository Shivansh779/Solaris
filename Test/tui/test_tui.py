"""Tests for tui_utils rendering helpers (no interactive terminal / network).

Rich's module-level `console` holds a reference to the original sys.stdout at
import time, so capsys cannot capture its output. Tests patch `tui_utils.console`
with a Console writing to a StringIO instead. `system_log` is stubbed so the
display helpers don't append to System_Logs.txt in the repo root.
"""

import io

import pytest
from rich.console import Console
from rich.markdown import Markdown

import tui_utils


@pytest.fixture
def out(monkeypatch):
    monkeypatch.setattr(tui_utils, "system_log", lambda *a, **k: None)
    buf = io.StringIO()
    monkeypatch.setattr(tui_utils, "console", Console(file=buf, width=80))
    return buf


def test_build_table_renders_headers_and_rows(out):
    table = tui_utils.build_table(["Name", "Age"], [["Al", "30"]])
    tui_utils.console.print(table)
    text = out.getvalue()
    assert "Name" in text
    assert "Age" in text
    assert "Al" in text
    assert "30" in text


def test_build_table_renders_title_and_col_styles(out):
    table = tui_utils.build_table(
        ["A", "B"],
        [["1", "2"]],
        title="People",
        col_styles={1: "bold bright_green"},
    )
    tui_utils.console.print(table)
    assert "People" in out.getvalue()


def test_display_table_panels_out(out):
    tui_utils.display_table(["Col"], [["cell-val"]])
    text = out.getvalue()
    assert "Col" in text
    assert "cell-val" in text


def test_display_plain_panel(out):
    tui_utils.display("hello world", title="PanelTitle", subtitle="sub")
    text = out.getvalue()
    assert "PanelTitle" in text
    assert "hello world" in text
    assert "sub" in text


def test_display_inline(out):
    tui_utils.display_inline("inline message")
    assert "inline message" in out.getvalue()


def test_render_markdown_returns_single_markdown_renderable():
    renderables = tui_utils.render_markdown("# Heading\n\nBody")
    assert len(renderables) == 1
    assert isinstance(renderables[0], Markdown)


def test_display_markdown_panel_and_return_value(out):
    content = "**bold** and *it* text"
    returned = tui_utils.display_markdown(content, title="MyTitle")
    assert returned == content
    text = out.getvalue()
    assert "MyTitle" in text
    assert "bold and it text" in text


def test_rule_prints_a_rule_line(out):
    tui_utils.rule()
    assert "─" in out.getvalue()


@pytest.mark.parametrize(
    "func,expected_title",
    [
        ("display_quiz", "Quiz Questions"),
        ("display_timeline", "Timeline"),
        ("display_steps", "Steps"),
        ("display_detail", "Detailed Explanation"),
        ("display_simple", "Simple Explanation"),
        ("display_compare", "Comparison"),
    ],
)
def test_display_markdown_wrappers(out, func, expected_title):
    content = "plain body text"
    returned = getattr(tui_utils, func)(content)
    assert returned == content
    text = out.getvalue()
    assert expected_title in text
    assert "plain body text" in text