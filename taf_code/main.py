"""
Main entry point for Gemini Code CLI.
Handles interactive mode, print mode (-p), and piped input.
"""

import os
import sys
import argparse
import signal
import json
from pathlib import Path
from typing import Optional

from .engine import GeminiEngine, MODEL_ID
from .ui.renderer import (
    console, err_console, print_welcome, print_error, print_success,
    print_info, print_warning, print_help, print_separator, print_tool_call,
    print_tool_result, print_thinking, LiveTextRenderer, SpinnerContext,
    render_markdown,
)
from .ui.commands import handle_command, SLASH_COMMANDS, _auto_save
from .ui.input_handler import create_prompt_session, get_prompt_text
from .utils.config import load_config, set_value, set_api_key, get_api_key, AVAILABLE_MODELS
from .utils.session import (
    list_sessions, save_session, load_session, restore_history,
    new_session_id, get_latest_session,
)
from .tools.implementations import get_working_dir, set_working_dir


VERSION = "1.0.0"


# ─── Signal Handling ──────────────────────────────────────────────────────────

_current_engine: Optional[GeminiEngine] = None
_current_session_id: Optional[str] = None
_current_session_name: Optional[str] = None
_config: dict = {}


def _handle_sigint(sig, frame):
    """Handle Ctrl+C gracefully."""
    console.print("\n[dim](Interrupted. Press Ctrl+C again to exit, or continue typing.)[/dim]")


# ─── Main Interactive Loop ────────────────────────────────────────────────────

def run_interactive(
    engine: GeminiEngine,
    session_id: str,
    session_name: Optional[str],
    config: dict,
    initial_prompt: Optional[str] = None,
):
    """Run the interactive REPL."""
    global _current_engine, _current_session_id, _current_session_name, _config
    _current_engine = engine
    _current_session_id = session_id
    _current_session_name = session_name
    _config = config

    signal.signal(signal.SIGINT, _handle_sigint)

    print_welcome(engine.model_id, get_working_dir(), VERSION)

    prompt_session = create_prompt_session(engine.model_id, get_working_dir())

    # Handle initial prompt if provided
    if initial_prompt:
        _process_message(initial_prompt, engine, session_id, session_name, config)

    while True:
        try:
            user_input = prompt_session.prompt(get_prompt_text(engine.model_id))
        except KeyboardInterrupt:
            console.print("\n[dim]Use /exit to quit.[/dim]")
            continue
        except EOFError:
            # Ctrl+D
            _auto_save(engine, session_id, session_name, config)
            console.print("\n[gemini.dim]Goodbye! 👋[/gemini.dim]\n")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Handle slash commands
        if user_input.startswith("/"):
            result = handle_command(user_input, engine, session_id, session_name, config)
            if result.should_exit:
                break
            if result.handled:
                continue
            # Not a recognized slash command — pass to AI
            print_warning(f"Unknown command: {user_input.split()[0]}. Type /help for help.")
            continue

        # Handle shell passthrough (! prefix like many REPLs)
        if user_input.startswith("!"):
            from .tools.implementations import bash
            cmd = user_input[1:].strip()
            if cmd:
                result = bash(cmd)
                stdout = result.get("stdout", "").strip()
                stderr = result.get("stderr", "").strip()
                if stdout:
                    console.print(stdout)
                if stderr:
                    console.print(f"[dim]{stderr}[/dim]")
            continue

        # Process as AI message
        _process_message(user_input, engine, session_id, session_name, config)

        # Auto-save periodically
        turns = len(engine.get_history()) // 2
        if turns % 5 == 0 and turns > 0:
            _auto_save(engine, session_id, session_name, config)


