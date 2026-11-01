"""
Quantro 2.0 CLI & Interactive REPL
Implements OpenCode 2.0 subcommands, @ fuzzy file mentions, /commit and /review Git automations,
and resilient Ctrl+C interrupt handling.
"""

import os
import re
import sys
import argparse
import subprocess
from pathlib import Path
from typing import Iterable, List
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.styles import Style

from quantro import __version__
from quantro.config import config_manager, DEFAULT_PROVIDERS
from quantro.session import Session, session_store
from quantro.agent import AgentEngine, ROLE_DEFINITIONS
from quantro.skills import SkillManager
from quantro import ui

SLASH_COMMANDS = [
    "/help",
    "/agent",
    "/model",
    "/commit",
    "/review",
    "/session",
    "/skills",
    "/init",
    "/diff",
    "/undo",
    "/compact",
    "/cost",
    "/clear",
    "/exit",
    "/quit"
]

prompt_style = Style.from_dict({
    "prompt": "bold #ffffff",
    "bottom-toolbar": "bg:#18181b #a1a1aa",
})


class QuantroCompleter(Completer):
    """
    Intelligent auto-completer:
    1. Completes / slash commands when line starts with /
    2. Completes @ file paths dynamically with fuzzy matching across project repository
    """

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def _get_project_files(self) -> List[str]:
        file_list: List[str] = []
        try:
            for root, dirs, files in os.walk(self.project_root):
                dirs[:] = [d for d in dirs if d not in {".git", "node_modules", "__pycache__", ".venv", ".cache"} and not d.startswith(".")]
                for f in files:
                    if not f.startswith("."):
                        full = Path(root) / f
                        try:
                            rel = full.relative_to(self.project_root)
                            file_list.append(str(rel))
                        except Exception:
                            file_list.append(f)
                if len(file_list) > 600:
                    break
        except Exception:
            pass
        return file_list

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        text = document.text_before_cursor

        # 1. Slash command completion
        if text.startswith("/"):
            word = text.strip()
            for cmd in SLASH_COMMANDS:
                if cmd.startswith(word):
                    yield Completion(cmd, start_position=-len(text))
            return

        # 2. @ file mention completion
        at_match = re.search(r"@([a-zA-Z0-9_\-\./]*)$", text)
        if at_match:
            sub = at_match.group(1).lower()
            start_pos = -len(sub) - 1
            files = self._get_project_files()
            for f in files:
                f_lower = f.lower()
                if sub in f_lower or not sub:
                    yield Completion(f"@{f}", start_position=start_pos, display=f"@{f}")


def expand_file_mentions(prompt: str, project_root: Path) -> str:
    """
    Finds @filepath occurrences in the user prompt and injects their content into the agent context.
    """
    mentions = re.findall(r"@([a-zA-Z0-9_\-\./]+)", prompt)
    if not mentions:
        return prompt

    injected_sections: List[str] = []
    seen = set()

    for m in mentions:
        if m in seen:
            continue
        seen.add(m)
        target = Path(m).expanduser()
        if not target.is_absolute():
            target = project_root / target

        if target.exists() and target.is_file():
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
                injected_sections.append(
                    f"\n--- [REFERENCED FILE: {m}] ---\n{content}\n--- [END OF {m}] ---\n"
                )
            except Exception:
                pass

    if injected_sections:
        return prompt + "\n" + "\n".join(injected_sections)
    return prompt


