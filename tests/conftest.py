"""Shared pytest fixtures for lmctl tests."""

from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass(frozen=True)
class CliPaths:
    """Filesystem paths commonly passed to lmctl CLI commands."""

    config_file: Path
    key_file: Path


@pytest.fixture
def cli_paths(tmp_path: Path) -> CliPaths:
    """Return isolated config and key paths for CLI tests."""

    return CliPaths(
        config_file=tmp_path / "config.json",
        key_file=tmp_path / "installation_key.json",
    )
