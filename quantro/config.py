"""
Quantro 2.0 Configuration & Permissions System
Manages provider credentials, model registry, granular permission policies, MCP servers, and system paths.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional, List

CONFIG_DIR = Path.home() / ".quantro"
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"
SKILLS_GLOBAL_DIR = CONFIG_DIR / "skills"

DEFAULT_PROVIDERS = {
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "env_var": "OPENROUTER_API_KEY",
        "default_model": "deepseek/deepseek-chat",
        "recommended_models": [
            "deepseek/deepseek-chat",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
            "google/gemini-2.5-pro",
            "meta-llama/llama-3.3-70b-instruct"
        ]
    },
    "gemini": {
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "env_var": "GEMINI_API_KEY",
        "default_model": "gemini-2.5-pro",
        "recommended_models": [
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash"
        ]
    },
    "deepseek": {
        "name": "DeepSeek Official",
        "base_url": "https://api.deepseek.com/v1",
        "env_var": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
        "recommended_models": [
            "deepseek-chat",
            "deepseek-reasoner"
        ]
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "env_var": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
        "recommended_models": [
            "gpt-4o",
            "gpt-4o-mini",
            "o3-mini",
            "o1"
        ]
    }
}

SAFE_READ_COMMANDS = {
    "git status", "git diff", "git log", "git branch", "git show",
    "ls", "dir", "pwd", "cat", "head", "tail", "grep", "which",
    "pytest", "python -m unittest", "cargo test", "cargo check",
    "npm test", "bun test", "ruff check", "flake8", "mypy"
}

STRICT_DANGEROUS_COMMANDS = {
    "rm", "rmdir", "sudo", "git push", "git reset --hard", "git clean",
    "chmod", "chown", "dd", "mkfs", "kill", "pkill", "killall",
    "shutdown", "reboot", "poweroff"
}

DEFAULT_CONFIG: Dict[str, Any] = {
    "version": "2.0.0",
    "active_provider": "openrouter",
    "active_model": "deepseek/deepseek-chat",
    "active_agent": "build",
    "permissions": {
        "bash": "ask",          # "ask" | "allow" | "deny"
        "safe_whitelist_auto": True,
        "strict_dangerous_ask": True,
        "file_write": "allow",
        "file_edit": "allow",
        "file_read": "allow",
        "web_access": "allow"
    },
    "auto_compact": {
        "enabled": True,
        "threshold_tokens": 35000,
        "prune_tool_outputs": True
    },
    "mcp_servers": {},
    "providers": {
        "openrouter": {"api_key": ""},
        "gemini": {"api_key": ""},
        "deepseek": {"api_key": ""},
        "openai": {"api_key": ""}
    },
    "max_tokens": 4096,
    "temperature": 0.2
}


class ConfigManager:
    """Handles ~/.quantro/config.json with granular security policies, MCP, and env fallbacks."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or CONFIG_FILE
        self.config: Dict[str, Any] = self._load()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        SKILLS_GLOBAL_DIR.mkdir(parents=True, exist_ok=True)

    def _load(self) -> Dict[str, Any]:
        """Loads configuration from disk or initializes defaults."""
        if not self.config_path.exists():
            data = DEFAULT_CONFIG.copy()
            self._save_raw(data)
            return data

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                merged = DEFAULT_CONFIG.copy()
                for key, val in loaded.items():
                    if isinstance(val, dict) and key in merged and isinstance(merged[key], dict):
                        merged[key].update(val)
                    else:
                        merged[key] = val
                return merged
        except Exception:
            return DEFAULT_CONFIG.copy()

    def _save_raw(self, data: Dict[str, Any]) -> None:
        """Writes configuration dictionary to disk."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def save(self) -> None:
        """Persists in-memory config to disk."""
        self._save_raw(self.config)

    @property
    def active_provider(self) -> str:
        return self.config.get("active_provider", "openrouter")

    @active_provider.setter
    def active_provider(self, provider: str) -> None:
        if provider in DEFAULT_PROVIDERS:
            self.config["active_provider"] = provider
            self.save()

    @property
    def active_model(self) -> str:
        return self.config.get("active_model", "deepseek/deepseek-chat")

    @active_model.setter
    def active_model(self, model: str) -> None:
        self.config["active_model"] = model
        self.save()

    @property
    def active_agent(self) -> str:
        return self.config.get("active_agent", "build")

    @active_agent.setter
    def active_agent(self, agent: str) -> None:
        self.config["active_agent"] = agent
        self.save()

    @property
    def bash_permission(self) -> str:
        return self.config.get("permissions", {}).get("bash", "ask")

    @bash_permission.setter
    def bash_permission(self, policy: str) -> None:
        if "permissions" not in self.config:
            self.config["permissions"] = {}
        self.config["permissions"]["bash"] = policy
        self.save()

    @property
    def auto_compact_enabled(self) -> bool:
        return self.config.get("auto_compact", {}).get("enabled", True)

    @property
    def auto_compact_threshold(self) -> int:
        return self.config.get("auto_compact", {}).get("threshold_tokens", 35000)

    @property
    def mcp_servers(self) -> Dict[str, Any]:
        return self.config.get("mcp_servers", {})

    def is_safe_command(self, cmd: str) -> bool:
        """Checks if command matches safe read-only patterns."""
        cmd_clean = cmd.strip()
        first_token = cmd_clean.split()[0] if cmd_clean.split() else ""
        for safe in SAFE_READ_COMMANDS:
            if cmd_clean == safe or cmd_clean.startswith(safe + " "):
                return True
        return False

    def is_strictly_dangerous(self, cmd: str) -> bool:
        """Checks if command contains dangerous mutating primitives."""
        cmd_clean = cmd.strip()
        tokens = cmd_clean.replace(";", " ").replace("&&", " ").replace("|", " ").split()
        for tok in tokens:
            if tok in STRICT_DANGEROUS_COMMANDS:
                return True
        if "curl" in tokens and "bash" in tokens:
            return True
        if "wget" in tokens and "sh" in tokens:
            return True
        return False

    def get_api_key(self, provider: Optional[str] = None) -> Optional[str]:
        """Resolves API key with priority: env var > config file."""
        prov = provider or self.active_provider
        prov_info = DEFAULT_PROVIDERS.get(prov, {})
        env_var = prov_info.get("env_var", "")

        if env_var and os.getenv(env_var):
            return os.getenv(env_var)

        providers_dict = self.config.get("providers", {})
        prov_cfg = providers_dict.get(prov, {})
        key = prov_cfg.get("api_key", "").strip()
        if key:
            return key

        return None

    def set_api_key(self, provider: str, key: str) -> None:
        """Stores API key for a provider."""
        if "providers" not in self.config:
            self.config["providers"] = {}
        if provider not in self.config["providers"]:
            self.config["providers"][provider] = {}
        self.config["providers"][provider]["api_key"] = key.strip()
        self.save()

    def get_base_url(self, provider: Optional[str] = None) -> str:
        prov = provider or self.active_provider
        prov_info = DEFAULT_PROVIDERS.get(prov, {})
        return prov_info.get("base_url", "https://openrouter.ai/api/v1")

    def get_recommended_models(self, provider: Optional[str] = None) -> List[str]:
        prov = provider or self.active_provider
        return DEFAULT_PROVIDERS.get(prov, {}).get("recommended_models", [])


config_manager = ConfigManager()
