"""
Quantro 2.0 OpenCode-Authentic Terminal UI Engine
Faithfully replicates OpenCode's iconic block font, centered layout, metadata card,
step timelines, unified diff panels, and alternate-screen buffer workspace.
"""

import os
import sys
import atexit
import platform
import subprocess
from pathlib import Path
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

# Track alternate screen buffer state
_in_alt_screen = False


def enter_alternate_screen():
    """Switches the terminal to the dedicated alternate screen buffer (clean new page)."""
    global _in_alt_screen
    if not _in_alt_screen and sys.stdout.isatty():
        sys.stdout.write("\033[?1049h\033[2J\033[H")
        sys.stdout.flush()
        _in_alt_screen = True


def leave_alternate_screen():
    """Restores the original terminal screen buffer upon exit."""
    global _in_alt_screen
    if _in_alt_screen and sys.stdout.isatty():
        sys.stdout.write("\033[?1049l")
        sys.stdout.flush()
        _in_alt_screen = False


atexit.register(leave_alternate_screen)

# Authentic OpenCode block font logo for QUANTRO
OPENCODE_LOGO = [
    "█▀▀█ █  █ █▀▀█ █▀▀▄ ▀█▀ █▀▀█ █▀▀█",
    "█  █ █  █ █▄▄█ █  █  █  █▄▄▀ █  █",
    "▀▀▀█ ▀▀▀▀ ▀  ▀ ▀  ▀  ▀  ▀  ▀ ▀▀▀▀"
]


def _get_workspace_meta(project_root: Path) -> Dict[str, Any]:
    """Collects git branch, dirty status, file count, and stack."""
    branch = "no-git"
    git_status = "clean"
    try:
        res = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, cwd=str(project_root), timeout=2
        )
        if res.returncode == 0 and res.stdout.strip():
            branch = res.stdout.strip()
            st_res = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, cwd=str(project_root), timeout=2
            )
            dirty_count = len([l for l in st_res.stdout.splitlines() if l.strip()])
            git_status = f"±{dirty_count}" if dirty_count > 0 else "clean"
    except Exception:
        pass

    file_count = 0
    try:
        for root, dirs, files in os.walk(project_root):
            dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__", ".venv", ".cache"} and not d.startswith(".")]
            file_count += len([f for f in files if not f.startswith(".")])
            if file_count > 300:
                break
    except Exception:
        pass

    # Abbreviate path with ~
    home_dir = str(Path.home())
    display_path = str(project_root)
    if display_path.startswith(home_dir):
        display_path = "~" + display_path[len(home_dir):]

    return {
        "display_path": display_path,
        "branch": branch,
        "git_status": git_status,
        "file_count": file_count
    }


def render_system_launch(
    session_id: str,
    model: str,
    provider: str,
    project_dir: str,
    role: str = "build",
    tokens: int = 0,
    cost: float = 0.0,
    session_title: str = "New Session"
):
    """
    Renders OpenCode's signature centered home screen inside alternate screen buffer.
    """
    enter_alternate_screen()

    project_path = Path(project_dir).resolve()
    meta = _get_workspace_meta(project_path)
    role_info = ROLE_DEFINITIONS.get(role, ROLE_DEFINITIONS["build"])
    badge = role_info.get("badge", "BUILD").lower()

    # Top spacing
    console.print()

    # 1. OpenCode-style Block Logo (Centered)
    logo_text = Text()
    for line in OPENCODE_LOGO:
        logo_text.append(f"          {line}\n", style="bold white")
    logo_text.append("                  q u a n t r o   v 2 . 0\n", style="dim white")
    console.print(logo_text)

    # 2. OpenCode Main Environment Card
    card_content = Text()
    card_content.append("  Ask a question, edit code, or run terminal commands...\n\n", style="dim white")
    card_content.append("  ────────────────────────────────────────────────────────────────\n", style="dim white")
    card_content.append(f"  {meta['display_path']}", style="bold white")
    if meta['branch'] != "no-git":
        card_content.append(f":{meta['branch']}", style="white")
    card_content.append("  ·  ⊙ 13 Tools", style="white")
    card_content.append(f"  ·  {model} [{badge}]\n", style="bold white")

    panel = Panel(
        card_content,
        border_style="dim white",
        padding=(0, 1)
    )
    console.print(panel)

    # 3. OpenCode Shortcuts & Tips Footer
    shortcuts = Text()
    shortcuts.append("  Tab ", style="bold white")
    shortcuts.append("Complete   ", style="dim")
    shortcuts.append("/ ", style="bold white")
    shortcuts.append("Commands   ", style="dim")
    shortcuts.append("@ ", style="bold white")
    shortcuts.append("Mention file   ", style="dim")
    shortcuts.append("/commit ", style="bold white")
    shortcuts.append("Git commit   ", style="dim")
    shortcuts.append("/review ", style="bold white")
    shortcuts.append("Review   ", style="dim")
    shortcuts.append("^C ", style="bold white")
    shortcuts.append("Cancel\n", style="dim")

    console.print(shortcuts)
    console.print("[dim]  Tip: Press @ to search and reference project files directly into context.[/dim]\n")


