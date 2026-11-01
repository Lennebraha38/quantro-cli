"""
Quantro 2.0 Autonomous Agent Execution Engine
Features SSE token streaming, live reasoning output, multi-action timelines, auto-compaction,
and graceful Ctrl+C interruption without terminating the host process.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx

from quantro.config import config_manager
from quantro.session import Session, session_store
from quantro.agent.memory import MemoryManager
from quantro.agent.roles import ROLE_DEFINITIONS
from quantro.tools import ToolExecutor, TOOLS_SCHEMA
from quantro import ui


class AgentEngine:
    """Manages the autonomous tool-calling execution lifecycle with SSE streaming."""

    def __init__(self, session: Session, auto_approve: bool = False):
        self.session = session
        self.auto_approve = auto_approve
        self.project_path = Path(session.project_dir).resolve()
        self.memory = MemoryManager(self.project_path)
        self.executor = ToolExecutor(self.project_path, session=session)

    def run(self, user_prompt: str, max_steps: int = 30) -> str:
        """Executes full autonomous turn for the prompt with SSE token streaming."""
        api_key = config_manager.get_api_key()
        if not api_key:
            err = (
                f"API anahtarı bulunamadı! Aktif sağlayıcı: {config_manager.active_provider}.\n"
                f"Lütfen export {config_manager.active_provider.upper()}_API_KEY='...' ayarlayın."
            )
            ui.console.print(f"[bold red]{err}[/bold red]")
            return err

        # Check and apply auto-compact if session exceeds token limit
        compacted = self.memory.check_and_auto_compact(self.session)
        if compacted:
            ui.console.print("[dim cyan]⚡ [Auto-Compact] Oturum hafızası otomatik olarak sıkıştırıldı.[/dim cyan]")

        # Update title if new session
        self.session.update_title_from_first_prompt(user_prompt)
        self.session.messages.append({"role": "user", "content": user_prompt})

        step_idx = 0
        final_answer = ""

        try:
            while step_idx < max_steps:
                step_idx += 1

                # Construct messages payload with active agent role and project memory
                sys_prompt = self.memory.build_system_prompt(config_manager.active_agent)
                full_messages = [{"role": "system", "content": sys_prompt}] + self.session.messages

                base_url = config_manager.get_base_url().rstrip("/")
                endpoint = f"{base_url}/chat/completions"
                active_model = config_manager.active_model

                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                if "openrouter.ai" in base_url:
                    headers["HTTP-Referer"] = "https://github.com/Lennebraha38/quantro-cli"
                    headers["X-Title"] = "Quantro 2.0"

                body = {
                    "model": active_model,
                    "messages": full_messages,
                    "tools": TOOLS_SCHEMA,
                    "temperature": 0.2,
                    "stream": True,
                    "stream_options": {"include_usage": True}
                }

                accumulated_content = ""
                accumulated_reasoning = ""
                accumulated_tool_calls: Dict[int, Dict[str, Any]] = {}
                prompt_tokens_est = 0
                completion_tokens_est = 0
                has_streamed_content = False
                has_streamed_reasoning = False

                role_badge = ROLE_DEFINITIONS.get(config_manager.active_agent, {}).get("badge", "BUILD")

                try:
                    with httpx.Client(timeout=120.0) as client:
                        with client.stream("POST", endpoint, headers=headers, json=body) as response:
                            if response.status_code != 200:
                                err_text = response.read().decode("utf-8", errors="replace")
                                ui.console.print(f"[bold red]API Hatası (HTTP {response.status_code}): {err_text}[/bold red]")
                                return f"API Hatası ({response.status_code})"

                            for raw_line in response.iter_lines():
                                line = raw_line.strip()
                                if not line or not line.startswith("data:"):
                                    continue
                                data_str = line[5:].strip()
                                if data_str == "[DONE]":
                                    break

                                try:
                                    chunk = json.loads(data_str)
                                except Exception:
                                    continue

                                # Capture usage if provided in stream chunk
                                if "usage" in chunk and chunk["usage"]:
                                    prompt_tokens_est = chunk["usage"].get("prompt_tokens", 0)
                                    completion_tokens_est = chunk["usage"].get("completion_tokens", 0)

                                choices = chunk.get("choices", [])
                                if not choices:
                                    continue
                                delta = choices[0].get("delta", {})

                                # 1. Stream reasoning (DeepSeek R1 / OpenRouter reasoning)
                                r_chunk = delta.get("reasoning_content") or delta.get("reasoning")
                                if r_chunk:
                                    if not has_streamed_reasoning:
                                        ui.stream_start_reasoning()
                                        has_streamed_reasoning = True
                                    accumulated_reasoning += r_chunk
                                    ui.stream_token(r_chunk, is_reasoning=True)

                                # 2. Stream content tokens
                                c_chunk = delta.get("content")
                                if c_chunk:
                                    if has_streamed_reasoning and not has_streamed_content:
                                        ui.stream_end()
                                    if not has_streamed_content:
                                        has_streamed_content = True
                                        ui.console.print(f"\n[bold white]Quantro[/bold white] [dim]· {active_model}[/dim]\n")
                                    accumulated_content += c_chunk
                                    ui.stream_token(c_chunk, is_reasoning=False)

                                # 3. Accumulate tool call fragments
                                tc_chunks = delta.get("tool_calls", [])
                                for tc in tc_chunks:
                                    tc_idx = tc.get("index", 0)
                                    if tc_idx not in accumulated_tool_calls:
                                        accumulated_tool_calls[tc_idx] = {
                                            "id": tc.get("id", ""),
                                            "type": "function",
                                            "function": {
                                                "name": tc.get("function", {}).get("name", ""),
                                                "arguments": ""
                                            }
                                        }
                                    if tc.get("id"):
                                        accumulated_tool_calls[tc_idx]["id"] = tc.get("id")
                                    if tc.get("function", {}).get("name"):
                                        accumulated_tool_calls[tc_idx]["function"]["name"] = tc.get("function", {}).get("name")
                                    if tc.get("function", {}).get("arguments"):
                                        accumulated_tool_calls[tc_idx]["function"]["arguments"] += tc.get("function", {}).get("arguments")

                except KeyboardInterrupt:
                    ui.render_interrupted()
                    self.session.messages.append({
                        "role": "assistant",
                        "content": accumulated_content + " (Kullanıcı tarafından durduruldu)"
                    })
                    session_store.save(self.session)
                    return "(İşlem kullanıcı tarafından durduruldu)"

                if has_streamed_content or has_streamed_reasoning:
                    ui.stream_end()

                # Fallback token estimation if usage not returned in stream
                if not prompt_tokens_est and not completion_tokens_est:
                    prompt_tokens_est = len(json.dumps(full_messages)) // 4
                    completion_tokens_est = len(accumulated_content) // 4

                cost = self.memory.calculate_cost(active_model, prompt_tokens_est, completion_tokens_est)
                self.session.record_usage(prompt_tokens_est, completion_tokens_est, cost)

                # Format tool calls list
                sorted_indices = sorted(accumulated_tool_calls.keys())
                tool_calls_list = [accumulated_tool_calls[i] for i in sorted_indices]

                # If no tool calls, response is complete
                if not tool_calls_list:
                    self.session.messages.append({
                        "role": "assistant",
                        "content": accumulated_content
                    })
                    final_answer = accumulated_content
                    session_store.save(self.session)
                    break

                # Execute tool calls in step timeline
                ui.render_step_header(step_idx, description=f"Executing {len(tool_calls_list)} action(s)")

                self.session.messages.append({
                    "role": "assistant",
                    "content": accumulated_content or None,
                    "tool_calls": tool_calls_list
                })

                for tc in tool_calls_list:
                    call_id = tc.get("id", "")
                    func_info = tc.get("function", {})
                    func_name = func_info.get("name", "")
                    raw_args = func_info.get("arguments", "{}")

                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception:
                        args = {}

                    args_preview = ", ".join(f"{k}={repr(v)[:32]}" for k, v in args.items())
                    ui.render_tool_call(func_name, args_preview)

                    tool_result = self.executor.dispatch(func_name, args, auto_approve=self.auto_approve)
                    tool_result_str = json.dumps(tool_result, ensure_ascii=False)

                    if func_name in ("edit_file", "multi_edit") and tool_result.get("success"):
                        diff = tool_result.get("diff", "")
                        additions = tool_result.get("additions", 0)
                        deletions = tool_result.get("deletions", 0)
                        ui.render_tool_result(f"Modified {args.get('path')} (+{additions}, -{deletions})", success=True)
                        if diff:
                            ui.render_diff(diff, filename=args.get("path", ""), additions=additions, deletions=deletions)
                    elif func_name == "write_file" and tool_result.get("success"):
                        ui.render_tool_result(tool_result.get("message", "File written"), success=True)
                    elif func_name == "run_bash":
                        success = tool_result.get("success", False)
                        summary = f"Exit code {tool_result.get('exit_code', 0)}" if success else "Failed / Aborted"
                        ui.render_tool_result(summary, success=success)
                    elif func_name == "dispatch_agent":
                        sub_res = tool_result.get("synthesis", "")
                        ui.render_tool_result(f"Subagent ({tool_result.get('role')}) completed", success=True)
                    elif func_name == "web_search":
                        ui.render_tool_result(f"Found {tool_result.get('results_count', 0)} web results", success=True)
                    elif func_name == "web_fetch":
                        ui.render_tool_result(f"Fetched page ({len(tool_result.get('content', ''))} chars)", success=True)
                    else:
                        success = tool_result.get("success", True)
                        summary = "Done" if success else f"Error: {tool_result.get('error')}"
                        ui.render_tool_result(summary, success=success)

                    self.session.messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": func_name,
                        "content": tool_result_str
                    })

                ui.render_step_footer("Step actions completed")
                session_store.save(self.session)

        except KeyboardInterrupt:
            ui.render_interrupted()
            session_store.save(self.session)
            return "(İşlem durduruldu)"

        return final_answer
