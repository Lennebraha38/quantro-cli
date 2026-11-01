"""
Quantro Live & Background Shell Engine
Supports line-by-line output streaming, background service management (PTY/daemon),
and OpenCode-style granular permission enforcement (safe whitelist vs strictly dangerous prompt).
"""

import os
import sys
import time
import signal
import threading
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from collections import deque

from quantro.config import config_manager


class BackgroundJob:
    """Represents a long-running background command (e.g. dev server, file watcher)."""

    def __init__(self, job_id: str, command: str, process: subprocess.Popen):
        self.job_id = job_id
        self.command = command
        self.process = process
        self.started_at = time.time()
        self.logs: deque = deque(maxlen=300)
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        try:
            if self.process.stdout:
                for line in iter(self.process.stdout.readline, ""):
                    if not line:
                        break
                    self.logs.append(line.rstrip())
        except Exception:
            pass

    @property
    def is_alive(self) -> bool:
        return self.process.poll() is None

    def stop(self) -> bool:
        try:
            if self.is_alive:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                return True
        except Exception:
            pass
        return False


class BackgroundJobManager:
    """Manages long-running daemon processes for web servers and background tasks."""

    def __init__(self):
        self.jobs: Dict[str, BackgroundJob] = {}
        self._counter = 0

    def start_job(self, command: str, cwd: Path) -> Dict[str, Any]:
        self._counter += 1
        job_id = f"job-{self._counter}"

        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(cwd),
                preexec_fn=os.setsid if hasattr(os, "setsid") else None
            )
            job = BackgroundJob(job_id, command, process)
            self.jobs[job_id] = job

            # Give process a moment to initialize or fail immediately
            time.sleep(0.4)
            if not job.is_alive:
                ret = job.process.poll()
                logs = list(job.logs)
                return {
                    "success": False,
                    "job_id": job_id,
                    "command": command,
                    "exit_code": ret,
                    "error": f"Job exited immediately with code {ret}",
                    "output": "\n".join(logs)
                }

            return {
                "success": True,
                "job_id": job_id,
                "command": command,
                "pid": process.pid,
                "status": "running",
                "message": f"Started background process [{job_id}] (PID: {process.pid})"
            }
        except Exception as e:
            return {"success": False, "error": f"Failed starting background job: {str(e)}"}

    def get_logs(self, job_id: str, lines: int = 50) -> Dict[str, Any]:
        job = self.jobs.get(job_id)
        if not job:
            return {"success": False, "error": f"Background job '{job_id}' not found"}

        recent = list(job.logs)[-lines:]
        return {
            "success": True,
            "job_id": job_id,
            "command": job.command,
            "is_alive": job.is_alive,
            "exit_code": job.process.poll(),
            "lines_returned": len(recent),
            "output": "\n".join(recent) or "(Henüz log kaydı yok)"
        }

    def stop_job(self, job_id: str) -> Dict[str, Any]:
        job = self.jobs.get(job_id)
        if not job:
            return {"success": False, "error": f"Background job '{job_id}' not found"}

        stopped = job.stop()
        return {
            "success": True,
            "job_id": job_id,
            "command": job.command,
            "stopped": stopped,
            "message": f"Background process [{job_id}] terminated"
        }

    def list_jobs(self) -> List[Dict[str, Any]]:
        return [
            {
                "job_id": j.job_id,
                "command": j.command,
                "pid": j.process.pid,
                "is_alive": j.is_alive,
                "running_seconds": int(time.time() - j.started_at)
            }
            for j in self.jobs.values()
        ]


# Global background process manager singleton
bg_manager = BackgroundJobManager()


