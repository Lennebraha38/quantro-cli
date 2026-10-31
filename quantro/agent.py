"""
Quantro Autonomous Agent Loop
ReAct / Tool-Calling engine communicating with OpenAI-compatible LLM endpoints via HTTPX.
Manages multi-turn reasoning, tool execution, and session context.
"""

import json
import re
from typing import Dict, Any, List, Optional
import httpx

from quantro.config import config_manager
from quantro.context import ContextManager
from quantro.tools import ToolExecutor, AGENT_TOOLS_SCHEMA
from quantro import ui


BASE_SYSTEM_PROMPT = """You are Quantro, an autonomous terminal coding and software engineering agent.
You operate directly inside the user's repository via terminal tools.

Your capabilities:
1. You can inspect project structure with `list_files` and search code with `grep_search`.
2. You can read code with `read_file` (with line numbers).
3. You can edit existing code with `edit_file` (which computes unified diffs) or create new files with `write_file`.
4. You can run bash commands (builds, tests, git, package managers) with `run_bash`.

Strict Operational Rules:
- ZERO PLACEHOLDER CODE: Never use `TODO`, `pass`, ellipses `...`, or dummy mock stubs. All code must be 100% production-ready.
- VERIFICATION FIRST: Before modifying any file, read it first to verify exact indentation and surrounding context.
- SYSTEM INTEGRITY: After modifying code, run tests or syntax checks using `run_bash` whenever appropriate.
- CONCISE COMMUNICATION: Explain what you did clearly and succinctly without unnecessary boilerplate.

Current Working Directory: {project_root}
Operating System: Linux
"""


