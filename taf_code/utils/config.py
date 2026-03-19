"""
Configuration management for Gemini Code CLI.
Stores settings in ~/.gemini-code/config.json
"""

import json
import os
from pathlib import Path
from typing import Any, Optional


CONFIG_DIR = Path.home() / ".gemini-code"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "api_key": "",
    "model": "gemini-3-flash-preview",
    "theme": "dark",
    "verbose": False,
    "show_thinking": False,
    "auto_compact_threshold": 0.85,
    "max_tool_rounds": 20,
    "default_timeout": 30,
}


def _ensure_config_dir():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """Load configuration from disk, merging with defaults."""
    _ensure_config_dir()
    config = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            stored = json.loads(CONFIG_FILE.read_text())
            config.update(stored)
        except Exception:
            pass

    # Environment variable overrides
    if os.environ.get("GEMINI_API_KEY"):
        config["api_key"] = os.environ["GEMINI_API_KEY"]
    elif os.environ.get("GOOGLE_API_KEY"):
        config["api_key"] = os.environ["GOOGLE_API_KEY"]

    return config


def save_config(config: dict) -> None:
    """Save configuration to disk."""
    _ensure_config_dir()
    # Don't save env-var API keys to disk
    to_save = {k: v for k, v in config.items() if k != "api_key" or not (
        os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    )}
    CONFIG_FILE.write_text(json.dumps(to_save, indent=2))


def get(key: str, default: Any = None) -> Any:
    """Get a single config value."""
    return load_config().get(key, default)


def set_value(key: str, value: Any) -> None:
    """Set a single config value."""
    config = load_config()
    config[key] = value
    save_config(config)


def set_api_key(api_key: str) -> None:
    """Store the API key securely in config."""
    config = load_config()
    config["api_key"] = api_key
    _ensure_config_dir()
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    # Set restrictive permissions
    try:
        CONFIG_FILE.chmod(0o600)
    except Exception:
        pass


def get_api_key() -> Optional[str]:
    """Get the API key from config or environment."""
    config = load_config()
    return config.get("api_key") or None


AVAILABLE_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-flash-preview-04-17",
    "gemini-2.5-pro-preview-03-25",
]
