"""
Quantro 2.0 OpenCode-Inspired Terminal UI Engine
Engineered with Rich for high-density, beautiful inline scrollback visual telemetry.
Features session cards, step timelines, colored diff boxes, role badges, and status spinners.
"""

from contextlib import contextmanager
from typing import Dict, Any, List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.table import Table
from rich.markdown import Markdown

from quantro.agent.roles import ROLE_DEFINITIONS

console = Console(highlight=False)


def render_header(
    session_id: str,
    model: str,
    provider: str,
    project_dir: str,
    role: str = "build",
    tokens: int = 0,
    cost: float = 0.0
):
    """Renders the top OpenCode 2.0 session dashboard bar."""
    role_info = ROLE_DEFINITIONS.get(role, ROLE_DEFINITIONS["build"])
    badge_color = role_info.get("color", "cyan")
    badge_name = role_info.get("badge", "BUILD")

    title_text = Text()
    title_text.append("⚡ QUANTRO ", style="bold cyan")
    title_text.append("2.0 ", style="bold white")
    title_text.append(f"[{badge_name}]", style=f"bold {badge_color}")

    grid = Table.grid(expand=True)
    grid.add_column(justify="left")
    grid.add_column(justify="right")

    left_text = Text()
    left_text.append("📂 ", style="dim")
    left_text.append(f"{project_dir}\n", style="white")
    left_text.append("🤖 ", style="dim")
    left_text.append(f"{model} ", style="cyan")
    left_text.append(f"({provider})", style="dim cyan")

    right_text = Text()
    right_text.append(f"Session: {session_id[:8]}\n", style="dim yellow")
    right_text.append(f"Tokens: {tokens:,} │ Cost: ${cost:.4f}", style="dim green")

    grid.add_row(left_text, right_text)

    panel = Panel(
        grid,
        title=title_text,
        title_align="left",
        border_style="cyan",
        padding=(0, 1)
    )
    console.print(panel)


def render_step_header(step_idx: int, description: str = ""):
    """Prints start of an execution step."""
    t = Text()
    t.append(f"┌─ Step {step_idx}", style="bold cyan")
    if description:
        t.append(f" · {description}", style="bold white")
    console.print(t)


def render_tool_call(tool_name: str, args_summary: str):
    """Prints a tool call item inside the timeline."""
    t = Text()
    t.append("│ ⚡ ", style="bold yellow")
    t.append(f"{tool_name}", style="bold white")
    t.append(f"({args_summary})", style="dim")
    console.print(t)


def render_tool_result(result_text: str, success: bool = True):
    """Prints tool result line."""
    t = Text()
    t.append("│   ↳ ", style="dim cyan")
    t.append(result_text, style="green" if success else "red")
    console.print(t)


def render_step_footer(status: str = "Completed"):
    """Prints step conclusion line."""
    t = Text()
    t.append(f"└─ ✓ {status}\n", style="dim cyan")
    console.print(t)


def render_diff(diff_content: str, filename: str = "", additions: int = 0, deletions: int = 0):
    """Renders OpenCode 2.0 unified diff panel with additions/deletions badge."""
    if not diff_content.strip():
        return

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

    title = Text()
    title.append(f"Diff: {filename} " if filename else "Code Diff ")
    if additions or deletions:
        title.append(f"(+{additions} -{deletions})", style="bold yellow")

    panel = Panel(
        colored_text,
        title=title,
        title_align="left",
        border_style="dim green",
        padding=(0, 1)
    )
    console.print(panel)


def render_reasoning(thought: str):
    """Displays chain-of-thought in a subtle box."""
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


def render_markdown(content: str):
    """Renders formatted markdown."""
    if not content.strip():
        return
    md = Markdown(content)
    console.print()
    console.print(md)
    console.print()


def render_sessions_table(sessions: List[Any]):
    """Renders session list table for 'quantro session list'."""
    table = Table(title="Quantro Sessions", border_style="cyan")
    table.add_column("ID", style="bold cyan", width=10)
    table.add_column("Title", style="bold white", width=35)
    table.add_column("Model", style="yellow")
    table.add_column("Tokens", justify="right", style="green")
    table.add_column("Cost", justify="right", style="green")
    table.add_column("Turns", justify="right", style="white")

    for s in sessions:
        table.add_row(
            s.id,
            s.title,
            s.model,
            f"{s.total_tokens:,}",
            f"${s.total_cost_usd:.4f}",
            str(s.turn_count)
        )

    console.print()
    console.print(table)
    console.print()


def render_models_table(providers: Dict[str, Any], active_model: str):
    """Renders supported models for 'quantro models'."""
    table = Table(title="Available LLM Providers & Recommended Models", border_style="cyan")
    table.add_column("Provider", style="bold cyan")
    table.add_column("Default Model", style="yellow")
    table.add_column("Recommended Models", style="white")

    for p_id, p_info in providers.items():
        recs = ", ".join(p_info.get("recommended_models", []))
        table.add_row(
            p_info.get("name", p_id),
            p_info.get("default_model", ""),
            recs
        )

    console.print()
    console.print(table)
    console.print()


def render_stats_table(stats_data: Dict[str, Any]):
    """Renders analytics summary for 'quantro stats'."""
    table = Table(title="Quantro Usage & Telemetry Stats", border_style="magenta")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="cyan")

    for k, v in stats_data.items():
        table.add_row(k, str(v))

    console.print()
    console.print(table)
    console.print()


def render_help():
    """Renders slash commands and CLI guidance."""
    table = Table(title="Quantro 2.0 Commands", border_style="cyan")
    table.add_column("Slash Command", style="bold magenta")
    table.add_column("Description", style="white")

    table.add_row("/help", "Show all interactive slash commands")
    table.add_row("/agent [build|plan|review|test]", "Switch specialized agent role")
    table.add_row("/model [name]", "View or switch active LLM model")
    table.add_row("/session [list|new|<id>]", "Manage or resume sessions")
    table.add_row("/init", "Scan project and generate/update QUANTRO.md")
    table.add_row("/diff", "Show git diff or last agent file change")
    table.add_row("/undo", "Revert last file modification")
    table.add_row("/compact", "Compress history to free token context")
    table.add_row("/cost", "Show current session cost breakdown")
    table.add_row("/clear", "Clear terminal screen")
    table.add_row("/exit, /quit", "Save and exit session")

    console.print()
    console.print(table)
    console.print()


@contextmanager
def spinner(message: str):
    with console.status(f"[bold cyan]{message}[/bold cyan]", spinner="dots") as status:
        yield status
