"""
Quantro Shell Execution Tool
Handles sandboxed bash execution, timeout controls, and OpenCode-style permission policies.
"""

import subprocess
from pathlib import Path
from typing import Dict, Any

from quantro.config import config_manager


class ShellTools:
    """Safely executes bash shell commands with configurable approval policies."""

    def __init__(self, project_root: Any):
        self.project_root = (Path(project_root) if project_root else Path.cwd()).resolve()

    def run_bash(self, command: str, auto_approve: bool = False) -> Dict[str, Any]:
        """
        Executes a bash command according to permission policy:
        'allow': runs without asking
        'deny': immediately rejects
        'ask': prompts user interactively [E]vet / [H]ayır / [D]aima
        """
        cmd_stripped = command.strip()
        policy = "allow" if auto_approve else config_manager.bash_permission

        if policy == "deny":
            return {
                "success": False,
                "command": cmd_stripped,
                "aborted": True,
                "output": "Komut yürütme güvenlik politikası tarafından reddedildi (policy=deny)."
            }

        if policy == "ask":
            print(f"\n[bold yellow]⚡ Güvenlik Onayı:[/bold yellow] Aşağıdaki komut çalıştırılmak isteniyor:")
            print(f"  $ {cmd_stripped}")
            try:
                choice = input("Çalıştırılsın mı? [[E]vet / [H]ayır / [D]aima]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                choice = "h"

            if choice in ("d", "daima"):
                config_manager.bash_permission = "allow"
                print("  ↳ Bundan sonraki komutlar için izin verildi (Daima).")
            elif choice in ("h", "hayır", "hayir", "n", "no"):
                return {
                    "success": False,
                    "command": cmd_stripped,
                    "aborted": True,
                    "output": "Komut kullanıcı tarafından reddedildi."
                }

        try:
            res = subprocess.run(
                cmd_stripped,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(self.project_root)
            )
            stdout = res.stdout.strip()
            stderr = res.stderr.strip()
            out = stdout
            if stderr:
                out = f"{stdout}\n[STDERR]\n{stderr}".strip() if stdout else stderr

            return {
                "success": res.returncode == 0,
                "command": cmd_stripped,
                "exit_code": res.returncode,
                "output": out or "(Komut sessizce tamamlandı, çıktı yok)"
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "command": cmd_stripped,
                "error": "Komut zaman aşımına uğradı (120 saniye sınırını aştı)."
            }
        except Exception as e:
            return {
                "success": False,
                "command": cmd_stripped,
                "error": f"Komut çalıştırma hatası: {str(e)}"
            }
