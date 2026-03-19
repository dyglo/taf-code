"""
Rich terminal UI renderer for Gemini Code CLI.
Claude Code-style: inline diffs on edits, rich tool results, spinner with timer,
proper markdown rendering, and named diff panels.
"""

import json
import os
import re
import difflib
import time
import threading
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.spinner import Spinner
from rich.rule import Rule
from rich.columns import Columns
from rich import box
from rich.style import Style
from rich.theme import Theme


# ─── Theme ────────────────────────────────────────────────────────────────────

GEMINI_THEME = Theme({
    "gemini.brand":       "bold #4285F4",
    "gemini.tool":        "bold #34A853",
    "gemini.tool.name":   "#34A853",
    "gemini.tool.args":   "#FBBC04",
    "gemini.tool.result": "#4285F4",
    "gemini.error":       "bold red",
    "gemini.warning":     "bold yellow",
    "gemini.success":     "bold #34A853",
    "gemini.thinking":    "italic #666666",
    "gemini.user":        "bold #4285F4",
    "gemini.dim":         "dim #888888",
    "gemini.path":        "#5BB8FF",
    "gemini.code":        "#98C379",
    "gemini.slash":       "bold #C678DD",
    "diff.add":           "#98C379",       # green
    "diff.remove":        "#E06C75",       # red
    "diff.header":        "bold #61AFEF",  # blue
    "diff.hunk":          "#56B6C2",       # teal
    "diff.add.bold":      "bold #98C379",
    "diff.remove.bold":   "bold #E06C75",
})

console     = Console(theme=GEMINI_THEME, highlight=False)
err_console = Console(stderr=True, theme=GEMINI_THEME)


# ─── Branding ─────────────────────────────────────────────────────────────────

LOGO = """\
[gemini.brand]  ████████╗ █████╗ ███████╗     ██████╗  ██████╗ ██████╗ ███████╗
 ╚══██╔══╝██╔══██╗██╔════╝    ██╔════╝ ██╔═══██╗██╔══██╗██╔════╝
    ██║   ███████║█████╗      ██║      ██║   ██║██║  ██║█████╗  
    ██║   ██╔══██║██╔══╝      ██║      ██║   ██║██║  ██║██╔══╝  
    ██║   ██║  ██║██║         ╚██████╗ ╚██████╔╝██████╔╝███████╗
    ╚═╝   ╚═╝  ╚═╝╚═╝          ╚═════╝  ╚═════╝ ╚═════╝ ╚══════╝[/gemini.brand]"""


def print_welcome(model_id: str, working_dir: str, version: str = "1.0.0"):
    console.print()
    console.print(LOGO)
    console.print()
    info_table = Table(show_header=False, box=None, padding=(0, 2))
    info_table.add_column(style="gemini.dim")
    info_table.add_column()
    info_table.add_row("Version",   f"[bold]{version}[/bold]")
    info_table.add_row("Model",     f"[gemini.brand]{model_id}[/gemini.brand]")
    info_table.add_row("Directory", f"[gemini.path]{working_dir}[/gemini.path]")
    info_table.add_row("Help",      "[gemini.slash]/help[/gemini.slash] for commands, [gemini.slash]/exit[/gemini.slash] to quit")
    console.print(info_table)
    console.print()


def print_separator(label: str = ""):
    if label:
        console.print(Rule(f"[gemini.dim]{label}[/gemini.dim]", style="gemini.dim"))
    else:
        console.rule(style="#1e1e2e")


# ─── Tool Display ─────────────────────────────────────────────────────────────

def print_tool_call(tool_name: str, args: dict):
    """Display a tool call — Claude Code style with green gear."""
    args_display = _format_tool_args(tool_name, args)
    console.print(
        f"  [gemini.tool]⚙[/gemini.tool] [gemini.tool.name]{tool_name}[/gemini.tool.name]"
        f"[gemini.dim]([/gemini.dim]{args_display}[gemini.dim])[/gemini.dim]"
    )


