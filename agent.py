"""
agent.py — Core MAX Agent Loop

Handles:
- LLM client initialization
- Tool/skill registration
- The ReAct-style reasoning loop (Reason → Act → Observe → Repeat)
- Context window management and compaction
- Memory injection into context
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime

from config.settings import Settings
from config.prompts import build_system_prompt
from memory.memory import MemoryStore
from tools.tool_registry import ToolRegistry
from tools.tool_executor import ToolExecutor

logger = logging.getLogger("MAX.agent")


@dataclass
class Message:
    role: str  # "user" | "assistant" | "tool_result"
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentResponse:
    text: str
    actions_taken: list[str] = field(default_factory=list)
    memories_used: list[str] = field(default_factory=list)
    error: Optional[str] = None


class MAXAgent:
    """
    Core agent class implementing the ReAct reasoning loop.

    The loop:
    1. Receive user message
    2. Inject relevant memories into context
    3. Ask LLM to reason about what to do
    4. If LLM calls a tool → execute it → feed result back
    5. Repeat until LLM produces a final text response
    6. Store important information in memory
    7. Return response to interface layer
    """

    MAX_ITERATIONS = 15  # Safety limit on tool call loops
    COMPACTION_THRESHOLD = 0.85  # Compact context at 85% of token limit

    def __init__(self, settings: Settings):
        self.settings = settings
        self.memory: Optional[MemoryStore] = None
        self.tool_registry: Optional[ToolRegistry] = None
        self.tool_executor: Optional[ToolExecutor] = None
        self.llm_client = None
        self.conversation_history: list[Message] = []
        self._initialized = False

    async def initialize(self):
        """Boot sequence — called once at startup."""
        logger.info("Initializing MAX agent...")

        # Initialize memory store
        self.memory = MemoryStore(db_path=self.settings.memory_db_path)
        await self.memory.initialize()
        logger.info(f"Memory initialized at {self.settings.memory_db_path}")

        # Initialize tool registry (auto-discovers skills)
        self.tool_registry = ToolRegistry(settings=self.settings)
        await self.tool_registry.discover_skills()
        logger.info(f"Loaded {len(self.tool_registry.tools)} tools: {list(self.tool_registry.tools.keys())}")

        # Initialize tool executor
        self.tool_executor = ToolExecutor(
            tool_registry=self.tool_registry,
            confirm_before_action=self.settings.confirm_before_action,
        )

        # Initialize LLM client
        self.llm_client = self._build_llm_client()
        logger.info(f"LLM client ready: {self.settings.llm_provider}/{self.settings.llm_model}")

        self._initialized = True
        logger.info("MAX agent fully initialized ✓")

    def _build_llm_client(self):
        """Factory for LLM clients — swap models without changing agent logic."""
        provider = self.settings.llm_provider.lower()

        if provider == "claude":
            import anthropic
            return anthropic.AsyncAnthropic(api_key=self.settings.anthropic_api_key)

        elif provider == "openai":
            from openai import AsyncOpenAI
            return AsyncOpenAI(api_key=self.settings.openai_api_key)

        elif provider == "deepseek":
            from openai import AsyncOpenAI
            return AsyncOpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url="https://api.deepseek.com/v1"
            )

        elif provider == "ollama":
            from openai import AsyncOpenAI
            return AsyncOpenAI(
                api_key="ollama",
                base_url=self.settings.ollama_base_url + "/v1"
            )

        else:
            raise ValueError(f"Unknown LLM provider: {provider}")

    async def process_message(
        self,
        user_input: str,
        user_id: str = "default",
        context: dict = None
    ) -> AgentResponse:
        """
        Main entry point. Takes user input, runs the full ReAct loop,
        returns an AgentResponse.
        """
        if not self._initialized:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        logger.debug(f"Processing message from {user_id}: {user_input[:100]}...")

        # Retrieve relevant memories
        relevant_memories = await self.memory.search(
            query=user_input,
            user_id=user_id,
            limit=5
        )

        # Build context-injected system prompt
        system_prompt = build_system_prompt(
            agent_name=self.settings.agent_name,
            memories=relevant_memories,
            available_tools=self.tool_registry.get_tool_descriptions(),
            current_time=datetime.utcnow().isoformat(),
        )

        # Append user message to history
        self.conversation_history.append(
            Message(role="user", content=user_input)
        )

        # Check if we need to compact context
        if self._should_compact():
            await self._compact_context(user_id)

        # Run the ReAct loop
        actions_taken = []
        final_response = None
        iterations = 0

        while iterations < self.MAX_ITERATIONS:
            iterations += 1
            logger.debug(f"ReAct iteration {iterations}")

            # Call the LLM
            raw_response = await self._call_llm(system_prompt)

            # Check if LLM wants to call a tool
            tool_calls = self._extract_tool_calls(raw_response)

            if not tool_calls:
                # No tool calls — this is the final response
                final_response = raw_response
                break

            # Execute each tool call
            for tool_call in tool_calls:
                tool_name = tool_call.get("name")
                tool_args = tool_call.get("arguments", {})

                logger.info(f"Executing tool: {tool_name}({tool_args})")

                tool_result = await self.tool_executor.execute(
                    tool_name=tool_name,
                    arguments=tool_args,
                    user_id=user_id,
                )

                actions_taken.append(f"{tool_name}: {str(tool_args)[:80]}")

                # Inject tool result back into conversation
                self.conversation_history.append(Message(
                    role="assistant",
                    content=json.dumps(tool_call),
                    metadata={"type": "tool_call"}
                ))
                self.conversation_history.append(Message(
                    role="tool_result",
                    content=json.dumps(tool_result),
                    metadata={"tool_name": tool_name}
                ))

        if not final_response:
            final_response = "I ran into trouble completing that task. Please try again."
            logger.warning("MAX hit iteration limit without final response")

        # Store assistant response in history
        self.conversation_history.append(
            Message(role="assistant", content=final_response)
        )

        # Proactively store important info in memory
        await self._maybe_memorize(user_input, final_response, user_id)

        return AgentResponse(
            text=final_response,
            actions_taken=actions_taken,
            memories_used=[m.content[:60] for m in relevant_memories],
        )

    async def _call_llm(self, system_prompt: str) -> str:
        """Call the configured LLM with current conversation history."""
        messages = self._history_to_messages()
        provider = self.settings.llm_provider.lower()

        if provider == "claude":
            response = await self.llm_client.messages.create(
                model=self.settings.llm_model,
                max_tokens=4096,
                system=system_prompt,
                tools=self.tool_registry.get_claude_tool_schemas(),
                messages=messages,
            )
            # Handle tool use blocks
            if response.stop_reason == "tool_use":
                return json.dumps({
                    "tool_calls": [
                        {"name": block.name, "arguments": block.input}
                        for block in response.content
                        if block.type == "tool_use"
                    ]
                })
            return response.content[0].text

        else:
            # OpenAI-compatible (openai, deepseek, ollama)
            response = await self.llm_client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[{"role": "system", "content": system_prompt}] + messages,
                tools=self.tool_registry.get_openai_tool_schemas(),
                max_tokens=4096,
            )
            choice = response.choices[0]
            if choice.finish_reason == "tool_calls":
                return json.dumps({
                    "tool_calls": [
                        {"name": tc.function.name, "arguments": json.loads(tc.function.arguments)}
                        for tc in choice.message.tool_calls
                    ]
                })
            return choice.message.content

    def _extract_tool_calls(self, raw_response: str) -> list[dict]:
        """Parse tool calls from LLM response."""
        try:
            parsed = json.loads(raw_response)
            return parsed.get("tool_calls", [])
        except (json.JSONDecodeError, AttributeError):
            return []

    def _history_to_messages(self) -> list[dict]:
        """Convert internal Message objects to LLM API format."""
        messages = []
        for msg in self.conversation_history[-40:]:  # Last 40 messages
            if msg.role == "tool_result":
                messages.append({"role": "user", "content": f"[Tool Result]: {msg.content}"})
            else:
                messages.append({"role": msg.role, "content": msg.content})
        return messages

    def _should_compact(self) -> bool:
        """
        Estimate if we're approaching the context window limit.
        Rough heuristic: 4 chars ≈ 1 token.
        """
        total_chars = sum(len(m.content) for m in self.conversation_history)
        estimated_tokens = total_chars / 4
        limit = self.settings.max_context_tokens
        ratio = estimated_tokens / limit
        if ratio > self.COMPACTION_THRESHOLD:
            logger.warning(f"Context at {ratio:.0%} capacity — triggering compaction")
            return True
        return False

    async def _compact_context(self, user_id: str):
        """
        Summarize old conversation history to free context space.
        Preserves the most recent 10 messages verbatim.
        """
        logger.info("Compacting conversation context...")
        if len(self.conversation_history) <= 10:
            return

        old_messages = self.conversation_history[:-10]
        recent_messages = self.conversation_history[-10:]

        # Ask LLM to summarize old messages
        summary_prompt = (
            "Summarize the following conversation history concisely, "
            "preserving all key facts, decisions, and outcomes:\n\n"
            + "\n".join(f"{m.role}: {m.content}" for m in old_messages)
        )

        summary = await self._call_llm_simple(summary_prompt)

        # Replace old history with summary
        self.conversation_history = [
            Message(role="assistant", content=f"[Context summary]: {summary}"),
        ] + recent_messages

        # Store the summary in long-term memory
        await self.memory.store(
            content=summary,
            user_id=user_id,
            tags=["context_summary"],
        )
        logger.info("Context compacted and stored in memory")

    async def _call_llm_simple(self, prompt: str) -> str:
        """Simple single-turn LLM call without tool use, for internal tasks."""
        provider = self.settings.llm_provider.lower()
        if provider == "claude":
            response = await self.llm_client.messages.create(
                model=self.settings.llm_model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        else:
            response = await self.llm_client.chat.completions.create(
                model=self.settings.llm_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,
            )
            return response.choices[0].message.content

    async def _maybe_memorize(self, user_input: str, response: str, user_id: str):
        """Ask the LLM if anything in this exchange is worth storing long-term."""
        check_prompt = f"""Analyze this exchange:
User: {user_input}
MAX: {response}

If this contains information worth remembering long-term (preferences, facts about the user, 
important decisions, contact info, etc.), respond with a JSON object:
{{"should_store": true, "content": "concise memory to store", "tags": ["tag1", "tag2"]}}

If nothing is worth storing, respond with: {{"should_store": false}}"""

        try:
            result_str = await self._call_llm_simple(check_prompt)
            result = json.loads(result_str)
            if result.get("should_store"):
                await self.memory.store(
                    content=result["content"],
                    user_id=user_id,
                    tags=result.get("tags", []),
                )
                logger.debug(f"Stored memory: {result['content'][:80]}")
        except Exception as e:
            logger.debug(f"Memory check failed (non-critical): {e}")

    async def shutdown(self):
        """Clean shutdown."""
        if self.memory:
            await self.memory.close()
        logger.info("Agent shutdown complete")
