"""
Quantro Sub-Agent Dispatcher (Isolated Sub-Task Execution)
Spawns temporary isolated agent sessions to explore, research, or test without bloating main context.
"""

import uuid
from typing import Dict, Any, Optional

from quantro.session import Session
from quantro.agent.roles import ROLE_DEFINITIONS


class SubAgentRunner:
    """Runs a dedicated sub-agent in a throwaway session and returns distilled synthesis."""

    def __init__(self, project_dir: str):
        self.project_dir = project_dir

    def dispatch(self, role: str, prompt: str, max_steps: int = 15) -> Dict[str, Any]:
        """
        Launches an isolated sub-agent. Returns the final answer string.
        """
        # Lazy import to avoid circular dependency
        from quantro.agent.loop import AgentEngine

        role_key = role.lower()
        if role_key not in ROLE_DEFINITIONS:
            role_key = "plan"

        # Ephemeral session with unique ID
        sub_id = f"sub-{uuid.uuid4().hex[:6]}"
        sub_session = Session(
            session_id=sub_id,
            title=f"Subtask: {prompt[:30]}",
            project_dir=self.project_dir
        )

        sub_engine = AgentEngine(sub_session, auto_approve=True)

        try:
            result_text = sub_engine.run(
                f"[SUB-AGENT TASK - ROLE: {role_key.upper()}]\n{prompt}\n"
                f"Please conduct the necessary investigation, summarize your findings, and provide a clear, concise conclusion.",
                max_steps=max_steps
            )

            return {
                "success": True,
                "subagent_id": sub_id,
                "role": role_key,
                "steps_taken": len(sub_session.messages),
                "tokens_used": sub_session.total_tokens,
                "synthesis": result_text or "(Sub-agent completed without output)"
            }
        except Exception as e:
            return {
                "success": False,
                "subagent_id": sub_id,
                "error": f"Sub-agent execution error: {str(e)}"
            }
