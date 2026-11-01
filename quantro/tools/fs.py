"""
Quantro Advanced Filesystem & Code Editing Engine
Features fuzzy matching, multi_edit transactions, unified diffs, and built-in LSP/AST syntax diagnostics.
"""

import ast
import json
import difflib
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple


def run_syntax_diagnostics(file_path: Path, content: str) -> Optional[str]:
    """
    Performs quick AST/syntax validation on saved files (Python, JSON).
    Returns error description if code fails to parse, allowing agent to self-heal.
    """
    ext = file_path.suffix.lower()

    if ext == ".py":
        try:
            ast.parse(content, filename=str(file_path))
        except SyntaxError as e:
            return f"Python SyntaxError at line {e.lineno}, col {e.offset}: {e.msg} -> '{e.text.strip() if e.text else ''}'"
        except Exception as e:
            return f"Python AST validation warning: {str(e)}"

    elif ext == ".json":
        try:
            json.loads(content)
        except json.JSONDecodeError as e:
            return f"JSON SyntaxError at line {e.lineno}, col {e.colno}: {e.msg}"

    return None


def fuzzy_find_block(haystack: str, needle: str) -> Optional[Tuple[int, int]]:
    """
    Locates needle in haystack with tolerance for indentation, line-ending, and whitespace differences.
    Returns (start_char_idx, end_char_idx) in haystack if found, else None.
    """
    # 1. Exact match
    idx = haystack.find(needle)
    if idx != -1:
        return (idx, idx + len(needle))

    # 2. Normalized newline match
    norm_haystack = haystack.replace("\r\n", "\n")
    norm_needle = needle.replace("\r\n", "\n")
    idx = norm_haystack.find(norm_needle)
    if idx != -1:
        return (idx, idx + len(norm_needle))

    # 3. Line-by-line whitespace-stripped sequence matching
    h_lines = norm_haystack.splitlines(keepends=True)
    n_lines = norm_needle.splitlines(keepends=True)

    h_stripped = [l.strip() for l in h_lines]
    n_stripped = [l.strip() for l in n_lines if l.strip()]

    if not n_stripped:
        return None

    # Search for subsequence
    for i in range(len(h_stripped) - len(n_stripped) + 1):
        window = [l for l in h_stripped[i : i + len(n_stripped)] if l]
        if window == n_stripped:
            # Found exact line subsequence ignoring indentation
            start_pos = sum(len(l) for l in h_lines[:i])
            end_pos = sum(len(l) for l in h_lines[: i + len(n_stripped)])
            return (start_pos, end_pos)

    # 4. Levenshtein / SequenceMatcher high similarity matching
    matcher = difflib.SequenceMatcher(None, h_lines, n_lines)
    match = matcher.find_longest_match(0, len(h_lines), 0, len(n_lines))
    if match.size >= len(n_lines) * 0.8:
        start_pos = sum(len(l) for l in h_lines[: match.a])
        end_pos = sum(len(l) for l in h_lines[: match.a + match.size])
        return (start_pos, end_pos)

    return None


class FileSystemTools:
    """Manages atomic file writes, fuzzy edits, multi_edits, and syntax diagnostics."""

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
        """Creates or overwrites a file and checks syntax diagnostics."""
        target = self._resolve_path(path)

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

            diag = run_syntax_diagnostics(target, content)
            res = {
                "success": True,
                "path": str(target),
                "line_count": lines,
                "bytes_written": size,
                "message": f"Successfully written {lines} lines to {target.name}"
            }
            if diag:
                res["diagnostics_warning"] = diag
            return res
        except Exception as e:
            return {"success": False, "error": f"Failed writing file: {str(e)}"}

    def edit_file(self, path: str, search_block: str, replace_block: str) -> Dict[str, Any]:
        """Edits target file using fuzzy matching, applies unified diff, and runs syntax diagnostics."""
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

        loc = fuzzy_find_block(original, search_block)
        if not loc:
            return {
                "success": False,
                "error": (
                    f"Search block could not be matched in {target.name} (fuzzy matching also failed). "
                    "Please read the exact lines of the file using read_file first."
                )
            }

        start_idx, end_idx = loc

        if self.session is not None:
            self.session.undo_stack.append({
                "path": str(target),
                "existed": True,
                "old_content": original,
                "action": "edit"
            })

        new_content = original[:start_idx] + replace_block + original[end_idx:]

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

        diag = run_syntax_diagnostics(target, new_content)
        result = {
            "success": True,
            "path": str(target),
            "diff": diff_str,
            "additions": additions,
            "deletions": deletions,
            "message": f"Applied fuzzy changes (+{additions}, -{deletions}) to {target.name}"
        }
        if diag:
            result["diagnostics_warning"] = diag
            result["message"] += f" [Warning: {diag}]"
        return result

    def multi_edit(self, path: str, edits: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Applies multiple search/replace blocks sequentially in a single atomic transaction.
        If any edit cannot be located, all edits are rolled back.
        """
        target = self._resolve_path(path)

        if not target.exists() or not target.is_file():
            return {"success": False, "error": f"Target file not found: {path}"}

        try:
            original = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return {"success": False, "error": f"Failed reading file: {str(e)}"}

        current_content = original
        applied_count = 0

        for i, edit_item in enumerate(edits, 1):
            s_block = edit_item.get("search", "")
            r_block = edit_item.get("replace", "")

            loc = fuzzy_find_block(current_content, s_block)
            if not loc:
                return {
                    "success": False,
                    "error": f"multi_edit failed at edit #{i}: search block not found. Rolled back all changes."
                }

            start_idx, end_idx = loc
            current_content = current_content[:start_idx] + r_block + current_content[end_idx:]
            applied_count += 1

        # Undo snapshot
        if self.session is not None:
            self.session.undo_stack.append({
                "path": str(target),
                "existed": True,
                "old_content": original,
                "action": "multi_edit"
            })

        diff = list(difflib.unified_diff(
            original.splitlines(keepends=True),
            current_content.splitlines(keepends=True),
            fromfile=f"a/{target.name}",
            tofile=f"b/{target.name}",
            n=3
        ))
        diff_str = "".join(diff)
        if self.session is not None:
            self.session.last_diff = diff_str

        additions = sum(1 for line in diff if line.startswith("+") and not line.startswith("+++"))
        deletions = sum(1 for line in diff if line.startswith("-") and not line.startswith("---"))

        target.write_text(current_content, encoding="utf-8")
        diag = run_syntax_diagnostics(target, current_content)

        res = {
            "success": True,
            "path": str(target),
            "edits_applied": applied_count,
            "diff": diff_str,
            "additions": additions,
            "deletions": deletions,
            "message": f"Applied {applied_count} edits (+{additions}, -{deletions}) to {target.name}"
        }
        if diag:
            res["diagnostics_warning"] = diag
        return res