def print_tool_result(tool_name: str, result: dict, tool_args: Optional[dict] = None):
    """
    Display a tool result.
    For edit_file and write_file, shows a Claude Code-style inline diff panel.
    """
    tool_args = tool_args or {}

    if "error" in result:
        console.print(f"    [gemini.error]✗ Error:[/gemini.error] {result['error']}")
        return

    # ── edit_file: inline diff ────────────────────────────────────────────────
    if tool_name == "edit_file":
        path       = tool_args.get("path", result.get("path", ""))
        old_string = tool_args.get("old_string", "")
        new_string = tool_args.get("new_string", "")
        reps       = result.get("replacements", 1)

        if old_string and new_string:
            old_lines  = old_string.splitlines(keepends=True)
            new_lines  = new_string.splitlines(keepends=True)
            additions  = sum(1 for l in new_lines if l.strip())
            removals   = sum(1 for l in old_lines if l.strip())
            filename   = Path(path).name if path else "file"
            summary    = Text()
            summary.append(f"  Updated ", style="gemini.dim")
            summary.append(filename, style="gemini.path")
            summary.append(f" with ", style="gemini.dim")
            summary.append(f"{additions} addition{'s' if additions != 1 else ''}", style="diff.add.bold")
            summary.append(" and ", style="gemini.dim")
            summary.append(f"{removals} removal{'s' if removals != 1 else ''}", style="diff.remove.bold")
            console.print(summary)
            _render_inline_tool_diff(old_string, new_string, path)
        else:
            console.print(f"    [gemini.dim]↳ {reps} replacement(s)[/gemini.dim]")
        return

    # ── write_file: show summary + first lines ────────────────────────────────
    if tool_name == "write_file":
        path  = result.get("path", tool_args.get("path", ""))
        size  = result.get("bytes_written", 0)
        lines = result.get("lines", 0)
        fname = Path(path).name if path else "file"
        console.print(
            f"    [gemini.dim]↳ [/gemini.dim][gemini.success]Wrote[/gemini.success] "
            f"[gemini.path]{fname}[/gemini.path] "
            f"[gemini.dim]({lines} lines, {size} bytes)[/gemini.dim]"
        )
        return

    # ── generic summary ───────────────────────────────────────────────────────
    summary = _summarize_tool_result(tool_name, result)
    if summary:
        console.print(f"    [gemini.dim]↳ {summary}[/gemini.dim]")


def _render_inline_tool_diff(old_str: str, new_str: str, path: str = ""):
    """
    Render a Claude Code-style inline diff panel showing added/removed lines
    with line numbers and color highlights.
    """
    filename = Path(path).name if path else "file"

    old_lines = old_str.splitlines()
    new_lines = new_str.splitlines()

    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm="",
        n=3,  # context lines
    ))

    if not diff:
        return

    output = Text()
    # Skip the --- / +++ header lines (first two)
    for line in diff[2:]:
        if line.startswith("@@"):
            output.append(line + "\n", style="diff.hunk")
        elif line.startswith("+"):
            output.append(line + "\n", style="diff.add")
        elif line.startswith("-"):
            output.append(line + "\n", style="diff.remove")
        else:
            output.append(line + "\n", style="dim")

    console.print(
        Panel(
            output,
            title=f"[diff.header]{filename}[/diff.header]",
            border_style="#3a3a5c",
            padding=(0, 1),
        )
    )


def print_thinking(text: str):
    if text.strip():
        snippet = text[:200] + "..." if len(text) > 200 else text
        console.print(f"[gemini.thinking]  💭 {snippet}[/gemini.thinking]")


# ─── Spinner ──────────────────────────────────────────────────────────────────

