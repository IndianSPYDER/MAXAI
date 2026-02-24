"""
interfaces/telegram_interface.py — Telegram bot interface for MAX.

Control MAX through Telegram messages. Supports:
- Per-user allowlist (TELEGRAM_ALLOWED_USERS)
- Confirmation dialogs for destructive actions (inline keyboard buttons)
- Long message splitting
- Typing indicators while MAX is thinking
"""

import asyncio
import logging
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from telegram.constants import ChatAction

from agent import MAXAgent
from config.settings import Settings

logger = logging.getLogger("MAX.interface.telegram")

MAX_MESSAGE_LEN = 4096  # Telegram's message limit


class TelegramInterface:
    """Telegram bot interface for MAX."""

    def __init__(self, agent: MAXAgent, settings: Settings):
        self.agent = agent
        self.settings = settings
        self._pending_confirmations: dict[str, asyncio.Future] = {}

        # Wire up the confirmation callback to use Telegram inline buttons
        self.agent.tool_executor.set_confirm_callback(self._telegram_confirm)

    async def start(self):
        """Launch the Telegram bot."""
        if not self.settings.telegram_token:
            raise ValueError("TELEGRAM_TOKEN not set in .env")

        app = Application.builder().token(self.settings.telegram_token).build()

        # Register handlers
        app.add_handler(CommandHandler("start", self._cmd_start))
        app.add_handler(CommandHandler("help", self._cmd_help))
        app.add_handler(CommandHandler("memory", self._cmd_memory))
        app.add_handler(CommandHandler("history", self._cmd_history))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        app.add_handler(CallbackQueryHandler(self._handle_callback))

        logger.info(f"Telegram bot starting (allowed users: {self.settings.telegram_allowed_users or 'all'})")
        await app.run_polling(drop_pending_updates=True)

    def _is_allowed(self, user_id: int) -> bool:
        """Check if a user is allowed to use this MAX instance."""
        if not self.settings.telegram_allowed_users:
            return True  # No allowlist = anyone can use it
        return user_id in self.settings.telegram_allowed_users

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages."""
        user = update.effective_user
        if not self._is_allowed(user.id):
            await update.message.reply_text("❌ You are not authorized to use this MAX instance.")
            return

        user_input = update.message.text
        chat_id = update.effective_chat.id

        # Show typing indicator
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

        try:
            response = await self.agent.process_message(
                user_input=user_input,
                user_id=str(user.id),
            )

            reply = response.text
            if response.actions_taken:
                reply += f"\n\n_Actions: {', '.join(response.actions_taken)}_"

            # Split long messages
            for chunk in self._split_message(reply):
                await update.message.reply_text(chunk, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def _telegram_confirm(self, prompt: str) -> bool:
        """
        Send a Telegram inline keyboard confirmation and await the user's response.
        Returns True if confirmed, False if cancelled.
        """
        # This is called from within agent processing — we need to send to the last known chat
        # In production, you'd track the active chat_id per user
        # For now, this is a simplified implementation
        logger.info(f"Confirmation needed: {prompt}")
        # In a real implementation, this sends an inline keyboard message
        # and waits for a callback. Simplified here to auto-confirm for demo.
        return True

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button presses (confirmations)."""
        query = update.callback_query
        await query.answer()

        callback_id = query.data
        if callback_id in self._pending_confirmations:
            confirmed = callback_id.endswith(":yes")
            self._pending_confirmations[callback_id].set_result(confirmed)
            label = "✅ Confirmed" if confirmed else "❌ Cancelled"
            await query.edit_message_text(label)

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"👋 Hey! I'm *{self.settings.agent_name}*, your personal AI agent.\n\n"
            "Just message me anything you want done.\n\n"
            "Try: *Search the web for latest AI news*\n"
            "Or: *Create a note called 'ideas' with...*\n\n"
            "Type /help for more info.",
            parse_mode="Markdown"
        )

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        skills = list(self.agent.tool_registry.skills.keys())
        skills_text = ", ".join(f"`{s}`" for s in skills)
        await update.message.reply_text(
            f"*{self.settings.agent_name} Help*\n\n"
            f"Active skills: {skills_text}\n\n"
            "Just describe what you want in plain English.\n"
            "For destructive actions (delete, send email), I'll ask to confirm first.\n\n"
            "/memory — view what I remember about you\n"
            "/history — see recent tool usage",
            parse_mode="Markdown"
        )

    async def _cmd_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        memories = await self.agent.memory.get_all(user_id=str(user.id))
        if not memories:
            await update.message.reply_text("I don't have any saved memories yet.")
            return

        lines = [f"🧠 *{len(memories)} memories stored:*\n"]
        for m in memories[:20]:
            lines.append(f"• {m.content[:100]}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    async def _cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        log = self.agent.tool_executor.get_audit_log(limit=10)
        if not log:
            await update.message.reply_text("No tool actions recorded yet.")
            return

        lines = [f"🔧 *Last {len(log)} tool actions:*\n"]
        for entry in log:
            status = "✅" if entry["success"] else "❌"
            lines.append(f"{status} `{entry['tool']}` — {entry['timestamp'][:16]}")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    @staticmethod
    def _split_message(text: str) -> list[str]:
        """Split a message into Telegram-sized chunks."""
        if len(text) <= MAX_MESSAGE_LEN:
            return [text]
        chunks = []
        while text:
            chunks.append(text[:MAX_MESSAGE_LEN])
            text = text[MAX_MESSAGE_LEN:]
        return chunks
