"""
Quantro Filesystem Tooling
Implements read_file, write_file, and edit_file with unified diff and session undo tracking.
"""

import os
import difflib
from pathlib import Path
from typing import Dict, Any, Optional, List


class FileSystemTools:
    """Manages secure file reading, atomic writing, and unified diff editing."""

    def __init__(self, project_root: Any, session=None):
        self.project_root = (Path(project_root) if project_root else Path.cwd()).resolve()
        self.session = session

    def _resolve_path(self, path_str: str) -> Path:
        p = Path(path_str).expanduser()
        if not p.is_absolute():
            p = (self.project_root / p).resolve()
        return p

    def read_file(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
        """Reads lines from a file with 1-based indexing."""
        target = self._resolve_path(path)

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
                "path": str(target),
                "total_lines": total_lines,
                "lines_shown": 0,
                "content": "",
                "message": f"Start line {s_line} is beyond total line count {total_lines}"
            }

        selected_lines = lines[s_line - 1 : e_line]
        numbered_lines = [f"{s_line + i:4d} │ {line}" for i, line in enumerate(selected_lines)]

        return {
            "success": True,
            "path": str(target),
            "total_lines": total_lines,
            "start_line": s_line,
            "end_line": e_line,
            "line_count": len(selected_lines),
            "content": "".join(numbered_lines)
        }

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Creates or overwrites a file and pushes snapshot to session undo stack."""
        target = self._resolve_path(path)

        # Snapshot for undo
        if self.session is not None:
            existed = target.exists() and target.is_file()
            old_data = target.read_text(encoding="utf-8", errors="replace") if existed else None
            self.session.undo_stack.append({
                "path": str(target),
                "existed": existed,
                "old_content": old_data,
                "action": "write"
            })

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)

            lines = len(content.splitlines())
            size = len(content.encode("utf-8"))
            return {
                "success": True,
                "path": str(target),
                "line_count": lines,
                "bytes_written": size,
                "message": f"Successfully written {lines} lines ({size} bytes) to {target.name}"
            }
        except Exception as e:
            return {"success": False, "error": f"Failed writing file: {str(e)}"}

    def edit_file(self, path: str, search_block: str, replace_block: str) -> Dict[str, Any]:
        """Edits target file section and returns unified diff."""
        target = self._resolve_path(path)

        if not target.exists():
            return {"success": False, "error": f"File not found: {path}"}
        if not target.is_file():
            return {"success": False, "error": f"Path is not a regular file: {path}"}

        try:
            with open(target, "r", encoding="utf-8", errors="replace") as f:
                original = f.read()
        except Exception as e:
            return {"success": False, "error": f"Failed reading file: {str(e)}"}

        if search_block not in original:
            norm_orig = original.replace("\r\n", "\n")
            norm_search = search_block.replace("\r\n", "\n")
            if norm_search not in norm_orig:
                return {
                    "success": False,
                    "error": (
                        f"Search block was not found in {target.name}. "
                        "Verify indentation and surrounding lines."
                    )
                }
            original = norm_orig
            search_block = norm_search
            replace_block = replace_block.replace("\r\n", "\n")

        # Snapshot for undo
        if self.session is not None:
            self.session.undo_stack.append({
                "path": str(target),
                "existed": True,
                "old_content": original,
                "action": "edit"
            })

        new_content = original.replace(search_block, replace_block, 1)

        # Unified diff
        orig_lines = original.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)
        diff = list(difflib.unified_diff(
            orig_lines, new_lines,
            fromfile=f"a/{target.name}",
            tofile=f"b/{target.name}",
            n=3
        ))
        diff_str = "".join(diff)

        if self.session is not None:
            self.session.last_diff = diff_str

        additions = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return {"success": False, "error": f"Failed writing modifications: {str(e)}"}

        return {
            "success": True,
            "path": str(target),
            "diff": diff_str,
            "additions": additions,
            "deletions": deletions,
            "message": f"Applied changes (+{additions}, -{deletions}) to {target.name}"
        }