class SpinnerContext:
    """
    Claude Code-style animated spinner with elapsed time counter.
    Shows: ⠋ Thinking… 3s  (auto-erases when done — transient=True)
    """

    def __init__(self, label: str = "Thinking"):
        self._label    = label
        self._start    = time.monotonic()
        self._lock     = threading.Lock()
        self._spinner  = Spinner("dots", style="gemini.brand")
        self._live: Optional[Live] = None
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def _make_renderable(self):
        elapsed = int(time.monotonic() - self._start)
        label   = self._label
        t       = Text()
        t.append("  ")
        t.append_text(Text.from_markup(f"[gemini.dim]{label}[/gemini.dim]"))
        if elapsed >= 2:
            t.append(f"  [gemini.dim]{elapsed}s · esc to interrupt[/gemini.dim]")
        return t

    def __enter__(self):
        self._start = time.monotonic()
        self._live  = Live(
            self._spinner,
            console=console,
            refresh_per_second=10,
            transient=True,
        )
        self._live.__enter__()

        # Background thread that updates both the spinner text and elapsed timer
        def _tick():
            while not self._stop_evt.wait(0.5):
                with self._lock:
                    elapsed = int(time.monotonic() - self._start)
                    label   = self._label
                    parts   = [f"[gemini.dim]{label}[/gemini.dim]"]
                    if elapsed >= 2:
                        parts.append(f"[gemini.dim]{elapsed}s · esc to interrupt[/gemini.dim]")
                    self._spinner.text = " ".join(parts)
                    if self._live:
                        self._live.update(self._spinner)

        self._thread = threading.Thread(target=_tick, daemon=True)
        self._thread.start()
        return self

    def update(self, label: str):
        with self._lock:
            self._label      = label
            self._start      = time.monotonic()   # reset timer per phase

    def __exit__(self, *args):
        self._stop_evt.set()
        if self._thread:
            self._thread.join(timeout=1)
        if self._live:
            self._live.__exit__(*args)


# ─── Markdown Rendering ───────────────────────────────────────────────────────

def render_markdown(text: str):
    """
    Render markdown text — bold, lists, headings, code blocks, and diffs.
    No raw ** or # symbols ever shown.
    """
    if not text.strip():
        return

    segments = _split_code_blocks(text)

    for seg_type, seg_lang, seg_content in segments:
        if seg_type == "code":
            if seg_lang in ("diff", "patch") or _looks_like_diff(seg_content):
                _render_diff_block(seg_content)
            else:
                lang = seg_lang or "text"
                try:
                    syntax = Syntax(
                        seg_content,
                        lang,
                        theme="one-dark",
                        line_numbers=False,
                        word_wrap=True,
                    )
                    console.print(syntax)
                except Exception:
                    console.print(seg_content)
        else:
            _render_prose(seg_content)


def _split_code_blocks(text: str):
    segments = []
    pattern  = re.compile(r"```(\w*)\n?(.*?)```", re.DOTALL)
    last_end = 0

    for m in pattern.finditer(text):
        before = text[last_end:m.start()]
        if before.strip():
            segments.append(("prose", "", before))
        lang = m.group(1).strip()
        code = m.group(2)
        if code.endswith("\n"):
            code = code[:-1]
        segments.append(("code", lang, code))
        last_end = m.end()

    remaining = text[last_end:]
    if remaining.strip():
        segments.append(("prose", "", remaining))

    return segments


def _render_prose(text: str):
    text = text.strip()
    if not text:
        return
    try:
        console.print(Markdown(text, justify="left"))
    except Exception:
        console.print(text)


def _looks_like_diff(text: str) -> bool:
    lines       = text.splitlines()
    diff_markers = sum(1 for l in lines if l.startswith(("+", "-", "@@", "---", "+++")))
    return diff_markers >= 3


def _extract_diff_filename(diff_text: str) -> str:
    """Extract filename from +++ line in a unified diff."""
    for line in diff_text.splitlines():
        if line.startswith("+++"):
            # e.g. "+++ b/README.md" → "README.md"
            parts = line.split(None, 1)
            if len(parts) > 1:
                fname = parts[1].strip()
                # strip "b/" prefix
                if fname.startswith(("b/", "a/")):
                    fname = fname[2:]
                return Path(fname).name
    return "diff"


