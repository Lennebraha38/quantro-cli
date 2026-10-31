"""
Quantro CLI Entrypoint & Interactive REPL
Provides prompt_toolkit session, slash commands, bottom status toolbar, and single-shot execution.
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
from quantro.context import ContextManager
from quantro.agent import Agent
from quantro import ui

SLASH_COMMANDS = [
    "/help",
    "/model",
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
    "bottom-toolbar": "bg:#1e293b #e2e8f0",
})


def handle_slash_command(cmd_line: str, context: ContextManager, agent: Agent) -> bool:
    """
    Executes slash command. Returns True if REPL should continue, False if REPL should exit.
    """
    parts = cmd_line.strip().split()
    cmd = parts[0].lower()
    args = parts[1:]

    if cmd in ("/exit", "/quit"):
        ui.console.print("\n[dim]Quantro oturumu sonlandırıldı. Görüşmek üzere![/dim]\n")
        return False

    elif cmd == "/help":
        ui.print_help_table()

    elif cmd == "/cost":
        ui.print_cost_table(context.get_cost_summary())

    elif cmd == "/clear":
        os.system("clear" if os.name != "nt" else "cls")

    elif cmd == "/init":
        path = context.initialize_project_memory()
        ui.print_success(f"Proje hafıza dosyası oluşturuldu:\n{path}", title="QUANTRO.md Hazırlandı")

    elif cmd == "/diff":
        # Check git diff first
        res = agent.tool_executor.run_bash("git diff", auto_approve=True)
        if res.get("success") and res.get("output") and res.get("output") != "(Komut sessizce tamamlandı, çıktı yok)":
            ui.print_diff(res["output"], filename="Git Working Tree Diff")
        elif context.last_action_diff:
            ui.print_diff(context.last_action_diff, filename="Son Dosya Değişikliği")
        else:
            ui.console.print("[dim]Şu anda bekleyen veya kaydedilmiş bir fark (diff) yok.[/dim]")

    elif cmd == "/undo":
        result = context.pop_undo()
        if result:
            action = result.get("action", "")
            target_path = result.get("path", "")
            reason = result.get("reason", "")
            ui.print_success(
                f"Dosya eski haline döndürüldü: {target_path}\nİşlem: {action} ({reason})",
                title="Geri Alma (Undo) Başarılı"
            )
        else:
            ui.console.print("[dim]Geri alınabilecek bir dosya işlemi geçmişte bulunamadı.[/dim]")

    elif cmd == "/compact":
        pruned = context.compact_history()
        ui.print_success(
            f"Geçmiş sıkıştırıldı. {pruned} adet eski mesaj özet haline getirildi.",
            title="Bağlam Sıkıştırma (Compact)"
        )

    elif cmd == "/model":
        if not args:
            ui.console.print(f"\n[bold]Aktif Model:[/bold] [cyan]{config_manager.active_model}[/cyan]")
            ui.console.print(f"[bold]Aktif Sağlayıcı:[/bold] [yellow]{config_manager.active_provider}[/yellow]")
            recs = config_manager.get_recommended_models()
            if recs:
                ui.console.print("\n[bold]Önerilen Modeller:[/bold]")
                for m in recs:
                    star = " ★ (aktif)" if m == config_manager.active_model else ""
                    ui.console.print(f"  • {m}{star}")
            ui.console.print("\nModel değiştirmek için: [magenta]/model <model_adi>[/magenta]\n")
        else:
            new_model = args[0]
            config_manager.active_model = new_model
            # Auto-detect provider if model prefix matches
            if "deepseek" in new_model and "/" not in new_model:
                config_manager.active_provider = "deepseek"
            elif "gemini" in new_model and "/" not in new_model:
                config_manager.active_provider = "gemini"
            elif new_model.startswith("gpt-") or new_model.startswith("o"):
                config_manager.active_provider = "openai"
            elif "/" in new_model:
                config_manager.active_provider = "openrouter"

            ui.print_success(
                f"Aktif model güncellendi: [cyan]{config_manager.active_model}[/cyan] ({config_manager.active_provider})",
                title="Model Güncellendi"
            )

    else:
        ui.print_error(f"Bilinmeyen komut: {cmd}. Komut listesi için /help yazın.", title="Komut Bulunamadı")

    return True


def run_repl(context: ContextManager, agent: Agent):
    """Runs interactive prompt_toolkit REPL session."""
    ui.print_banner(
        version=__version__,
        model=config_manager.active_model,
        provider=config_manager.active_provider,
        project_root=str(context.project_root)
    )

    completer = WordCompleter(SLASH_COMMANDS, ignore_case=True, match_middle=False)
    session = PromptSession(completer=completer, style=prompt_style)

    def bottom_toolbar():
        metrics = context.get_cost_summary()
        return [
            ("class:bottom-toolbar", f" Quantro v{__version__} │ Model: {config_manager.active_model} │ "
                                     f"Tokens: {metrics['total_tokens']:,} │ Cost: {metrics['formatted_cost']} │ "
                                     f"Dir: {context.project_root.name} ")
        ]

    while True:
        try:
            user_input = session.prompt(
                "\n❯ ",
                bottom_toolbar=bottom_toolbar
            ).strip()

            if not user_input:
                continue

            if user_input.startswith("/"):
                keep_going = handle_slash_command(user_input, context, agent)
                if not keep_going:
                    break
                continue

            # Standard user prompt for autonomous agent
            agent.run_turn(user_input)

        except (KeyboardInterrupt, EOFError):
            ui.console.print("\n[dim]Quantro oturumu sonlandırıldı.[/dim]\n")
            break


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="quantro",
        description="Quantro — Autonomous Terminal Coding Agent (CLI)",
        epilog="Examples:\n  quantro\n  quantro 'fix syntax error in app.py'\n  quantro -m anthropic/claude-3.5-sonnet",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("prompt", nargs="?", help="Direct prompt to execute in single-shot mode without REPL")
    parser.add_argument("-m", "--model", help="Override active model for this session")
    parser.add_argument("-p", "--provider", choices=list(DEFAULT_PROVIDERS.keys()), help="Override active provider")
    parser.add_argument("-k", "--api-key", help="Specify API key for the active provider")
    parser.add_argument("-y", "--auto-approve", action="store_true", help="Auto-approve bash commands without safety confirmation")
    parser.add_argument("-v", "--version", action="version", version=f"quantro {__version__}")

    args = parser.parse_args()

    # Apply command line overrides
    if args.provider:
        config_manager.active_provider = args.provider
    if args.model:
        config_manager.active_model = args.model
    if args.api_key:
        config_manager.set_api_key(config_manager.active_provider, args.api_key)

    context = ContextManager()
    agent = Agent(context, auto_approve_bash=args.auto_approve)

    if args.prompt:
        # Single-shot command mode
        agent.run_turn(args.prompt)
        sys.exit(0)
    else:
        # Interactive REPL mode
        run_repl(context, agent)


if __name__ == "__main__":
    main()
