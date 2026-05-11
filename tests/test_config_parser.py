import argparse
import builtins
import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from lmctl import _credentials as credentials
from lmctl import cli


def output_json(capsys):
    return json.loads(capsys.readouterr().out)


@pytest.fixture
def parser(monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    key_file = tmp_path / "installation_key.json"
    monkeypatch.setenv("LMCTL_CONFIG_FILE", str(config_file))
    monkeypatch.setenv("LMCTL_KEY_FILE", str(key_file))
    return cli.build_parser()


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (
            ["login"],
            {
                "command": "login",
                "serial": None,
                "save_password": True,
                "func": cli.login,
            },
        ),
        (
            ["login", "--serial", "GS3-001", "--no-save-password"],
            {
                "command": "login",
                "serial": "GS3-001",
                "save_password": False,
                "func": cli.login,
            },
        ),
        (
            ["login", "--save-password"],
            {
                "command": "login",
                "save_password": True,
                "func": cli.login,
            },
        ),
        (
            ["switch", "--serial", "GS3-001"],
            {
                "command": "switch",
                "serial": "GS3-001",
                "func": cli.switch_machine,
            },
        ),
        (
            ["password", "save"],
            {
                "command": "password",
                "password_command": "save",
                "func": cli.save_password,
            },
        ),
        (
            ["password", "status"],
            {
                "command": "password",
                "password_command": "status",
                "func": cli.password_status,
            },
        ),
        (
            ["password", "forget"],
            {
                "command": "password",
                "password_command": "forget",
                "func": cli.forget_password,
            },
        ),
        (
            ["config", "show"],
            {
                "command": "config",
                "config_command": "show",
                "func": cli.show_config,
            },
        ),
        (
            ["config", "set-serial", "GS3-001"],
            {
                "command": "config",
                "config_command": "set-serial",
                "serial": "GS3-001",
                "func": cli.set_default_serial,
            },
        ),
        (
            ["config", "clear-serial"],
            {
                "command": "config",
                "config_command": "clear-serial",
                "func": cli.clear_default_serial,
            },
        ),
        (
            [
                "key",
                "generate",
                "--output",
                "key.json",
                "--installation-id",
                "install-1",
                "--force",
            ],
            {
                "command": "key",
                "key_command": "generate",
                "output": Path("key.json"),
                "installation_id": "install-1",
                "force": True,
                "func": cli.generate_key,
            },
        ),
        (["register"], {"command": "register", "func": cli.register}),
        (
            ["things", "--json"],
            {"command": "things", "json": True, "func": cli.list_things},
        ),
        (
            ["show", "GS3-001"],
            {"command": "show", "serial": "GS3-001", "func": cli.show_machine},
        ),
        (
            ["dashboard"],
            {
                "command": "dashboard",
                "serial": None,
                "data_name": "dashboard",
                "func": cli.fetch_machine_data,
            },
        ),
        (
            ["settings", "GS3-001"],
            {
                "command": "settings",
                "serial": "GS3-001",
                "data_name": "settings",
                "func": cli.fetch_machine_data,
            },
        ),
        (
            ["statistics"],
            {
                "command": "statistics",
                "serial": None,
                "data_name": "statistics",
                "func": cli.fetch_machine_data,
            },
        ),
        (
            ["schedule", "GS3-001"],
            {
                "command": "schedule",
                "serial": "GS3-001",
                "data_name": "schedule",
                "func": cli.fetch_machine_data,
            },
        ),
        (
            ["firmware"],
            {
                "command": "firmware",
                "serial": None,
                "data_name": "firmware",
                "func": cli.fetch_machine_data,
            },
        ),
        (
            ["power", "on"],
            {
                "command": "power",
                "serial": None,
                "state": "on",
                "func": cli.set_power,
            },
        ),
        (
            ["power", "--serial", "GS3-001", "off"],
            {
                "command": "power",
                "serial": "GS3-001",
                "state": "off",
                "func": cli.set_power,
            },
        ),
        (
            ["steam", "off"],
            {
                "command": "steam",
                "serial": None,
                "state": "off",
                "func": cli.set_steam,
            },
        ),
        (
            ["steam", "--serial", "GS3-001", "on"],
            {
                "command": "steam",
                "serial": "GS3-001",
                "state": "on",
                "func": cli.set_steam,
            },
        ),
    ],
)
def test_build_parser_command_shapes(parser, argv, expected):
    args = parser.parse_args(argv)

    for name, value in expected.items():
        assert getattr(args, name) == value