def _render_diff_block(diff_text: str):
    """Render a diff block with colour-coded lines and filename in the panel title."""
    filename = _extract_diff_filename(diff_text)
    output   = Text()

    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            output.append(line + "\n", style="diff.header")
        elif line.startswith("@@"):
            output.append(line + "\n", style="diff.hunk")
        elif line.startswith("+"):
            output.append(line + "\n", style="diff.add")
        elif line.startswith("-"):
            output.append(line + "\n", style="diff.remove")
        else:
            output.append(line + "\n", style="dim")

    title = f"[diff.header]{filename}[/diff.header]" if filename != "diff" else "[diff.header]Diff[/diff.header]"
    console.print(
        Panel(output, title=title, border_style="blue", padding=(0, 1))
    )


# ─── Live Text Renderer (compatibility shim) ──────────────────────────────────

class LiveTextRenderer:
    """Kept for compatibility — accumulates text that main.py renders after streaming."""
    def __init__(self):
        self._buffer = ""

    def append(self, text: str):
        self._buffer += text

    def flush(self):
        buf = self._buffer.strip()
        self._buffer = ""
        if buf:
            render_markdown(buf)


# ─── Standard Printers ───────────────────────────────────────────────────────

def print_response(text: str):
    if text.strip():
        render_markdown(text)


def print_error(message: str):
    console.print(f"[gemini.error]✗ {message}[/gemini.error]")


def print_success(message: str):
    console.print(f"[gemini.success]✓ {message}[/gemini.success]")


def print_warning(message: str):
    console.print(f"[gemini.warning]⚠ {message}[/gemini.warning]")


def print_info(message: str):
    console.print(f"[gemini.dim]ℹ {message}[/gemini.dim]")


# ─── Todo / Session / Model tables ───────────────────────────────────────────

