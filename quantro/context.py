"""
Quantro Context & Session State Engine
Manages project memory (QUANTRO.md), token & cost calculations, file undo snapshots, and context compaction.
"""

import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

# Standard pricing table per 1M tokens in USD ($)
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # OpenRouter & DeepSeek
    "deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek/deepseek-reasoner": {"input": 0.55, "output": 2.19},
    "deepseek-reasoner": {"input": 0.55, "output": 2.19},
    # Anthropic
    "anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
    # OpenAI
    "openai/gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "openai/o3-mini": {"input": 1.10, "output": 4.40},
    "o3-mini": {"input": 1.10, "output": 4.40},
    # Google Gemini
    "google/gemini-2.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-2.5-pro": {"input": 1.25, "output": 5.00},
    "google/gemini-2.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-2.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
}

DEFAULT_FALLBACK_PRICE = {"input": 1.00, "output": 3.00}


class FileSnapshot:
    """Represents a pre-modification snapshot of a file for the undo engine."""

    def __init__(self, path: Path, content: Optional[str], existed: bool, reason: str = ""):
        self.path = path.resolve()
        self.content = content
        self.existed = existed
        self.reason = reason
        self.timestamp = time.time()


class ContextManager:
    """Tracks session conversation history, project memory, token expenditure, and undo states."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = (project_root or Path.cwd()).resolve()
        self.messages: List[Dict[str, Any]] = []
        self.undo_stack: List[FileSnapshot] = []
        self.total_input_tokens: int = 0
        self.total_output_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self.last_action_diff: Optional[str] = None

    # --- Project Memory (QUANTRO.md) ---

    def find_project_memory_file(self) -> Optional[Path]:
        """Looks for QUANTRO.md in project root or current working dir."""
        target = self.project_root / "QUANTRO.md"
        if target.exists() and target.is_file():
            return target
        return None

    def read_project_memory(self) -> Optional[str]:
        """Reads content of QUANTRO.md if present."""
        mem_file = self.find_project_memory_file()
        if mem_file:
            try:
                return mem_file.read_text(encoding="utf-8")
            except Exception:
                return None
        return None

    def initialize_project_memory(self) -> str:
        """Analyzes directory and creates a tailored QUANTRO.md file."""
        target = self.project_root / "QUANTRO.md"

        # Discover project facts
        files = [p.name for p in self.project_root.iterdir() if not p.name.startswith(".")]
        has_git = (self.project_root / ".git").exists()
        has_py = any(f.endswith(".py") or f == "pyproject.toml" or f == "setup.py" for f in files)
        has_js = any(f.endswith((".js", ".ts", ".json")) or f == "package.json" for f in files)
        has_rust = "Cargo.toml" in files
        has_go = "go.mod" in files

        detected_lang = []
        if has_py:
            detected_lang.append("Python")
        if has_js:
            detected_lang.append("JavaScript / TypeScript")
        if has_rust:
            detected_lang.append("Rust")
        if has_go:
            detected_lang.append("Go")
        if not detected_lang:
            detected_lang.append("General / Polyglot")

        content = f"""# QUANTRO.md — Project Memory & Architecture Guide

## Project Identity
- **Project Name:** {self.project_root.name}
- **Root Directory:** {self.project_root}
- **Primary Languages:** {", ".join(detected_lang)}
- **Version Control:** {"Git initialized" if has_git else "Not detected"}

## Architecture & Structure
- Key directories and entry points should be kept modular and documented.
- Follow test-driven verification before deploying changes.

## Development Guidelines
1. **Code Quality:** Ensure all modules have zero placeholder code (no `TODO`, `pass`, or mock logic).
2. **Safety:** All external shell and filesystem edits are previewed with unified diffs.
3. **Testing:** Run local test suites before completing tasks.

---
*Created automatically by Quantro CLI (`/init`). Update this file to customize agent behavior for this repository.*
"""
        target.write_text(content, encoding="utf-8")
        return str(target)

    # --- Token & Cost Tracking ---

    def record_usage(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Records token usage and increments total USD cost."""
        self.total_input_tokens += prompt_tokens
        self.total_output_tokens += completion_tokens

        pricing = MODEL_PRICING.get(model, DEFAULT_FALLBACK_PRICE)
        step_cost = (prompt_tokens / 1_000_000 * pricing["input"]) + (completion_tokens / 1_000_000 * pricing["output"])
        self.total_cost_usd += step_cost
        return step_cost

    def get_cost_summary(self) -> Dict[str, Any]:
        """Returns structured metrics for the session."""
        return {
            "total_tokens": self.total_input_tokens + self.total_output_tokens,
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "total_cost_usd": self.total_cost_usd,
            "formatted_cost": f"${self.total_cost_usd:.4f}",
            "turn_count": len(self.messages)
        }

    # --- Undo Engine ---

    def push_undo_snapshot(self, path: Path, reason: str = "") -> None:
        """Saves current state of a file before modifying it."""
        resolved = path.resolve()
        if resolved.exists() and resolved.is_file():
            try:
                content = resolved.read_text(encoding="utf-8")
                self.undo_stack.append(FileSnapshot(resolved, content, existed=True, reason=reason))
            except Exception:
                pass
        else:
            self.undo_stack.append(FileSnapshot(resolved, None, existed=False, reason=reason))

    def pop_undo(self) -> Optional[Dict[str, Any]]:
        """Restores the last file modification."""
        if not self.undo_stack:
            return None

        snapshot = self.undo_stack.pop()
        target = snapshot.path

        if snapshot.existed:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(snapshot.content or "", encoding="utf-8")
            return {
                "path": str(target),
                "action": "restored",
                "reason": snapshot.reason
            }
        else:
            if target.exists():
                target.unlink()
            return {
                "path": str(target),
                "action": "deleted_created_file",
                "reason": snapshot.reason
            }

    # --- Context Compaction ---

    def compact_history(self) -> int:
        """
        Compresses conversation history into a concise summary retaining key insights.
        Returns the count of pruned message items.
        """
        if len(self.messages) <= 4:
            return 0

        initial_count = len(self.messages)
        # Keep the latest 2 user/assistant interactions intact
        recent_messages = self.messages[-4:]
        older_messages = self.messages[:-4]

        # Form a bullet summary of pruned actions
        summaries = []
        for msg in older_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                snippet = content.strip().replace("\n", " ")[:90]
                summaries.append(f"- [{role}]: {snippet}...")
            elif msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {}).get("name", "tool")
                    summaries.append(f"- [executed tool]: {fn}")

        summary_text = (
            "[SYSTEM MEMORY SUMMARY OF PREVIOUS STEPS]\n"
            + "\n".join(summaries[-15:])  # Keep up to 15 key points
            + "\n[END OF COMPACTED HISTORY]"
        )

        compacted_msg = {
            "role": "system",
            "content": summary_text
        }

        self.messages = [compacted_msg] + recent_messages
        pruned_count = initial_count - len(self.messages)
        return max(0, pruned_count)