def handle_git_commit(engine: AgentEngine, session: Session):
    """
    Autonomous Git commit generator:
    Inspects diff, calls LLM to generate conventional commit, prompts user, and commits.
    """
    diff_res = engine.executor.shell.run_bash("git diff HEAD", auto_approve=True)
    if not diff_res.get("success") or not diff_res.get("output") or "(Komut sessizce" in diff_res.get("output"):
        diff_res = engine.executor.shell.run_bash("git status -s", auto_approve=True)
        if not diff_res.get("output") or "(Komut sessizce" in diff_res.get("output"):
            ui.console.print("[dim]Değişiklik bulunamadı (Working tree clean).[/dim]")
            return

    diff_text = diff_res.get("output", "")[:4000]

    ui.console.print("[cyan]Git diff analiz ediliyor ve commit mesajı üretiliyor...[/cyan]")
    prompt = (
        "Generate a single-line conventional commit message (e.g. 'feat(auth): add jwt support' or 'fix(cli): resolve path error') "
        "based strictly on this git diff. Output ONLY the commit message itself, nothing else:\n\n"
        + diff_text
    )

    commit_msg = engine.run(prompt, max_steps=1).strip().replace('"', '')
    # If returned as markdown code, clean it
    commit_msg = re.sub(r"^`+|`+$", "", commit_msg).strip()

    ui.console.print(f"\n[bold green]Önerilen Commit Mesajı:[/bold green] [yellow]\"{commit_msg}\"[/yellow]")
    choice = input("Değişiklikler stage edilip commit atılsın mı? [E/H]: ").strip().lower()
    if choice in ("e", "evet", "y", "yes", ""):
        engine.executor.shell.run_bash("git add -A", auto_approve=True)
        res = engine.executor.shell.run_bash(f'git commit -m "{commit_msg}"', auto_approve=True)
        if res.get("success"):
            ui.console.print(f"[bold green]✓ Commit başarıyla oluşturuldu:[/bold green] {commit_msg}")
        else:
            ui.console.print(f"[bold red]Commit hatası:[/bold red] {res.get('output')}")


def handle_git_review(engine: AgentEngine, session: Session):
    """
    Autonomous Senior Code Review:
    Audits current git diff against HEAD and prints findings.
    """
    diff_res = engine.executor.shell.run_bash("git diff HEAD", auto_approve=True)
    diff_text = diff_res.get("output", "")
    if not diff_text or "(Komut sessizce" in diff_text:
        ui.console.print("[dim]İncelenecek git değişikliği bulunamadı (git diff HEAD boş).[/dim]")
        return

    old_role = config_manager.active_agent
    config_manager.active_agent = "review"

    ui.console.print("[bold magenta]🔍 Kıdemli Kod İncelemesi (Senior Code Review) Başlatılıyor...[/bold magenta]")
    review_prompt = (
        "Lütfen aşağıdaki git değişikliklerini ayrıntılı olarak incele:\n"
        "1. Potansiyel mantık ve sözdizimi hataları (bugs)\n"
        "2. Güvenlik açıkları ve sınır durumlar (edge-cases)\n"
        "3. Mimari ve okunabilirlik önerileri\n\n"
        + diff_text[:7000]
    )

    engine.run(review_prompt, max_steps=5)
    config_manager.active_agent = old_role


