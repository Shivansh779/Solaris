from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box
from rich.rule import Rule
from rich.style import Style

console = Console()


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
        expand=True,
    )
    col_styles = col_styles or {}
    for i, header in enumerate(headers):
        table.add_column(header, style=col_styles.get(i, "white"), header_style="bold bright_cyan")
    for row in rows:
        table.add_row(*row)
    return table


def display_table(headers, rows, title=None, col_styles=None):
    table = build_table(headers, rows, title, col_styles)
    console.print(table)


def display_quiz(questions_text):
    system_log("AI", "INFO", "Displaying quiz content")
    display(questions_text, title="Quiz Questions")


def display_timeline(events_text):
    system_log("AI", "INFO", "Displaying timeline content")
    display(events_text, title="Timeline")


def display_steps(steps_text):
    system_log("AI", "INFO", "Displaying steps content")
    display(steps_text, title="Steps")


def display_detail(content):
    system_log("AI", "INFO", "Displaying detailed explanation")
    display(content, title="Detailed Explanation")


def display_simple(content):
    system_log("AI", "INFO", "Displaying simple explanation")
    display(content, title="Simple Explanation")


def display_compare(content):
    system_log("AI", "INFO", "Displaying comparison content")
    display(content, title="Comparison")