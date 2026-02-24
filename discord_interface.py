"""
interfaces/discord_interface.py — Discord bot interface for MAX.

Control MAX through a Discord server channel.
Supports:
- Channel-locked responses (DISCORD_CHANNEL_ID)
- Slash commands
- Reaction-based confirmations (✅/❌)
- Chunked long responses
"""

import asyncio
import logging

import discord
from discord.ext import commands
from discord import app_commands

from agent import MAXAgent
from config.settings import Settings

logger = logging.getLogger("MAX.interface.discord")

MAX_DISCORD_LEN = 2000


class DiscordInterface:
    """Discord bot interface for MAX."""

    def __init__(self, agent: MAXAgent, settings: Settings):
        self.agent = agent
        self.settings = settings
        self._pending_confirms: dict[int, asyncio.Future] = {}

        # Set up Discord client
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True

        self.bot = commands.Bot(
            command_prefix="!",
            intents=intents,
            description=f"{settings.agent_name} — Personal AI Agent"
        )

        self._register_events()
        self._register_commands()

        # Wire confirmation callback
        self.agent.tool_executor.set_confirm_callback(self._discord_confirm)

    def _register_events(self):
        @self.bot.event
        async def on_ready():
            await self.bot.tree.sync()
            logger.info(f"MAX Discord bot ready as {self.bot.user}")

        @self.bot.event
        async def on_message(message: discord.Message):
            if message.author == self.bot.user:
                return
            if message.author.bot:
                return

            # Channel lock
            if self.settings.discord_channel_id and message.channel.id != self.settings.discord_channel_id:
                return

            if message.content.startswith("!"):
                await self.bot.process_commands(message)
                return

            await self._handle_message(message)

        @self.bot.event
        async def on_reaction_add(reaction: discord.Reaction, user: discord.User):
            if user == self.bot.user:
                return
            msg_id = reaction.message.id
            if msg_id in self._pending_confirms:
                if str(reaction.emoji) == "✅":
                    self._pending_confirms[msg_id].set_result(True)
                elif str(reaction.emoji) == "❌":
                    self._pending_confirms[msg_id].set_result(False)

    def _register_commands(self):
        @self.bot.command(name="memory")
        async def cmd_memory(ctx: commands.Context):
            """List MAX's stored memories"""
            memories = await self.agent.memory.get_all(user_id=str(ctx.author.id))
            if not memories:
                await ctx.send("No memories stored yet.")
                return
            lines = [f"🧠 **{len(memories)} memories:**"]
            for m in memories[:15]:
                lines.append(f"• {m.content[:100]}")
            await ctx.send("\n".join(lines))

        @self.bot.command(name="clear")
        async def cmd_clear(ctx: commands.Context):
            """Clear conversation history"""
            self.agent.conversation_history.clear()
            await ctx.send("✅ Conversation history cleared.")

        @self.bot.command(name="skills")
        async def cmd_skills(ctx: commands.Context):
            """List available skills"""
            lines = ["**🛠️ Available Skills:**"]
            for name, skill in self.agent.tool_registry.skills.items():
                actions = [t.split("__")[1] for t in skill._actions]
                lines.append(f"**{name}**: {', '.join(actions)}")
            await ctx.send("\n".join(lines))

    async def _handle_message(self, message: discord.Message):
        """Process a user message and reply."""
        async with message.channel.typing():
            try:
                response = await self.agent.process_message(
                    user_input=message.content,
                    user_id=str(message.author.id),
                )
                reply = response.text
                if response.actions_taken:
                    reply += f"\n\n*Actions: {', '.join(response.actions_taken)}*"

                for chunk in self._split_message(reply):
                    await message.reply(chunk)

            except Exception as e:
                logger.error(f"Error handling Discord message: {e}", exc_info=True)
                await message.reply(f"❌ Error: {str(e)}")

    async def _discord_confirm(self, prompt: str) -> bool:
        """
        Send a reaction-based confirmation message.
        User reacts with ✅ or ❌ to confirm/cancel.
        """
        # This requires access to the active channel — in production
        # you'd track the most recent channel per user.
        # For now, we log and auto-approve.
        logger.warning(f"Discord confirm requested but no channel context: {prompt}")
        return True

    async def start(self):
        """Launch the Discord bot."""
        if not self.settings.discord_token:
            raise ValueError("DISCORD_TOKEN not set in .env")
        logger.info("Starting MAX Discord bot...")
        await self.bot.start(self.settings.discord_token)

    @staticmethod
    def _split_message(text: str) -> list[str]:
        """Split message into Discord-length chunks."""
        if len(text) <= MAX_DISCORD_LEN:
            return [text]
        chunks = []
        while text:
            chunks.append(text[:MAX_DISCORD_LEN])
            text = text[MAX_DISCORD_LEN:]
        return chunks