def test_build_parser_global_options_and_defaults(parser, tmp_path):
    args = parser.parse_args(
        [
            "--username",
            "user",
            "--password",
            "pass",
            "--no-keyring",
            "things",
            "--json",
        ]
    )

    assert args.username == "user"
    assert args.password == "pass"
    assert args.no_keyring is True
    assert args.json is True
    assert args.key_file == tmp_path / "installation_key.json"
    assert args.config_file == tmp_path / "config.json"


def test_build_parser_global_json_is_not_overwritten(parser):
    args = parser.parse_args(["--json", "things"])

    assert args.json is True


@pytest.mark.parametrize(
    "argv",
    [
        ["login", "--json"],
        ["switch", "--json"],
        ["password", "save", "--json"],
        ["password", "status", "--json"],
        ["password", "forget", "--json"],
        ["config", "show", "--json"],
        ["config", "set-serial", "GS3-001", "--json"],
        ["config", "clear-serial", "--json"],
        ["key", "generate", "--json"],
        ["register", "--json"],
        ["things", "--json"],
        ["show", "--json"],
        ["dashboard", "--json"],
        ["settings", "--json"],
        ["statistics", "--json"],
        ["schedule", "--json"],
        ["firmware", "--json"],
        ["power", "on", "--json"],
        ["steam", "off", "--json"],
    ],
)
def test_leaf_commands_accept_json(parser, argv):
    args = parser.parse_args(argv)

    assert args.json is True


def test_build_parser_rejects_invalid_state(parser):
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["power", "maybe"])

    assert exc_info.value.code == 2


def test_power_help_uses_clear_state_and_serial_names(parser, capsys):
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["power", "-h"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "serial_or_state" not in output
    assert "--serial SERIAL" in output
    assert "{on,off}" in output
    assert "Desired state." in output


def test_load_config_returns_empty_for_missing_file(tmp_path):
    assert cli.load_config(tmp_path / "missing.json") == {}


def test_load_config_returns_json_object(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"username": "user", "default_serial": "GS3-001"}),
        encoding="utf-8",
    )

    assert cli.load_config(config_file) == {
        "username": "user",
        "default_serial": "GS3-001",
    }


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("{not json", "not valid JSON"),
        ("[]", "must contain a JSON object"),
        ('"not an object"', "must contain a JSON object"),
    ],
)
def test_load_config_rejects_invalid_config(tmp_path, contents, message):
    config_file = tmp_path / "config.json"
    config_file.write_text(contents, encoding="utf-8")

    with pytest.raises(cli.CliError, match=message):
        cli.load_config(config_file)


def test_save_config_creates_parent_and_writes_sorted_json(tmp_path):
    config_file = tmp_path / "nested" / "config.json"

    cli.save_config(config_file, {"z": 1, "a": {"b": 2}})

    assert config_file.read_text(encoding="utf-8") == (
        '{\n  "a": {\n    "b": 2\n  },\n  "z": 1\n}\n'
    )


def test_show_config_outputs_selected_fields(tmp_path, capsys):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"username": "user", "default_serial": "GS3-001", "x": "ignored"}),
        encoding="utf-8",
    )

    cli.show_config(argparse.Namespace(config_file=config_file))

    output = capsys.readouterr().out
    assert "field           value" in output
    assert f"config_file     {config_file.resolve()}" in output
    assert "username        user" in output
    assert "default_serial  GS3-001" in output


def test_show_config_outputs_json_when_requested(tmp_path, capsys):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"username": "user", "default_serial": "GS3-001", "x": "ignored"}),
        encoding="utf-8",
    )

    cli.show_config(argparse.Namespace(config_file=config_file, json=True))

    assert output_json(capsys) == {
        "config_file": str(config_file.resolve()),
        "username": "user",
        "default_serial": "GS3-001",
    }


