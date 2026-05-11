"""Smoke coverage for the lmctl CLI test harness."""

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
    assert capsys.readouterr().out == (
        f"Default serial set to GS3-001 in {cli_paths.config_file.resolve()}.\n"
    )

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
    output = capsys.readouterr().out
    assert f"config_file     {cli_paths.config_file.resolve()}" in output
    assert "default_serial  GS3-001" in output