def handle_slash_command(cmd_line: str, session: Session, engine: AgentEngine) -> bool:
    """Handles interactive slash commands. Returns False to exit session."""
    parts = cmd_line.strip().split()
    cmd = parts[0].lower()
    args = parts[1:]

    if cmd in ("/exit", "/quit"):
        return False

    elif cmd == "/help":
        ui.render_help()

    elif cmd == "/commit":
        handle_git_commit(engine, session)

    elif cmd == "/review":
        handle_git_review(engine, session)

    elif cmd == "/agent":
        if not args:
            if sys.stdout.isatty():
                selected = ui.open_agent_dialog(config_manager.active_agent)
                if selected and selected in ROLE_DEFINITIONS:
                    config_manager.active_agent = selected
                    badge = ROLE_DEFINITIONS[selected]["badge"]
                    ui.console.print(f"[bold green]✓ Ajan modu değiştirildi:[/bold green] [{badge}] ({ROLE_DEFINITIONS[selected]['name']})")
            else:
                ui.console.print(f"\n[bold]Aktif Rol:[/bold] [cyan]{config_manager.active_agent}[/cyan]")
                ui.console.print("Kullanılabilir Roller: [bold cyan]build[/bold cyan], [bold yellow]plan[/bold yellow], [bold magenta]review[/bold magenta], [bold green]test[/bold green]")
                ui.console.print("Rol değiştirmek için: [magenta]/agent <rol>[/magenta]\n")
        else:
            role = args[0].lower()
            if role in ROLE_DEFINITIONS:
                config_manager.active_agent = role
                badge = ROLE_DEFINITIONS[role]["badge"]
                ui.console.print(f"[bold green]✓ Ajan modu değiştirildi:[/bold green] [{badge}] ({ROLE_DEFINITIONS[role]['name']})")
            else:
                ui.console.print(f"[bold red]Geçersiz rol:[/bold red] {role}. (build, plan, review, test)")

    elif cmd == "/model":
        if not args:
            if sys.stdout.isatty():
                selected = ui.open_model_dialog(config_manager.active_model)
                if selected:
                    config_manager.active_model = selected
                    if "deepseek" in selected and "/" not in selected:
                        config_manager.active_provider = "deepseek"
                    elif "gemini" in selected and "/" not in selected:
                        config_manager.active_provider = "gemini"
                    elif selected.startswith("gpt-") or selected.startswith("o"):
                        config_manager.active_provider = "openai"
                    elif "/" in selected:
                        config_manager.active_provider = "openrouter"
                    session.model = selected
                    session.provider = config_manager.active_provider
                    session_store.save(session)
                    ui.console.print(f"[bold green]✓ Aktif model:[/bold green] [cyan]{selected}[/cyan] ({config_manager.active_provider})")
            else:
                ui.render_models_table(DEFAULT_PROVIDERS, config_manager.active_model)
        else:
            new_model = args[0]
            config_manager.active_model = new_model
            if "deepseek" in new_model and "/" not in new_model:
                config_manager.active_provider = "deepseek"
            elif "gemini" in new_model and "/" not in new_model:
                config_manager.active_provider = "gemini"
            elif new_model.startswith("gpt-") or new_model.startswith("o"):
                config_manager.active_provider = "openai"
            elif "/" in new_model:
                config_manager.active_provider = "openrouter"
            session.model = new_model
            session.provider = config_manager.active_provider
            session_store.save(session)
            ui.console.print(f"[bold green]✓ Aktif model:[/bold green] [cyan]{new_model}[/cyan] ({config_manager.active_provider})")

    elif cmd == "/session":
        if not args:
            sessions = session_store.list_all()
            if sys.stdout.isatty() and sessions:
                selected_id = ui.open_session_dialog(sessions)
                if selected_id:
                    loaded = session_store.load(selected_id)
                    if loaded:
                        session.id = loaded.id
                        session.title = loaded.title
                        session.messages = loaded.messages
                        session.total_cost_usd = loaded.total_cost_usd
                        session.model = loaded.model
                        session.provider = loaded.provider
                        ui.console.print(f"[bold green]✓ Oturuma geçildi:[/bold green] {loaded.id} - '{loaded.title}'")
            else:
                ui.render_sessions_table(sessions)
        elif args[0] == "list":
            sessions = session_store.list_all()
            ui.render_sessions_table(sessions)
        elif args[0] == "new":
            new_s = Session(project_dir=str(Path.cwd().resolve()))
            session_store.save(new_s)
            session.id = new_s.id
            session.title = new_s.title
            session.messages = []
            session.total_cost_usd = 0.0
            ui.console.print(f"[bold green]✓ Yeni oturuma geçildi:[/bold green] {new_s.id}")
        else:
            target_id = args[0]
            loaded = session_store.load(target_id)
            if loaded:
                session.id = loaded.id
                session.title = loaded.title
                session.messages = loaded.messages
                session.total_cost_usd = loaded.total_cost_usd
                session.model = loaded.model
                session.provider = loaded.provider
                ui.console.print(f"[bold green]✓ Oturuma geçildi:[/bold green] {loaded.id} - '{loaded.title}'")
            else:
                ui.console.print(f"[bold red]Oturum bulunamadı:[/bold red] {target_id}")

    elif cmd == "/skills":
        sm = SkillManager(Path(session.project_dir))
        skills = sm.discover()
        if not skills:
            ui.console.print("[dim]Tanımlı özel beceri (skill) bulunamadı. (.quantro/skills veya ~/.quantro/skills dizinine ekleyin)[/dim]")
        else:
            ui.console.print(f"\n[bold cyan]Yüklü Beceriler ({len(skills)}):[/bold cyan]")
            for sk in skills:
                ui.console.print(f"  • [bold white]{sk.name}[/bold white]: {sk.description}")
            ui.console.print()

    elif cmd == "/init":
        path = engine.memory.initialize_project_memory()
        ui.console.print(f"[bold green]✓ Kalıcı repo hafıza rehberi oluşturuldu:[/bold green] {path}")

    elif cmd == "/diff":
        res = engine.executor.shell.run_bash("git diff", auto_approve=True)
        if res.get("success") and res.get("output") and "(Komut sessizce" not in res.get("output"):
            ui.render_diff(res["output"], filename="Git Working Tree")
        elif session.last_diff:
            ui.render_diff(session.last_diff, filename="Son Dosya Düzenlemesi")
        else:
            ui.console.print("[dim]Bekleyen bir diff bulunamadı.[/dim]")

    elif cmd == "/undo":
        if not session.undo_stack:
            ui.console.print("[dim]Geri alınabilecek bir işlem geçmişte yok.[/dim]")
        else:
            snapshot = session.undo_stack.pop()
            target = Path(snapshot["path"])
            if snapshot["existed"]:
                target.write_text(snapshot["old_content"] or "", encoding="utf-8")
                ui.console.print(f"[bold green]✓ Dosya geri yüklendi:[/bold green] {target.name}")
            else:
                if target.exists():
                    target.unlink()
                ui.console.print(f"[bold green]✓ Oluşturulan dosya silindi:[/bold green] {target.name}")
            session_store.save(session)

    elif cmd == "/compact":
        compacted, pruned = engine.memory.compact_messages(session.messages)
        session.messages = compacted
        session_store.save(session)
        ui.console.print(f"[bold green]✓ Oturum hafızası sıkıştırıldı.[/bold green] {pruned} adet eski mesaj özetlendi.")

    elif cmd == "/cost":
        ui.render_stats_table({
            "Session ID": session.id,
            "Total Tokens": f"{session.total_tokens:,}",
            "Total Cost (USD)": f"${session.total_cost_usd:.4f}",
            "Active Model": session.model,
            "Provider": session.provider,
            "Turns": len([m for m in session.messages if m.get("role") == "user"])
        })

    elif cmd == "/clear":
        os.system("clear" if os.name != "nt" else "cls")

    return True


