from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box
from rich.rule import Rule
from rich.style import Style
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.console import Group
from rich.text import Text
from rich.theme import Theme
from markdown_it import MarkdownIt

console = Console()

MARKDOWN_IT = MarkdownIt("commonmark", {"html": False}).enable("table")

# Distinct color emphasis so bold/italic/headings stand out in the terminal.
MARKDOWN_THEME = Theme(
    {
        "markdown.strong": "bold bright_yellow",
        "markdown.em": "italic bright_cyan",
        "markdown.h1": "bold underline bright_white",
        "markdown.h2": "bold bright_green",
        "markdown.h3": "bold bright_magenta",
        "markdown.h4": "bold bright_blue",
        "markdown.h5": "italic bright_cyan",
        "markdown.h6": "dim",
    }
)


# Logging Function Definition
def system_log(category, level, message):
    with open("System_Logs.txt", "a") as f:
        f.write(f"[{level}] [{category}] [{current_time()}]: {message}\n")


# Current Time Function
def current_time():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


STYLES = {
    "header": Style(color="bright_cyan", bold=True),
    "subtitle": Style(color="bright_magenta", bold=True),
    "accent": Style(color="bright_yellow"),
    "success": Style(color="bright_green"),
    "error": Style(color="bright_red"),
    "dim": Style(dim=True),
}


def display(content, title="Solaris", subtitle=None):
    """Display plain content inside a panel (no Markdown parsing)."""
    system_log("AI", "INFO", f"Displaying panel: {title}")
    console.print()
    console.print(
        Panel(
            content,
            title=title,
            subtitle=subtitle,
            border_style="bright_cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()


def display_inline(text):
    console.print(text)


def rule():
    console.print(Rule(style="bright_cyan"))


def build_table(headers, rows, title=None, col_styles=None):
    table = Table(
        title=title,
        box=box.ROUNDED,
        title_style="bold bright_cyan",
        header_style="bold bright_cyan",
        expand=True,
    )
    col_styles = col_styles or {}
    for i, header in enumerate(headers):
        table.add_column(str(header), style=col_styles.get(i, "white"))
    for row in rows:
        table.add_row(*[str(c) for c in row])
    return table


def display_table(headers, rows, title=None, col_styles=None):
    table = build_table(headers, rows, title, col_styles)
    console.print(table)


def display_quiz(questions_text):
    system_log("AI", "INFO", "Displaying quiz content")
    return display_markdown(questions_text, title="Quiz Questions")


def display_timeline(events_text):
    system_log("AI", "INFO", "Displaying timeline content")
    return display_markdown(events_text, title="Timeline")


def display_steps(steps_text):
    system_log("AI", "INFO", "Displaying steps content")
    return display_markdown(steps_text, title="Steps")


def display_detail(content):
    system_log("AI", "INFO", "Displaying detailed explanation")
    return display_markdown(content, title="Detailed Explanation")


def display_simple(content):
    system_log("AI", "INFO", "Displaying simple explanation")
    return display_markdown(content, title="Simple Explanation")


def display_compare(content):
    system_log("AI", "INFO", "Displaying comparison content")
    return display_markdown(content, title="Comparison")


# ---------------------------------------------------------------------------
# Markdown-aware rendering for AI responses
# ---------------------------------------------------------------------------

def _split_markdown_table(content):
    """Split Markdown text into (kind, block) segments, isolating markdown
    tables so they can be rendered as terminal-native Rich tables."""
    lines = content.split("\n")
    tokens = MARKDOWN_IT.parse(content)

    ranges = [tuple(t.map) for t in tokens if t.type == "table_open" and t.map]

    segments = []
    pos = 0
    for start, end in ranges:
        if pos < start:
            segments.append(("text", "\n".join(lines[pos:start])))
        segments.append(("table", "\n".join(lines[start:end])))
        pos = end
    if pos < len(lines):
        segments.append(("text", "\n".join(lines[pos:])))
    return segments


def _parse_table_block(block):
    lines = [ln.strip() for ln in block.strip().split("\n") if ln.strip()]

    def split_cells(line):
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]
        return [cell.strip() for cell in line.split("|")]

    header = split_cells(lines[0])
    rows = [split_cells(ln) for ln in lines[2:]]
    return header, rows


def _table_to_rich(header, rows, title=None):
    table = Table(
        title=title,
        box=box.ROUNDED,
        title_style="bold bright_cyan",
        header_style="bold bright_cyan",
        show_edge=True,
        pad_edge=True,
        expand=True,
    )
    for i, heading in enumerate(header):
        header_style = "bold bright_cyan"
        table.add_column(str(heading), overflow="fold", no_wrap=False, header_style=header_style)
    for row in rows:
        row = [str(c) for c in row]
        if len(row) < len(header):
            row += [""] * (len(header) - len(row))
        rendered = [Markdown(cell, justify="left") if _has_inline_markdown(cell) else cell
                    for cell in row[: len(header)]]
        table.add_row(*rendered)
    return table


def _has_inline_markdown(cell):
    return any(marker in cell for marker in ("**", "__", "*", "_", "`"))


def _markdown_text(text):
    """Escape stray HTML that Rich's Markdown renderer would otherwise parse."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_markdown(content):
    """Convert AI Markdown content (headings, lists, blockquotes, code and
    tables) into a list of Rich renderables."""
    renderables = []
    for kind, block in _split_markdown_table(content):
        if kind == "table":
            header, rows = _parse_table_block(block)
            renderables.append(_table_to_rich(header, rows))
        else:
            block = _markdown_text(block)
            if block.strip():
                renderables.append(Markdown(block, justify="left"))
    return renderables


def display_markdown(content, title="Solaris", subtitle=None):
    """Render AI Markdown (including tables) inside a readable panel."""
    system_log("AI", "INFO", f"Displaying rendered content: {title}")
    renderables = render_markdown(content)
    content_group = Group(*renderables) if renderables else Text()
    console.print()
    console.push_theme(MARKDOWN_THEME)
    try:
        console.print(
            Panel(
                content_group,
                title=title,
                subtitle=subtitle,
                border_style="bright_cyan",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
    finally:
        console.pop_theme()
    console.print()
    return content


# ---------------------------------------------------------------------------
# Prompt input box
# ---------------------------------------------------------------------------

def prompt_box(label, prompt_text="", width=None):
    """A clean, width-aware input prompt box with a labeled header.

    Returns the user's trimmed input.
    """
    term_width = width or console.width or 80

    box_content = Text(prompt_text, style="dim") if prompt_text else Text("Type your message and press Enter...", style="dim")

    console.print()
    console.print(
        Panel(
            box_content,
            title=label,
            border_style="bright_yellow",
            box=box.ROUNDED,
            padding=(0, 1),
            width=term_width,
        )
    )
    answer = Prompt.ask("", console=console)
    console.print()
    return answer.strip()