def test_set_default_serial_saves_config_and_outputs_path(tmp_path, capsys):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"username": "user"}), encoding="utf-8")

    cli.set_default_serial(
        argparse.Namespace(config_file=config_file, serial="GS3-001")
    )

    assert json.loads(config_file.read_text(encoding="utf-8")) == {
        "default_serial": "GS3-001",
        "username": "user",
    }
    assert capsys.readouterr().out == (
        f"Default serial set to GS3-001 in {config_file.resolve()}.\n"
    )


def test_clear_default_serial_removes_only_default_serial(tmp_path, capsys):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"username": "user", "default_serial": "GS3-001"}),
        encoding="utf-8",
    )

    cli.clear_default_serial(argparse.Namespace(config_file=config_file))

    assert json.loads(config_file.read_text(encoding="utf-8")) == {"username": "user"}
    assert capsys.readouterr().out == (
        f"Default serial cleared in {config_file.resolve()}.\n"
    )


def test_resolve_serial_prefers_explicit_serial(tmp_path):
    bad_config = tmp_path / "config.json"
    bad_config.write_text("{not json", encoding="utf-8")

    assert (
        cli.resolve_serial(argparse.Namespace(serial="GS3-001", config_file=bad_config))
        == "GS3-001"
    )


def test_resolve_serial_uses_default_serial(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"default_serial": "GS3-001"}), encoding="utf-8")

    assert (
        cli.resolve_serial(argparse.Namespace(serial=None, config_file=config_file))
        == "GS3-001"
    )


def test_resolve_serial_requires_default_serial(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"username": "user"}), encoding="utf-8")

    with pytest.raises(cli.CliError, match="missing serial"):
        cli.resolve_serial(argparse.Namespace(serial=None, config_file=config_file))


@pytest.mark.parametrize("configured_serial", ["", 123, None])
def test_resolve_serial_rejects_invalid_default_serial(tmp_path, configured_serial):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"default_serial": configured_serial}),
        encoding="utf-8",
    )

    expected_message = (
        "missing serial"
        if configured_serial is None
        else f"invalid {cli.DEFAULT_SERIAL_KEY}"
    )
    with pytest.raises(cli.CliError, match=expected_message):
        cli.resolve_serial(argparse.Namespace(serial=None, config_file=config_file))


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["power", "on"], ("GS3-001", "on")),
        (["steam", "off"], ("GS3-001", "off")),
        (["power", "--serial", "GS3-002", "off"], ("GS3-002", "off")),
        (["steam", "--serial", "GS3-002", "on"], ("GS3-002", "on")),
    ],
)
def test_resolve_stateful_command_default_and_explicit_serials(
    parser, tmp_path, argv, expected
):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"default_serial": "GS3-001"}), encoding="utf-8")

    args = parser.parse_args(["--config-file", str(config_file), *argv])

    assert cli.resolve_stateful_command(args) == expected


def test_resolve_stateful_command_prefers_explicit_serial(tmp_path):
    bad_config = tmp_path / "config.json"
    bad_config.write_text("{not json", encoding="utf-8")

    assert cli.resolve_stateful_command(
        argparse.Namespace(serial="GS3-001", state="off", config_file=bad_config)
    ) == ("GS3-001", "off")


def test_credential_prefers_explicit_value(monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"username": 123}), encoding="utf-8")
    monkeypatch.setenv("LMCTL_USERNAME", "env-user")

    assert (
        cli.credential(
            "explicit-user",
            cli.USERNAME_ENV_VARS,
            "username",
            config_file=config_file,
            config_key=cli.USERNAME_KEY,
        )
        == "explicit-user"
    )


def test_credential_prefers_first_environment_value(monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"username": "config-user"}), encoding="utf-8")
    monkeypatch.setenv("LMCTL_USERNAME", "primary-env-user")
    monkeypatch.setenv("LAMARZOCCO_USERNAME", "secondary-env-user")

    assert (
        cli.credential(
            None,
            cli.USERNAME_ENV_VARS,
            "username",
            config_file=config_file,
            config_key=cli.USERNAME_KEY,
        )
        == "primary-env-user"
    )


