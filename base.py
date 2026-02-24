"""
skills/base.py — BaseSkill class and @skill_action decorator.

All MAX skills inherit from BaseSkill.
The @skill_action decorator registers methods as callable tools.
"""

import functools
import inspect
import logging
from typing import Any, Callable, get_type_hints

logger = logging.getLogger("MAX.skills")


def skill_action(description: str, confirm_required: bool = False):
    """
    Decorator to mark a BaseSkill method as a callable agent action.

    Args:
        description: Human-readable description of what this action does.
        confirm_required: If True, MAX will ask user to confirm before executing.
    """
    def decorator(func: Callable) -> Callable:
        func._is_skill_action = True
        func._action_description = description
        func._confirm_required = confirm_required

        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            logger.debug(f"Executing skill action: {self.name}.{func.__name__}")
            return await func(self, *args, **kwargs)

        wrapper._is_skill_action = True
        wrapper._action_description = description
        wrapper._confirm_required = confirm_required
        return wrapper
    return decorator


class BaseSkill:
    """
    Abstract base class for all MAX skills.

    Subclass this, set `name` and `description`, and decorate
    methods with @skill_action to expose them to the agent.

    Example:
        class WeatherSkill(BaseSkill):
            name = "weather"
            description = "Get weather information for any location"

            @skill_action(description="Get current weather for a city")
            async def get_weather(self, city: str) -> str:
                ...
    """

    name: str = "base"
    description: str = "Base skill"
    enabled: bool = True

    def __init__(self, settings=None):
        self.settings = settings
        self._actions = self._discover_actions()

    def _discover_actions(self) -> dict[str, Callable]:
        """Auto-discover all methods decorated with @skill_action."""
        actions = {}
        for attr_name in dir(self):
            if attr_name.startswith("_"):
                continue
            attr = getattr(self, attr_name)
            if callable(attr) and getattr(attr, "_is_skill_action", False):
                actions[f"{self.name}__{attr_name}"] = attr
        return actions

    def get_tool_descriptions(self) -> list[dict]:
        """Return tool metadata for inclusion in LLM prompts."""
        tools = []
        for tool_name, action in self._actions.items():
            sig = inspect.signature(action)
            params = {}
            hints = get_type_hints(action)

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                param_type = hints.get(param_name, str)
                params[param_name] = {
                    "type": self._python_type_to_json(param_type),
                    "required": param.default is inspect.Parameter.empty,
                }

            tools.append({
                "name": tool_name,
                "description": action._action_description,
                "parameters": params,
                "confirm_required": action._confirm_required,
            })
        return tools

    def get_claude_schemas(self) -> list[dict]:
        """Return Claude-format tool schemas."""
        schemas = []
        for tool_name, action in self._actions.items():
            sig = inspect.signature(action)
            hints = get_type_hints(action)
            properties = {}
            required = []

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                param_type = hints.get(param_name, str)
                properties[param_name] = {
                    "type": self._python_type_to_json(param_type),
                    "description": f"The {param_name} parameter",
                }
                if param.default is inspect.Parameter.empty:
                    required.append(param_name)

            schemas.append({
                "name": tool_name,
                "description": action._action_description,
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            })
        return schemas

    def get_openai_schemas(self) -> list[dict]:
        """Return OpenAI-format function tool schemas."""
        schemas = []
        for tool_name, action in self._actions.items():
            sig = inspect.signature(action)
            hints = get_type_hints(action)
            properties = {}
            required = []

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue
                param_type = hints.get(param_name, str)
                properties[param_name] = {
                    "type": self._python_type_to_json(param_type),
                    "description": f"The {param_name} parameter",
                }
                if param.default is inspect.Parameter.empty:
                    required.append(param_name)

            schemas.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": action._action_description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    }
                }
            })
        return schemas

    async def execute(self, action_name: str, arguments: dict) -> Any:
        """Execute a named action with given arguments."""
        full_name = f"{self.name}__{action_name}" if "__" not in action_name else action_name
        action = self._actions.get(full_name)

        if not action:
            raise ValueError(f"Unknown action '{action_name}' in skill '{self.name}'")

        return await action(**arguments)

    @staticmethod
    def _python_type_to_json(python_type) -> str:
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }
        return type_map.get(python_type, "string")
