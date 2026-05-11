"""Installation key helpers."""

from __future__ import annotations

import uuid
from pathlib import Path

from pylamarzocco.util import InstallationKey, generate_installation_key

from ._config import expand_path
from ._errors import CliError
from ._output import json_text


def load_installation_key(path: Path) -> InstallationKey:
    """Load an installation key from disk."""
    key_file = expand_path(path)
    if not key_file.exists():
        raise CliError(f"{key_file} does not exist; run `lmctl key generate` first")
    try:
        return InstallationKey.from_json(key_file.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise CliError(f"{key_file} is not a valid installation key") from exc


def ensure_installation_key(path: Path) -> tuple[InstallationKey, bool]:
    """Load an installation key, or create one when missing."""
    key_file = expand_path(path)
    if key_file.exists():
        return load_installation_key(key_file), False

    installation_key = generate_installation_key(str(uuid.uuid4()).lower())
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(json_text(installation_key.to_json()), encoding="utf-8")
    return installation_key, True
