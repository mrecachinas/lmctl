"""Configuration and path helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ._constants import APP_NAME, DEFAULT_SERIAL_KEY
from ._errors import CliError


def default_key_file() -> Path:
    """Return the default installation key path."""
    configured = os.environ.get("LMCTL_KEY_FILE")
    if configured:
        return Path(configured).expanduser()

    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / APP_NAME / "installation_key.json"


def default_config_file() -> Path:
    """Return the default lmctl config path."""
    configured = os.environ.get("LMCTL_CONFIG_FILE")
    if configured:
        return Path(configured).expanduser()

    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / APP_NAME / "config.json"


def load_config(path: Path) -> dict[str, Any]:
    """Load lmctl configuration from disk."""
    config_file = expand_path(path)
    if not config_file.exists():
        return {}

    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"{config_file} is not valid JSON") from exc

    if not isinstance(config, dict):
        raise CliError(f"{config_file} must contain a JSON object")

    return config


def save_config(path: Path, config: dict[str, Any]) -> None:
    """Save lmctl configuration to disk."""
    config_file = expand_path(path)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def resolve_serial(args: Any) -> str:
    """Resolve a serial number from args or the configured default."""
    explicit_serial = getattr(args, "serial", None)
    if explicit_serial:
        return explicit_serial

    config = load_config(args.config_file)
    configured_serial = config.get(DEFAULT_SERIAL_KEY)
    if configured_serial is None:
        raise CliError(
            "missing serial; pass a serial or run `lmctl config set-serial SERIAL`"
        )
    if not isinstance(configured_serial, str) or configured_serial == "":
        raise CliError(
            f"{expand_path(args.config_file)} has an invalid {DEFAULT_SERIAL_KEY}"
        )
    return configured_serial


def resolve_stateful_command(args: Any) -> tuple[str, str]:
    """Resolve serial/state for power and steam commands."""
    return resolve_serial(args), args.state


def expand_path(path: Path) -> Path:
    """Expand and resolve a user-facing path."""
    return path.expanduser().resolve()
