"""Smoke coverage for the lmctl CLI test harness."""

import json

import pytest

from lmctl import cli


def test_main_help_exits_success(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--help"])

    assert exc_info.value.code == 0
    assert "Control La Marzocco Home machines" in capsys.readouterr().out


def test_config_commands_round_trip(
    cli_paths, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli.main(
            [
                "--config-file",
                str(cli_paths.config_file),
                "config",
                "set-serial",
                "GS3-001",
            ]
        )
        == 0
    )
    set_payload = json.loads(capsys.readouterr().out)

    assert set_payload == {
        "config_file": str(cli_paths.config_file.resolve()),
        "default_serial": "GS3-001",
    }

    assert (
        cli.main(
            [
                "--config-file",
                str(cli_paths.config_file),
                "config",
                "show",
            ]
        )
        == 0
    )
    show_payload = json.loads(capsys.readouterr().out)

    assert show_payload == {
        "config_file": str(cli_paths.config_file.resolve()),
        "default_serial": "GS3-001",
        "username": None,
    }
