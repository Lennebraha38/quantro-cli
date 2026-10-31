"""
Quantro 2.0 Session Storage Engine
Handles JSON-based persistence of multi-turn sessions, resume capability (-c / -s), and metadata index.
"""

import os
import json
import uuid
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from quantro.config import SESSIONS_DIR, config_manager


@dataclass
class SessionMetadata:
    id: str
    title: str
    created_at: float
    updated_at: float
    model: str
    provider: str
    project_dir: str
    total_tokens: int
    total_cost_usd: float
    turn_count: int


class Session:
    """Represents an active or persisted Quantro engineering session."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        title: str = "New Session",
        project_dir: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        total_tokens: int = 0,
        total_cost_usd: float = 0.0
    ):
        self.id = session_id or uuid.uuid4().hex[:8]
        self.title = title
        self.project_dir = project_dir or str(Path.cwd().resolve())
        self.model = model or config_manager.active_model
        self.provider = provider or config_manager.active_provider
        self.messages: List[Dict[str, Any]] = messages or []
        self.created_at = time.time()
        self.updated_at = time.time()
        self.total_tokens = total_tokens
        self.total_cost_usd = total_cost_usd
        self.undo_stack: List[Dict[str, Any]] = []
        self.last_diff: Optional[str] = None

    def record_usage(self, prompt_tokens: int, completion_tokens: int, cost: float):
        self.total_tokens += (prompt_tokens + completion_tokens)
        self.total_cost_usd += cost
        self.updated_at = time.time()

    def update_title_from_first_prompt(self, prompt: str):
        if self.title == "New Session" and prompt.strip():
            # Generate clean 4-6 word title
            cleaned = prompt.strip().replace("\n", " ")
            self.title = cleaned[:50] + ("..." if len(cleaned) > 50 else "")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "project_dir": self.project_dir,
            "model": self.model,
            "provider": self.provider,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "messages": self.messages,
            "undo_stack": self.undo_stack,
            "turn_count": len([m for m in self.messages if m.get("role") == "user"])
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        s = cls(
            session_id=data.get("id"),
            title=data.get("title", "Session"),
            project_dir=data.get("project_dir"),
            model=data.get("model"),
            provider=data.get("provider"),
            messages=data.get("messages", []),
            total_tokens=data.get("total_tokens", 0),
            total_cost_usd=data.get("total_cost_usd", 0.0)
        )
        s.created_at = data.get("created_at", time.time())
        s.updated_at = data.get("updated_at", time.time())
        s.undo_stack = data.get("undo_stack", [])
        return s


class SessionStore:
    """Manages storage and retrieval of sessions in ~/.quantro/sessions/."""

    def __init__(self, storage_dir: Optional[Path] = None):
        self.dir = storage_dir or SESSIONS_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, session_id: str) -> Path:
        return self.dir / f"{session_id}.json"

    def save(self, session: Session) -> None:
        session.updated_at = time.time()
        path = self._file_path(session.id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)

    def load(self, session_id: str) -> Optional[Session]:
        path = self._file_path(session_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return Session.from_dict(data)
        except Exception:
            return None

    def load_latest(self, project_dir: Optional[str] = None) -> Optional[Session]:
        """Finds the most recently updated session matching project_dir."""
        sessions = self.list_all()
        if project_dir:
            sessions = [s for s in sessions if s.project_dir == project_dir]

        if not sessions:
            return None

        # Sorted by updated_at descending
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return self.load(sessions[0].id)

    def list_all(self) -> List[SessionMetadata]:
        results: List[SessionMetadata] = []
        for p in self.dir.glob("*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    results.append(SessionMetadata(
                        id=data.get("id", p.stem),
                        title=data.get("title", "Untitled"),
                        created_at=data.get("created_at", 0),
                        updated_at=data.get("updated_at", 0),
                        model=data.get("model", "unknown"),
                        provider=data.get("provider", "unknown"),
                        project_dir=data.get("project_dir", ""),
                        total_tokens=data.get("total_tokens", 0),
                        total_cost_usd=data.get("total_cost_usd", 0.0),
                        turn_count=data.get("turn_count", 0)
                    ))
            except Exception:
                continue

        results.sort(key=lambda s: s.updated_at, reverse=True)
        return results

    def delete(self, session_id: str) -> bool:
        path = self._file_path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False


session_store = SessionStore()
