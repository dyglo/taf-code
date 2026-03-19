"""
Interactive input handler using prompt_toolkit.
Claude Code-style: real bordered input box using a custom Application + Frame widget,
bottom toolbar with key hints, history, autocomplete.
"""

import os
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.filters import is_done
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window, ConditionalContainer
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea

from .commands import SLASH_COMMANDS
from ..tools.implementations import get_working_dir


HISTORY_FILE = Path.home() / ".gemini-code" / "history"


# ─── Completer ────────────────────────────────────────────────────────────────

class GeminiCompleter(Completer):
    """Autocomplete for slash commands and file paths."""

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        if text.startswith("/"):
            cmd_part = text.split()[0] if text.split() else text
            for cmd in SLASH_COMMANDS:
                if cmd.startswith(cmd_part):
                    yield Completion(
                        cmd,
                        start_position=-len(cmd_part),
                        display=cmd,
                        display_meta=_get_command_description(cmd),
                    )
            return

        if any(text.startswith(f"/{c} ") for c in ["read", "cd", "run", "find"]):
            prefix = text.split(" ", 1)[1] if " " in text else ""
            yield from _complete_path(prefix)
            return


def _complete_path(prefix: str):
    try:
        base = Path(get_working_dir())
        if prefix:
            p = Path(prefix)
            if not p.is_absolute():
                p = base / p
            search_dir  = p.parent if not prefix.endswith("/") else p
            name_prefix = p.name  if not prefix.endswith("/") else ""
        else:
            search_dir  = base
            name_prefix = ""
        if search_dir.is_dir():
            for item in sorted(search_dir.iterdir())[:30]:
                name = item.name
                if name.startswith(name_prefix):
                    rel    = str(item.relative_to(base))
                    suffix = "/" if item.is_dir() else ""
                    yield Completion(rel + suffix, start_position=-len(prefix), display=name + suffix)
    except Exception:
        pass


def _get_command_description(cmd: str) -> str:
    descriptions = {
        "/help": "Show help", "/clear": "Clear history", "/compact": "Compress context",
        "/exit": "Exit", "/quit": "Exit", "/status": "Session status",
        "/model": "Switch model", "/cost": "Token usage", "/tasks": "Show tasks",
        "/resume": "Resume session", "/sessions": "List sessions", "/save": "Save session",
        "/memory": "View GEMINI.md", "/init": "Init project", "/verbose": "Toggle verbose",
        "/thinking": "Toggle thinking", "/cd": "Change directory", "/pwd": "Print directory",
        "/diff": "Git diff", "/git": "Git command", "/run": "Run command",
        "/read": "Read file", "/ls": "List directory", "/find": "Find files",
        "/grep": "Search files", "/review": "Review changes", "/config": "Show config",
    }
    return descriptions.get(cmd, "")


# ─── Style ────────────────────────────────────────────────────────────────────

PROMPT_STYLE = Style.from_dict({
    # Frame border (the box)
    "frame.border":                            "#2a2a4a",

    # Inner text area
    "text-area":                               "#e0e0e0",
    "text-area focused":                       "#e0e0e0",

    # Prompt prefix inside the box
    "prompt-prefix":                           "#4285F4 bold",

    # Bottom toolbar
    "bottom-toolbar":                          "bg:#111111 #444444",

    # Autocomplete
    "completion-menu.completion":              "bg:#1e1e2e #cccccc",
    "completion-menu.completion.current":      "bg:#3a3a5c #ffffff bold",
    "completion-menu.meta.completion":         "bg:#1e1e2e #888888",
    "completion-menu.meta.completion.current": "bg:#3a3a5c #aaaaaa",
    "scrollbar.background":                    "bg:#1e1e2e",
    "scrollbar.button":                        "bg:#4285F4",

    # Ghost text suggestion
    "auto-suggestion":                         "#444444 italic",
})


# ─── Bottom Toolbar ───────────────────────────────────────────────────────────

