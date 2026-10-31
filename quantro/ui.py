"""
Quantro Terminal UI Engine
Claude Code & OpenCode inspired inline scrollback interface powered by Rich.
Features colored diffs, branch tool call logs, status spinners, and markdown responses.
"""

from contextlib import contextmanager
from typing import Optional, Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.markdown import Markdown
from rich.table import Table

console = Console(highlight=False)


def print_banner(version: str, model: str, provider: str, project_root: str):
    """Renders the startup banner in the terminal scrollback."""
    title_text = Text()
    title_text.append("⚡ ", style="bold yellow")
    title_text.append("QUANTRO", style="bold cyan")
    title_text.append(f" v{version}", style="dim")
    title_text.append(" — Autonomous Terminal Coding Agent\n", style="bold white")

    info_text = Text()
    info_text.append("  • Model: ", style="bold green")
    info_text.append(f"{model} ", style="white")
    info_text.append(f"({provider})\n", style="dim cyan")
    info_text.append("  • Project: ", style="bold green")
    info_text.append(f"{project_root}\n", style="white")
    info_text.append("  • Tip: ", style="bold yellow")
    info_text.append("Type ", style="dim")
    info_text.append("/help", style="bold magenta")
    info_text.append(" for slash commands or enter your request directly.", style="dim")

    panel = Panel(
        info_text,
        title=title_text,
        title_align="left",
        border_style="cyan",
        padding=(0, 1),
    )
    console.print(panel)


def print_tool_start(tool_name: str, args_summary: str):
    """Prints start of a tool call with Claude Code branch symbol."""
    t = Text()
    t.append("● ", style="bold cyan")
    t.append(f"{tool_name}", style="bold white")
    t.append(f"({args_summary})", style="dim")
    console.print(t)


def print_tool_result(result_text: str, success: bool = True):
    """Prints tool completion summary."""
    t = Text()
    prefix = "  ⎿  "
    style = "green" if success else "red"
    t.append(prefix, style="dim cyan")
    t.append(result_text, style=style)
    console.print(t)


def print_diff(diff_content: str, filename: str = ""):
    """Renders a colorized unified diff inside an elegant panel."""
    if not diff_content.strip():
        return

    # Colorize lines
    colored_text = Text()
    for line in diff_content.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            colored_text.append(line + "\n", style="bold yellow")
        elif line.startswith("@@"):
            colored_text.append(line + "\n", style="bold cyan")
        elif line.startswith("+"):
            colored_text.append(line + "\n", style="green")
        elif line.startswith("-"):
            colored_text.append(line + "\n", style="red")
        else:
            colored_text.append(line + "\n", style="dim")

    title = f"Diff Preview: {filename}" if filename else "Code Changes"
    panel = Panel(
        colored_text,
        title=title,
        title_align="left",
        border_style="dim green",
        padding=(0, 1)
    )
    console.print(panel)


def print_thinking(thought: str):
    """Displays the agent's internal reasoning in a subtle dimmed box."""
    if not thought.strip():
        return
    text = Text(thought.strip(), style="italic dim white")
    panel = Panel(
        text,
        title="💭 Reasoning",
        title_align="left",
        border_style="dim blue",
        padding=(0, 1)
    )
    console.print(panel)


def print_markdown(content: str):
    """Renders rich markdown formatted responses."""
    if not content.strip():
        return
    md = Markdown(content)
    console.print()
    console.print(md)
    console.print()


def print_error(message: str, title: str = "Hata"):
    """Prints error banner."""
    panel = Panel(
        Text(message, style="bold red"),
        title=f"❌ {title}",
        title_align="left",
        border_style="red",
        padding=(0, 1)
    )
    console.print(panel)


def print_success(message: str, title: str = "Başarılı"):
    """Prints success banner."""
    panel = Panel(
        Text(message, style="bold green"),
        title=f"✓ {title}",
        title_align="left",
        border_style="green",
        padding=(0, 1)
    )
    console.print(panel)


def print_cost_table(metrics: Dict[str, Any]):
    """Renders session token and cost metrics table."""
    table = Table(title="Quantro Session Metrics", border_style="cyan")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="cyan")

    table.add_row("Input Tokens", f"{metrics.get('input_tokens', 0):,}")
    table.add_row("Output Tokens", f"{metrics.get('output_tokens', 0):,}")
    table.add_row("Total Tokens", f"{metrics.get('total_tokens', 0):,}")
    table.add_row("Total Cost (USD)", metrics.get("formatted_cost", "$0.0000"))
    table.add_row("Conversation Turns", str(metrics.get("turn_count", 0)))

    console.print()
    console.print(table)
    console.print()


def print_help_table():
    """Renders slash command help table."""
    table = Table(title="Quantro Slash Commands (/)", border_style="magenta")
    table.add_column("Command", style="bold magenta")
    table.add_column("Description", style="white")

    table.add_row("/help", "Show this commands reference list")
    table.add_row("/model [name]", "Show or switch active LLM model & provider")
    table.add_row("/init", "Scan project and generate/update QUANTRO.md guide")
    table.add_row("/diff", "Show git status diff or last file modification")
    table.add_row("/undo", "Revert the last file modification made by agent")
    table.add_row("/compact", "Compress conversation history to free token space")
    table.add_row("/cost", "Display token usage and estimated USD cost breakdown")
    table.add_row("/clear", "Clear the terminal screen")
    table.add_row("/exit, /quit", "Exit the Quantro interactive session")

    console.print()
    console.print(table)
    console.print()


@contextmanager
def status_spinner(message: str):
    """Context manager for inline live spinner."""
    with console.status(f"[bold cyan]{message}[/bold cyan]", spinner="dots") as status:
        yield status