def test_credential_uses_config_value(monkeypatch, tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"username": "config-user"}), encoding="utf-8")
    for env_var in cli.USERNAME_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)

    assert (
        cli.credential(
            None,
            cli.USERNAME_ENV_VARS,
            "username",
            config_file=config_file,
            config_key=cli.USERNAME_KEY,
        )
        == "config-user"
    )


@pytest.mark.parametrize("configured_value", ["", 123])
def test_credential_rejects_invalid_config_value(
    monkeypatch, tmp_path, configured_value
):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"username": configured_value}),
        encoding="utf-8",
    )
    for env_var in cli.USERNAME_ENV_VARS:
        monkeypatch.delenv(env_var, raising=False)

    with pytest.raises(cli.CliError, match=f"invalid {cli.USERNAME_KEY}"):
        cli.credential(
            None,
            cli.USERNAME_ENV_VARS,
            "username",
            config_file=config_file,
            config_key=cli.USERNAME_KEY,
        )


def test_credential_prompts_for_visible_value(monkeypatch):
    prompts = []
    monkeypatch.delenv("LMCTL_TEST_USERNAME", raising=False)
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(
        builtins,
        "input",
        lambda prompt: prompts.append(prompt) or "typed-user",
    )

    assert cli.credential(None, ("LMCTL_TEST_USERNAME",), "username") == "typed-user"
    assert prompts == ["La Marzocco username: "]


def test_credential_prompts_for_secret_value(monkeypatch):
    prompts = []
    monkeypatch.delenv("LMCTL_TEST_PASSWORD", raising=False)
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(
        cli.getpass,
        "getpass",
        lambda prompt: prompts.append(prompt) or "typed-password",
    )

    assert (
        cli.credential(
            None,
            ("LMCTL_TEST_PASSWORD",),
            "password",
            prompt_secret=True,
        )
        == "typed-password"
    )
    assert prompts == ["La Marzocco password: "]


def test_credential_reports_missing_value(monkeypatch):
    monkeypatch.delenv("LMCTL_TEST_USERNAME", raising=False)
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: False))

    with pytest.raises(
        cli.CliError,
        match="missing username; pass --username or set one of: LMCTL_TEST_USERNAME",
    ):
        cli.credential(None, ("LMCTL_TEST_USERNAME",), "username")


