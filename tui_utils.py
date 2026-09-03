from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich import box
from rich.rule import Rule
from rich.style import Style

console = Console()

STYLES = {
    "header": Style(color="bright_cyan", bold=True),
    "subtitle": Style(color="bright_magenta", bold=True),
    "accent": Style(color="bright_yellow"),
    "success": Style(color="bright_green"),
    "error": Style(color="bright_red"),
    "dim": Style(dim=True),
}


def display(content, title="Solaris", subtitle=None):
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
    display(questions_text, title="Quiz Questions")


def display_quiz_results(score, total, details):
    percentage = round((score / total) * 100, 1) if total > 0 else 0

    summary_lines = []
    summary_lines.append(f"[bold bright_cyan]Score: {score}/{total}[/]")
    summary_lines.append(
        f"[bold {'bright_green' if percentage >= 50 else 'bright_red'}]Percentage: {percentage}%[/]"
    )

    grade = "A" if percentage >= 90 else "B" if percentage >= 80 else "C" if percentage >= 70 else "D" if percentage >= 60 else "F"
    summary_lines.append(f"[bold]Grade: {grade}[/]")
    summary_lines.append("")
    summary_lines.append("[bold]Detailed Breakdown:[/]")
    for d in details:
        status = "[green]Correct[/green]" if d["correct"] else "[red]Wrong[/red]"
        summary_lines.append(
            f"  Q{d['q']}: {status} — Your answer: [yellow]{d['user_answer']}[/yellow] "
            f"| Correct: [green]{d['correct_answer']}[/green]"
        )
        if d.get("explanation"):
            summary_lines.append(f"    [dim]{d['explanation']}[/dim]")

    console.print()
    console.print(
        Panel(
            "\n".join(summary_lines),
            title="Quiz Results",
            border_style="bright_green" if percentage >= 50 else "bright_red",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()


def display_timeline(events_text):
    display(events_text, title="Timeline")


def display_steps(steps_text):
    display(steps_text, title="Steps")


def display_detail(content):
    display(content, title="Detailed Explanation")


def display_simple(content):
    display(content, title="Simple Explanation")


def display_compare(content):
    display(content, title="Comparison")