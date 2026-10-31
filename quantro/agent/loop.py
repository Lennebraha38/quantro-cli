"""
Quantro 2.0 Autonomous Agent Execution Engine
Orchestrates multi-turn ReAct loops, step timeline rendering, and session persistence.
"""

import json
import re
from typing import Dict, Any, List, Optional
import httpx

from quantro.config import config_manager
from quantro.session import Session, session_store
from quantro.agent.memory import MemoryManager
from quantro.agent.roles import ROLE_DEFINITIONS
from quantro.tools import ToolExecutor, TOOLS_SCHEMA
from quantro import ui


class AgentEngine:
    """Manages the autonomous tool-calling execution lifecycle."""

    def __init__(self, session: Session, auto_approve: bool = False):
        self.session = session
        self.auto_approve = auto_approve
        self.memory = MemoryManager(session.project_dir)
        self.executor = ToolExecutor(session.project_dir, session=session)

    def _extract_thinking(self, content: str) -> tuple[str, str]:
        match = re.search(r"<think>(.*?)</think>", content, flags=re.DOTALL)
        if match:
            return match.group(1).strip(), content.replace(match.group(0), "").strip()
        return "", content

    def run(self, user_prompt: str, max_steps: int = 30) -> str:
        """Executes full autonomous turn for the prompt."""
        api_key = config_manager.get_api_key()
        if not api_key:
            err = (
                f"API anahtarı bulunamadı! Aktif sağlayıcı: {config_manager.active_provider}.\n"
                f"Lütfen export {config_manager.active_provider.upper()}_API_KEY='...' ayarlayın."
            )
            ui.console.print(f"[bold red]{err}[/bold red]")
            return err

        # Update title if new session
        self.session.update_title_from_first_prompt(user_prompt)
        self.session.messages.append({"role": "user", "content": user_prompt})

        step_idx = 0
        final_answer = ""

        while step_idx < max_steps:
            step_idx += 1

            # Build messages payload with active agent role and project memory
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
                "temperature": 0.2
            }

            role_badge = ROLE_DEFINITIONS.get(config_manager.active_agent, {}).get("badge", "BUILD")
            with ui.spinner(f"Quantro [{role_badge}] düşünüyor... ({active_model})"):
                try:
                    with httpx.Client(timeout=120.0) as client:
                        response = client.post(endpoint, headers=headers, json=body)
                except Exception as e:
                    ui.console.print(f"[bold red]Ağ bağlantı hatası: {str(e)}[/bold red]")
                    return f"Bağlantı hatası: {str(e)}"

            if response.status_code != 200:
                ui.console.print(f"[bold red]API Hatası (HTTP {response.status_code}): {response.text}[/bold red]")
                return f"API Hatası ({response.status_code})"

            res_json = response.json()
            choice = res_json.get("choices", [{}])[0]
            message = choice.get("message", {})

            # Track tokens & cost
            usage = res_json.get("usage", {})
            p_tokens = usage.get("prompt_tokens", 0)
            c_tokens = usage.get("completion_tokens", 0)
            if p_tokens or c_tokens:
                step_cost = self.memory.calculate_cost(active_model, p_tokens, c_tokens)
                self.session.record_usage(p_tokens, c_tokens, step_cost)

            # Check for thinking
            content = message.get("content") or ""
            reasoning = message.get("reasoning_content") or ""
            if not reasoning and "<think>" in content:
                reasoning, content = self._extract_thinking(content)

            if reasoning:
                ui.render_reasoning(reasoning)

            tool_calls = message.get("tool_calls")

            # Final answer delivered without tool calls
            if not tool_calls:
                self.session.messages.append({
                    "role": "assistant",
                    "content": content
                })
                ui.render_markdown(content)
                final_answer = content
                session_store.save(self.session)
                break

            # Execute tool calls in a structured step timeline
            ui.render_step_header(step_idx, description=f"Executing {len(tool_calls)} action(s)")

            self.session.messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": tool_calls
            })

            for tc in tool_calls:
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

                if func_name == "edit_file" and tool_result.get("success"):
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
            # Persist session state after each turn step
            session_store.save(self.session)

        return final_answer
