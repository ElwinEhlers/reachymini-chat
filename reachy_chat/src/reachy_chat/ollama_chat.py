"""Chat handler for local LLM via Ollama (OpenAI-compatible API)."""

import json
import asyncio
import logging
from typing import Any, AsyncGenerator

from openai import AsyncOpenAI

from reachy_chat.config import config
from reachy_chat.prompts import get_session_instructions
from reachy_chat.tools.core_tools import (
    ToolDependencies,
    get_tool_specs,
    dispatch_tool_call,
)


logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5


class OllamaChatHandler:
    """Handles chat interactions with a local Ollama LLM including tool-calling."""

    def __init__(self, deps: ToolDependencies, conversation_id: int | None = None) -> None:
        self.client = AsyncOpenAI(
            base_url=config.OLLAMA_BASE_URL,
            api_key="ollama",
        )
        self.model = config.OLLAMA_MODEL
        self.deps = deps
        self._conversation_id = conversation_id

        system_prompt = get_session_instructions()
        if conversation_id is not None:
            try:
                import sys as _sys
                if "/home/sbin/reachy" not in _sys.path:
                    _sys.path.insert(0, "/home/sbin/reachy")
                from memory.context import build_system_prompt
                system_prompt = build_system_prompt(system_prompt, person_id=1)
            except Exception as _e:
                logger.warning("Memory context unavailable: %s", _e)

        self.messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]

        # Build OpenAI-style tool definitions from the SDK tool specs
        raw_specs = get_tool_specs()
        self.tools = _convert_tool_specs(raw_specs)
        logger.info(
            "OllamaChatHandler ready (model=%s, tools=%d)",
            self.model,
            len(self.tools),
        )

    async def check_connection(self) -> bool:
        """Return True if Ollama is reachable."""
        try:
            await self.client.models.list()
            return True
        except Exception:
            return False

    async def chat(self, user_message: str) -> AsyncGenerator[str, None]:
        """Send a user message and yield assistant response tokens.

        Handles tool-calling loops transparently: when the LLM requests a
        tool call, execute it, feed the result back, and continue until the
        LLM produces a text response.
        """
        self.messages.append({"role": "user", "content": user_message})
        self._log_message("user", user_message)

        for _ in range(MAX_TOOL_ROUNDS):
            collected_text = ""
            tool_calls_raw: list[dict[str, Any]] = []

            try:
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,
                    tools=self.tools if self.tools else None,
                    stream=True,
                )

                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta is None:
                        continue

                    # Accumulate text tokens
                    if delta.content:
                        collected_text += delta.content
                        yield delta.content

                    # Accumulate tool call fragments
                    if delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            while len(tool_calls_raw) <= idx:
                                tool_calls_raw.append(
                                    {"id": "", "function": {"name": "", "arguments": ""}}
                                )
                            if tc.id:
                                tool_calls_raw[idx]["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    tool_calls_raw[idx]["function"]["name"] += tc.function.name
                                if tc.function.arguments:
                                    tool_calls_raw[idx]["function"]["arguments"] += tc.function.arguments

            except Exception as e:
                error_msg = f"[LLM error: {e}]"
                logger.error("Ollama chat error: %s", e)
                yield error_msg
                self.messages.append({"role": "assistant", "content": error_msg})
                return

            # If the model produced tool calls, execute them and loop
            if tool_calls_raw and tool_calls_raw[0]["function"]["name"]:
                # Record the assistant message with tool_calls
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": collected_text or None}
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"] or f"call_{i}",
                        "type": "function",
                        "function": tc["function"],
                    }
                    for i, tc in enumerate(tool_calls_raw)
                ]
                self.messages.append(assistant_msg)

                # Execute each tool call
                for i, tc in enumerate(tool_calls_raw):
                    fn_name = tc["function"]["name"]
                    fn_args = tc["function"]["arguments"]
                    call_id = tc["id"] or f"call_{i}"

                    yield f"\n[Tool: {fn_name}]\n"
                    logger.info("Executing tool: %s(%s)", fn_name, fn_args)

                    result = await dispatch_tool_call(fn_name, fn_args, self.deps)

                    result_str = json.dumps(result, default=str)
                    self.messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": result_str,
                        }
                    )
                    yield f"[Result: {result_str}]\n"

                # Continue the loop so the LLM can respond to the tool results
                continue

            # No tool calls — we have a final text response
            if collected_text:
                self.messages.append({"role": "assistant", "content": collected_text})
                self._log_message("assistant", collected_text)
            return

        # Safety: max rounds exceeded
        fallback = "[Max tool rounds reached]"
        yield fallback
        self.messages.append({"role": "assistant", "content": fallback})

    def _log_message(self, role: str, content: str) -> None:
        """Write message to memory DB if a conversation_id is set."""
        if self._conversation_id is None:
            return
        try:
            from memory.conversations import log_message
            log_message(self._conversation_id, role, content)
        except Exception as e:
            logger.debug("Memory log failed: %s", e)

    def clear_history(self) -> None:
        """Reset conversation history, keeping the system prompt."""
        system_msg = self.messages[0] if self.messages else None
        self.messages = []
        if system_msg and system_msg.get("role") == "system":
            self.messages.append(system_msg)

    def get_history(self) -> list[dict[str, str]]:
        """Return a simplified chat history for the UI (user and assistant only)."""
        history = []
        for msg in self.messages:
            role = msg.get("role")
            content = msg.get("content")
            if role in ("user", "assistant") and content:
                history.append({"role": role, "content": content})
        return history


def _convert_tool_specs(raw_specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert SDK tool specs to the OpenAI function-calling format."""
    tools = []
    for spec in raw_specs:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": spec["name"],
                    "description": spec.get("description", ""),
                    "parameters": spec.get("parameters", {"type": "object", "properties": {}}),
                },
            }
        )
    return tools
