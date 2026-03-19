"""
Core engine for Gemini Code CLI.
Handles Gemini API communication, streaming, and the agentic tool-use loop.
"""

import os
import json
from pathlib import Path
from typing import Optional, Generator, Callable
from google import genai
from google.genai import types

from .tools.definitions import ALL_TOOLS
from .tools.implementations import dispatch_tool, get_working_dir, set_working_dir, get_todos


MODEL_ID = "gemini-3-flash-preview"

SYSTEM_PROMPT = """You are Gemini Code, an expert AI coding assistant running in the terminal.
You help developers understand, write, debug, and refactor code.

You have access to powerful tools:
- **read_file** / **write_file** / **edit_file**: Read and modify files
- **list_directory**: Explore project structure
- **glob**: Find files by pattern
- **grep**: Search file contents with regex
- **bash**: Execute shell commands (git, npm, pip, tests, etc.)
- **web_fetch**: Fetch web pages and documentation
- **web_search**: Search the web for information
- **todo_write**: Manage a task checklist for complex multi-step work
- **memory_write**: Write persistent notes to GEMINI.md

## Guidelines

1. **Be proactive**: When asked to fix a bug or implement a feature, actually do it — read the relevant files, make the changes, verify with tests.
2. **Use tools efficiently**: Chain tool calls logically. Read before writing. Run tests after changes.
3. **Show your work**: Briefly explain what you're doing and why, especially for non-obvious decisions.
4. **Respect the codebase**: Follow existing code style, conventions, and patterns.
5. **Handle errors gracefully**: If a tool fails, diagnose the issue and try an alternative approach.
6. **Be concise**: Avoid unnecessary verbosity. Developers value clarity and brevity.
7. **Security**: Never expose secrets, API keys, or sensitive data. Be careful with destructive operations.

When working on complex tasks, use todo_write to track progress and keep the user informed.
Always read the GEMINI.md file if it exists — it contains important project context.
"""


class GeminiEngine:
    """Core engine managing the Gemini API session."""

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise ValueError(
                "No API key found. Set GEMINI_API_KEY or GOOGLE_API_KEY environment variable, "
                "or run: gemini-code config --api-key YOUR_KEY"
            )
        self.api_key = key
        self.client = genai.Client(api_key=key)
        self.history: list[types.Content] = []
        self.model_id = MODEL_ID
        self.system_prompt = SYSTEM_PROMPT
        self.session_cost = {"input_tokens": 0, "output_tokens": 0}
        self._load_memory()

    def _load_memory(self):
        """Load GEMINI.md if it exists and prepend to system prompt."""
        memory_path = Path(get_working_dir()) / "GEMINI.md"
        if memory_path.exists():
            try:
                memory_content = memory_path.read_text(encoding="utf-8")
                self.system_prompt = (
                    self.system_prompt
                    + f"\n\n## Project Memory (GEMINI.md)\n\n{memory_content}"
                )
            except Exception:
                pass

    def set_model(self, model_id: str):
        """Switch the active model."""
        self.model_id = model_id

    def clear_history(self):
        """Clear conversation history."""
        self.history = []

    def get_history(self) -> list:
        """Return conversation history."""
        return self.history

    def compact_history(self, instructions: str = "") -> str:
        """Summarize and compress conversation history."""
        if not self.history:
            return "No conversation history to compact."

        summary_prompt = "Summarize the key points, decisions, and outcomes of this conversation in a concise format."
        if instructions:
            summary_prompt += f" Focus on: {instructions}"

        summary_messages = self.history + [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=summary_prompt)],
            )
        ]

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=summary_messages,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    temperature=0.3,
                ),
            )
            summary = response.text or "Unable to generate summary."
        except Exception as e:
            summary = f"Compaction failed: {e}"

        self.history = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"[Previous conversation summary]\n\n{summary}")],
            ),
            types.Content(
                role="model",
                parts=[types.Part.from_text(text="Understood. I have the context from our previous conversation.")],
            ),
        ]
        return summary

    def chat_stream(
        self,
        user_message: str,
        on_text: Optional[Callable[[str], None]] = None,
        on_tool_call: Optional[Callable[[str, dict], None]] = None,
        on_tool_result: Optional[Callable[[str, dict], None]] = None,
        on_thinking: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Send a message and stream the response, executing tool calls as they arrive.
        Returns the final text response.
        """
        self.history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
        )

        full_response_text = ""
        max_tool_rounds = 20

        for _round in range(max_tool_rounds):
            response_parts = []
            current_text = ""
            tool_calls_made = []

            try:
                # Check if model supports thinking
                config_args = {
                    "system_instruction": self.system_prompt,
                    "tools": [ALL_TOOLS],
                    "temperature": 1.0,
                }
                if "pro" in self.model_id.lower() or "thinking" in self.model_id.lower():
                    config_args["thinking_config"] = types.ThinkingConfig(
                        thinking_budget=8000,
                    )
                
                stream = self.client.models.generate_content_stream(
                    model=self.model_id,
                    contents=self.history,
                    config=types.GenerateContentConfig(**config_args),
                )

                for chunk in stream:
                    if not chunk.candidates:
                        continue
                    candidate = chunk.candidates[0]
                    if not candidate.content or not candidate.content.parts:
                        continue

                    for part in candidate.content.parts:
                        # Thinking / reasoning
                        if hasattr(part, "thought") and part.thought:
                            if on_thinking and part.text:
                                on_thinking(part.text)
                            continue

                        # Text content
                        if part.text:
                            current_text += part.text
                            full_response_text += part.text
                            if on_text:
                                on_text(part.text)
                            response_parts.append(part)

                        # Function call
                        elif part.function_call:
                            fc = part.function_call
                            tool_name = fc.name
                            tool_args = dict(fc.args) if fc.args else {}
                            tool_calls_made.append((fc, tool_name, tool_args))
                            response_parts.append(part)

            except Exception as e:
                error_msg = f"\n[Error: {e}]\n"
                if on_text:
                    on_text(error_msg)
                full_response_text += error_msg
                break

            if response_parts:
                self.history.append(
                    types.Content(role="model", parts=response_parts)
                )

            if not tool_calls_made:
                break

            tool_result_parts = []
            for fc, tool_name, tool_args in tool_calls_made:
                if on_tool_call:
                    on_tool_call(tool_name, tool_args)

                result = dispatch_tool(tool_name, tool_args)

                if on_tool_result:
                    on_tool_result(tool_name, result)

                result_str = json.dumps(result, ensure_ascii=False, default=str)

                tool_result_parts.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": result_str},
                    )
                )

            self.history.append(
                types.Content(role="user", parts=tool_result_parts)
            )

        return full_response_text

    def chat_once(self, user_message: str) -> str:
        """Non-streaming single-turn chat (for internal use)."""
        self.history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
        )
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=self.history,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_prompt,
                    tools=[ALL_TOOLS],
                    temperature=0.7,
                ),
            )
            text = response.text or ""
            self.history.append(
                types.Content(role="model", parts=[types.Part.from_text(text=text)])
            )
            return text
        except Exception as e:
            return f"Error: {e}"

    def get_session_info(self) -> dict:
        """Return session metadata."""
        return {
            "model": self.model_id,
            "history_turns": len(self.history) // 2,
            "working_dir": get_working_dir(),
            "todos": get_todos(),
        }