class Agent:
    """Orchestrates ReAct agent loop, tool execution, and LLM communication."""

    def __init__(self, context: ContextManager, auto_approve_bash: bool = False):
        self.context = context
        self.tool_executor = ToolExecutor(context)
        self.auto_approve_bash = auto_approve_bash

    def _build_system_message(self) -> Dict[str, str]:
        """Constructs system prompt dynamically, injecting project memory if available."""
        sys_content = BASE_SYSTEM_PROMPT.format(project_root=str(self.context.project_root))

        # Check for QUANTRO.md project memory
        project_mem = self.context.read_project_memory()
        if project_mem:
            sys_content += f"\n\n--- [PROJECT MEMORY: QUANTRO.md] ---\n{project_mem}\n--- [END PROJECT MEMORY] ---\n"

        return {"role": "system", "content": sys_content}

    def _extract_thinking(self, content: str) -> tuple[str, str]:
        """Extracts <think>...</think> reasoning blocks if present in model output."""
        match = re.search(r"<think>(.*?)</think>", content, flags=re.DOTALL)
        if match:
            thinking = match.group(1).strip()
            clean_content = content.replace(match.group(0), "").strip()
            return thinking, clean_content
        return "", content

    def run_turn(self, user_prompt: str, max_iterations: int = 30) -> str:
        """
        Executes one full conversation turn for user_prompt.
        Runs tool-calling loop until model delivers final answer.
        """
        api_key = config_manager.get_api_key()
        if not api_key:
            err = (
                f"API anahtarı bulunamadı! Aktif sağlayıcı: {config_manager.active_provider}.\n"
                f"Lütfen ortam değişkeni ayarlayın veya ~/.quantro/config.json dosyasına ekleyin.\n"
                f"Örnek: export OPENROUTER_API_KEY='anahtariniz'"
            )
            ui.print_error(err, title="API Anahtarı Eksik")
            return err

        # Append user message
        self.context.messages.append({"role": "user", "content": user_prompt})

        iteration = 0
        final_response_text = ""

        while iteration < max_iterations:
            iteration += 1

            # Prepare messages payload
            messages_payload = [self._build_system_message()] + self.context.messages

            base_url = config_manager.get_base_url().rstrip("/")
            endpoint = f"{base_url}/chat/completions"
            active_model = config_manager.active_model

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            if "openrouter.ai" in base_url:
                headers["HTTP-Referer"] = "https://github.com/Lennebraha38/quantro-cli"
                headers["X-Title"] = "Quantro CLI"

            body = {
                "model": active_model,
                "messages": messages_payload,
                "tools": AGENT_TOOLS_SCHEMA,
                "temperature": 0.2
            }

            # Call LLM endpoint
            with ui.status_spinner(f"Quantro yanıt üretiyor... ({active_model})"):
                try:
                    with httpx.Client(timeout=120.0) as client:
                        response = client.post(endpoint, headers=headers, json=body)
                except Exception as e:
                    ui.print_error(f"Ağ bağlantı hatası: {str(e)}", title="LLM Bağlantı Hatası")
                    return f"Bağlantı hatası: {str(e)}"

            if response.status_code != 200:
                err_body = response.text
                ui.print_error(f"HTTP {response.status_code}: {err_body}", title="Sağlayıcı API Hatası")
                return f"API Hatası ({response.status_code})"

            res_json = response.json()
            choice = res_json.get("choices", [{}])[0]
            message = choice.get("message", {})

            # Record token usage
            usage = res_json.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            if prompt_tokens or completion_tokens:
                self.context.record_usage(active_model, prompt_tokens, completion_tokens)

            # Check for reasoning / thinking
            raw_content = message.get("content") or ""
            reasoning = message.get("reasoning_content") or ""
            if not reasoning and "<think>" in raw_content:
                reasoning, raw_content = self._extract_thinking(raw_content)

            if reasoning:
                ui.print_thinking(reasoning)

            tool_calls = message.get("tool_calls")

            # If no tool calls, this is the final response
            if not tool_calls:
                self.context.messages.append({
                    "role": "assistant",
                    "content": raw_content
                })
                ui.print_markdown(raw_content)
                final_response_text = raw_content
                break

            # Handle tool calls
            # Append assistant message with tool calls to context
            assistant_msg_entry = {
                "role": "assistant",
                "content": raw_content or None,
                "tool_calls": tool_calls
            }
            self.context.messages.append(assistant_msg_entry)

            for tc in tool_calls:
                call_id = tc.get("id", "")
                func_info = tc.get("function", {})
                func_name = func_info.get("name", "")
                raw_args = func_info.get("arguments", "{}")

                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}

                # Display tool execution
                args_summary = ", ".join(f"{k}={repr(v)[:30]}" for k, v in args.items())
                ui.print_tool_start(func_name, args_summary)

                # Execute tool
                tool_output_dict = self._dispatch_tool(func_name, args)
                tool_result_str = json.dumps(tool_output_dict, ensure_ascii=False)

                # Render result UI
                if func_name == "edit_file" and tool_output_dict.get("success"):
                    diff = tool_output_dict.get("diff", "")
                    ui.print_tool_result(tool_output_dict.get("message", "Edit applied"), success=True)
                    if diff:
                        ui.print_diff(diff, filename=args.get("path", ""))
                elif func_name == "write_file" and tool_output_dict.get("success"):
                    ui.print_tool_result(tool_output_dict.get("message", "File written"), success=True)
                elif func_name == "run_bash":
                    success = tool_output_dict.get("success", False)
                    out = tool_output_dict.get("output", tool_output_dict.get("error", ""))
                    summary = f"Exit code {tool_output_dict.get('exit_code', 0)}" if success else "Failed/Aborted"
                    ui.print_tool_result(summary, success=success)
                    if out and len(out.splitlines()) <= 8:
                        for line in out.splitlines():
                            ui.console.print(f"    [dim]{line}[/dim]")
                else:
                    success = tool_output_dict.get("success", True)
                    summary = f"Completed ({tool_output_dict.get('count', tool_output_dict.get('matches_found', 'ok'))})"
                    if not success:
                        summary = f"Error: {tool_output_dict.get('error', 'unknown error')}"
                    ui.print_tool_result(summary, success=success)

                # Append tool result to context
                self.context.messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": func_name,
                    "content": tool_result_str
                })

        return final_response_text

    def _dispatch_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """Maps tool name to ToolExecutor implementation."""
        try:
            if name == "read_file":
                return self.tool_executor.read_file(
                    path=args.get("path", ""),
                    start_line=args.get("start_line"),
                    end_line=args.get("end_line")
                )
            elif name == "write_file":
                return self.tool_executor.write_file(
                    path=args.get("path", ""),
                    content=args.get("content", "")
                )
            elif name == "edit_file":
                return self.tool_executor.edit_file(
                    path=args.get("path", ""),
                    search_block=args.get("search_block", ""),
                    replace_block=args.get("replace_block", "")
                )
            elif name == "run_bash":
                return self.tool_executor.run_bash(
                    command=args.get("command", ""),
                    auto_approve=self.auto_approve_bash
                )
            elif name == "list_files":
                return self.tool_executor.list_files(
                    directory=args.get("directory", "."),
                    max_depth=args.get("max_depth", 3)
                )
            elif name == "grep_search":
                return self.tool_executor.grep_search(
                    pattern=args.get("pattern", ""),
                    path=args.get("path", "."),
                    recursive=args.get("recursive", True)
                )
            else:
                return {"success": False, "error": f"Unknown tool: {name}"}
        except Exception as e:
            return {"success": False, "error": f"Internal tool execution error: {str(e)}"}
