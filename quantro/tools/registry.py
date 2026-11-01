"""
Quantro Tool Registry & Dispatcher
Unifies file, shell, background jobs, web search/fetch, subagents, and MCP under OpenAI-compatible tool schemas.
"""

from pathlib import Path
from typing import Dict, Any, Optional, List

from quantro.tools.fs import FileSystemTools
from quantro.tools.shell import ShellTools
from quantro.tools.search import SearchTools
from quantro.tools.web import WebTools
from quantro.tools.mcp import mcp_client


class ToolExecutor:
    """Central facade coordinating all sub-tool subsystems."""

    def __init__(self, project_root: Optional[Any] = None, session=None):
        self.project_root = (Path(project_root) if project_root else Path.cwd()).resolve()
        self.session = session
        self.fs = FileSystemTools(self.project_root, session=session)
        self.shell = ShellTools(self.project_root)
        self.search = SearchTools(self.project_root)
        self.web = WebTools()
        self._subagent_runner = None

    def dispatch(self, name: str, args: Dict[str, Any], auto_approve: bool = False) -> Dict[str, Any]:
        """Dispatches tool call to appropriate handler."""
        # Filesystem
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
        elif name == "multi_edit":
            return self.fs.multi_edit(
                path=args.get("path", ""),
                edits=args.get("edits", [])
            )

        # Codebase search
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

        # Shell & Background Daemons
        elif name == "run_bash":
            return self.shell.run_bash(
                command=args.get("command", ""),
                auto_approve=auto_approve
            )
        elif name == "run_in_background":
            return self.shell.run_in_background(
                command=args.get("command", "")
            )
        elif name == "get_background_logs":
            return self.shell.get_background_logs(
                job_id=args.get("job_id", ""),
                lines=args.get("lines", 50)
            )
        elif name == "stop_background_job":
            return self.shell.stop_background_job(
                job_id=args.get("job_id", "")
            )
        elif name == "list_background_jobs":
            return self.shell.list_background_jobs()

        # Web & Online Docs
        elif name == "web_fetch":
            return self.web.web_fetch(
                url=args.get("url", "")
            )
        elif name == "web_search":
            return self.web.web_search(
                query=args.get("query", ""),
                max_results=args.get("max_results", 5)
            )

        # Sub-Agents
        elif name == "dispatch_agent":
            if self._subagent_runner is None:
                from quantro.agent.subagent import SubAgentRunner
                self._subagent_runner = SubAgentRunner(str(self.project_root))
            return self._subagent_runner.dispatch(
                role=args.get("role", "plan"),
                prompt=args.get("prompt", ""),
                max_steps=args.get("max_steps", 15)
            )

        # MCP
        elif name == "call_mcp_tool":
            return mcp_client.call_tool(
                server_name=args.get("server_name", ""),
                tool_name=args.get("tool_name", ""),
                arguments=args.get("arguments", {})
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
            "description": "Creates a new file or completely overwrites an existing file with provided content. Validates syntax.",
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
            "description": "Replaces code using fuzzy matching (whitespace & indentation tolerant). Returns unified diff preview and AST syntax warnings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to edit."},
                    "search_block": {"type": "string", "description": "Code snippet to locate."},
                    "replace_block": {"type": "string", "description": "New replacement code."}
                },
                "required": ["path", "search_block", "replace_block"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "multi_edit",
            "description": "Applies multiple search/replace edits sequentially to a single file in one atomic transaction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File to edit."},
                    "edits": {
                        "type": "array",
                        "description": "Array of objects containing 'search' and 'replace' string pairs.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "search": {"type": "string"},
                                "replace": {"type": "string"}
                            },
                            "required": ["search", "replace"]
                        }
                    }
                },
                "required": ["path", "edits"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash",
            "description": "Executes shell command in project directory with streaming output and granular security checks.",
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
            "name": "run_in_background",
            "description": "Starts a long-running support process (dev server, file watcher, daemon) in background without blocking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to run in background (e.g. 'npm run dev')."}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_background_logs",
            "description": "Fetches recent log output from a background job.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "ID of background job (e.g. 'job-1')."},
                    "lines": {"type": "integer", "description": "Number of recent lines to retrieve (default: 50)."}
                },
                "required": ["job_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stop_background_job",
            "description": "Terminates an active background process.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "ID of background job to stop."}
                },
                "required": ["job_id"]
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
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Fetches web page or documentation at URL and converts HTML to clean readable Markdown.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "HTTP or HTTPS URL to fetch."}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches DuckDuckGo for documentation, APIs, error messages, and package specs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "max_results": {"type": "integer", "description": "Number of results (default: 5)."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "dispatch_agent",
            "description": "Spawns an isolated sub-agent in a clean throwaway session to research or explore codebase without bloating main conversation context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "enum": ["plan", "build", "review", "test"], "description": "Role for the sub-agent."},
                    "prompt": {"type": "string", "description": "Specific research or task instruction for the sub-agent."},
                    "max_steps": {"type": "integer", "description": "Maximum steps for sub-agent (default: 15)."}
                },
                "required": ["role", "prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "call_mcp_tool",
            "description": "Invokes a tool on a registered external MCP server via JSON-RPC stdio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server_name": {"type": "string", "description": "Registered MCP server name from ~/.quantro/config.json."},
                    "tool_name": {"type": "string", "description": "Name of the tool to invoke on the server."},
                    "arguments": {"type": "object", "description": "Arguments payload for the tool."}
                },
                "required": ["server_name", "tool_name"]
            }
        }
    }
]
