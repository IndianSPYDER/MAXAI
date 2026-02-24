"""
tools/tool_executor.py — Safe execution layer for MAX tools.

Handles:
- Pre-execution confirmation for destructive actions
- Error catching and formatting
- Execution logging and audit trail
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from tools.tool_registry import ToolRegistry

logger = logging.getLogger("MAX.tool_executor")


class ToolExecutor:
    """
    Executes tools safely with optional user confirmation for
    destructive or irreversible actions.

    Maintains an audit log of all tool executions.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        confirm_before_action: bool = True,
        confirm_callback: Optional[callable] = None,
    ):
        self.registry = tool_registry
        self.confirm_before_action = confirm_before_action
        self.confirm_callback = confirm_callback  # Set by interface layer
        self.audit_log: list[dict] = []

    async def execute(
        self,
        tool_name: str,
        arguments: dict,
        user_id: str = "default",
    ) -> dict:
        """
        Execute a tool by name with given arguments.

        Returns a dict with:
            - success: bool
            - result: str (on success)
            - error: str (on failure)
            - tool_name: str
            - duration_ms: float
        """
        tool = self.registry.tools.get(tool_name)
        if not tool:
            return self._error_result(tool_name, f"Unknown tool: '{tool_name}'")

        # Check if confirmation needed
        if self.confirm_before_action and self.registry.requires_confirmation(tool_name):
            confirmed = await self._request_confirmation(tool_name, arguments)
            if not confirmed:
                return {
                    "success": False,
                    "result": None,
                    "error": "Action cancelled by user",
                    "tool_name": tool_name,
                    "cancelled": True,
                }

        # Execute
        start = datetime.utcnow()
        try:
            result = await tool(**arguments)
            duration = (datetime.utcnow() - start).total_seconds() * 1000

            log_entry = {
                "tool": tool_name,
                "arguments": arguments,
                "user_id": user_id,
                "success": True,
                "duration_ms": duration,
                "timestamp": start.isoformat(),
            }
            self.audit_log.append(log_entry)
            logger.info(f"Tool '{tool_name}' executed in {duration:.0f}ms")

            return {
                "success": True,
                "result": str(result),
                "error": None,
                "tool_name": tool_name,
                "duration_ms": duration,
            }

        except Exception as e:
            duration = (datetime.utcnow() - start).total_seconds() * 1000
            logger.error(f"Tool '{tool_name}' failed: {e}", exc_info=True)

            self.audit_log.append({
                "tool": tool_name,
                "arguments": arguments,
                "user_id": user_id,
                "success": False,
                "error": str(e),
                "duration_ms": duration,
                "timestamp": start.isoformat(),
            })

            return self._error_result(tool_name, str(e), duration)

    async def _request_confirmation(self, tool_name: str, arguments: dict) -> bool:
        """
        Request user confirmation for a destructive action.
        If a confirm_callback is set (by the interface), use it.
        Otherwise default to True (auto-approve) if confirm_before_action is False.
        """
        if self.confirm_callback:
            args_str = ", ".join(f"{k}={repr(v)[:60]}" for k, v in arguments.items())
            prompt = f"⚠️ MAX wants to run: **{tool_name}**({args_str})\nConfirm? (yes/no)"
            return await self.confirm_callback(prompt)

        # No callback — if we got here with confirm=True, we can't confirm
        # So we deny by default (safe)
        logger.warning(f"No confirm_callback set — auto-denying {tool_name}")
        return False

    def set_confirm_callback(self, callback: callable):
        """Set the confirmation callback from the interface layer."""
        self.confirm_callback = callback

    def get_audit_log(self, limit: int = 50) -> list[dict]:
        """Return recent tool execution history."""
        return self.audit_log[-limit:]

    @staticmethod
    def _error_result(tool_name: str, error: str, duration_ms: float = 0) -> dict:
        return {
            "success": False,
            "result": None,
            "error": error,
            "tool_name": tool_name,
            "duration_ms": duration_ms,
        }
