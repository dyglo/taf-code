"""
Tool implementations for Gemini Code CLI.
Each function corresponds to a tool declared in definitions.py.
"""

import os
import re
import glob as glob_module
import subprocess
import fnmatch
import json
from pathlib import Path
from typing import Optional
from datetime import datetime


# ─── State ────────────────────────────────────────────────────────────────────

_working_dir: str = os.getcwd()
_todos: list = []


def get_working_dir() -> str:
    return _working_dir


def set_working_dir(path: str) -> None:
    global _working_dir
    _working_dir = str(Path(path).resolve())


# ─── File System Tools ────────────────────────────────────────────────────────

def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> dict:
    """Read file contents, optionally within a line range."""
    try:
        full_path = _resolve_path(path)
        if not full_path.exists():
            return {"error": f"File not found: {path}"}
        if not full_path.is_file():
            return {"error": f"Path is not a file: {path}"}

        content = full_path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)

        if start_line is not None or end_line is not None:
            s = (start_line or 1) - 1
            e = end_line if end_line and end_line != -1 else total_lines
            lines = lines[s:e]
            content = "".join(lines)
            return {
                "content": content,
                "path": str(full_path),
                "total_lines": total_lines,
                "shown_lines": f"{s+1}-{min(e, total_lines)}",
            }

        return {
            "content": content,
            "path": str(full_path),
            "total_lines": total_lines,
        }
    except PermissionError:
        return {"error": f"Permission denied: {path}"}
    except Exception as e:
        return {"error": str(e)}


