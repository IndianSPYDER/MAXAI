# 🤖 MAX — My Autonomous eXecutor

> **The personal AI agent that lives on your machine, not in the cloud.**

MAX is a free, open-source autonomous AI agent that runs **locally on your hardware**, connects to the LLM of your choice (Claude, GPT-4, DeepSeek, Llama), and is controlled through the messaging apps you already use — Telegram, Discord, Signal, or the command line.

MAX doesn't just answer questions. It **does things**.

---

## ✨ Features

- 🏠 **Runs locally** — your data never leaves your machine
- 🔌 **Model-agnostic** — plug in Claude, GPT-4, DeepSeek, Ollama, or any OpenAI-compatible API
- 💬 **Chat-native interface** — control MAX through Telegram, Discord, or CLI
- 🧠 **Persistent memory** — MAX remembers you across sessions
- 🛠️ **Skills system** — extend MAX with modular plugins (email, web, files, calendar, code, and more)
- 🔒 **Privacy-first** — nothing stored in the cloud, all local SQLite
- ⚡ **Async-first** — built on Python asyncio for fast, non-blocking agent loops

---

## 🚀 Quick Start

### Requirements
- Python 3.11+
- An API key for at least one LLM provider (Claude, OpenAI, DeepSeek, or a local Ollama instance)

### Install

```bash
git clone https://github.com/yourusername/MAX.git
cd MAX
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys and preferences
python main.py
```

### Run with Telegram
1. Create a bot via [@BotFather](https://t.me/botfather) and get your token
2. Add `TELEGRAM_TOKEN=your_token` to `.env`
3. Run `python main.py --interface telegram`

### Run with Discord
1. Create a Discord app at https://discord.com/developers
2. Add `DISCORD_TOKEN=your_token` to `.env`
3. Run `python main.py --interface discord`

### Run in CLI mode
```bash
python main.py --interface cli
```

---

## 🧩 Skills

Skills are modular plugins that give MAX new capabilities. Built-in skills:

| Skill | Description |
|-------|-------------|
| `web` | Search the web, fetch URLs, summarize pages |
| `email` | Read, draft, send, and organize email (IMAP/SMTP) |
| `files` | Read, write, move, and organize local files |
| `calendar` | View and create calendar events (iCal/Google) |
| `code` | Write and execute Python code in a sandbox |
| `memory` | Explicitly store and retrieve memories |
| `weather` | Fetch current weather for any location |
| `notes` | Create and search markdown notes |

### Writing a Custom Skill

```python
from skills.base import BaseSkill, skill_action

class MySkill(BaseSkill):
    name = "my_skill"
    description = "Does something useful"

    @skill_action(description="Do the thing")
    async def do_the_thing(self, input: str) -> str:
        return f"Did the thing with: {input}"
```

Drop your skill file in the `skills/` directory and MAX will auto-discover it on next boot.

---

## 🏗️ Architecture

```
MAX/
├── main.py              # Entry point & CLI
├── agent.py             # Core agent loop & reasoning engine
├── memory/
│   ├── memory.py        # Persistent memory (SQLite)
│   └── vector_store.py  # Semantic search over memories
├── skills/
│   ├── base.py          # BaseSkill class & decorators
│   ├── web.py           # Web browsing & search
│   ├── email_skill.py   # Email management
│   ├── files.py         # File system operations
│   ├── calendar_skill.py# Calendar integration
│   └── code_runner.py   # Sandboxed code execution
├── interfaces/
│   ├── base_interface.py# Abstract interface
│   ├── telegram_interface.py
│   ├── discord_interface.py
│   └── cli_interface.py
├── tools/
│   ├── tool_registry.py # Discovers and registers tools
│   └── tool_executor.py # Executes tool calls safely
├── config/
│   ├── settings.py      # Central config loader
│   └── prompts.py       # System prompt templates
├── .env.example
└── requirements.txt
```

---

## ⚙️ Configuration

All configuration is in `.env`:

```env
# LLM Provider (claude | openai | deepseek | ollama)
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=...
OLLAMA_BASE_URL=http://localhost:11434

# Model selection
LLM_MODEL=claude-opus-4-6

# Interface
INTERFACE=cli   # cli | telegram | discord

# Memory
MEMORY_DB_PATH=./max_memory.db
MAX_CONTEXT_TOKENS=80000

# Agent behavior
AGENT_NAME=MAX
AGENT_AUTONOMY=medium   # low | medium | high
CONFIRM_BEFORE_ACTION=true  # Always ask before irreversible actions

# Skills to enable (comma-separated, or "all")
ENABLED_SKILLS=web,files,notes,memory
```

---

## ⚠️ Safety & Ethics

**MAX can take real actions in the world. Use responsibly.**

- Always start with `CONFIRM_BEFORE_ACTION=true` until you trust your configuration
- Review skills before enabling them — especially `email`, `files`, and `code`
- Be aware of prompt injection risks if MAX reads external content (emails, web pages)
- MAX inherits the safety properties of whatever LLM you configure — choose wisely
- Do not grant MAX access to production systems without extensive testing

See [SECURITY.md](SECURITY.md) for a detailed threat model.

---

## 🤝 Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) first.

- Found a bug? Open an issue.
- Want to add a skill? Submit a PR to `skills/`
- Improving docs? Always appreciated.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details. Use it, fork it, build on it.

---

*MAX is inspired by the wave of personal AI agents demonstrating what truly local, private, extensible AI can look like. Built with ❤️ and a firm belief that your AI should work for you — not for a corporation.*