def password_args(**overrides):
    defaults = {
        "password": None,
        "no_keyring": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_password_credential_prefers_explicit_value(monkeypatch):
    monkeypatch.setenv("LMCTL_PASSWORD", "env-pass")

    assert (
        cli.password_credential(
            password_args(password="explicit-pass"),
            "user@example.com",
        )
        == "explicit-pass"
    )


def test_password_credential_prefers_environment_over_keyring(monkeypatch):
    saved_password_calls = []
    monkeypatch.setenv("LMCTL_PASSWORD", "env-pass")
    monkeypatch.setattr(
        cli,
        "get_saved_password",
        lambda username, args: saved_password_calls.append(username) or "saved-pass",
    )

    assert cli.password_credential(password_args(), "user@example.com") == "env-pass"
    assert saved_password_calls == []


def test_password_credential_uses_saved_password(monkeypatch):
    monkeypatch.delenv("LMCTL_PASSWORD", raising=False)
    monkeypatch.delenv("LAMARZOCCO_PASSWORD", raising=False)
    monkeypatch.setattr(
        credentials,
        "get_saved_password",
        lambda username, args: "saved-pass" if username == "user@example.com" else None,
    )

    assert cli.password_credential(password_args(), "user@example.com") == "saved-pass"


def test_password_credential_can_skip_saved_password(monkeypatch):
    monkeypatch.delenv("LMCTL_PASSWORD", raising=False)
    monkeypatch.delenv("LAMARZOCCO_PASSWORD", raising=False)
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(
        cli.getpass,
        "getpass",
        lambda prompt: "typed-password",
    )
    monkeypatch.setattr(
        credentials,
        "get_saved_password",
        lambda username, args: "saved-pass",
    )

    assert (
        cli.password_credential(
            password_args(),
            "user@example.com",
            allow_saved=False,
        )
        == "typed-password"
    )


def test_password_credential_reports_missing_value(monkeypatch):
    monkeypatch.delenv("LMCTL_PASSWORD", raising=False)
    monkeypatch.delenv("LAMARZOCCO_PASSWORD", raising=False)
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(credentials, "get_saved_password", lambda username, args: None)

    with pytest.raises(cli.CliError, match="missing password"):
        cli.password_credential(password_args(), "user@example.com")


def test_keyring_helpers_convert_keyring_errors(monkeypatch):
    args = password_args()

    def raise_keyring_error(*_args):
        raise cli.KeyringError("backend unavailable")

    monkeypatch.setattr(cli.keyring, "get_password", raise_keyring_error)
    monkeypatch.setattr(cli.keyring, "set_password", raise_keyring_error)

    assert cli.get_saved_password("user@example.com", args) is None
    with pytest.raises(cli.CliError, match="keyring unavailable"):
        cli.get_saved_password("user@example.com", args, required=True)
    with pytest.raises(cli.CliError, match="keyring unavailable"):
        cli.set_saved_password("user@example.com", "pass", args)


def test_keyring_helpers_respect_no_keyring(monkeypatch):
    args = password_args(no_keyring=True)
    monkeypatch.setattr(
        cli.keyring,
        "get_password",
        lambda *_args: pytest.fail("keyring should not be read"),
    )

    assert cli.get_saved_password("user@example.com", args) is None
    with pytest.raises(cli.CliError, match="disabled"):
        cli.get_saved_password("user@example.com", args, required=True)
    with pytest.raises(cli.CliError, match="disabled"):
        cli.set_saved_password("user@example.com", "pass", args)
    assert cli.keyring_disabled(args) is True


class DictModel:
    def to_dict(self):
        return {
            Path("path-key"): Path("machine.json"),
            "date": dt.date(2026, 5, 10),
            "items": (Value("ready"), {"nested": Value("ok")}),
        }


class Value:
    def __init__(self, value):
        self.value = value


def test_to_jsonable_converts_models_paths_dates_tuples_and_values():
    assert cli.to_jsonable(DictModel()) == {
        "path-key": "machine.json",
        "date": "2026-05-10",
        "items": ["ready", {"nested": "ok"}],
    }


def test_print_json_outputs_sorted_pretty_json(capsys):
    cli.print_json({"b": Path("machine.json"), "a": Value("ready")})

    assert capsys.readouterr().out == ('{\n  "a": "ready",\n  "b": "machine.json"\n}\n')


def test_print_table_formats_display_values(capsys):
    cli.print_table(
        ("name", "value"),
        [
            ("alpha", None),
            (Value("enum"), "longer"),
        ],
    )

    assert [line.rstrip() for line in capsys.readouterr().out.splitlines()] == [
        "name   value",
        "-----  ------",
        "alpha",
        "enum   longer",
    ]


def test_print_key_values_flattens_nested_values(capsys):
    cli.print_key_values(
        {
            "serial": "GS3-001",
            "nested": {"enabled": True},
            "items": [{"name": "weekday"}],
        }
    )

    output = capsys.readouterr().out
    assert "serial          GS3-001" in output
    assert "nested.enabled  True" in output
    assert "items[0].name   weekday" in output


def test_display_value_formats_none_value_objects_and_plain_values():
    assert cli.display_value(None) == ""
    assert cli.display_value(Value("ready")) == "ready"
    assert cli.display_value(123) == "123"


def test_main_returns_zero_for_successful_config_show(tmp_path, capsys):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"default_serial": "GS3-001"}), encoding="utf-8")

    assert cli.main(["--config-file", str(config_file), "config", "show"]) == 0
    assert "default_serial  GS3-001" in capsys.readouterr().out


def test_main_reports_user_correctable_errors(tmp_path, capsys):
    config_file = tmp_path / "config.json"
    config_file.write_text("{not json", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--config-file", str(config_file), "config", "show"])

    assert exc_info.value.code == 1
    assert capsys.readouterr().err == (
        f"lmctl: error: {config_file.resolve()} is not valid JSON\n"
    )
