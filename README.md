# ⚡ Quantro 2.0 (OpenCode & Claude Code Peer Architecture)

> **Autonomous Terminal Coding & Software Engineering Agent**  
> Built for developers who live in the terminal. Features live SSE token streaming, `@` fuzzy file referencing, fuzzy code patching, AST syntax diagnostics, background daemon shell, sub-agent isolation, web search, MCP support, granular permissions, and automated Git workflows.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Version: 2.0.0](https://img.shields.io/badge/version-2.0.0-cyan)](https://github.com/Lennebraha38/quantro-cli)
[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)](https://www.python.org/)
[![Architecture: OpenCode 2.0](https://img.shields.io/badge/architecture-OpenCode%202.0-magenta)](https://github.com/Lennebraha38/quantro-cli)

---

## 🏛️ OpenCode 2.0 Modular Architecture

```
quantro-cli/
├── pyproject.toml              # Entry point: `quantro = quantro.cli:main`
├── README.md                   # Complete documentation
├── LICENSE                     # MIT License
└── quantro/
    ├── __init__.py             # Version (2.0.0)
    ├── cli.py                  # OpenCode subcommands, @ fuzzy completer, /commit, /review & REPL
    ├── config.py               # Granular security policies (safe whitelist vs dangerous prompt), MCP config
    ├── ui.py                   # OpenCode 2.0 visual telemetry, step timeline, live SSE streaming & diffs
    ├── agent/
    │   ├── loop.py             # SSE streaming ReAct loop with Ctrl+C interrupt preservation
    │   ├── roles.py            # Specialized roles: BUILD, PLAN, REVIEW, TEST
    │   ├── memory.py           # QUANTRO.md project memory, output pruning & auto-compaction
    │   └── subagent.py         # Isolated sub-agent execution (`dispatch_agent`)
    ├── session/
    │   └── storage.py          # Session persistence (~/.quantro/sessions/<id>.json), resume (-c / -s)
    ├── tools/
    │   ├── fs.py               # Fuzzy edit, multi_edit, unified diffs & AST/LSP syntax diagnostics
    │   ├── shell.py            # Live output streaming & background daemon manager (run_in_background)
    │   ├── search.py           # list_files, grep_search (noise filtering)
    │   ├── web.py              # web_fetch (HTML to Markdown) & web_search (DuckDuckGo integration)
    │   ├── mcp.py              # Model Context Protocol (MCP) JSON-RPC client
    │   └── registry.py         # Unified tool dispatcher & 13 OpenAI function schemas
    └── skills/
        └── __init__.py         # Custom skills discovery (.quantro/skills & ~/.quantro/skills)
```

---

## 🌟 8 Deep Engineering Capabilities

### 1. Live SSE Token Streaming & Non-Destructive Ctrl+C
- Uses Server-Sent Events (`stream=True`) to stream thinking/reasoning and code responses token-by-token.
- Pressing **Ctrl+C** or **Esc** cleanly interrupts only the active LLM generation or long-running tool and drops back to the prompt `❯` without killing the REPL session.

### 2. `@` Fuzzy File Mentions & Automatic Context Injection
- Typing `@` opens dynamic fuzzy autocomplete across the repository.
- Referencing `@src/app.py` in your prompt automatically reads and embeds the file content into the agent's context.

### 3. Fuzzy Code Patching, `multi_edit`, and AST Syntax Self-Correction
- **Whitespace & Indentation Tolerant:** Fuzzy matching ensures code edits succeed even if the model slightly alters indentation.
- **`multi_edit`:** Applies multiple search/replace blocks across a file in a single atomic transaction.
- **AST / Syntax Diagnostics:** After saving Python or JSON files, validates syntax via `ast.parse`. If a syntax error is introduced, the error is immediately returned to the agent so it self-corrects before continuing.

### 4. Live Output Streaming & Background Daemon Shell
- Foreground commands stream their output line-by-line so your terminal never locks up during long builds or test suites.
- Long-running servers (`npm run dev`, `python -m http.server`) run as background jobs (`run_in_background`) with output ring buffers and log retrieval (`get_background_logs`).

### 5. Sub-Agent Delegation (`dispatch_agent`)
- When researching large codebases or reading dozens of files, the main agent launches an isolated sub-agent.
- The sub-agent inspects 15-20 files in a temporary session, terminates, and returns a concise summary back to the main agent, keeping the primary context window lean and focused.

### 6. Internet Access (`web_fetch` & `web_search`) and MCP Support
- **`web_fetch`:** Fetches remote documentation or URLs and converts raw HTML into clean, readable Markdown.
- **`web_search`:** Performs real-time online searches for APIs, libraries, and error messages.
- **MCP Client:** Connects to Model Context Protocol servers configured in `~/.quantro/config.json`.

### 7. Granular Command Security Policy
- **Safe Whitelist:** Commands like `git status`, `git diff`, `ls`, `cat`, and `pytest` are automatically allowed.
- **Strict Confirmation:** Dangerous commands like `rm`, `sudo`, `git push`, and `chmod` ALWAYS require interactive confirmation (`[E]vet / [H]ayır`), even if general shell approval is active.

### 8. Auto-Compact & Automated Git Workflows (`/commit` & `/review`)
- **Auto-Compact:** Triggers automatically when tokens reach the threshold (e.g. 35k tokens), pruning older tool outputs and summarizing conversation history.
- **`/commit`:** Analyzes working tree diffs, generates conventional commit messages (`feat(...)`, `fix(...)`), stages files, and commits with one click.
- **`/review`:** Executes automated senior code review on unstaged or staged git changes.

---

## 🚀 Installation & Usage

```bash
git clone https://github.com/Lennebraha38/quantro-cli.git
cd quantro-cli
pip install -e .
```

### Starting Quantro
```bash
quantro                         # Launch interactive session
quantro -c                      # Resume previous session
quantro -s <id>                 # Resume specific session
quantro -a review               # Launch in REVIEWER mode
quantro -a plan                 # Launch in PLANNER mode
quantro --auto                  # Auto-approve non-dangerous commands
```

### Subcommands
```bash
quantro run "Run test suite and fix failing tests"
quantro session list
quantro models
quantro stats
quantro auth -p openrouter -k "sk-or-v1-..."
```

### Slash Commands Cheat Sheet
| Command | Action |
| :--- | :--- |
| `@<file>` | Fuzzy file reference and context injection |
| `/commit` | Generate conventional commit from git diff and commit |
| `/review` | Audit git changes with Senior Reviewer agent |
| `/agent [role]` | Switch agent role (`build`, `plan`, `review`, `test`) |
| `/model [name]` | Switch LLM model |
| `/session [list\|new]` | Manage sessions |
| `/init` | Generate repository guide (`QUANTRO.md`) |
| `/diff` | Inspect git diff or last file edit |
| `/undo` | Roll back last file modification |
| `/compact` | Compress session history |
| `/cost` | View session token and cost analytics |
| `/clear` | Clear terminal screen |
| `/exit`, `/quit` | Save and exit session |

---

## 📄 License

MIT © [Faruk Hilmi Akpinar](https://github.com/Lennebraha38)
