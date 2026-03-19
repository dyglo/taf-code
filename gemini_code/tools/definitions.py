"""
Tool definitions for Gemini function calling.
Each tool mirrors the capabilities of Claude Code.
"""

from google.genai import types

# ─── File System Tools ────────────────────────────────────────────────────────

read_file_tool = types.FunctionDeclaration(
    name="read_file",
    description=(
        "Read the contents of a file at the given path. "
        "Supports optional line range to read only a portion of large files. "
        "Returns the file content as a string."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "path": types.Schema(
                type=types.Type.STRING,
                description="Absolute or relative path to the file to read.",
            ),
            "start_line": types.Schema(
                type=types.Type.INTEGER,
                description="Optional 1-based start line number (inclusive).",
            ),
            "end_line": types.Schema(
                type=types.Type.INTEGER,
                description="Optional 1-based end line number (inclusive). -1 means end of file.",
            ),
        },
        required=["path"],
    ),
)

write_file_tool = types.FunctionDeclaration(
    name="write_file",
    description=(
        "Create a new file or completely overwrite an existing file with the given content. "
        "Creates parent directories if they do not exist. "
        "Use edit_file for targeted changes to existing files."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "path": types.Schema(
                type=types.Type.STRING,
                description="Absolute or relative path to the file to write.",
            ),
            "content": types.Schema(
                type=types.Type.STRING,
                description="The full content to write to the file.",
            ),
        },
        required=["path", "content"],
    ),
)

edit_file_tool = types.FunctionDeclaration(
    name="edit_file",
    description=(
        "Make targeted edits to an existing file by replacing specific text. "
        "Finds the exact 'old_string' in the file and replaces it with 'new_string'. "
        "The old_string must match exactly (including whitespace and indentation). "
        "Use this for surgical edits rather than rewriting the whole file."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "path": types.Schema(
                type=types.Type.STRING,
                description="Absolute or relative path to the file to edit.",
            ),
            "old_string": types.Schema(
                type=types.Type.STRING,
                description="The exact text to find and replace. Must match exactly.",
            ),
            "new_string": types.Schema(
                type=types.Type.STRING,
                description="The replacement text.",
            ),
            "replace_all": types.Schema(
                type=types.Type.BOOLEAN,
                description="If true, replace all occurrences. Default is false (replace first only).",
            ),
        },
        required=["path", "old_string", "new_string"],
    ),
)

list_directory_tool = types.FunctionDeclaration(
    name="list_directory",
    description=(
        "List files and directories at the given path. "
        "Returns a tree-style listing with file sizes and types."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "path": types.Schema(
                type=types.Type.STRING,
                description="Directory path to list. Defaults to current working directory.",
            ),
            "recursive": types.Schema(
                type=types.Type.BOOLEAN,
                description="If true, list recursively. Default is false.",
            ),
            "max_depth": types.Schema(
                type=types.Type.INTEGER,
                description="Maximum depth for recursive listing. Default is 3.",
            ),
        },
        required=[],
    ),
)

glob_tool = types.FunctionDeclaration(
    name="glob",
    description=(
        "Find files matching a glob pattern. "
        "Supports patterns like '**/*.py', 'src/**/*.ts', '*.json'. "
        "Returns a list of matching file paths."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "pattern": types.Schema(
                type=types.Type.STRING,
                description="Glob pattern to match files against.",
            ),
            "directory": types.Schema(
                type=types.Type.STRING,
                description="Base directory to search from. Defaults to current working directory.",
            ),
            "exclude_patterns": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description="Glob patterns to exclude (e.g., ['node_modules/**', '.git/**']).",
            ),
        },
        required=["pattern"],
    ),
)

grep_tool = types.FunctionDeclaration(
    name="grep",
    description=(
        "Search for a regex pattern in file contents. "
        "Returns matching lines with file paths and line numbers. "
        "Supports context lines before/after matches."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "pattern": types.Schema(
                type=types.Type.STRING,
                description="Regular expression pattern to search for.",
            ),
            "path": types.Schema(
                type=types.Type.STRING,
                description="File or directory to search in. Defaults to current directory.",
            ),
            "file_pattern": types.Schema(
                type=types.Type.STRING,
                description="Glob pattern to filter which files to search (e.g., '*.py').",
            ),
            "case_sensitive": types.Schema(
                type=types.Type.BOOLEAN,
                description="Whether the search is case-sensitive. Default is true.",
            ),
            "context_lines": types.Schema(
                type=types.Type.INTEGER,
                description="Number of context lines to show before and after each match.",
            ),
            "max_results": types.Schema(
                type=types.Type.INTEGER,
                description="Maximum number of results to return. Default is 100.",
            ),
        },
        required=["pattern"],
    ),
)

