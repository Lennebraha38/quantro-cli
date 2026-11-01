"""
Quantro MCP (Model Context Protocol) Client Engine
Enables integration with external MCP servers via JSON-RPC stdio transport.
"""

import json
import subprocess
from typing import Dict, Any, List, Optional
from quantro.config import config_manager


class MCPClient:
    """Manages connections and tool execution across configured MCP servers."""

    def __init__(self):
        self.servers: Dict[str, Dict[str, Any]] = config_manager.mcp_servers

    def list_servers(self) -> List[Dict[str, Any]]:
        """Returns list of registered MCP server profiles."""
        return [
            {"name": name, "command": cfg.get("command"), "args": cfg.get("args", [])}
            for name, cfg in self.servers.items()
        ]

    def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Calls a tool on a registered MCP server via JSON-RPC stdio."""
        server_cfg = self.servers.get(server_name)
        if not server_cfg:
            return {"success": False, "error": f"MCP server '{server_name}' is not registered in config.json"}

        command = server_cfg.get("command")
        args = server_cfg.get("args", [])

        if not command:
            return {"success": False, "error": f"Invalid configuration for MCP server '{server_name}'"}

        cmd_list = [command] + args

        # Prepare JSON-RPC request
        rpc_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        try:
            process = subprocess.Popen(
                cmd_list,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, stderr = process.communicate(input=json.dumps(rpc_request) + "\n", timeout=30)

            if process.returncode != 0:
                return {
                    "success": False,
                    "server": server_name,
                    "tool": tool_name,
                    "exit_code": process.returncode,
                    "error": stderr.strip() or stdout.strip()
                }

            # Parse JSON-RPC response
            for line in stdout.splitlines():
                if line.strip().startswith("{") and "jsonrpc" in line:
                    try:
                        res = json.loads(line)
                        if "error" in res:
                            return {"success": False, "error": res["error"]}
                        return {"success": True, "result": res.get("result")}
                    except Exception:
                        pass

            return {"success": True, "output": stdout.strip()}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"MCP tool call timed out (30s): {tool_name}"}
        except Exception as e:
            return {"success": False, "error": f"MCP execution error: {str(e)}"}


mcp_client = MCPClient()