def write_file(path: str, content: str) -> dict:
    """Create or overwrite a file with the given content."""
    try:
        full_path = _resolve_path(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return {
            "success": True,
            "path": str(full_path),
            "bytes_written": len(content.encode("utf-8")),
            "lines": lines,
        }
    except PermissionError:
        return {"error": f"Permission denied: {path}"}
    except Exception as e:
        return {"error": str(e)}


def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> dict:
    """Make a targeted edit to a file by replacing specific text."""
    try:
        full_path = _resolve_path(path)
        if not full_path.exists():
            return {"error": f"File not found: {path}"}

        content = full_path.read_text(encoding="utf-8", errors="replace")

        if old_string not in content:
            # Try to give a helpful diff hint
            return {
                "error": f"The exact string was not found in {path}. "
                         "Make sure the text matches exactly including whitespace and indentation.",
                "hint": f"First few chars searched: {repr(old_string[:80])}",
            }

        count = content.count(old_string)
        if replace_all:
            new_content = content.replace(old_string, new_string)
            replacements = count
        else:
            new_content = content.replace(old_string, new_string, 1)
            replacements = 1

        full_path.write_text(new_content, encoding="utf-8")
        return {
            "success": True,
            "path": str(full_path),
            "replacements": replacements,
            "total_occurrences": count,
        }
    except PermissionError:
        return {"error": f"Permission denied: {path}"}
    except Exception as e:
        return {"error": str(e)}


def list_directory(path: str = "", recursive: bool = False, max_depth: int = 3) -> dict:
    """List directory contents."""
    try:
        base = _resolve_path(path) if path else Path(_working_dir)
        if not base.exists():
            return {"error": f"Path not found: {path}"}
        if not base.is_dir():
            return {"error": f"Not a directory: {path}"}

        entries = []
        _collect_entries(base, base, entries, recursive, max_depth, 0)

        return {
            "path": str(base),
            "entries": entries,
            "total": len(entries),
        }
    except Exception as e:
        return {"error": str(e)}


def _collect_entries(base: Path, current: Path, entries: list, recursive: bool, max_depth: int, depth: int):
    """Recursively collect directory entries."""
    try:
        items = sorted(current.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return

    for item in items:
        rel = item.relative_to(base)
        entry = {
            "name": item.name,
            "path": str(rel),
            "type": "dir" if item.is_dir() else "file",
        }
        if item.is_file():
            try:
                entry["size"] = item.stat().st_size
            except Exception:
                entry["size"] = 0
        entries.append(entry)
        if recursive and item.is_dir() and depth < max_depth - 1:
            _collect_entries(base, item, entries, recursive, max_depth, depth + 1)


def glob(pattern: str, directory: str = "", exclude_patterns: Optional[list] = None) -> dict:
    """Find files matching a glob pattern."""
    try:
        base = _resolve_path(directory) if directory else Path(_working_dir)
        exclude_patterns = exclude_patterns or ["**/.git/**", "**/node_modules/**", "**/__pycache__/**", "**/.venv/**"]

        matches = []
        for p in base.glob(pattern):
            rel = str(p.relative_to(base))
            # Check exclusions
            excluded = False
            for exc in exclude_patterns:
                if fnmatch.fnmatch(rel, exc) or fnmatch.fnmatch(str(p), exc):
                    excluded = True
                    break
            if not excluded:
                matches.append({
                    "path": str(p),
                    "relative": rel,
                    "type": "dir" if p.is_dir() else "file",
                })

        matches.sort(key=lambda x: x["relative"])
        return {"matches": matches, "count": len(matches), "pattern": pattern}
    except Exception as e:
        return {"error": str(e)}


def grep(
    pattern: str,
    path: str = "",
    file_pattern: str = "",
    case_sensitive: bool = True,
    context_lines: int = 0,
    max_results: int = 100,
) -> dict:
    """Search for a regex pattern in file contents."""
    try:
        base = _resolve_path(path) if path else Path(_working_dir)
        flags = 0 if case_sensitive else re.IGNORECASE

        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return {"error": f"Invalid regex pattern: {e}"}

        results = []
        files_searched = 0

        if base.is_file():
            files_to_search = [base]
        else:
            if file_pattern:
                files_to_search = list(base.rglob(file_pattern))
            else:
                files_to_search = [f for f in base.rglob("*") if f.is_file()]

        # Filter out binary/hidden/ignored files
        ignore_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache"}
        filtered_files = []
        for f in files_to_search:
            parts = set(f.parts)
            if not parts.intersection(ignore_dirs):
                filtered_files.append(f)

        for filepath in filtered_files:
            if len(results) >= max_results:
                break
            try:
                text = filepath.read_text(encoding="utf-8", errors="replace")
                lines = text.splitlines()
                files_searched += 1

                for i, line in enumerate(lines):
                    if regex.search(line):
                        ctx_before = lines[max(0, i - context_lines):i] if context_lines else []
                        ctx_after = lines[i + 1:min(len(lines), i + 1 + context_lines)] if context_lines else []
                        results.append({
                            "file": str(filepath),
                            "line_number": i + 1,
                            "line": line,
                            "context_before": ctx_before,
                            "context_after": ctx_after,
                        })
                        if len(results) >= max_results:
                            break
            except (PermissionError, UnicodeDecodeError):
                continue

        return {
            "results": results,
            "count": len(results),
            "files_searched": files_searched,
            "pattern": pattern,
            "truncated": len(results) >= max_results,
        }
    except Exception as e:
        return {"error": str(e)}


# ─── Shell / Execution Tools ──────────────────────────────────────────────────

def bash(command: str, timeout: int = 30, working_dir: Optional[str] = None) -> dict:
    """Execute a shell command."""
    try:
        cwd = working_dir if working_dir else _working_dir
        timeout = min(max(1, timeout), 300)

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            env={**os.environ, "TERM": "xterm-256color"},
        )

        output = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
            "command": command,
        }

        # Truncate very long outputs
        max_output = 20000
        if len(result.stdout) > max_output:
            output["stdout"] = result.stdout[:max_output] + f"\n... [truncated, {len(result.stdout)} total chars]"
            output["truncated"] = True
        if len(result.stderr) > max_output:
            output["stderr"] = result.stderr[:max_output] + f"\n... [truncated, {len(result.stderr)} total chars]"

        return output
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout} seconds", "command": command}
    except Exception as e:
        return {"error": str(e), "command": command}


# ─── Web Tools ────────────────────────────────────────────────────────────────

