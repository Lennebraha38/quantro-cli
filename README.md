# ⚡ Quantro CLI

> **Autonomous Terminal Coding & Software Engineering Agent**  
> Designed with Claude Code & OpenCode architecture for developers who live in the terminal.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![Code Style: Production Ready](https://img.shields.io/badge/code%20quality-100%25%20production-green)](https://github.com/Lennebraha38/quantro-cli)

Quantro is an autonomous, inline-scrollback terminal AI pair programmer. It navigates repositories, reads files with line numbering, performs edits with colored unified diffs, runs builds and tests in your shell, and maintains persistent project memory — all directly from your terminal.

---

## 🌟 Key Features

- **Inline Scrollback UI:** No clunky full-screen TUI apps. Quantro flows naturally in your terminal history, displaying branch tree logs (`● Read(src/main.py)` ➔ `  ⎿  120 satır okundu.`).
- **Production-Quality Autonomous Loop:** Equipped with ReAct tool-calling logic that reads before modifying, verifies syntax, and inspects errors.
- **Unified Diff Viewer & Undo Engine:** Every file modification displays a color-coded unified diff and snapshots previous states. Revert unwanted changes instantly with `/undo`.
- **Multi-Provider & Model Agnostic:**
  - **OpenRouter** (DeepSeek, Claude 3.5 Sonnet, GPT-4o, Llama 3.3)
  - **Google Gemini** (Gemini 2.5 Pro, Gemini 2.5 Flash)
  - **DeepSeek Official** (DeepSeek V3, DeepSeek R1 / Reasoner)
  - **OpenAI** (GPT-4o, GPT-4o mini, o3-mini)
- **Interactive Shell Safety:** Shell commands require explicit approval (`[E]vet / [H]ayır / [D]aima`) unless overridden.
- **Live Token & Cost Meter:** Real-time token usage and USD pricing tracking across all providers.
- **Persistent Project Memory (`QUANTRO.md`):** Automatically scans and stores project architecture, coding rules, and conventions for context preservation.

---

## 📦 Installation

### From Source (Editable Mode)

```bash
git clone https://github.com/Lennebraha38/quantro-cli.git
cd quantro-cli
pip install -e .
```

*Note: On Linux distributions with externally-managed environments (PEP 668), add `--break-system-packages` if not using a virtualenv.*

---

## 🚀 Quick Start

### 1. Configure Your API Key

Quantro supports standard environment variables:

```bash
# OpenRouter (Default)
export OPENROUTER_API_KEY="sk-or-v1-..."

# Or Google Gemini
export GEMINI_API_KEY="AIzaSy..."

# Or DeepSeek
export DEEPSEEK_API_KEY="sk-..."

# Or OpenAI
export OPENAI_API_KEY="sk-proj-..."
```

Alternatively, you can pass your API key or configure it in `~/.quantro/config.json`:

```bash
quantro --api-key "your-api-key"
```

### 2. Interactive REPL Mode

Simply run `quantro` inside any repository:

```bash
quantro
```

### 3. Fast Single-Shot Mode

Execute tasks directly from your shell without entering the REPL:

```bash
quantro "Find all occurrences of deprecated API in src/ and update them"
quantro "Run test suite and fix any failing assertions in tests/test_core.py"
```

---

## 🎮 Slash Commands

Within the interactive REPL, prefix commands with `/`:

| Command | Description |
| :--- | :--- |
| `/help` | Display the commands quick reference |
| `/model [name]` | View active model or switch to a new model/provider |
| `/init` | Scan repository and generate/update `QUANTRO.md` project guide |
| `/diff` | Inspect git diff or review the agent's last file modification |
| `/undo` | Roll back the last file edit made by Quantro |
| `/compact` | Compress long conversation history into a structured summary |
| `/cost` | Display session token usage and estimated USD cost breakdown |
| `/clear` | Clear the terminal screen |
| `/exit`, `/quit` | Exit the Quantro interactive session |

---

## 🛠️ Built-in Autonomous Tools

Quantro provides 6 production-grade tools used autonomously during tasks:

1. `read_file(path, start_line, end_line)`: Inspects source code with line numbers.
2. `write_file(path, content)`: Creates new modules or writes files with automatic undo snapshots.
3. `edit_file(path, search_block, replace_block)`: Safely replaces blocks of code with unified diff preview.
4. `run_bash(command)`: Executes build, test, and git commands with safety approval.
5. `list_files(directory, max_depth)`: Scans project hierarchy, filtering ignore patterns (`.git`, `node_modules`, `__pycache__`).
6. `grep_search(pattern, path, recursive)`: Performs lightning-fast regex search across the codebase.

---

## 🏗️ Architecture

```
quantro-cli/
├── pyproject.toml          # Package configuration & console entrypoint: quantro = "quantro.cli:main"
├── README.md               # Documentation and guides
├── LICENSE                 # MIT License
├── .gitignore              # Repository exclusions
└── quantro/
    ├── __init__.py         # Package version (1.0.0)
    ├── cli.py              # CLI parser, prompt_toolkit REPL, bottom toolbar, slash commands
    ├── config.py           # ~/.quantro/config.json & provider credentials
    ├── ui.py               # Rich inline scrollback UI, branch tree logs, unified diffs
    ├── agent.py            # ReAct tool-calling loop with HTTPX client
    ├── tools.py            # 6 autonomous file & shell tools + OpenAI JSON schemas
    └── context.py          # QUANTRO.md project memory, token/cost meter, undo stack
```

---

## 📄 License

MIT © [Faruk Hilmi Akpinar](https://github.com/Lennebraha38)