def get_bottom_toolbar(model_id: str, working_dir: str):
    """Claude Code-style bottom status toolbar."""
    def toolbar():
        cwd         = Path(working_dir).name or working_dir
        short_model = model_id.split("/")[-1] if "/" in model_id else model_id
        if len(short_model) > 26:
            short_model = short_model[:24] + "…"
        return HTML(
            '<b><style fg="#4285F4">◆ TAF Code</style></b>'
            '<style fg="#2a2a2a"> │ </style>'
            f'<style fg="#555555">model: </style><style fg="#5BB8FF">{short_model}</style>'
            '<style fg="#2a2a2a"> │ </style>'
            f'<style fg="#555555">dir: </style><style fg="#cccccc">{cwd}</style>'
            '   '
            '<style fg="#444444">! for bash mode</style>'
            '<style fg="#2a2a2a"> · </style>'
            '<style fg="#444444">/ for commands</style>'
            '<style fg="#2a2a2a"> · </style>'
            '<style fg="#444444">tab to undo</style>'
            '   '
            '<style fg="#333333">\\= for newline</style>'
        )
    return toolbar


# ─── Bordered Input Box ───────────────────────────────────────────────────────

def prompt_with_border(model_id: str, working_dir: str, history: FileHistory) -> str:
    """
    Show a Claude Code-style bordered input box and return the entered text.

    Layout:
      ╭─────────────────────────────────────╮
      │ ◆ _                                 │
      ╰─────────────────────────────────────╯
      ◆ Gemini Code │ model: … │ dir: …   ! bash · / commands · \\= newline
    """
    result_holder = [""]

    # ── TextArea (the actual editable region) ─────────────────────────────────
    text_area = TextArea(
        multiline=False,
        password=False,
        completer=GeminiCompleter(),
        complete_while_typing=True,
        auto_suggest=AutoSuggestFromHistory(),
        history=history,
        style="class:text-area",
        prompt=HTML('<b><style fg="#4285F4">◆</style></b> '),
        wrap_lines=True,
    )

    # ── Key bindings ──────────────────────────────────────────────────────────
    kb = KeyBindings()

    @kb.add("enter")
    def _accept(event):
        result_holder[0] = text_area.text
        event.app.exit()

    @kb.add("c-c")
    def _interrupt(event):
        result_holder[0] = ""
        event.app.exit(exception=KeyboardInterrupt)

    @kb.add("c-d")
    def _eof(event):
        result_holder[0] = ""
        event.app.exit(exception=EOFError)

    @kb.add("c-l")
    def _clear(event):
        import subprocess
        subprocess.run(["clear"], check=False)

    # ── Layout (Frame wrapping the TextArea) ──────────────────────────────────
    framed = Frame(
        text_area,
        style="class:frame.border",
    )

    cwd         = Path(working_dir).name or working_dir
    short_model = model_id if len(model_id) <= 26 else model_id[:24] + "…"

    toolbar_window = Window(
        content=FormattedTextControl(get_bottom_toolbar(model_id, working_dir)),
        height=1,
        style="class:bottom-toolbar",
    )

    root = HSplit([framed, toolbar_window])
    layout = Layout(root, focused_element=text_area)

    # ── Application ───────────────────────────────────────────────────────────
    app: Application = Application(
        layout=layout,
        key_bindings=kb,
        style=PROMPT_STYLE,
        mouse_support=False,
        full_screen=False,
        erase_when_done=False,   # keep the box visible after submission
    )

    app.run()
    return result_holder[0]


# ─── Legacy PromptSession (used for get_prompt_text compatibility) ────────────

def get_prompt_text(model_id: str) -> HTML:
    """Kept for compatibility with any callers."""
    return HTML('<b><style fg="#4285F4">◆</style></b> ')


def create_prompt_session(model_id: str, working_dir: str):
    """
    Returns a thin wrapper that exposes a .prompt() interface
    but uses the bordered Application internally.
    """
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    history = FileHistory(str(HISTORY_FILE))

    class _BorderedSession:
        def prompt(self, prompt_text=None, **kwargs):
            return prompt_with_border(model_id, working_dir, history)

    return _BorderedSession()
