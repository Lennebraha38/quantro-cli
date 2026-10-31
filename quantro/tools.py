"""
Quantro Autonomous Tool Suite
Provides 6 production-grade tools: read_file, write_file, edit_file, run_bash, list_files, grep_search.
Includes JSON function call specifications for OpenAI-compatible LLMs.
"""

import os
import re
import difflib
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from quantro.config import config_manager
from quantro.context import ContextManager


IGNORED_DIRECTORIES = {
    ".git", ".venv", "venv", "env", ".env", "node_modules",
    "__pycache__", ".quantro", ".cache", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build", "target", ".idea", ".vscode"
}


class ToolExecutor:
    """Executes filesystem and shell tools with diff tracking and user safety approvals."""

    def __init__(self, context: ContextManager):
        self.context = context

    # 1. read_file
    def read_file(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
        """Reads contents of a file with line numbering and optional line range slicing."""
        target = Path(path).expanduser().resolve()

        if not target.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if not target.is_file():
            return {"success": False, "error": f"Path is not a regular file: {path}"}

        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return {"success": False, "error": f"Failed reading file: {str(e)}"}

        total_lines = len(lines)
        s_line = max(1, start_line) if start_line is not None else 1
        e_line = min(total_lines, end_line) if end_line is not None else total_lines

        if s_line > total_lines:
            return {
                "success": True,
                "total_lines": total_lines,
                "lines_shown": 0,
                "content": "",
                "message": f"Start line {s_line} is beyond total line count {total_lines}"
            }

        selected_lines = lines[s_line - 1 : e_line]
        numbered_lines = [f"{s_line + i:4d} | {line}" for i, line in enumerate(selected_lines)]
        content_str = "".join(numbered_lines)

        return {
            "success": True,
            "path": str(target),
            "total_lines": total_lines,
            "start_line": s_line,
            "end_line": e_line,
            "line_count": len(selected_lines),
            "content": content_str
        }

    # 2. write_file
    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Writes full content to a file, creating parent directories and recording an undo snapshot."""
        target = Path(path).expanduser().resolve()

        # Capture snapshot for undo before modifying
        self.context.push_undo_snapshot(target, reason=f"write_file to {target.name}")

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
            line_count = len(content.splitlines())
            byte_size = len(content.encode("utf-8"))
            return {
                "success": True,
                "path": str(target),
                "line_count": line_count,
                "bytes_written": byte_size,
                "message": f"Successfully wrote {line_count} lines ({byte_size} bytes) to {target.name}"
            }
        except Exception as e:
            return {"success": False, "error": f"Failed writing to file: {str(e)}"}

    # 3. edit_file
    def edit_file(self, path: str, search_block: str, replace_block: str) -> Dict[str, Any]:
        """
        Replaces search_block with replace_block in a file.
        Produces a unified diff and pushes an undo snapshot.
        """
        target = Path(path).expanduser().resolve()

        if not target.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if not target.is_file():
            return {"success": False, "error": f"Path is not a regular file: {path}"}

        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                original_content = f.read()
        except Exception as e:
            return {"success": False, "error": f"Failed reading file: {str(e)}"}

        # Exact match check
        if search_block not in original_content:
            # Try normalized line endings
            norm_orig = original_content.replace("\r\n", "\n")
            norm_search = search_block.replace("\r\n", "\n")
            if norm_search not in norm_orig:
                return {
                    "success": False,
                    "error": (
                        f"Search block was not found in {target.name}. "
                        "Please verify the exact characters, indentation, and line breaks."
                    )
                }
            original_content = norm_orig
            search_block = norm_search
            replace_block = replace_block.replace("\r\n", "\n")

        # Snapshot for undo
        self.context.push_undo_snapshot(target, reason=f"edit_file in {target.name}")

        new_content = original_content.replace(search_block, replace_block, 1)

        # Generate unified diff
        orig_lines = original_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff_lines = list(difflib.unified_diff(
            orig_lines,
            new_lines,
            fromfile=f"a/{target.name}",
            tofile=f"b/{target.name}",
            n=3
        ))
        diff_text = "".join(diff_lines)
        self.context.last_action_diff = diff_text

        # Count additions and deletions
        additions = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))

        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return {"success": False, "error": f"Failed saving modifications: {str(e)}"}

        return {
            "success": True,
            "path": str(target),
            "diff": diff_text,
            "additions": additions,
            "deletions": deletions,
            "message": f"Successfully applied changes (+{additions}, -{deletions}) to {target.name}"
        }

    # 4. run_bash
    def run_bash(self, command: str, auto_approve: bool = False) -> Dict[str, Any]:
        """
        Executes a bash shell command with optional interactive confirmation.
        Prompt: [E]vet / [H]ayır / [D]aima
        """
        cmd_stripped = command.strip()
        needs_approval = not (auto_approve or config_manager.auto_approve_bash)

        if needs_approval:
            print(f"\n[Quantro Güvenlik Kontrolü] Aşağıdaki komut çalıştırılmak isteniyor:")
            print(f"  $ {cmd_stripped}")
            try:
                choice = input("Çalıştırılsın mı? [[E]vet / [H]ayır / [D]aima]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                choice = "h"

            if choice in ("d", "daima"):
                config_manager.auto_approve_bash = True
                print("  ↳ Bundan sonraki komutlar için otomatik onay açıldı (Daima).")
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
                cwd=str(self.context.project_root)
            )
            stdout = res.stdout.strip()
            stderr = res.stderr.strip()
            output = stdout
            if stderr:
                output = f"{stdout}\n[STDERR]\n{stderr}".strip() if stdout else stderr

            return {
                "success": res.returncode == 0,
                "command": cmd_stripped,
                "exit_code": res.returncode,
                "output": output or "(Komut sessizce tamamlandı, çıktı yok)"
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
                "error": f"Komut yürütme hatası: {str(e)}"
            }

    # 5. list_files
    def list_files(self, directory: str = ".", max_depth: int = 3) -> Dict[str, Any]:
        """Recursively lists files and directories up to max_depth, filtering noise."""
        root_path = Path(directory).expanduser()
        if not root_path.is_absolute():
            root_path = (self.context.project_root / root_path).resolve()

        if not root_path.exists():
            return {"success": False, "error": f"Directory not found: {directory}"}
        if not root_path.is_dir():
            return {"success": False, "error": f"Path is not a directory: {directory}"}

        entries: List[str] = []
        base_depth = len(root_path.parts)

        for current_root, dirs, files in os.walk(root_path):
            curr_path = Path(current_root)
            depth = len(curr_path.parts) - base_depth

            # Exclude ignored directories in-place
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES and not d.startswith(".")]

            if depth > max_depth:
                dirs[:] = []
                continue

            rel_dir = curr_path.relative_to(root_path)
            prefix = "" if str(rel_dir) == "." else f"{rel_dir}/"

            for d in sorted(dirs):
                entries.append(f"{prefix}{d}/")

            for f in sorted(files):
                if not f.startswith("."):
                    entries.append(f"{prefix}{f}")

        return {
            "success": True,
            "root": str(root_path),
            "count": len(entries),
            "files": entries[:300],  # Cap output at 300 to prevent context flooding
            "truncated": len(entries) > 300
        }

    # 6. grep_search
    def grep_search(self, pattern: str, path: str = ".", recursive: bool = True) -> Dict[str, Any]:
        """Searches files for regex or literal pattern, skipping ignored directories."""
        root_path = Path(path).expanduser()
        if not root_path.is_absolute():
            root_path = (self.context.project_root / root_path).resolve()

        if not root_path.exists():
            return {"success": False, "error": f"Search path not found: {path}"}

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return {"success": False, "error": f"Invalid regular expression '{pattern}': {str(e)}"}

        matches: List[str] = []
        max_matches = 80

        def search_single_file(fpath: Path):
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for idx, line in enumerate(f, 1):
                        if regex.search(line):
                            rel = fpath.relative_to(self.context.project_root)
                            matches.append(f"{rel}:{idx}: {line.strip()}")
                            if len(matches) >= max_matches:
                                return
            except Exception:
                pass

        if root_path.is_file():
            search_single_file(root_path)
        else:
            for current_root, dirs, files in os.walk(root_path):
                dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES and not d.startswith(".")]
                for filename in sorted(files):
                    if filename.startswith("."):
                        continue
                    file_path = Path(current_root) / filename
                    search_single_file(file_path)
                    if len(matches) >= max_matches:
                        break
                if not recursive or len(matches) >= max_matches:
                    break

        return {
            "success": True,
            "pattern": pattern,
            "matches_found": len(matches),
            "matches": matches,
            "truncated": len(matches) >= max_matches
        }


# OpenAI-compatible function calling specifications
AGENT_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads contents of a file with line numbers. Use this to inspect code before modifying.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to read."},
                    "start_line": {"type": "integer", "description": "Optional 1-based start line."},
                    "end_line": {"type": "integer", "description": "Optional 1-based end line."}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Creates a new file or completely overwrites an existing file with provided content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the destination file."},
                    "content": {"type": "string", "description": "The exact full contents to write."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edits a section of a file by finding search_block and replacing it with replace_block. Shows unified diff.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path of the file to edit."},
                    "search_block": {"type": "string", "description": "The exact block of code to find and replace."},
                    "replace_block": {"type": "string", "description": "The replacement code."}
                },
                "required": ["path", "search_block", "replace_block"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Executes a shell command in the project directory (e.g. git, pytest, pip, npm, cargo, ls).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash shell command to execute."}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Lists repository files and directory hierarchy, ignoring build caches and node_modules.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directory path to list (defaults to '.')."},
                    "max_depth": {"type": "integer", "description": "Maximum directory traversal depth (default: 3)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "Searches for regex or keyword pattern across project files, returning matching line numbers and text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex or string pattern to search for."},
                    "path": {"type": "string", "description": "Path to file or directory to search in (default: '.')."},
                    "recursive": {"type": "boolean", "description": "Whether to search recursively in subdirectories."}
                },
                "required": ["pattern"]
            }
        }
    }
]