def _process_message(
    message: str,
    engine: GeminiEngine,
    session_id: str,
    session_name: Optional[str],
    config: dict,
):
    """
    Process a user message through the AI engine.

    Flow:
      1. Spinner shows while model is processing (elapsed timer counts up).
      2. Text chunks accumulate silently behind the spinner.
      3. Tool calls stop spinner, print call line, show result with inline diff, restart spinner.
      4. After full response, spinner stops and markdown is rendered once.
    """
    verbose       = config.get("verbose", False)
    show_thinking = config.get("show_thinking", False)

    console.print()

    response_buffer   = ""
    tool_section_text = ""
    spinner_ctx: Optional[SpinnerContext] = None
    _spinner_active   = [False]
    _last_tool_args   = {}  # store latest tool call args for result renderer

    def _start_spinner(label: str = "Thinking"):
        nonlocal spinner_ctx
        if not _spinner_active[0]:
            spinner_ctx = SpinnerContext(label)
            spinner_ctx.__enter__()
            _spinner_active[0] = True

    def _stop_spinner():
        nonlocal spinner_ctx
        if _spinner_active[0] and spinner_ctx:
            spinner_ctx.__exit__(None, None, None)
            spinner_ctx = None
            _spinner_active[0] = False

    def on_text(text: str):
        nonlocal response_buffer, tool_section_text
        response_buffer   += text
        tool_section_text += text
        # Keep spinner label fresh without hammering the lock
        if _spinner_active[0] and spinner_ctx and len(response_buffer) % 80 == 0:
            spinner_ctx.update("Writing…")

    def on_tool_call(name: str, args: dict):
        nonlocal tool_section_text, _last_tool_args
        _last_tool_args = args
        _stop_spinner()
        if tool_section_text.strip():
            render_markdown(tool_section_text)
            tool_section_text = ""
            console.print()
        print_tool_call(name, args)
        _start_spinner(f"Running {name}…")

    def on_tool_result(name: str, result: dict):
        _stop_spinner()
        # Pass the captured tool args so edit_file can show the inline diff
        print_tool_result(name, result, tool_args=_last_tool_args)
        _start_spinner("Continuing…")

    def on_thinking(text: str):
        if show_thinking:
            _stop_spinner()
            print_thinking(text)
            _start_spinner("Thinking…")

    _start_spinner("Thinking")
    try:
        engine.chat_stream(
            message,
            on_text=on_text,
            on_tool_call=on_tool_call,
            on_tool_result=on_tool_result,
            on_thinking=on_thinking,
        )
    except KeyboardInterrupt:
        _stop_spinner()
        console.print("\n[dim](Generation interrupted)[/dim]")
        return
    except Exception as e:
        _stop_spinner()
        print_error(f"Error: {e}")
        return
    finally:
        _stop_spinner()

    if tool_section_text.strip():
        render_markdown(tool_section_text)

    console.print()



# ─── Print Mode (non-interactive) ─────────────────────────────────────────────

def run_print_mode(
    engine: GeminiEngine,
    prompt: str,
    output_format: str = "text",
    config: dict = None,
):
    """Run in non-interactive print mode (-p flag)."""
    config = config or {}
    verbose = config.get("verbose", False)

    tool_calls = []

    def on_text(text: str):
        if output_format == "text":
            sys.stdout.write(text)
            sys.stdout.flush()

    def on_tool_call(name: str, args: dict):
        tool_calls.append({"tool": name, "args": args})
        if verbose:
            err_console.print(f"[gemini.tool]⚙ {name}[/gemini.tool]", highlight=False)

    def on_tool_result(name: str, result: dict):
        if verbose:
            err_console.print(f"[gemini.dim]  ↳ {name} done[/gemini.dim]", highlight=False)

    full_text = engine.chat_stream(
        prompt,
        on_text=on_text,
        on_tool_call=on_tool_call,
        on_tool_result=on_tool_result,
    )

    if output_format == "json":
        output = {
            "response": full_text,
            "tool_calls": tool_calls,
            "model": engine.model_id,
        }
        print(json.dumps(output, indent=2))
    elif output_format == "text":
        if not full_text.endswith("\n"):
            sys.stdout.write("\n")


