"""
interfaces/cli_interface.py — Terminal/CLI interface for MAX.

Rich interactive REPL with:
- Color output using Rich
- Typing spinner while MAX thinks
- Confirmation prompts for destructive actions
- Command history
- Special slash commands
"""

import asyncio
import logging
import sys

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.spinner import Spinner
    from rich.live import Live
    from rich.prompt import Confirm
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

from agent import MAXAgent
from config.settings import Settings

logger = logging.getLogger("MAX.interface.cli")


class CLIInterface:
    """
    Interactive terminal interface for MAX.
    Works with or without the `rich` library installed.
    """

    COMMANDS = {
        "/quit": "Exit MAX",
        "/exit": "Exit MAX",
        "/memory": "List stored memories",
        "/clear": "Clear conversation history",
        "/history": "Show recent tool actions",
        "/skills": "List available skills and tools",
        "/help": "Show this help message",
    }

    def __init__(self, agent: MAXAgent, settings: Settings):
        self.agent = agent
        self.settings = settings
        self.console = Console() if HAS_RICH else None
        self.running = True

        # Wire confirmation callback to CLI prompt
        self.agent.tool_executor.set_confirm_callback(self._cli_confirm)

    async def start(self):
        """Start the interactive CLI loop."""
        self._print_welcome()

        while self.running:
            try:
                user_input = await self._get_input()
            except (EOFError, KeyboardInterrupt):
                self._print("\n👋 Goodbye!")
                break

            if not user_input.strip():
                continue

            if user_input.startswith("/"):
                await self._handle_command(user_input.strip())
                continue

            await self._process_and_display(user_input)

    async def _process_and_display(self, user_input: str):
        """Send message to agent and display the response."""
        if HAS_RICH:
            with Live(Spinner("dots", text=" MAX is thinking..."), console=self.console, refresh_per_second=10):
                response = await self.agent.process_message(
                    user_input=user_input,
                    user_id="cli_user",
                )
        else:
            print("⏳ MAX is thinking...")
            response = await self.agent.process_message(
                user_input=user_input,
                user_id="cli_user",
            )

        # Display response
        if HAS_RICH:
            self.console.print()
            self.console.print(
                Panel(
                    Markdown(response.text),
                    title=f"[bold green]{self.settings.agent_name}[/bold green]",
                    border_style="green",
                )
            )
            if response.actions_taken:
                self.console.print(
                    f"[dim]🔧 Actions: {', '.join(response.actions_taken)}[/dim]"
                )
        else:
            print(f"\n{self.settings.agent_name}: {response.text}\n")
            if response.actions_taken:
                print(f"  [Actions: {', '.join(response.actions_taken)}]\n")

    async def _get_input(self) -> str:
        """Async wrapper for input() with a nice prompt."""
        loop = asyncio.get_event_loop()
        if HAS_RICH:
            self.console.print(f"\n[bold cyan]You:[/bold cyan] ", end="")

        return await loop.run_in_executor(None, input, "" if HAS_RICH else "You: ")

    async def _handle_command(self, command: str):
        """Handle slash commands."""
        cmd = command.lower().split()[0]

        if cmd in ("/quit", "/exit"):
            self.running = False
            self._print("👋 Shutting down MAX...")

        elif cmd == "/help":
            lines = [f"  {k:12s} — {v}" for k, v in self.COMMANDS.items()]
            self._print("\n".join(["", "Available commands:"] + lines, ))

        elif cmd == "/memory":
            memories = await self.agent.memory.get_all(user_id="cli_user")
            if not memories:
                self._print("No memories stored yet.")
            else:
                self._print(f"\n🧠 {len(memories)} stored memories:")
                for m in memories[:20]:
                    tags = f" [{', '.join(m.tags)}]" if m.tags else ""
                    self._print(f"  • {m.content[:100]}{tags}")

        elif cmd == "/clear":
            self.agent.conversation_history.clear()
            self._print("✅ Conversation history cleared.")

        elif cmd == "/history":
            log = self.agent.tool_executor.get_audit_log(limit=15)
            if not log:
                self._print("No tool actions recorded yet.")
            else:
                self._print(f"\n🔧 Last {len(log)} tool actions:")
                for e in log:
                    status = "✅" if e["success"] else "❌"
                    self._print(f"  {status} {e['tool']:30s} {e['timestamp'][:16]}")

        elif cmd == "/skills":
            self._print(f"\n🛠️  Loaded skills:")
            for name, skill in self.agent.tool_registry.skills.items():
                tools = list(skill._actions.keys())
                self._print(f"  📦 {name}: {', '.join(t.split('__')[1] for t in tools)}")

        else:
            self._print(f"Unknown command: {command}. Type /help for available commands.")

    async def _cli_confirm(self, prompt: str) -> bool:
        """Interactive confirmation prompt for destructive actions."""
        self._print(f"\n⚠️  {prompt}")
        if HAS_RICH:
            return Confirm.ask("Proceed?", console=self.console, default=False)
        else:
            answer = input("Proceed? (yes/no): ").strip().lower()
            return answer in ("yes", "y")

    def _print(self, text: str):
        if HAS_RICH:
            self.console.print(text)
        else:
            print(text)

    def _print_welcome(self):
        if HAS_RICH:
            self.console.print(
                Panel(
                    f"[bold]Welcome to {self.settings.agent_name}[/bold]\n"
                    f"Model: [cyan]{self.settings.llm_provider}/{self.settings.llm_model}[/cyan]\n"
                    f"Skills: [green]{', '.join(self.settings.enabled_skills)}[/green]\n\n"
                    "Type anything to get started. Use /help for commands.",
                    border_style="blue",
                )
            )
        else:
            print(f"\n=== {self.settings.agent_name} ===")
            print(f"Model: {self.settings.llm_provider}/{self.settings.llm_model}")
            print(f"Skills: {', '.join(self.settings.enabled_skills)}")
            print("Type anything to get started. Use /help for commands.\n")
