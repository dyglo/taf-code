"""
Session management: save, load, list, and resume conversation sessions.
"""

import os
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional


SESSIONS_DIR = Path.home() / ".gemini-code" / "sessions"


def _ensure_sessions_dir():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def save_session(
    session_id: str,
    name: Optional[str],
    history: list,
    working_dir: str,
    model_id: str,
) -> str:
    """Save a session to disk. Returns the session file path."""
    _ensure_sessions_dir()

    # Convert history to serializable format
    serialized_history = []
    for content in history:
        parts_data = []
        for part in content.parts:
            if part.text:
                parts_data.append({"type": "text", "text": part.text})
            elif hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                parts_data.append({
                    "type": "function_call",
                    "name": fc.name,
                    "args": dict(fc.args) if fc.args else {},
                })
            elif hasattr(part, "function_response") and part.function_response:
                fr = part.function_response
                parts_data.append({
                    "type": "function_response",
                    "name": fr.name,
                    "response": dict(fr.response) if fr.response else {},
                })
        serialized_history.append({"role": content.role, "parts": parts_data})

    session_data = {
        "id": session_id,
        "name": name or "",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "working_dir": working_dir,
        "model_id": model_id,
        "history": serialized_history,
        "turn_count": len([c for c in history if c.role == "user"]),
    }

    session_file = SESSIONS_DIR / f"{session_id}.json"
    session_file.write_text(json.dumps(session_data, indent=2, ensure_ascii=False))
    return str(session_file)


def load_session(session_id_or_name: str) -> Optional[dict]:
    """Load a session by ID or name."""
    _ensure_sessions_dir()

    # Try by exact ID first
    session_file = SESSIONS_DIR / f"{session_id_or_name}.json"
    if session_file.exists():
        return json.loads(session_file.read_text())

    # Try by name
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if data.get("name", "").lower() == session_id_or_name.lower():
                return data
        except Exception:
            continue

    return None


def list_sessions(limit: int = 20) -> list:
    """List recent sessions sorted by update time."""
    _ensure_sessions_dir()
    sessions = []
    for f in SESSIONS_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            sessions.append({
                "id": data["id"],
                "name": data.get("name", ""),
                "updated_at": data.get("updated_at", ""),
                "working_dir": data.get("working_dir", ""),
                "model_id": data.get("model_id", ""),
                "turn_count": data.get("turn_count", 0),
            })
        except Exception:
            continue

    sessions.sort(key=lambda x: x["updated_at"], reverse=True)
    return sessions[:limit]


def get_latest_session(working_dir: Optional[str] = None) -> Optional[dict]:
    """Get the most recent session, optionally filtered by working directory."""
    sessions = list_sessions(50)
    if working_dir:
        sessions = [s for s in sessions if s.get("working_dir") == working_dir]
    return sessions[0] if sessions else None


def new_session_id() -> str:
    """Generate a new unique session ID."""
    return str(uuid.uuid4())[:8]


def delete_session(session_id: str) -> bool:
    """Delete a session file."""
    session_file = SESSIONS_DIR / f"{session_id}.json"
    if session_file.exists():
        session_file.unlink()
        return True
    return False


def restore_history(session_data: dict):
    """Restore conversation history from session data."""
    from google.genai import types

    history = []
    for item in session_data.get("history", []):
        parts = []
        for part_data in item.get("parts", []):
            ptype = part_data.get("type")
            if ptype == "text":
                parts.append(types.Part.from_text(text=part_data["text"]))
            elif ptype == "function_call":
                # Reconstruct as text for simplicity (function calls can't be directly reconstructed)
                parts.append(types.Part.from_text(
                    text=f"[Tool call: {part_data['name']}({json.dumps(part_data.get('args', {}))})]"
                ))
            elif ptype == "function_response":
                parts.append(types.Part.from_text(
                    text=f"[Tool result: {part_data['name']} -> {json.dumps(part_data.get('response', {}))}]"
                ))
        if parts:
            history.append(types.Content(role=item["role"], parts=parts))

    return history
