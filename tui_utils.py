from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.rule import Rule
from rich.style import Style
from rich.markdown import Markdown as RichMarkdown
from rich.markdown import CodeBlock as RichCodeBlock
from rich.markup import escape
from rich.syntax import Syntax
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
        "markdown.link": "underline bright_blue",
        "markdown.link_url": "dim",
        "markdown.block_quote": "italic",
        "markdown.hr": "dim",
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


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

class CodeBlock(RichCodeBlock):
    """A fenced code block as its own bordered card.

    The language stays in the border and the indentation is kept, so the block
    reads as code even without colour. Highlighting is free: rich already
    ships with pygments.
    """

    def __rich_console__(self, console, options):
        code = str(self.text).rstrip()
        syntax = Syntax(code, self.lexer_name, theme=self.theme, word_wrap=True, padding=0)
        yield Panel(
            syntax,
            title=self.lexer_name,
            title_align="left",
            border_style="dim",
            box=box.ROUNDED,
            padding=(0, 1),
        )


class Markdown(RichMarkdown):
    """Markdown with visible link URLs and boxed code blocks."""

    elements = {**RichMarkdown.elements, "fence": CodeBlock, "code_block": CodeBlock}

    def __init__(self, markup, *args, **kwargs):
        kwargs.setdefault("justify", "left")
        kwargs.setdefault("hyperlinks", False)   # a terminal cannot follow a link
        super().__init__(markup, *args, **kwargs)


def _fit(text, width, keep=6):
    """Shorten a panel title so it can never break the card's border."""
    text = str(text)
    room = max(8, (width or 80) - keep)
    if len(text) <= room:
        return text
    return text[: room - 1].rstrip() + "…"


def display(content, title="Solaris", subtitle=None):
    """Display plain content inside a panel (no Markdown parsing)."""
    system_log("AI", "INFO", f"Displaying panel: {title}")
    # Plain text, never markup: model output and file content may contain "[".
    body = Text(content) if isinstance(content, str) else content
    console.print()
    console.print(
        Panel(
            body,
            title=_fit(title, console.width),
            subtitle=_fit(subtitle, console.width) if subtitle else None,
            border_style="bright_cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()


def display_inline(text):
    console.print(text)


def error(text):
    """An error the user can read without colour."""
    console.print(f"[bold red]Error:[/] {escape(str(text))}")


def warn(text):
    """A warning the user can read without colour."""
    console.print(f"[bold yellow]Warning:[/] {escape(str(text))}")


def ok(text):
    """A confirmation the user can read without colour."""
    console.print(f"[bold green]OK:[/] {escape(str(text))}")


def info(text):
    """A neutral note the user can read without colour."""
    console.print(f"[bold cyan]Note:[/] {escape(str(text))}")


def rule():
    console.print(Rule(style="bright_cyan"))


def build_table(headers, rows, title=None, col_styles=None, expand=True):
    table = Table(
        title=title,
        box=box.ROUNDED,
        title_style="bold bright_cyan",
        header_style="bold bright_cyan",
        expand=expand,
    )
    col_styles = col_styles or {}
    for i, header in enumerate(headers):
        # overflow="fold" wraps a long cell (a URL, a path) instead of cutting it off.
        table.add_column(str(header), style=col_styles.get(i, "white"), overflow="fold")
    for row in rows:
        table.add_row(*[str(c) for c in row])
    return table


def display_table(headers, rows, title=None, col_styles=None, expand=True):
    table = build_table(headers, rows, title, col_styles, expand)
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
                title=_fit(title, console.width),
                subtitle=_fit(subtitle, console.width) if subtitle else None,
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
# Cards for the shared core: pulse, sources, refinements
# ---------------------------------------------------------------------------

def display_pulse(pulse, title="Privacy Pulse"):
    """The privacy pulse of one answer: route, provider, context, fallbacks.

    Every line carries a label, so it still reads in a terminal without colour.
    """
    if not pulse:
        return

    classification = str(pulse.get("classification") or "unknown")
    provider = pulse.get("provider")
    if not provider:
        # Flows that pick their own model do not name the winner — show the
        # candidate providers instead of claiming one of them answered.
        names = []
        for step in pulse.get("steps") or []:
            name = step.get("provider")
            if name and name not in names:
                names.append(name)
        provider = ", ".join(f"{name} (candidate)" for name in names)
    provider = provider or "not recorded"
    model = pulse.get("model") or "not recorded"
    latency = pulse.get("latency_ms")

    rows = [
        ("Route", f"{classification} — provider: {provider}, model: {model}"),
        ("Latency", f"{latency / 1000:.1f}s" if latency is not None else "not recorded"),
    ]

    context = []
    memories = pulse.get("memories") or 0
    if memories:
        context.append(f"{memories} memory node{'s' if memories != 1 else ''}")
    files = pulse.get("files_selected") or 0
    if files:
        context.append(f"{files} file{'s' if files != 1 else ''}")
    skills = pulse.get("skills") or []
    if skills:
        context.append(f"{len(skills)} skill{'s' if len(skills) != 1 else ''}: {', '.join(skills)}")
    rows.append(("In prompt", ", ".join(context) or "no memories, files or skills"))

    fallbacks = [str(item) for item in (pulse.get("fallbacks") or [])]
    if fallbacks:
        rows.append(("Fallbacks", " ".join(fallbacks)))
    if pulse.get("web_search"):
        rows.append(("Web search", "used"))
    if pulse.get("study_trail"):
        rows.append(("Study trail", str(pulse["study_trail"])))

    width = max(len(key) for key, _ in rows)
    body = Text()
    for index, (key, value) in enumerate(rows):
        body.append(f"{key.ljust(width)}  ", style="bold bright_cyan")
        body.append(f"{value}\n" if index < len(rows) - 1 else value)
    display(body, title=title)


def display_sources(sources, title="Sources"):
    """Web sources as a numbered list: [1] Python docs (tavily) — never a URL dump."""
    if not sources:
        return
    lines = []
    for index, source in enumerate(sources, 1):
        label = f"[{index}] {source.get('title') or 'Untitled'}"
        provider = source.get("source")
        if provider:
            label += f" ({provider})"
        lines.append(label)
        url = source.get("url")
        if url:
            lines.append(f"    {url}")
    display(Text("\n".join(lines)), title=title)


def display_controls(controls, title="Refine this answer"):
    """The shared answer controls, numbered so one can be picked."""
    rows = [
        (str(index), control.get("label", ""), control.get("hint", ""))
        for index, control in enumerate(controls, 1)
    ]
    display_table(["#", "Refinement", "What it does"], rows, title=title)


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