# ─── CLI Entry Point ──────────────────────────────────────────────────────────

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="gemini-code",
        description="Gemini Code — AI-powered coding assistant for your terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  gemini-code                          Start interactive session
  gemini-code "explain this project"   Start with initial prompt
  gemini-code -p "fix the bug"         Non-interactive (print mode)
  cat file.py | gemini-code -p "review this"  Process piped input
  gemini-code -c                       Continue last session
  gemini-code -r my-session            Resume named session
  gemini-code config --api-key KEY     Set API key
        """,
    )

    # Positional
    parser.add_argument("prompt", nargs="?", help="Initial prompt to send")

    # Session flags
    parser.add_argument("-p", "--print", action="store_true", dest="print_mode",
                        help="Non-interactive print mode (exits after response)")
    parser.add_argument("-c", "--continue", action="store_true", dest="continue_session",
                        help="Continue the most recent session")
    parser.add_argument("-r", "--resume", metavar="SESSION",
                        help="Resume a session by ID or name")
    parser.add_argument("-n", "--name", metavar="NAME",
                        help="Name for this session")

    # Model flags
    parser.add_argument("--model", metavar="MODEL",
                        help=f"Model to use (default: {MODEL_ID})")

    # Output flags
    parser.add_argument("--output-format", choices=["text", "json"], default="text",
                        help="Output format for print mode")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose output")
    parser.add_argument("--thinking", action="store_true",
                        help="Show model thinking/reasoning")

    # System prompt flags
    parser.add_argument("--system-prompt", metavar="PROMPT",
                        help="Replace the system prompt")
    parser.add_argument("--append-system-prompt", metavar="PROMPT",
                        help="Append to the system prompt")

    # Directory
    parser.add_argument("--add-dir", metavar="DIR",
                        help="Set working directory")

    # Version
    parser.add_argument("-v", "--version", action="version", version=f"gemini-code {VERSION}")

    # Subcommands
    subparsers = parser.add_subparsers(dest="subcommand")

    # config subcommand
    config_parser = subparsers.add_parser("config", help="Configure Gemini Code")
    config_parser.add_argument("--api-key", metavar="KEY", help="Set Gemini API key")
    config_parser.add_argument("--model", metavar="MODEL", help="Set default model")
    config_parser.add_argument("--show", action="store_true", help="Show current config")

    # sessions subcommand
    sessions_parser = subparsers.add_parser("sessions", help="List saved sessions")

    # update subcommand
    update_parser = subparsers.add_parser("update", help="Check for updates")

    args = parser.parse_args()

    # ─── Handle subcommands ───────────────────────────────────────────────────

    if args.subcommand == "config":
        _handle_config_subcommand(args)
        return

    elif args.subcommand == "sessions":
        sessions = list_sessions()
        from .ui.renderer import print_session_list
        print_session_list(sessions)
        return

    elif args.subcommand == "update":
        console.print("[gemini.dim]Checking for updates...[/gemini.dim]")
        console.print(f"[gemini.dim]Current version: {VERSION}[/gemini.dim]")
        console.print("[gemini.dim]Visit https://github.com/gemini-code/gemini-code for updates.[/gemini.dim]")
        return

    # ─── Load config ──────────────────────────────────────────────────────────

    config = load_config()

    # Apply CLI overrides to config
    if args.verbose:
        config["verbose"] = True
    if args.thinking:
        config["show_thinking"] = True

    # ─── Set working directory ────────────────────────────────────────────────

    if args.add_dir:
        target = Path(args.add_dir).resolve()
        if target.is_dir():
            set_working_dir(str(target))
            os.chdir(str(target))
        else:
            print_error(f"Directory not found: {args.add_dir}")
            sys.exit(1)

    # ─── Initialize engine ────────────────────────────────────────────────────

    api_key = config.get("api_key") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        err_console.print(
            "[gemini.error]No API key found.[/gemini.error]\n"
            "Set your Gemini API key with:\n"
            "  [bold]gemini-code config --api-key YOUR_KEY[/bold]\n"
            "Or set the environment variable:\n"
            "  [bold]export GEMINI_API_KEY=YOUR_KEY[/bold]\n"
            "\nGet a free API key at: [link]https://aistudio.google.com/apikey[/link]"
        )
        sys.exit(1)

    try:
        engine = GeminiEngine(api_key=api_key)
    except Exception as e:
        err_console.print(f"[gemini.error]Failed to initialize engine: {e}[/gemini.error]")
        sys.exit(1)

    # Apply model override
    model = args.model or config.get("model", MODEL_ID)
    engine.set_model(model)

    # Apply system prompt overrides
    if args.system_prompt:
        engine.system_prompt = args.system_prompt
    elif args.append_system_prompt:
        engine.system_prompt += f"\n\n{args.append_system_prompt}"

    # ─── Session management ───────────────────────────────────────────────────

    session_id = new_session_id()
    session_name = args.name

    if args.resume:
        session_data = load_session(args.resume)
        if session_data:
            engine.history = restore_history(session_data)
            engine.model_id = session_data.get("model_id", engine.model_id)
            session_id = session_data["id"]
            session_name = session_data.get("name") or session_name
            wd = session_data.get("working_dir", get_working_dir())
            if Path(wd).exists():
                set_working_dir(wd)
                os.chdir(wd)
            print_info(f"Resumed session: {args.resume}")
        else:
            print_error(f"Session not found: {args.resume}")
            sys.exit(1)

    elif args.continue_session:
        session_data = get_latest_session(get_working_dir())
        if session_data:
            full_data = load_session(session_data["id"])
            if full_data:
                engine.history = restore_history(full_data)
                engine.model_id = full_data.get("model_id", engine.model_id)
                session_id = full_data["id"]
                session_name = full_data.get("name") or session_name
                print_info(f"Continuing session: {session_id}")

    # ─── Handle piped input ───────────────────────────────────────────────────

    piped_content = ""
    if not sys.stdin.isatty():
        piped_content = sys.stdin.read()

    # ─── Build final prompt ───────────────────────────────────────────────────

    prompt = args.prompt or ""
    if piped_content:
        if prompt:
            prompt = f"{prompt}\n\n{piped_content}"
        else:
            prompt = piped_content

    # ─── Run in appropriate mode ──────────────────────────────────────────────

    if args.print_mode:
        if not prompt:
            print_error("Print mode requires a prompt. Use: gemini-code -p 'your prompt'")
            sys.exit(1)
        run_print_mode(engine, prompt, args.output_format, config)

    else:
        # Interactive mode
        run_interactive(engine, session_id, session_name, config, initial_prompt=prompt or None)


def _handle_config_subcommand(args):
    """Handle the config subcommand."""
    if args.api_key:
        set_api_key(args.api_key)
        print_success("API key saved.")

    if args.model:
        set_value("model", args.model)
        print_success(f"Default model set to: {args.model}")

    if args.show or (not args.api_key and not args.model):
        config = load_config()
        display = {k: ("***" if k == "api_key" and v else v) for k, v in config.items()}
        console.print_json(json.dumps(display, indent=2))


if __name__ == "__main__":
    main()
