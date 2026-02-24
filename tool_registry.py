"""
tools/tool_registry.py — Auto-discovers and registers all MAX skills as tools.

Scans the skills/ directory, imports each skill, and maintains
a unified registry of all callable actions.
"""

import importlib
import inspect
import logging
import os
from pathlib import Path
from typing import Optional, Type

from skills.base import BaseSkill

logger = logging.getLogger("MAX.tool_registry")


class ToolRegistry:
    """
    Discovers, loads, and registers all skills and their actions.

    Skills are auto-discovered by scanning the skills/ directory
    for classes that inherit from BaseSkill. No manual registration needed.
    """

    def __init__(self, settings=None):
        self.settings = settings
        self.skills: dict[str, BaseSkill] = {}
        self.tools: dict[str, callable] = {}
        self._tool_metadata: dict[str, dict] = {}

    async def discover_skills(self):
        """Scan skills/ directory and load enabled skill classes."""
        skills_dir = Path(__file__).parent.parent / "skills"
        enabled = self.settings.enabled_skills if self.settings else []
        load_all = "all" in enabled

        logger.info(f"Discovering skills (enabled: {enabled})...")

        for skill_file in skills_dir.glob("*.py"):
            if skill_file.name.startswith("_"):
                continue

            module_name = f"skills.{skill_file.stem}"
            try:
                module = importlib.import_module(module_name)
            except Exception as e:
                logger.warning(f"Failed to import {module_name}: {e}")
                continue

            for name, obj in inspect.getmembers(module, inspect.isclass):
                if not issubclass(obj, BaseSkill) or obj is BaseSkill:
                    continue

                skill_instance = obj.__new__(obj)
                skill_name = getattr(skill_instance, "name", None) or obj.__name__.lower()

                if not load_all and skill_name not in enabled:
                    logger.debug(f"Skipping skill '{skill_name}' (not in ENABLED_SKILLS)")
                    continue

                try:
                    skill_instance = obj(settings=self.settings)
                    self.skills[skill_name] = skill_instance

                    # Register individual actions
                    for tool_name, action in skill_instance._actions.items():
                        self.tools[tool_name] = action
                        self._tool_metadata[tool_name] = {
                            "skill": skill_name,
                            "description": getattr(action, "_action_description", ""),
                            "confirm_required": getattr(action, "_confirm_required", False),
                        }
                        logger.debug(f"Registered tool: {tool_name}")

                    logger.info(f"✓ Loaded skill '{skill_name}' with {len(skill_instance._actions)} actions")

                except Exception as e:
                    logger.error(f"Failed to initialize skill '{skill_name}': {e}")

        logger.info(f"Tool discovery complete. {len(self.tools)} tools available across {len(self.skills)} skills.")

    def get_tool_descriptions(self) -> list[dict]:
        """Return all tool descriptions for prompt injection."""
        descriptions = []
        for skill in self.skills.values():
            descriptions.extend(skill.get_tool_descriptions())
        return descriptions

    def get_claude_tool_schemas(self) -> list[dict]:
        """Return all tools in Anthropic Claude format."""
        schemas = []
        for skill in self.skills.values():
            schemas.extend(skill.get_claude_schemas())
        return schemas

    def get_openai_tool_schemas(self) -> list[dict]:
        """Return all tools in OpenAI function-calling format."""
        schemas = []
        for skill in self.skills.values():
            schemas.extend(skill.get_openai_schemas())
        return schemas

    def requires_confirmation(self, tool_name: str) -> bool:
        """Check if a tool requires user confirmation before execution."""
        meta = self._tool_metadata.get(tool_name, {})
        return meta.get("confirm_required", False)

    def get_skill_for_tool(self, tool_name: str) -> Optional[BaseSkill]:
        """Find the skill instance that owns a given tool."""
        meta = self._tool_metadata.get(tool_name)
        if meta:
            return self.skills.get(meta["skill"])
        return None