def web_fetch(url: str, max_length: int = 10000) -> dict:
    """Fetch content from a URL."""
    try:
        import urllib.request
        import html
        from html.parser import HTMLParser

        class TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text_parts = []
                self._skip = False
                self._skip_tags = {"script", "style", "head", "meta", "link"}

            def handle_starttag(self, tag, attrs):
                if tag.lower() in self._skip_tags:
                    self._skip = True

            def handle_endtag(self, tag):
                if tag.lower() in self._skip_tags:
                    self._skip = False

            def handle_data(self, data):
                if not self._skip:
                    stripped = data.strip()
                    if stripped:
                        self.text_parts.append(stripped)

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; GeminiCode/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(max_length * 3).decode("utf-8", errors="replace")

        if "text/html" in content_type or raw.strip().startswith("<"):
            extractor = TextExtractor()
            extractor.feed(raw)
            text = "\n".join(extractor.text_parts)
        else:
            text = raw

        text = text[:max_length]
        return {"content": text, "url": url, "length": len(text)}
    except Exception as e:
        return {"error": str(e), "url": url}


def web_search(query: str, num_results: int = 5) -> dict:
    """Search the web using DuckDuckGo."""
    try:
        import urllib.request
        import urllib.parse
        import json

        encoded = urllib.parse.quote(query)
        url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "GeminiCode/1.0"})

        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []

        # Abstract (top result)
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", ""),
                "url": data.get("AbstractURL", ""),
                "snippet": data["AbstractText"],
                "source": data.get("AbstractSource", ""),
            })

        # Related topics
        for topic in data.get("RelatedTopics", [])[:num_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:100],
                    "url": topic.get("FirstURL", ""),
                    "snippet": topic.get("Text", ""),
                })

        if not results:
            # Fallback: try HTML search
            url2 = f"https://html.duckduckgo.com/html/?q={encoded}"
            req2 = urllib.request.Request(
                url2,
                headers={"User-Agent": "Mozilla/5.0 (compatible; GeminiCode/1.0)"},
            )
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                html_content = resp2.read().decode("utf-8", errors="replace")

            # Parse results from HTML
            import re as _re
            titles = _re.findall(r'class="result__title"[^>]*>.*?<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html_content, _re.DOTALL)
            snippets = _re.findall(r'class="result__snippet"[^>]*>(.*?)</div>', html_content, _re.DOTALL)

            for i, (href, title) in enumerate(titles[:num_results]):
                snippet = snippets[i] if i < len(snippets) else ""
                # Clean HTML tags
                title = _re.sub(r"<[^>]+>", "", title).strip()
                snippet = _re.sub(r"<[^>]+>", "", snippet).strip()
                results.append({"title": title, "url": href, "snippet": snippet})

        return {"results": results[:num_results], "query": query, "count": len(results[:num_results])}
    except Exception as e:
        return {"error": str(e), "query": query, "results": []}


# ─── Task / Todo Tools ────────────────────────────────────────────────────────

def todo_write(todos: list) -> dict:
    """Update the session todo list."""
    global _todos
    _todos = todos
    return {"success": True, "todos": _todos, "count": len(_todos)}


def get_todos() -> list:
    """Get current todos."""
    return _todos


# ─── Memory Tool ──────────────────────────────────────────────────────────────

def memory_write(content: str, mode: str = "overwrite") -> dict:
    """Write to the GEMINI.md memory file."""
    try:
        memory_path = Path(_working_dir) / "GEMINI.md"
        if mode == "append" and memory_path.exists():
            existing = memory_path.read_text(encoding="utf-8")
            content = existing + "\n\n" + content
        memory_path.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(memory_path), "mode": mode}
    except Exception as e:
        return {"error": str(e)}


# ─── Dispatcher ───────────────────────────────────────────────────────────────

TOOL_MAP = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_directory": list_directory,
    "glob": glob,
    "grep": grep,
    "bash": bash,
    "web_fetch": web_fetch,
    "web_search": web_search,
    "todo_write": todo_write,
    "memory_write": memory_write,
}


def dispatch_tool(name: str, args: dict) -> dict:
    """Dispatch a tool call to its implementation."""
    fn = TOOL_MAP.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        return fn(**args)
    except TypeError as e:
        return {"error": f"Invalid arguments for {name}: {e}"}
    except Exception as e:
        return {"error": f"Tool execution error: {e}"}


# ─── Path Helper ──────────────────────────────────────────────────────────────

def _resolve_path(path: str) -> Path:
    """Resolve a path relative to the working directory."""
    p = Path(path)
    if p.is_absolute():
        return p
    return Path(_working_dir) / p