def run_interactive_repl(session: Session, auto_approve: bool = False):
    """Runs prompt_toolkit REPL with full Mission Control system dashboard and @ file completion."""
    engine = AgentEngine(session, auto_approve=auto_approve)
    project_root = Path(session.project_dir).resolve()

    # Launch complete OpenCode-style Mission Control System
    ui.render_system_launch(
        session_id=session.id,
        model=config_manager.active_model,
        provider=config_manager.active_provider,
        project_dir=session.project_dir,
        role=config_manager.active_agent,
        tokens=session.total_tokens,
        cost=session.total_cost_usd,
        session_title=session.title
    )

    completer = QuantroCompleter(project_root)
    pt_session = PromptSession(completer=completer, style=prompt_style)

    def bottom_bar():
        role = config_manager.active_agent.lower()
        meta = ui._get_workspace_meta(project_root)
        branch_str = f" : {meta['branch']}" if meta['branch'] != "no-git" else ""
        return [
            ("class:bottom-toolbar", f" {meta['display_path']}{branch_str} │ ⊙ 13 Tools │ {config_manager.active_model} [{role}] │ /help │ ^C: Cancel ")
        ]

    def get_prompt_text():
        return "\n❯ "

    try:
        while True:
            try:
                user_input = pt_session.prompt(
                    get_prompt_text,
                    bottom_toolbar=bottom_bar
                ).strip()

                if not user_input:
                    continue

                if user_input.startswith("/"):
                    keep_going = handle_slash_command(user_input, session, engine)
                    if not keep_going:
                        break
                    continue

                # Process @file mentions and expand into prompt
                expanded_prompt = expand_file_mentions(user_input, project_root)

                # Render user message card
                ui.render_user_message(user_input)

                # Run agent turn
                engine.run(expanded_prompt)

            except KeyboardInterrupt:
                # Ctrl+C at prompt resets current line, does not crash REPL
                ui.console.print("\n[dim](İptal edildi, yeni komut girin)[/dim]")
                continue
            except EOFError:
                break
    finally:
        session_store.save(session)
        ui.leave_alternate_screen()
        ui.console.print("\n[dim]Quantro oturumu kaydedildi ve kapatıldı.[/dim]\n")


