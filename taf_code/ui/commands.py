"""
Slash command handler for Gemini Code CLI.
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..engine import GeminiEngine

from .renderer import (
    console, print_help, print_status, print_todos, print_session_list,
    print_models, print_error, print_success, print_info, print_warning,
    print_separator,
)
from ..utils.config import load_config, set_value, AVAILABLE_MODELS
from ..utils.session import list_sessions, save_session, load_session, restore_history, new_session_id
from ..tools.implementations import get_working_dir, set_working_dir, bash


SLASH_COMMANDS = [
    "/help", "/clear", "/compact", "/exit", "/quit", "/status",
    "/model", "/cost", "/tasks", "/resume", "/sessions", "/save",
    "/memory", "/init", "/verbose", "/thinking", "/cd", "/pwd",
    "/diff", "/git", "/run", "/read", "/ls", "/find", "/grep",
    "/review", "/config", "/fork", "/rename",
]


class CommandResult:
    """Result of a slash command execution."""
    def __init__(self, handled: bool = True, should_exit: bool = False, message: Optional[str] = None):
        self.handled = handled
        self.should_exit = should_exit
        self.message = message


def handle_command(
    line: str,
    engine: "GeminiEngine",
    session_id: str,
    session_name: Optional[str],
    config: dict,
) -> CommandResult:
    """
    Handle a slash command.
    Returns a CommandResult indicating whether the command was handled.
    """
    parts = line.strip().split(None, 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    # ─── Session Management ───────────────────────────────────────────────────

    if cmd in ("/exit", "/quit"):
        _auto_save(engine, session_id, session_name, config)
        console.print("\n[gemini.dim]Goodbye! 👋[/gemini.dim]\n")
        return CommandResult(should_exit=True)

    elif cmd == "/clear":
        engine.clear_history()
        console.clear()
        print_success("Conversation history cleared.")
        return CommandResult()

    elif cmd == "/compact":
        print_info("Compacting conversation history...")
        summary = engine.compact_history(instructions=args)
        print_success(f"History compacted. Summary:\n{summary[:300]}...")
        return CommandResult()

    elif cmd == "/fork":
        new_id = new_session_id()
        _auto_save(engine, new_id, args or None, config)
        print_success(f"Forked session as: {new_id}" + (f" ({args})" if args else ""))
        return CommandResult()

    elif cmd == "/rename":
        if args:
            session_name = args
            print_success(f"Session renamed to: {args}")
        else:
            print_error("Usage: /rename <name>")
        return CommandResult()

    elif cmd == "/save":
        name = args or session_name
        path = save_session(session_id, name, engine.get_history(), get_working_dir(), engine.model_id)
        print_success(f"Session saved: {session_id}" + (f" ({name})" if name else ""))
        return CommandResult()

    elif cmd == "/sessions":
        sessions = list_sessions()
        print_session_list(sessions)
        return CommandResult()

    elif cmd == "/resume":
        if not args:
            sessions = list_sessions()
            print_session_list(sessions)
            print_info("Usage: /resume <id|name>")
            return CommandResult()

        session_data = load_session(args)
        if not session_data:
            print_error(f"Session not found: {args}")
            return CommandResult()

        history = restore_history(session_data)
        engine.history = history
        engine.model_id = session_data.get("model_id", engine.model_id)
        wd = session_data.get("working_dir", get_working_dir())
        if Path(wd).exists():
            set_working_dir(wd)
        print_success(f"Resumed session: {args} ({len(history)//2} turns)")
        return CommandResult()

    # ─── Information ──────────────────────────────────────────────────────────

    elif cmd == "/help":
        print_help()
        return CommandResult()

    elif cmd == "/status":
        print_status(engine.get_session_info(), config)
        return CommandResult()

    elif cmd == "/cost":
        info = engine.get_session_info()
        turns = info.get("history_turns", 0)
        console.print(f"[gemini.dim]Turns: {turns} | Model: {engine.model_id}[/gemini.dim]")
        console.print("[gemini.dim]Note: Exact token counts are not available in streaming mode.[/gemini.dim]")
        return CommandResult()

    elif cmd == "/tasks":
        from ..tools.implementations import get_todos
        todos = get_todos()
        print_todos(todos)
        return CommandResult()

    elif cmd == "/config":
        cfg = load_config()
        # Mask API key
        display = {k: ("***" if k == "api_key" and v else v) for k, v in cfg.items()}
        console.print_json(json.dumps(display, indent=2))
        return CommandResult()

    # ─── Model Control ────────────────────────────────────────────────────────

    elif cmd == "/model":
        if not args:
            print_models(AVAILABLE_MODELS, engine.model_id)
            return CommandResult()

        # Find matching model
        model = args.strip()
        if model not in AVAILABLE_MODELS:
            # Try prefix match
            matches = [m for m in AVAILABLE_MODELS if model in m]
            if len(matches) == 1:
                model = matches[0]
            elif len(matches) > 1:
                print_warning(f"Ambiguous model name. Matches: {', '.join(matches)}")
                return CommandResult()
            else:
                print_warning(f"Unknown model: {model}. Using as-is.")

        engine.set_model(model)
        set_value("model", model)
        print_success(f"Switched to model: {model}")
        return CommandResult()

    # ─── Settings Toggles ─────────────────────────────────────────────────────

    elif cmd == "/verbose":
        current = config.get("verbose", False)
        config["verbose"] = not current
        set_value("verbose", config["verbose"])
        state = "enabled" if config["verbose"] else "disabled"
        print_success(f"Verbose mode {state}.")
        return CommandResult()

    elif cmd == "/thinking":
        current = config.get("show_thinking", False)
        config["show_thinking"] = not current
        set_value("show_thinking", config["show_thinking"])
        state = "enabled" if config["show_thinking"] else "disabled"
        print_success(f"Thinking display {state}.")
        return CommandResult()

    # ─── File System ──────────────────────────────────────────────────────────

    elif cmd == "/cd":
        if not args:
            print_error("Usage: /cd <path>")
            return CommandResult()
        target = Path(args).expanduser()
        if not target.is_absolute():
            target = Path(get_working_dir()) / target
        target = target.resolve()
        if not target.exists():
            print_error(f"Directory not found: {target}")
        elif not target.is_dir():
            print_error(f"Not a directory: {target}")
        else:
            set_working_dir(str(target))
            os.chdir(str(target))
            print_success(f"Changed directory to: {target}")
        return CommandResult()

    elif cmd == "/pwd":
        console.print(f"[gemini.path]{get_working_dir()}[/gemini.path]")
        return CommandResult()

    elif cmd == "/ls":
        from ..tools.implementations import list_directory
        path = args or ""
        result = list_directory(path, recursive=False)
        if "error" in result:
            print_error(result["error"])
        else:
            _print_directory_listing(result)
        return CommandResult()

    elif cmd == "/read":
        if not args:
            print_error("Usage: /read <file>")
            return CommandResult()
        from ..tools.implementations import read_file
        result = read_file(args)
        if "error" in result:
            print_error(result["error"])
        else:
            from rich.syntax import Syntax
            ext = Path(args).suffix.lstrip(".")
            lang = _ext_to_lang(ext)
            content = result.get("content", "")
            syntax = Syntax(content, lang, theme="monokai", line_numbers=True)
            console.print(syntax)
        return CommandResult()

    elif cmd == "/find":
        if not args:
            print_error("Usage: /find <pattern>")
            return CommandResult()
        from ..tools.implementations import glob
        result = glob(args)
        if "error" in result:
            print_error(result["error"])
        else:
            matches = result.get("matches", [])
            for m in matches:
                console.print(f"  [gemini.path]{m['relative']}[/gemini.path]")
            print_info(f"{len(matches)} file(s) found.")
        return CommandResult()

    elif cmd == "/grep":
        if not args:
            print_error("Usage: /grep <pattern>")
            return CommandResult()
        from ..tools.implementations import grep
        result = grep(args)
        if "error" in result:
            print_error(result["error"])
        else:
            results = result.get("results", [])
            for r in results[:50]:
                console.print(
                    f"  [gemini.path]{r['file']}[/gemini.path]:[cyan]{r['line_number']}[/cyan]: {r['line']}"
                )
            if result.get("truncated"):
                print_info(f"Showing first 50 of {result['count']} matches.")
            else:
                print_info(f"{result['count']} match(es) in {result['files_searched']} file(s).")
        return CommandResult()

    # ─── Git Commands ─────────────────────────────────────────────────────────

    elif cmd == "/diff":
        result = bash("git diff --stat HEAD 2>/dev/null || git diff --stat 2>/dev/null")
        output = result.get("stdout", "").strip()
        if output:
            from rich.syntax import Syntax
            console.print(Syntax(output, "diff", theme="monokai"))
        else:
            print_info("No uncommitted changes.")
        return CommandResult()

    elif cmd == "/git":
        if not args:
            print_error("Usage: /git <command>")
            return CommandResult()
        result = bash(f"git {args}")
        _print_bash_result(result)
        return CommandResult()

    elif cmd == "/review":
        result = bash("git log --oneline -10 2>/dev/null")
        if result.get("stdout"):
            console.print("[bold]Recent commits:[/bold]")
            console.print(result["stdout"])
        result2 = bash("git diff --stat HEAD 2>/dev/null")
        if result2.get("stdout"):
            console.print("[bold]Uncommitted changes:[/bold]")
            console.print(result2["stdout"])
        return CommandResult()

    # ─── Shell ────────────────────────────────────────────────────────────────

    elif cmd == "/run":
        if not args:
            print_error("Usage: /run <command>")
            return CommandResult()
        result = bash(args)
        _print_bash_result(result)
        return CommandResult()

    # ─── Memory ───────────────────────────────────────────────────────────────

    elif cmd == "/memory":
        memory_path = Path(get_working_dir()) / "GEMINI.md"
        if memory_path.exists():
            from rich.syntax import Syntax
            content = memory_path.read_text(encoding="utf-8")
            console.print(Syntax(content, "markdown", theme="monokai"))
        else:
            print_info("No GEMINI.md found. Use /init to create one.")
        return CommandResult()

    elif cmd == "/init":
        _init_project(engine)
        return CommandResult()

    # ─── Not a slash command ──────────────────────────────────────────────────

    return CommandResult(handled=False)


def _auto_save(engine, session_id, session_name, config):
    """Auto-save session on exit."""
    if engine.get_history():
        try:
            save_session(session_id, session_name, engine.get_history(), get_working_dir(), engine.model_id)
        except Exception:
            pass


def _print_bash_result(result: dict):
    """Print bash command output."""
    stdout = result.get("stdout", "").strip()
    stderr = result.get("stderr", "").strip()
    exit_code = result.get("exit_code", 0)

    if stdout:
        console.print(stdout)
    if stderr:
        console.print(f"[dim]{stderr}[/dim]")
    if exit_code != 0:
        print_warning(f"Exit code: {exit_code}")


def _print_directory_listing(result: dict):
    """Print a directory listing."""
    entries = result.get("entries", [])
    path = result.get("path", "")
    console.print(f"[gemini.path]{path}[/gemini.path]")
    for entry in entries:
        if entry["type"] == "dir":
            console.print(f"  [bold blue]{entry['name']}/[/bold blue]")
        else:
            size = entry.get("size", 0)
            size_str = _format_size(size)
            console.print(f"  [gemini.path]{entry['name']}[/gemini.path] [dim]{size_str}[/dim]")


def _format_size(size: int) -> str:
    """Format file size for display."""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size/1024:.1f}KB"
    else:
        return f"{size/1024/1024:.1f}MB"


def _ext_to_lang(ext: str) -> str:
    """Map file extension to syntax highlighting language."""
    mapping = {
        "py": "python", "js": "javascript", "ts": "typescript",
        "jsx": "jsx", "tsx": "tsx", "html": "html", "css": "css",
        "json": "json", "yaml": "yaml", "yml": "yaml", "toml": "toml",
        "md": "markdown", "sh": "bash", "bash": "bash", "zsh": "bash",
        "rs": "rust", "go": "go", "java": "java", "c": "c", "cpp": "cpp",
        "h": "c", "hpp": "cpp", "rb": "ruby", "php": "php", "sql": "sql",
        "xml": "xml", "dockerfile": "dockerfile", "tf": "hcl",
        "txt": "text", "log": "text",
    }
    return mapping.get(ext.lower(), "text")


def _init_project(engine: "GeminiEngine"):
    """Initialize GEMINI.md for the current project."""
    from ..tools.implementations import bash as run_bash, get_working_dir
    from rich.prompt import Confirm

    cwd = get_working_dir()
    memory_path = Path(cwd) / "GEMINI.md"

    if memory_path.exists():
        if not Confirm.ask(f"[yellow]GEMINI.md already exists. Overwrite?[/yellow]", default=False):
            return

    # Gather project info
    print_info("Analyzing project structure...")
    ls_result = run_bash("ls -la 2>/dev/null | head -30")
    git_result = run_bash("git log --oneline -5 2>/dev/null")
    pkg_result = run_bash(
        "cat package.json 2>/dev/null | head -20 || "
        "cat pyproject.toml 2>/dev/null | head -20 || "
        "cat Cargo.toml 2>/dev/null | head -20 || "
        "cat go.mod 2>/dev/null | head -10 || echo ''"
    )

    project_info = f"""Project directory: {cwd}

Files:
{ls_result.get('stdout', '')}

Recent git history:
{git_result.get('stdout', 'No git history')}

Package info:
{pkg_result.get('stdout', 'No package file found')}
"""

    # Ask Gemini to generate GEMINI.md
    prompt = f"""Based on this project information, generate a GEMINI.md file.
This file will be loaded as context for every session.
Include: project overview, tech stack, key conventions, important files, and any notes.
Keep it concise (under 500 words).

{project_info}"""

    print_info("Generating GEMINI.md with Gemini...")
    content = engine.chat_once(prompt)

    memory_path.write_text(content, encoding="utf-8")
    print_success(f"Created GEMINI.md at {memory_path}")
    console.print(f"[dim]{content[:300]}...[/dim]" if len(content) > 300 else f"[dim]{content}[/dim]")
