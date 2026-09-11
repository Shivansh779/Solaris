from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.rule import Rule
from rich.style import Style
from rich.markdown import Markdown
from rich.prompt import Prompt
from rich.text import Text
from rich.theme import Theme

from _log import system_log, current_time

console = Console()

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

def render_markdown(content):
    """Convert AI Markdown content into a list of Rich renderables."""
    return [Markdown(content, justify="left")]


def display_markdown(content, title="Solaris", subtitle=None):
    """Render AI Markdown inside a readable panel."""
    system_log("AI", "INFO", f"Displaying rendered content: {title}")
    console.print()
    console.push_theme(MARKDOWN_THEME)
    try:
        console.print(
            Panel(
                Markdown(content, justify="left"),
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