def main():
    parser = argparse.ArgumentParser(
        prog="quantro",
        description="Quantro 2.0 — Autonomous Terminal Coding Agent (OpenCode 2.0 Architecture)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Subcommand to execute")

    # Subcommand: run
    run_parser = subparsers.add_parser("run", help="Run a prompt directly")
    run_parser.add_argument("prompt", help="Prompt to execute")
    run_parser.add_argument("-m", "--model", help="Override active model")
    run_parser.add_argument("-a", "--agent", choices=list(ROLE_DEFINITIONS.keys()), help="Agent role (build, plan, review, test)")
    run_parser.add_argument("-y", "--auto", action="store_true", help="Auto-approve shell commands")

    # Subcommand: session
    session_parser = subparsers.add_parser("session", help="Manage sessions")
    session_parser.add_argument("action", choices=["list", "delete"], default="list", nargs="?")
    session_parser.add_argument("session_id", nargs="?", help="Session ID for delete")

    # Subcommand: models
    subparsers.add_parser("models", help="List available models and providers")

    # Subcommand: stats
    subparsers.add_parser("stats", help="Show usage and telemetry stats")

    # Subcommand: auth
    auth_parser = subparsers.add_parser("auth", help="Configure provider API keys")
    auth_parser.add_argument("-p", "--provider", choices=list(DEFAULT_PROVIDERS.keys()), required=True)
    auth_parser.add_argument("-k", "--key", required=True, help="API Key")

    # Root flags
    parser.add_argument("prompt", nargs="?", help="Direct prompt to execute")
    parser.add_argument("-c", "--continue", dest="cont", action="store_true", help="Continue the most recent session")
    parser.add_argument("-s", "--session", dest="session_id", help="Session ID to create or resume")
    parser.add_argument("-a", "--agent", choices=list(ROLE_DEFINITIONS.keys()), help="Agent role (build, plan, review, test)")
    parser.add_argument("-m", "--model", help="Override active model")
    parser.add_argument("-p", "--provider", choices=list(DEFAULT_PROVIDERS.keys()), help="Override active provider")
    parser.add_argument("-y", "--auto", action="store_true", help="Auto-approve tool permissions")
    parser.add_argument("-v", "--version", action="version", version=f"quantro {__version__}")

    args = parser.parse_args()

    # Handle Subcommands
    if args.subcommand == "models":
        ui.render_models_table(DEFAULT_PROVIDERS, config_manager.active_model)
        sys.exit(0)

    elif args.subcommand == "session":
        if args.action == "delete" and args.session_id:
            if session_store.delete(args.session_id):
                ui.console.print(f"[bold green]✓ Oturum silindi:[/bold green] {args.session_id}")
            else:
                ui.console.print(f"[bold red]Oturum bulunamadı:[/bold red] {args.session_id}")
        else:
            sessions = session_store.list_all()
            ui.render_sessions_table(sessions)
        sys.exit(0)

    elif args.subcommand == "stats":
        sessions = session_store.list_all()
        total_tokens = sum(s.total_tokens for s in sessions)
        total_cost = sum(s.total_cost_usd for s in sessions)
        total_turns = sum(s.turn_count for s in sessions)
        ui.render_stats_table({
            "Total Stored Sessions": len(sessions),
            "Total Conversation Turns": total_turns,
            "Total Tokens Processed": f"{total_tokens:,}",
            "Total Estimated Cost (USD)": f"${total_cost:.4f}",
            "Active Default Model": config_manager.active_model,
            "Active Provider": config_manager.active_provider
        })
        sys.exit(0)

    elif args.subcommand == "auth":
        config_manager.set_api_key(args.provider, args.key)
        ui.console.print(f"[bold green]✓ API anahtarı kaydedildi:[/bold green] {args.provider}")
        sys.exit(0)

    elif args.subcommand == "run":
        if args.model:
            config_manager.active_model = args.model
        if args.agent:
            config_manager.active_agent = args.agent
        sess = Session(project_dir=str(Path.cwd().resolve()))
        engine = AgentEngine(sess, auto_approve=args.auto)
        engine.run(args.prompt)
        session_store.save(sess)
        sys.exit(0)

    # Root flags handling
    if args.model:
        config_manager.active_model = args.model
    if args.provider:
        config_manager.active_provider = args.provider
    if args.agent:
        config_manager.active_agent = args.agent

    curr_dir = str(Path.cwd().resolve())
    session: Optional[Session] = None

    if args.session_id:
        session = session_store.load(args.session_id) or Session(session_id=args.session_id, project_dir=curr_dir)
    elif args.cont:
        session = session_store.load_latest(curr_dir)
        if not session:
            ui.console.print("[dim]Önceki oturum bulunamadı, yeni oturum açılıyor...[/dim]")
            session = Session(project_dir=curr_dir)
    else:
        session = Session(project_dir=curr_dir)

    session_store.save(session)

    if args.prompt:
        engine = AgentEngine(session, auto_approve=args.auto)
        engine.run(args.prompt)
        session_store.save(session)
        sys.exit(0)
    else:
        run_interactive_repl(session, auto_approve=args.auto)


if __name__ == "__main__":
    main()