class ShellTools:
    """Safely executes bash shell commands with live streaming and granular security checks."""

    def __init__(self, project_root: Any):
        self.project_root = (Path(project_root) if project_root else Path.cwd()).resolve()

    def _evaluate_security(self, command: str, auto_approve: bool = False) -> tuple[bool, str]:
        """
        Granular security gatekeeper:
        1. Safe read-only commands (git status, pytest, ls) -> True automatically.
        2. Strictly dangerous commands (rm, sudo, git push, chmod) -> ALWAYS prompts user.
        3. Normal commands -> checks user policy ('allow', 'ask', 'deny').
        """
        cmd_clean = command.strip()

        # 1. Safe command whitelist check
        if config_manager.is_safe_command(cmd_clean):
            return True, "safe_whitelisted"

        # 2. Strictly dangerous check (forces user confirmation even if auto_approve is True)
        if config_manager.is_strictly_dangerous(cmd_clean):
            print(f"\n[bold red]⚠️  KRİTİK GÜVENLİK UYARISI:[/bold red] Tehlikeli/sistem değiştiren bir komut algılandı:")
            print(f"  $ {cmd_clean}")
            try:
                choice = input("Bu tehlikeli komut kesinlikle çalıştırılsın mı? [E/H]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                choice = "h"

            if choice in ("e", "evet", "y", "yes"):
                return True, "strictly_approved"
            return False, "Kullanıcı tehlikeli komutu reddetti."

        # 3. Standard permission check
        policy = "allow" if auto_approve else config_manager.bash_permission
        if policy == "deny":
            return False, "Komut yürütme politikası 'deny' olarak ayarlanmış."

        if policy == "ask":
            print(f"\n[bold yellow]⚡ Kabuk İzni:[/bold yellow] $ {cmd_clean}")
            try:
                choice = input("Çalıştırılsın mı? [[E]vet / [H]ayır / [D]aima]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                choice = "h"

            if choice in ("d", "daima"):
                config_manager.bash_permission = "allow"
                print("  ↳ Bundan sonraki standart komutlar için izin verildi (Daima).")
                return True, "always_allowed"
            elif choice in ("e", "evet", "y", "yes", ""):
                return True, "one_time_approved"
            else:
                return False, "Komut kullanıcı tarafından reddedildi."

        return True, "policy_allow"

    def run_bash(self, command: str, auto_approve: bool = False, timeout: int = 120) -> Dict[str, Any]:
        """
        Executes bash command in real-time streaming mode so UI doesn't freeze.
        """
        cmd_stripped = command.strip()
        allowed, reason = self._evaluate_security(cmd_stripped, auto_approve=auto_approve)

        if not allowed:
            return {
                "success": False,
                "command": cmd_stripped,
                "aborted": True,
                "output": reason
            }

        try:
            process = subprocess.Popen(
                cmd_stripped,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(self.project_root)
            )

            output_lines: List[str] = []
            start_time = time.time()

            # Stream output live if interactive terminal
            while True:
                if process.stdout:
                    line = process.stdout.readline()
                    if line:
                        output_lines.append(line)
                    elif process.poll() is not None:
                        break
                else:
                    break

                if time.time() - start_time > timeout:
                    process.kill()
                    return {
                        "success": False,
                        "command": cmd_stripped,
                        "error": f"Komut zaman aşımına uğradı ({timeout}s sınırını aştı)."
                    }

            exit_code = process.poll() or 0
            full_output = "".join(output_lines).strip()

            return {
                "success": exit_code == 0,
                "command": cmd_stripped,
                "exit_code": exit_code,
                "output": full_output or "(Komut sessizce tamamlandı, çıktı yok)"
            }
        except Exception as e:
            return {
                "success": False,
                "command": cmd_stripped,
                "error": f"Komut çalıştırma hatası: {str(e)}"
            }

    def run_in_background(self, command: str) -> Dict[str, Any]:
        """Launches a long-running background command like web servers or daemon services."""
        cmd_stripped = command.strip()
        allowed, reason = self._evaluate_security(cmd_stripped, auto_approve=False)
        if not allowed:
            return {"success": False, "command": cmd_stripped, "aborted": True, "error": reason}

        return bg_manager.start_job(cmd_stripped, self.project_root)

    def get_background_logs(self, job_id: str, lines: int = 50) -> Dict[str, Any]:
        """Fetches output buffer for a background job."""
        return bg_manager.get_logs(job_id, lines=lines)

    def stop_background_job(self, job_id: str) -> Dict[str, Any]:
        """Stops an active background job."""
        return bg_manager.stop_job(job_id)

    def list_background_jobs(self) -> Dict[str, Any]:
        """Lists active background jobs."""
        jobs = bg_manager.list_jobs()
        return {"success": True, "count": len(jobs), "jobs": jobs}