# ─── Shell / Execution Tools ──────────────────────────────────────────────────

bash_tool = types.FunctionDeclaration(
    name="bash",
    description=(
        "Execute a shell command in the current working directory. "
        "The working directory persists across calls. "
        "Returns stdout, stderr, and exit code. "
        "Use for running tests, git commands, package managers, compilers, etc."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "command": types.Schema(
                type=types.Type.STRING,
                description="The shell command to execute.",
            ),
            "timeout": types.Schema(
                type=types.Type.INTEGER,
                description="Timeout in seconds. Default is 30. Max is 300.",
            ),
            "working_dir": types.Schema(
                type=types.Type.STRING,
                description="Override working directory for this command only.",
            ),
        },
        required=["command"],
    ),
)

# ─── Web Tools ────────────────────────────────────────────────────────────────

web_fetch_tool = types.FunctionDeclaration(
    name="web_fetch",
    description=(
        "Fetch the content of a URL. "
        "Returns the page content as text (HTML converted to readable text). "
        "Useful for reading documentation, APIs, or web pages."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "url": types.Schema(
                type=types.Type.STRING,
                description="The URL to fetch.",
            ),
            "max_length": types.Schema(
                type=types.Type.INTEGER,
                description="Maximum characters to return. Default is 10000.",
            ),
        },
        required=["url"],
    ),
)

web_search_tool = types.FunctionDeclaration(
    name="web_search",
    description=(
        "Search the web for information. "
        "Returns a list of search results with titles, URLs, and snippets."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "query": types.Schema(
                type=types.Type.STRING,
                description="The search query.",
            ),
            "num_results": types.Schema(
                type=types.Type.INTEGER,
                description="Number of results to return. Default is 5.",
            ),
        },
        required=["query"],
    ),
)

# ─── Task / Todo Tools ────────────────────────────────────────────────────────

todo_write_tool = types.FunctionDeclaration(
    name="todo_write",
    description=(
        "Manage a task checklist for the current session. "
        "Can create, update, or replace the entire todo list. "
        "Use this to track multi-step work and show progress."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "todos": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "id": types.Schema(type=types.Type.STRING, description="Unique ID for the task."),
                        "content": types.Schema(type=types.Type.STRING, description="Task description."),
                        "status": types.Schema(
                            type=types.Type.STRING,
                            description="Status: 'pending', 'in_progress', or 'completed'.",
                        ),
                        "priority": types.Schema(
                            type=types.Type.STRING,
                            description="Priority: 'high', 'medium', or 'low'.",
                        ),
                    },
                    required=["id", "content", "status"],
                ),
                description="The complete list of todos to set.",
            ),
        },
        required=["todos"],
    ),
)

# ─── Memory / Notes Tool ──────────────────────────────────────────────────────

memory_write_tool = types.FunctionDeclaration(
    name="memory_write",
    description=(
        "Write or update the GEMINI.md memory file for the current project. "
        "This file persists across sessions and contains project context, "
        "conventions, and important notes."
    ),
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "content": types.Schema(
                type=types.Type.STRING,
                description="Full content to write to the GEMINI.md memory file.",
            ),
            "mode": types.Schema(
                type=types.Type.STRING,
                description="'overwrite' to replace entirely, 'append' to add to existing. Default is 'overwrite'.",
            ),
        },
        required=["content"],
    ),
)

# ─── All Tools ────────────────────────────────────────────────────────────────

ALL_TOOLS = types.Tool(
    function_declarations=[
        read_file_tool,
        write_file_tool,
        edit_file_tool,
        list_directory_tool,
        glob_tool,
        grep_tool,
        bash_tool,
        web_fetch_tool,
        web_search_tool,
        todo_write_tool,
        memory_write_tool,
    ]
)

TOOL_NAMES = [
    "read_file",
    "write_file",
    "edit_file",
    "list_directory",
    "glob",
    "grep",
    "bash",
    "web_fetch",
    "web_search",
    "todo_write",
    "memory_write",
]
