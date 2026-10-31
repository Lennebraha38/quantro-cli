"""
Quantro 2.0 CLI & Subcommands Engine
Implements OpenCode 2.0 subcommands (run, session, models, stats, auth) and interactive REPL.
"""

import os
import sys
import argparse
from pathlib import Path
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
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
    "prompt": "ansicyan bold",
    "bottom-toolbar": "bg:#0f172a #94a3b8",
})


def handle_slash_command(cmd_line: str, session: Session, engine: AgentEngine) -> bool:
    """Handles interactive slash commands. Returns False to exit session."""
    parts = cmd_line.strip().split()
    cmd = parts[0].lower()
    args = parts[1:]

    if cmd in ("/exit", "/quit"):
        session_store.save(session)
        ui.console.print("\n[dim]Quantro 2.0 oturumu kaydedildi ve sonlandırıldı. Görüşmek üzere![/dim]\n")
        return False

    elif cmd == "/help":
        ui.render_help()

    elif cmd == "/agent":
        if not args:
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
        if not args or args[0] == "list":
            sessions = session_store.list_all()
            ui.render_sessions_table(sessions)
        elif args[0] == "new":
            new_s = Session(project_dir=str(Path.cwd().resolve()))
            session_store.save(new_s)
            ui.console.print(f"[bold green]✓ Yeni oturum başlatıldı:[/bold green] {new_s.id}")
            ui.console.print("Bu oturuma geçmek için: [dim]quantro -s " + new_s.id + "[/dim]")
        else:
            target_id = args[0]
            loaded = session_store.load(target_id)
            if loaded:
                ui.console.print(f"[bold green]✓ Oturum bulundu:[/bold green] {loaded.id} - '{loaded.title}'")
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
    """Runs prompt_toolkit REPL with OpenCode 2.0 telemetry."""
    engine = AgentEngine(session, auto_approve=auto_approve)

    ui.render_header(
        session_id=session.id,
        model=config_manager.active_model,
        provider=config_manager.active_provider,
        project_dir=session.project_dir,
        role=config_manager.active_agent,
        tokens=session.total_tokens,
        cost=session.total_cost_usd
    )

    completer = WordCompleter(SLASH_COMMANDS, ignore_case=True, match_middle=False)
    pt_session = PromptSession(completer=completer, style=prompt_style)

    def bottom_bar():
        role = config_manager.active_agent.upper()
        return [
            ("class:bottom-toolbar", f" quantro 2.0 │ [{role}] │ {config_manager.active_model} │ "
                                     f"Tokens: {session.total_tokens:,} │ ${session.total_cost_usd:.4f} │ "
                                     f"Session: {session.id[:8]} ")
        ]

    while True:
        try:
            user_input = pt_session.prompt(
                "\n❯ ",
                bottom_toolbar=bottom_bar
            ).strip()

            if not user_input:
                continue

            if user_input.startswith("/"):
                keep_going = handle_slash_command(user_input, session, engine)
                if not keep_going:
                    break
                continue

            engine.run(user_input)

        except (KeyboardInterrupt, EOFError):
            session_store.save(session)
            ui.console.print("\n[dim]Quantro oturumu kaydedildi ve kapatıldı.[/dim]\n")
            break


def main():
    parser = argparse.ArgumentParser(
        prog="quantro",
        description="Quantro 2.0 — Autonomous Terminal Coding Agent (OpenCode Architecture)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    # Subcommands
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

    # Root argument handling
    if args.model:
        config_manager.active_model = args.model
    if args.provider:
        config_manager.active_provider = args.provider
    if args.agent:
        config_manager.active_agent = args.agent

    # Session resolution
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