def print_todos(todos: list):
    if not todos:
        console.print("[gemini.dim]No tasks.[/gemini.dim]")
        return
    table = Table(title="Tasks", box=box.ROUNDED, show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Status", width=12)
    table.add_column("Priority", width=10)
    table.add_column("Task")
    status_icons   = {"completed": "[green]✓ done[/green]", "in_progress": "[yellow]⟳ active[/yellow]", "pending": "[dim]○ pending[/dim]"}
    priority_colors = {"high": "[red]high[/red]", "medium": "[yellow]medium[/yellow]", "low": "[dim]low[/dim]"}
    for i, todo in enumerate(todos, 1):
        status   = todo.get("status", "pending")
        priority = todo.get("priority", "medium")
        content  = todo.get("content", "")
        if status == "completed":
            content = f"[dim]{content}[/dim]"
        table.add_row(str(i), status_icons.get(status, status), priority_colors.get(priority, priority), content)
    console.print(table)


def print_session_list(sessions: list):
    if not sessions:
        console.print("[gemini.dim]No saved sessions.[/gemini.dim]")
        return
    table = Table(title="Sessions", box=box.ROUNDED)
    table.add_column("ID",        style="cyan", width=10)
    table.add_column("Name",      width=20)
    table.add_column("Turns",     width=6, justify="right")
    table.add_column("Model",     width=30)
    table.add_column("Directory")
    table.add_column("Updated")
    for s in sessions:
        table.add_row(s["id"], s.get("name",""), str(s.get("turn_count",0)), s.get("model_id",""), _shorten_path(s.get("working_dir","")), _format_time(s.get("updated_at","")))
    console.print(table)


def print_help():
    console.print()
    console.print(Panel(_build_help_text(), title="[gemini.brand]TAF Code — Help[/gemini.brand]", border_style="blue", padding=(1, 2)))
    console.print()


def print_status(engine_info: dict, config: dict):
    table = Table(show_header=False, box=box.ROUNDED, title="[gemini.brand]TAF Code — Session Status[/gemini.brand]")
    table.add_column(style="gemini.dim", width=20)
    table.add_column()
    table.add_row("Model",         f"[gemini.brand]{engine_info.get('model','unknown')}[/gemini.brand]")
    table.add_row("Working Dir",   f"[gemini.path]{engine_info.get('working_dir', os.getcwd())}[/gemini.path]")
    table.add_row("Turns",         str(engine_info.get("history_turns", 0)))
    table.add_row("Verbose",       "on" if config.get("verbose") else "off")
    table.add_row("Show Thinking", "on" if config.get("show_thinking") else "off")
    todos = engine_info.get("todos", [])
    if todos:
        pending = sum(1 for t in todos if t.get("status") == "pending")
        done    = sum(1 for t in todos if t.get("status") == "completed")
        table.add_row("Tasks", f"{done} done, {pending} pending")
    console.print(table)


def print_models(models: list, current: str):
    table = Table(title="Available Models", box=box.ROUNDED)
    table.add_column("Model ID")
    table.add_column("Status", width=10)
    for m in models:
        is_current = m == current
        table.add_row(
            f"[gemini.brand]{m}[/gemini.brand]" if is_current else m,
            "[green]active[/green]" if is_current else "",
        )
    console.print(table)


def stream_text_live(initial_text: str = "") -> "LiveTextRenderer":
    return LiveTextRenderer()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _format_tool_args(tool_name: str, args: dict) -> str:
    if not args:
        return ""
    if tool_name == "bash":
        cmd = args.get("command", "")
        if len(cmd) > 60:
            cmd = cmd[:57] + "..."
        return f"[gemini.tool.args]{cmd}[/gemini.tool.args]"
    elif tool_name in ("read_file", "write_file", "edit_file"):
        path   = args.get("path", "")
        offset = args.get("offset", "")
        limit  = args.get("limit", "")
        extra  = f"[gemini.dim], offset: {offset}, limit: {limit}[/gemini.dim]" if offset else ""
        return f"[gemini.path]{path}[/gemini.path]{extra}"
    elif tool_name == "glob":
        return f"[gemini.tool.args]{args.get('pattern','')}[/gemini.tool.args]"
    elif tool_name == "grep":
        return f"[gemini.tool.args]{args.get('pattern','')}[/gemini.tool.args]"
    elif tool_name == "web_fetch":
        url = args.get("url", "")
        if len(url) > 60:
            url = url[:57] + "..."
        return f"[link]{url}[/link]"
    elif tool_name == "web_search":
        return f"[gemini.tool.args]{args.get('query','')}[/gemini.tool.args]"
    elif tool_name == "list_directory":
        return f"[gemini.path]{args.get('path','.')}[/gemini.path]"
    else:
        parts = []
        for k, v in list(args.items())[:2]:
            v_str = str(v)
            if len(v_str) > 30:
                v_str = v_str[:27] + "..."
            parts.append(f"[gemini.tool.args]{k}={v_str}[/gemini.tool.args]")
        return ", ".join(parts)


def _summarize_tool_result(tool_name: str, result: dict) -> str:
    if tool_name == "bash":
        exit_code = result.get("exit_code", 0)
        stdout    = result.get("stdout", "").strip()
        if exit_code != 0:
            stderr = result.get("stderr", "").strip()
            msg = stderr[:80] if stderr else f"exit code {exit_code}"
            return f"[red]exit {exit_code}[/red]: {msg}"
        if stdout:
            first_line = stdout.split("\n")[0]
            lines = stdout.count("\n") + 1
            if lines > 1:
                return f"{first_line[:60]} [dim](+{lines-1} lines)[/dim]"
            return first_line[:80]
        return "[green]ok[/green]"
    elif tool_name == "read_file":
        lines = result.get("total_lines", 0)
        path  = Path(result.get("path", "")).name
        return f"{path} ({lines} lines)"
    elif tool_name == "glob":
        return f"{result.get('count', 0)} file(s) found"
    elif tool_name == "grep":
        return f"{result.get('count', 0)} match(es) in {result.get('files_searched', 0)} file(s)"
    elif tool_name == "list_directory":
        return f"{result.get('total', 0)} entries"
    elif tool_name == "web_fetch":
        return f"{result.get('length', 0)} chars fetched"
    elif tool_name == "web_search":
        return f"{result.get('count', 0)} result(s)"
    elif tool_name == "todo_write":
        return f"{result.get('count', 0)} task(s) updated"
    elif tool_name == "memory_write":
        return "[green]GEMINI.md updated[/green]"
    return ""


def _shorten_path(path: str, max_len: int = 40) -> str:
    if len(path) <= max_len:
        return path
    parts = Path(path).parts
    if len(parts) > 3:
        return str(Path(*parts[:1]) / "..." / Path(*parts[-2:]))
    return path[-max_len:]


def _format_time(iso_time: str) -> str:
    if not iso_time:
        return ""
    try:
        from datetime import datetime
        dt   = datetime.fromisoformat(iso_time)
        now  = datetime.now()
        diff = now - dt
        if diff.days > 0:
            return f"{diff.days}d ago"
        hours = diff.seconds // 3600
        if hours > 0:
            return f"{hours}h ago"
        mins = diff.seconds // 60
        return f"{mins}m ago"
    except Exception:
        return iso_time[:16]


def _build_help_text() -> str:
    return """[bold]Slash Commands[/bold]

[gemini.slash]/help[/gemini.slash]                    Show this help
[gemini.slash]/clear[/gemini.slash]                   Clear conversation history
[gemini.slash]/compact[/gemini.slash] [instructions]  Compress conversation context
[gemini.slash]/exit[/gemini.slash], [gemini.slash]/quit[/gemini.slash]          Exit Gemini Code
[gemini.slash]/status[/gemini.slash]                  Show session status
[gemini.slash]/model[/gemini.slash] [name]            Switch model (or list models)
[gemini.slash]/cost[/gemini.slash]                    Show token usage
[gemini.slash]/tasks[/gemini.slash]                   Show task list
[gemini.slash]/resume[/gemini.slash] [id|name]        Resume a saved session
[gemini.slash]/sessions[/gemini.slash]                List saved sessions
[gemini.slash]/save[/gemini.slash] [name]             Save current session
[gemini.slash]/memory[/gemini.slash]                  View/edit GEMINI.md memory file
[gemini.slash]/init[/gemini.slash]                    Initialize GEMINI.md for this project
[gemini.slash]/verbose[/gemini.slash]                 Toggle verbose tool output
[gemini.slash]/thinking[/gemini.slash]                Toggle thinking display
[gemini.slash]/cd[/gemini.slash] <path>               Change working directory
[gemini.slash]/pwd[/gemini.slash]                     Print working directory
[gemini.slash]/diff[/gemini.slash]                    Show git diff
[gemini.slash]/git[/gemini.slash] <args>              Run git command
[gemini.slash]/run[/gemini.slash] <command>           Run a shell command
[gemini.slash]/read[/gemini.slash] <file>             Read and display a file
[gemini.slash]/ls[/gemini.slash] [path]               List directory
[gemini.slash]/find[/gemini.slash] <pattern>          Find files by glob pattern
[gemini.slash]/grep[/gemini.slash] <pattern>          Search file contents
[gemini.slash]/review[/gemini.slash]                  Review recent git changes
[gemini.slash]/config[/gemini.slash]                  Show configuration

[bold]Keyboard Shortcuts[/bold]

[dim]Ctrl+C[/dim]          Cancel current generation or exit
[dim]Ctrl+L[/dim]          Clear screen
[dim]Up/Down[/dim]         Navigate input history
[dim]Tab[/dim]             Autocomplete slash commands

[bold]Usage Tips[/bold]

• Start with a question or task: [dim]"explain this codebase"[/dim]
• Pipe files: [dim]cat file.py | gemini-code -p "review this"[/dim]
• Non-interactive: [dim]gemini-code -p "fix the bug in main.py"[/dim]
• Continue session: [dim]gemini-code -c[/dim]"""