def render_step_header(step_idx: int, description: str = ""):
    """Prints start of an execution step."""
    t = Text()
    t.append(f"┌ Step {step_idx}", style="bold white")
    if description:
        t.append(f" · {description}", style="dim white")
    console.print(t)


def render_tool_call(tool_name: str, args_summary: str):
    """Prints a tool call item inside the timeline."""
    t = Text()
    t.append("│ ", style="dim white")
    t.append("● ", style="white")
    t.append(f"{tool_name}", style="bold white")
    t.append(f"({args_summary})", style="dim")
    console.print(t)


def render_tool_result(result_text: str, success: bool = True):
    """Prints tool result line."""
    t = Text()
    t.append("│   ↳ ", style="dim white")
    t.append(result_text, style="white" if success else "red")
    console.print(t)


def render_step_footer(status: str = "Completed"):
    """Prints step conclusion line."""
    t = Text()
    t.append(f"└ ✓ {status}\n", style="dim white")
    console.print(t)


def render_diff(diff_content: str, filename: str = "", additions: int = 0, deletions: int = 0):
    """Renders unified diff panel with clean monochromatic borders."""
    if not diff_content.strip():
        return

    colored_text = Text()
    for line in diff_content.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            colored_text.append(line + "\n", style="bold white")
        elif line.startswith("@@"):
            colored_text.append(line + "\n", style="dim cyan")
        elif line.startswith("+"):
            colored_text.append(line + "\n", style="green")
        elif line.startswith("-"):
            colored_text.append(line + "\n", style="red")
        else:
            colored_text.append(line + "\n", style="dim")

    title = Text()
    title.append(f"Diff: {filename} " if filename else "Code Diff ")
    if additions or deletions:
        title.append(f"(+{additions} -{deletions})", style="bold white")

    panel = Panel(
        colored_text,
        title=title,
        title_align="left",
        border_style="dim white",
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
        title="Reasoning",
        title_align="left",
        border_style="dim white",
        padding=(0, 1)
    )
    console.print(panel)


def stream_token(token: str, is_reasoning: bool = False):
    """Streams tokens live to the terminal as they are produced by LLM."""
    if is_reasoning:
        sys.stdout.write(f"\033[2;37m{token}\033[0m")
    else:
        sys.stdout.write(token)
    sys.stdout.flush()


def stream_start_reasoning():
    console.print("[dim]Thinking...[/dim]")


def stream_end():
    sys.stdout.write("\n")
    sys.stdout.flush()


def render_interrupted():
    console.print("\n[dim](Cancelled via Ctrl+C)[/dim]\n")


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
    table = Table(title="Sessions", border_style="dim white")
    table.add_column("ID", style="bold white", width=10)
    table.add_column("Title", style="white", width=35)
    table.add_column("Model", style="dim white")
    table.add_column("Tokens", justify="right", style="white")
    table.add_column("Cost", justify="right", style="white")
    table.add_column("Turns", justify="right", style="dim")

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
    table = Table(title="LLM Providers & Models", border_style="dim white")
    table.add_column("Provider", style="bold white")
    table.add_column("Default Model", style="white")
    table.add_column("Recommended Models", style="dim")

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
    table = Table(title="Usage & Telemetry", border_style="dim white")
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="white")

    for k, v in stats_data.items():
        table.add_row(k, str(v))

    console.print()
    console.print(table)
    console.print()


def render_help():
    """Renders slash commands and CLI guidance."""
    table = Table(title="Quantro Commands", border_style="dim white")
    table.add_column("Command / Hotkey", style="bold white", width=22)
    table.add_column("Description", style="white")

    table.add_row("/help", "Show all interactive slash commands")
    table.add_row("@<file>", "Fuzzy file reference (e.g. @app.py) auto-completes and injects file")
    table.add_row("/agent [role]", "Switch role: build (coder), plan (architect), review (audit), test (QA)")
    table.add_row("/model [name]", "View or switch active LLM model/provider")
    table.add_row("/commit", "Analyze git diff and generate conventional commit automatically")
    table.add_row("/review", "Audit current git changes and run Senior Code Review")
    table.add_row("/session [list|new|<id>]", "Manage, list, or resume sessions")
    table.add_row("/skills", "List discovered repository and user skills")
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
    with console.status(f"[dim white]{message}[/dim white]", spinner="dots") as status:
        yield status
