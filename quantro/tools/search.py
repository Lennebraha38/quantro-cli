"""
Quantro Codebase Search Tools
Fast filesystem traversal and regex grep with smart exclusions.
"""

import os
import re
from pathlib import Path
from typing import Dict, Any, List

IGNORED_DIRECTORIES = {
    ".git", ".venv", "venv", "env", ".env", "node_modules",
    "__pycache__", ".quantro", ".cache", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "dist", "build", "target", ".idea", ".vscode"
}


class SearchTools:
    """Provides high-performance repository tree scanning and pattern search."""

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()

    def list_files(self, directory: str = ".", max_depth: int = 3) -> Dict[str, Any]:
        """Scans folder structure, filtering noise and build caches."""
        root = Path(directory).expanduser()
        if not root.is_absolute():
            root = (self.project_root / root).resolve()

        if not root.exists():
            return {"success": False, "error": f"Directory not found: {directory}"}
        if not root.is_dir():
            return {"success": False, "error": f"Path is not a directory: {directory}"}

        entries: List[str] = []
        base_depth = len(root.parts)

        for current_root, dirs, files in os.walk(root):
            curr_path = Path(current_root)
            depth = len(curr_path.parts) - base_depth

            dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES and not d.startswith(".")]

            if depth > max_depth:
                dirs[:] = []
                continue

            rel_dir = curr_path.relative_to(root)
            prefix = "" if str(rel_dir) == "." else f"{rel_dir}/"

            for d in sorted(dirs):
                entries.append(f"{prefix}{d}/")

            for f in sorted(files):
                if not f.startswith("."):
                    entries.append(f"{prefix}{f}")

        return {
            "success": True,
            "root": str(root),
            "count": len(entries),
            "files": entries[:300],
            "truncated": len(entries) > 300
        }

    def grep_search(self, pattern: str, path: str = ".", recursive: bool = True) -> Dict[str, Any]:
        """Searches regex or substring pattern across files."""
        root = Path(path).expanduser()
        if not root.is_absolute():
            root = (self.project_root / root).resolve()

        if not root.exists():
            return {"success": False, "error": f"Path not found: {path}"}

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return {"success": False, "error": f"Invalid regular expression: {str(e)}"}

        matches: List[str] = []
        max_limit = 100

        def scan_file(fpath: Path):
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for line_no, line in enumerate(f, 1):
                        if regex.search(line):
                            try:
                                rel = fpath.relative_to(self.project_root)
                            except ValueError:
                                rel = fpath
                            matches.append(f"{rel}:{line_no}: {line.strip()}")
                            if len(matches) >= max_limit:
                                return
            except Exception:
                pass

        if root.is_file():
            scan_file(root)
        else:
            for current_root, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES and not d.startswith(".")]
                for fname in sorted(files):
                    if fname.startswith("."):
                        continue
                    scan_file(Path(current_root) / fname)
                    if len(matches) >= max_limit:
                        break
                if not recursive or len(matches) >= max_limit:
                    break

        return {
            "success": True,
            "pattern": pattern,
            "matches_found": len(matches),
            "matches": matches,
            "truncated": len(matches) >= max_limit
        }
