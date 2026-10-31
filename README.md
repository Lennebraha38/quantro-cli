# ⚡ Quantro 2.0

> **Autonomous Terminal Coding & Software Engineering Agent**  
> Architected following **OpenCode 2.0** and **Claude Code** standards: specialized agent roles (`build`, `plan`, `review`, `test`), full session persistence, step telemetry timeline, and instant unified diffs.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Version: 2.0.0](https://img.shields.io/badge/version-2.0.0-cyan)](https://github.com/Lennebraha38/quantro-cli)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![Architecture: OpenCode 2.0](https://img.shields.io/badge/architecture-OpenCode%202.0-magenta)](https://github.com/Lennebraha38/quantro-cli)

---

## 🏛️ OpenCode 2.0 Modular Architecture

Quantro 2.0 decouples agent orchestration, session storage, tool dispatch, and visual telemetry into modular subsystems:

```
quantro-cli/
├── pyproject.toml              # Packaging & entry point (`quantro = quantro.cli:main`)
├── README.md                   # Complete documentation
├── LICENSE                     # MIT License
└── quantro/
    ├── __init__.py             # Version (2.0.0)
    ├── cli.py                  # CLI Subcommands (run, session, models, stats, auth) & REPL
    ├── config.py               # Credentials, permission policies (ask/allow/deny)
    ├── ui.py                   # OpenCode 2.0 visual telemetry, step timeline & diffs
    ├── agent/
    │   ├── loop.py             # ReAct multi-step autonomous tool execution loop
    │   ├── roles.py            # Specialized roles: BUILD, PLAN, REVIEW, TEST
    │   └── memory.py           # QUANTRO.md project memory & context compaction
    ├── session/
    │   └── storage.py          # Multi-session persistence (~/.quantro/sessions/<id>.json), resume (-c)
    ├── tools/
    │   ├── fs.py               # read_file, write_file, edit_file (with unified diffs & undo snapshots)
    │   ├── shell.py            # run_bash (permission check [E]/[H]/[D], timeout handling)
    │   ├── search.py           # list_files, grep_search (noise filtering)
    │   └── registry.py         # Unified tool dispatcher & OpenAI function schemas
    └── skills/
        └── __init__.py         # Custom skills discovery (.quantro/skills and ~/.quantro/skills)
```

---

## 🌟 Key Capabilities

### 1. Specialized Agent Roles
Switch roles on the fly using `/agent <mode>` or CLI flag `-a <mode>`:
- **`BUILD` (Developer):** Autonomous feature implementation, refactoring, and bug fixes.
- **`PLAN` (Architect):** Deep codebase inspection and step-by-step roadmap drafting without touching files.
- **`REVIEW` (Senior Reviewer):** Comprehensive audit of git working tree, identifying bugs, security flaws, and regressions.
- **`TEST` (QA Engineer):** Test suite execution via `run_bash`, generating unit tests and asserting coverage.

### 2. Multi-Session Persistence & Resume
- Automatically persists turns, undo snapshots, token metrics, and tool calls under `~/.quantro/sessions/`.
- Resume the last active session with:
  ```bash
  quantro -c
  # Or resume a specific session by ID:
  quantro -s 3f9a1b2c
  ```
- Manage stored sessions:
  ```bash
  quantro session list
  quantro session delete <id>
  ```

### 3. OpenCode 2.0 Inline Telemetry
No full-screen TUI locks. Quantro 2.0 renders high-density visual telemetry directly in terminal scrollback:
```text
┌── quantro 2.0 ────────────────────────────────────────── [BUILD] ──┐
│ 📂 /root/projects/quantro-cli                                       │
│ 🤖 deepseek/deepseek-chat (OpenRouter) │ ⚡ session: 7b841e0a        │
└─────────────────────────────────────────────────────────────────────┘

┌─ Step 1 · Executing 2 action(s)
│ ⚡ list_files(directory='.', max_depth=2)
│   ↳ Done
│ ⚡ read_file(path='quantro/cli.py', start_line=1, end_line=50)
│   ↳ Done
└─ ✓ Step actions completed

┌── Code Diff: quantro/cli.py (+14 -2) ───────────────────────────────┐
│ @@ -20,4 +20,16 @@                                                  │
│ - old_implementation()                                              │
│ + new_production_code()                                             │
└─────────────────────────────────────────────────────────────────────┘
```

### 4. Safety & Permissions Engine
- Permission levels: `ask` (default), `allow` (`--auto`), `deny`.
- Shell prompts: `[E]vet / [H]ayır / [D]aima`. Choosing `D` enables auto-approval for the remainder of the session.

### 5. Multi-Provider LLM Support
- **OpenRouter** (`deepseek/deepseek-chat`, `anthropic/claude-3.5-sonnet`, `openai/gpt-4o`, `meta-llama/llama-3.3-70b-instruct`)
- **Google Gemini** (`gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-1.5-pro`)
- **DeepSeek Official** (`deepseek-chat`, `deepseek-reasoner`)
- **OpenAI** (`gpt-4o`, `gpt-4o-mini`, `o3-mini`, `o1`)

---

## 📦 Installation

```bash
git clone https://github.com/Lennebraha38/quantro-cli.git
cd quantro-cli
pip install -e .
```

---

## 🚀 CLI Commands & Subcommands

### Subcommands
```bash
# Direct task execution
quantro run "Refactor configuration parser and run pytest"

# View usage telemetry & token expenditure
quantro stats

# Inspect supported providers and model catalog
quantro models

# List or delete sessions
quantro session list
quantro session delete <session_id>

# Store provider credentials
quantro auth -p openrouter -k "sk-or-v1-..."
```

### Interactive REPL Flags
```bash
quantro                         # Start new session in current directory
quantro -c                      # Continue last session
quantro -s <id>                 # Resume specific session
quantro -a plan                 # Start in PLANNER role
quantro -a review               # Start in REVIEWER role
quantro -m gpt-4o               # Start with specific model
quantro --auto                  # Auto-approve shell execution
```

---

## 🎮 Interactive Slash Commands

Inside the REPL, type `/` to access commands with autocomplete:

| Slash Command | Description |
| :--- | :--- |
| `/help` | Display interactive command cheat sheet |
| `/agent [role]` | Switch agent mode: `build`, `plan`, `review`, `test` |
| `/model [name]` | View model table or switch active LLM |
| `/session [list\|new]` | Manage, list, or start new sessions |
| `/skills` | List discovered project and user skills |
| `/init` | Analyze repository and generate `QUANTRO.md` |
| `/diff` | Inspect git diff or last agent file change |
| `/undo` | Roll back the last file edit made by Quantro |
| `/compact` | Compress history to free token context window |
| `/cost` | Display session token usage and USD pricing breakdown |
| `/clear` | Clear terminal screen |
| `/exit`, `/quit` | Save session state and exit |

---

## 📄 License

MIT © [Faruk Hilmi Akpinar](https://github.com/Lennebraha38)
