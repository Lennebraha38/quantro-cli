"""
Quantro Tool Registry & Dispatcher
Unifies file, shell, and search operations under standard OpenAI-compatible tool calling schemas.
"""

from pathlib import Path
from typing import Dict, Any, Optional

from quantro.tools.fs import FileSystemTools
from quantro.tools.shell import ShellTools
from quantro.tools.search import SearchTools


class ToolExecutor:
    """Central facade coordinating all sub-tool subsystems."""

    def __init__(self, project_root: Optional[Any] = None, session=None):
        self.project_root = (Path(project_root) if project_root else Path.cwd()).resolve()
        self.session = session
        self.fs = FileSystemTools(self.project_root, session=session)
        self.shell = ShellTools(self.project_root)
        self.search = SearchTools(self.project_root)

    def dispatch(self, name: str, args: Dict[str, Any], auto_approve: bool = False) -> Dict[str, Any]:
        """Dispatches tool call to appropriate handler."""
        if name == "read_file":
            return self.fs.read_file(
                path=args.get("path", ""),
                start_line=args.get("start_line"),
                end_line=args.get("end_line")
            )
        elif name == "write_file":
            return self.fs.write_file(
                path=args.get("path", ""),
                content=args.get("content", "")
            )
        elif name == "edit_file":
            return self.fs.edit_file(
                path=args.get("path", ""),
                search_block=args.get("search_block", ""),
                replace_block=args.get("replace_block", "")
            )
        elif name == "run_bash":
            return self.shell.run_bash(
                command=args.get("command", ""),
                auto_approve=auto_approve
            )
        elif name == "list_files":
            return self.search.list_files(
                directory=args.get("directory", "."),
                max_depth=args.get("max_depth", 3)
            )
        elif name == "grep_search":
            return self.search.grep_search(
                pattern=args.get("pattern", ""),
                path=args.get("path", "."),
                recursive=args.get("recursive", True)
            )
        else:
            return {"success": False, "error": f"Unknown tool: {name}"}


TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads lines from a file with 1-based line numbers. Inspect code before modifying.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to file."},
                    "start_line": {"type": "integer", "description": "Optional start line number."},
                    "end_line": {"type": "integer", "description": "Optional end line number."}
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
                    "path": {"type": "string", "description": "Path to destination file."},
                    "content": {"type": "string", "description": "Full file contents."}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replaces a specific code snippet with replacement code. Computes unified diff preview.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to edit."},
                    "search_block": {"type": "string", "description": "Exact text/code block to locate."},
                    "replace_block": {"type": "string", "description": "New replacement code block."}
                },
                "required": ["path", "search_block", "replace_block"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Executes shell command in project directory (e.g. tests, linters, git, builds).",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Bash command line to execute."}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Scans repository hierarchy, filtering noise and build caches.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Directory to inspect (default: '.')."},
                    "max_depth": {"type": "integer", "description": "Max depth traversal (default: 3)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "Searches for regex pattern across codebase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex or keyword to search."},
                    "path": {"type": "string", "description": "Starting directory or file."},
                    "recursive": {"type": "boolean", "description": "Whether to search recursively."}
                },
                "required": ["pattern"]
            }
        }
    }
]
