from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pylamarzocco.util import generate_installation_key as real_generate_installation_key

from lmctl import _client as client_module
from lmctl import _commands as commands_module
from lmctl import cli


@dataclass
class FakeThing:
    serial_number: str
    name: str | None = None
    model_name: str | None = None
    connected: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "serial_number": self.serial_number,
            "name": self.name,
            "model_name": self.model_name,
            "connected": self.connected,
        }


class FakeSession:
    instances: list[FakeSession] = []

    def __init__(self) -> None:
        self.closed = False
        self.entered = False
        FakeSession.instances.append(self)

    async def __aenter__(self) -> FakeSession:
        self.entered = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        self.closed = True


class FakeCloudClient:
    instances: list[FakeCloudClient] = []
    things: list[FakeThing] = []

    def __init__(
        self,
        *,
        username: str,
        password: str,
        installation_key: Any,
        client: FakeSession | None = None,
    ) -> None:
        self.username = username
        self.password = password
        self.installation_key = installation_key
        self.client = client
        self.register_calls = 0
        self.list_calls = 0
        FakeCloudClient.instances.append(self)

    async def async_register_client(self) -> dict[str, bool]:
        self.register_calls += 1
        return {"registered": True}

    async def list_things(self) -> list[FakeThing]:
        self.list_calls += 1
        return list(self.things)


class FakeMachine:
    instances: list[FakeMachine] = []
    command_results = {"power": True, "steam": True}

    def __init__(self, serial_number: str, cloud_client: FakeCloudClient | object) -> None:
        self.serial_number = serial_number
        self.cloud_client = cloud_client
        self.calls: list[Any] = []
        self.dashboard: dict[str, Any] | None = None
        self.settings: dict[str, Any] | None = None
        self.statistics: dict[str, Any] | None = None
        self.schedule: dict[str, Any] | None = None
        FakeMachine.instances.append(self)

    async def get_firmware(self) -> dict[str, Any]:
        self.calls.append("firmware")
        return {"serial": self.serial_number, "version": "1.2.3"}

    async def get_dashboard(self) -> None:
        self.calls.append("dashboard")
        self.dashboard = {"resource": "dashboard", "serial": self.serial_number}

    async def get_settings(self) -> None:
        self.calls.append("settings")
        self.settings = {"resource": "settings", "serial": self.serial_number}

    async def get_statistics(self) -> None:
        self.calls.append("statistics")
        self.statistics = {"resource": "statistics", "serial": self.serial_number}

    async def get_schedule(self) -> None:
        self.calls.append("schedule")
        self.schedule = {"resource": "schedule", "serial": self.serial_number}

    async def set_power(self, enabled: bool) -> bool:
        self.calls.append(("power", enabled))
        return self.command_results["power"]

    async def set_steam(self, enabled: bool) -> bool:
        self.calls.append(("steam", enabled))
        return self.command_results["steam"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "serial_number": self.serial_number,
            "dashboard": self.dashboard,
            "settings": self.settings,
            "statistics": self.statistics,
        }


@pytest.fixture(autouse=True)
def clean_credential_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*cli.USERNAME_ENV_VARS, *cli.PASSWORD_ENV_VARS):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake_cloud(monkeypatch: pytest.MonkeyPatch) -> type[FakeCloudClient]:
    FakeSession.instances = []
    FakeCloudClient.instances = []
    FakeCloudClient.things = []
    monkeypatch.setattr(client_module, "ClientSession", FakeSession)
    monkeypatch.setattr(client_module, "LaMarzoccoCloudClient", FakeCloudClient)
    monkeypatch.setattr(commands_module, "ClientSession", FakeSession)
    monkeypatch.setattr(commands_module, "LaMarzoccoCloudClient", FakeCloudClient)
    return FakeCloudClient


@pytest.fixture
def fake_machine(monkeypatch: pytest.MonkeyPatch) -> type[FakeMachine]:
    FakeMachine.instances = []
    FakeMachine.command_results = {"power": True, "steam": True}
    monkeypatch.setattr(commands_module, "LaMarzoccoMachine", FakeMachine)
    return FakeMachine


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def args_for(tmp_path: Path, **overrides: Any) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "username": None,
        "password": None,
        "key_file": tmp_path / "installation_key.json",
        "config_file": tmp_path / "config.json",
        "serial": None,
        "json": False,
        "data_name": None,
        "state": None,
        "output": None,
        "installation_id": None,
        "force": False,
        "save_password": True,
        "no_keyring": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def write_key(path: Path, installation_id: str = "installation-id") -> Any:
    key = real_generate_installation_key(installation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cli.json_text(key.to_json()), encoding="utf-8")
    return key


def write_config(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def read_output_json(capsys: pytest.CaptureFixture[str]) -> Any:
    return json.loads(capsys.readouterr().out)


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> dict[tuple[str, str], str]:
    passwords: dict[tuple[str, str], str] = {}

    monkeypatch.setattr(
        cli.keyring,
        "get_password",
        lambda service, username: passwords.get((service, username)),
    )
    monkeypatch.setattr(
        cli.keyring,
        "set_password",
        lambda service, username, password: passwords.__setitem__(
            (service, username), password
        ),
    )
    monkeypatch.setattr(
        cli.keyring,
        "delete_password",
        lambda service, username: passwords.pop((service, username), None),
    )
    return passwords


def test_login_generates_key_registers_and_saves_selected_machine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
    fake_keyring: dict[tuple[str, str], str],
) -> None:
    key_file = tmp_path / "keys" / "generated.json"
    config_file = tmp_path / "config" / "config.json"
    fake_cloud.things = [
        FakeThing("SERIAL-1", "Kitchen", "Linea Mini", True),
        FakeThing("SERIAL-2", "Office", "GS3", False),
    ]
    monkeypatch.setenv("LMCTL_USERNAME", "env-user")
    monkeypatch.setenv("LMCTL_PASSWORD", "env-pass")

    run(cli.login(args_for(tmp_path, key_file=key_file, config_file=config_file, serial="SERIAL-2")))

    client = fake_cloud.instances[0]
    assert client.username == "env-user"
    assert client.password == "env-pass"
    assert client.register_calls == 1
    assert client.list_calls == 1
    assert key_file.exists()
    assert FakeSession.instances[0].closed is True
    assert json.loads(config_file.read_text(encoding="utf-8")) == {
        "default_serial": "SERIAL-2",
        "username": "env-user",
    }
    assert "env-pass" not in config_file.read_text(encoding="utf-8")
    assert fake_keyring[(cli.KEYRING_SERVICE, "env-user")] == "env-pass"
    assert capsys.readouterr().out.splitlines() == [
        "Logged in as env-user.",
        "Default machine set to SERIAL-2 - Office - GS3.",
        f"Generated installation key at {key_file.resolve()}.",
        "Saved password to the OS keychain.",
    ]


def test_login_save_password_stores_verified_password_after_success(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
    fake_keyring: dict[tuple[str, str], str],
) -> None:
    key_file = tmp_path / "existing-key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file, "existing-installation")
    fake_cloud.things = [FakeThing("SERIAL-1", "Kitchen", "Linea Mini", True)]

    run(
        cli.login(
            args_for(
                tmp_path,
                key_file=key_file,
                config_file=config_file,
                username="explicit-user",
                password="explicit-pass",
                save_password=True,
            )
        )
    )

    assert fake_keyring[(cli.KEYRING_SERVICE, "explicit-user")] == "explicit-pass"
    assert "explicit-pass" not in config_file.read_text(encoding="utf-8")
    assert "Saved password to the OS keychain." in capsys.readouterr().out


def test_login_no_keyring_skips_default_password_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
    fake_keyring: dict[tuple[str, str], str],
) -> None:
    key_file = tmp_path / "existing-key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file, "existing-installation")
    fake_cloud.things = [FakeThing("SERIAL-1")]
    monkeypatch.setenv("LMCTL_USERNAME", "env-user")
    monkeypatch.setenv("LMCTL_PASSWORD", "env-pass")

    run(
        cli.login(
            args_for(
                tmp_path,
                key_file=key_file,
                config_file=config_file,
                no_keyring=True,
            )
        )
    )

    assert fake_keyring == {}
    assert "Password not saved." in capsys.readouterr().out


def test_login_no_save_password_skips_password_save(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
    fake_keyring: dict[tuple[str, str], str],
) -> None:
    key_file = tmp_path / "existing-key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file, "existing-installation")
    fake_cloud.things = [FakeThing("SERIAL-1")]
    monkeypatch.setenv("LMCTL_USERNAME", "env-user")
    monkeypatch.setenv("LMCTL_PASSWORD", "env-pass")

    run(
        cli.login(
            args_for(
                tmp_path,
                key_file=key_file,
                config_file=config_file,
                save_password=False,
            )
        )
    )

    assert fake_keyring == {}
    assert "Password not saved." in capsys.readouterr().out


def test_login_loads_existing_key_without_registering(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
    fake_keyring: dict[tuple[str, str], str],
) -> None:
    key_file = tmp_path / "existing-key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file, "existing-installation")
    fake_cloud.things = [FakeThing("SERIAL-1", "Kitchen", "Linea Mini", True)]

    run(
        cli.login(
            args_for(
                tmp_path,
                key_file=key_file,
                config_file=config_file,
                username="explicit-user",
                password="explicit-pass",
            )
        )
    )

    client = fake_cloud.instances[0]
    assert client.installation_key.installation_id == "existing-installation"
    assert client.register_calls == 0
    assert json.loads(config_file.read_text(encoding="utf-8")) == {
        "default_serial": "SERIAL-1",
        "username": "explicit-user",
    }
    output = capsys.readouterr().out
    assert "Generated installation key" not in output
    assert "Saved password to the OS keychain." in output
    assert fake_keyring[(cli.KEYRING_SERVICE, "explicit-user")] == "explicit-pass"


def test_switch_machine_updates_default_serial_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
) -> None:
    key_file = tmp_path / "key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file, "switch-key")
    write_config(
        config_file,
        {"username": "saved-user", "default_serial": "OLD", "other": {"kept": True}},
    )
    fake_cloud.things = [FakeThing("OLD"), FakeThing("NEW", "New machine")]
    monkeypatch.setenv("LMCTL_PASSWORD", "switch-pass")

    run(cli.switch_machine(args_for(tmp_path, key_file=key_file, config_file=config_file, serial="NEW")))

    client = fake_cloud.instances[0]
    assert client.username == "saved-user"
    assert client.password == "switch-pass"
    assert client.installation_key.installation_id == "switch-key"
    assert FakeSession.instances[0].closed is True
    assert json.loads(config_file.read_text(encoding="utf-8")) == {
        "username": "saved-user",
        "default_serial": "NEW",
        "other": {"kept": True},
    }
    assert capsys.readouterr().out == "Default machine set to NEW - New machine.\n"


def test_switch_machine_shows_selector_even_for_one_machine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
) -> None:
    key_file = tmp_path / "key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file, "switch-key")
    write_config(config_file, {"username": "saved-user", "default_serial": "OLD"})
    fake_cloud.things = [FakeThing("ONLY", "Kitchen")]
    monkeypatch.setenv("LMCTL_PASSWORD", "switch-pass")
    choose_calls: list[tuple[list[str], str | None, bool]] = []

    def fake_choose_thing(things: list[FakeThing], serial: str | None, *, always_select: bool = False) -> FakeThing:
        choose_calls.append(([thing.serial_number for thing in things], serial, always_select))
        return things[0]

    monkeypatch.setattr(commands_module, "choose_thing", fake_choose_thing)

    run(cli.switch_machine(args_for(tmp_path, key_file=key_file, config_file=config_file)))

    assert choose_calls == [(["ONLY"], None, True)]
    assert capsys.readouterr().out == "Default machine set to ONLY - Kitchen.\n"


def test_list_things_json_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
) -> None:
    key_file = tmp_path / "key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file)
    write_config(config_file, {"username": "saved-user"})
    monkeypatch.setenv("LMCTL_PASSWORD", "pass")
    fake_cloud.things = [FakeThing("SERIAL-1", "Kitchen", "Linea Mini", True)]

    run(cli.list_things(args_for(tmp_path, key_file=key_file, config_file=config_file, json=True)))

    assert read_output_json(capsys) == [
        {
            "serial_number": "SERIAL-1",
            "name": "Kitchen",
            "model_name": "Linea Mini",
            "connected": True,
        }
    ]


def test_list_things_table_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
) -> None:
    key_file = tmp_path / "key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file)
    write_config(config_file, {"username": "saved-user"})
    monkeypatch.setenv("LMCTL_PASSWORD", "pass")
    fake_cloud.things = [
        FakeThing("SERIAL-1", "Kitchen", "Linea Mini", True),
        FakeThing("SERIAL-2", None, None, False),
    ]

    run(cli.list_things(args_for(tmp_path, key_file=key_file, config_file=config_file)))

    output = capsys.readouterr().out
    assert "serial    name     model       connected" in output
    assert "SERIAL-1  Kitchen  Linea Mini  True" in output
    assert "SERIAL-2                       False" in output


def test_show_machine_fetches_and_prints_combined_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
    fake_machine: type[FakeMachine],
) -> None:
    key_file = tmp_path / "key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file)
    write_config(config_file, {"username": "saved-user", "default_serial": "DEFAULT"})
    monkeypatch.setenv("LMCTL_PASSWORD", "pass")

    run(cli.show_machine(args_for(tmp_path, key_file=key_file, config_file=config_file)))

    machine = fake_machine.instances[0]
    assert machine.serial_number == "DEFAULT"
    assert machine.calls == ["firmware", "dashboard", "settings", "statistics", "schedule"]
    output = capsys.readouterr().out
    assert "serial_number  DEFAULT" in output
    assert "dashboard\nfield" in output
    assert "settings\nfield" in output
    assert "statistics\nfield" in output
    assert "schedule\nfield" in output
    assert "firmware\nfield" in output
    assert "version  1.2.3" in output


def test_show_machine_prints_json_when_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
    fake_machine: type[FakeMachine],
) -> None:
    key_file = tmp_path / "key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file)
    write_config(config_file, {"username": "saved-user", "default_serial": "DEFAULT"})
    monkeypatch.setenv("LMCTL_PASSWORD", "pass")

    run(
        cli.show_machine(
            args_for(tmp_path, key_file=key_file, config_file=config_file, json=True)
        )
    )

    assert read_output_json(capsys) == {
        "serial_number": "DEFAULT",
        "dashboard": {"resource": "dashboard", "serial": "DEFAULT"},
        "settings": {"resource": "settings", "serial": "DEFAULT"},
        "statistics": {"resource": "statistics", "serial": "DEFAULT"},
        "schedule": {"resource": "schedule", "serial": "DEFAULT"},
        "firmware": {"serial": "DEFAULT", "version": "1.2.3"},
    }


@pytest.mark.parametrize(
    ("data_name", "expected_calls", "expected_payload"),
    [
        ("dashboard", ["dashboard"], {"resource": "dashboard", "serial": "SERIAL"}),
        ("settings", ["settings"], {"resource": "settings", "serial": "SERIAL"}),
        ("statistics", ["statistics"], {"resource": "statistics", "serial": "SERIAL"}),
        ("schedule", ["schedule"], {"resource": "schedule", "serial": "SERIAL"}),
        ("firmware", ["firmware"], {"serial": "SERIAL", "version": "1.2.3"}),
    ],
)
def test_fetch_machine_data_prints_each_resource(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
    fake_machine: type[FakeMachine],
    data_name: str,
    expected_calls: list[str],
    expected_payload: dict[str, Any],
) -> None:
    key_file = tmp_path / "key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file)
    write_config(config_file, {"username": "saved-user"})
    monkeypatch.setenv("LMCTL_PASSWORD", "pass")

    run(
        cli.fetch_machine_data(
            args_for(
                tmp_path,
                key_file=key_file,
                config_file=config_file,
                serial="SERIAL",
                data_name=data_name,
            )
        )
    )

    assert fake_machine.instances[0].calls == expected_calls
    output = capsys.readouterr().out
    assert output.startswith(f"{data_name}\n")
    for key, value in expected_payload.items():
        assert str(key) in output
        assert str(value) in output


def test_fetch_data_resource_rejects_unknown_resource() -> None:
    with pytest.raises(cli.CliError, match="unknown data resource: unknown"):
        run(cli.fetch_data_resource(FakeMachine("SERIAL", object()), "unknown"))


def test_register_calls_cloud_client_and_prints_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
) -> None:
    key_file = tmp_path / "key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file)
    write_config(config_file, {"username": "saved-user"})
    monkeypatch.setenv("LMCTL_PASSWORD", "pass")

    run(cli.register(args_for(tmp_path, key_file=key_file, config_file=config_file)))

    assert fake_cloud.instances[0].register_calls == 1
    assert capsys.readouterr().out == (
        f"Registered installation key {key_file.resolve()}.\n"
    )


def test_generate_key_writes_loadable_key_and_refuses_existing_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    key_file = tmp_path / "generated.json"
    cli.generate_key(
        args_for(tmp_path, output=key_file, installation_id="generated-id", force=False)
    )

    assert cli.load_installation_key(key_file).installation_id == "generated-id"
    assert capsys.readouterr().out == (
        f"Generated installation key generated-id at {key_file.resolve()}.\n"
    )
    with pytest.raises(cli.CliError, match="already exists"):
        cli.generate_key(
            args_for(tmp_path, output=key_file, installation_id="second-id", force=False)
        )

    cli.generate_key(
        args_for(tmp_path, output=key_file, installation_id="forced-id", force=True)
    )

    assert cli.load_installation_key(key_file).installation_id == "forced-id"


def test_ensure_and_load_installation_key_paths(tmp_path: Path) -> None:
    key_file = tmp_path / "nested" / "installation_key.json"

    created_key, generated = cli.ensure_installation_key(key_file)
    loaded_key, loaded_generated = cli.ensure_installation_key(key_file)

    assert generated is True
    assert loaded_generated is False
    assert key_file.exists()
    assert loaded_key.installation_id == created_key.installation_id
    assert cli.load_installation_key(key_file).installation_id == created_key.installation_id
    with pytest.raises(cli.CliError, match="does not exist"):
        cli.load_installation_key(tmp_path / "missing.json")

    invalid_key_file = tmp_path / "invalid.json"
    invalid_key_file.write_text("not json", encoding="utf-8")
    with pytest.raises(cli.CliError, match="not a valid installation key"):
        cli.load_installation_key(invalid_key_file)


def test_set_power_and_set_steam_print_success_and_map_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
    fake_machine: type[FakeMachine],
) -> None:
    key_file = tmp_path / "key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file)
    write_config(config_file, {"username": "saved-user", "default_serial": "DEFAULT"})
    monkeypatch.setenv("LMCTL_PASSWORD", "pass")

    run(
        cli.set_power(
            args_for(
                tmp_path,
                key_file=key_file,
                config_file=config_file,
                state="on",
            )
        )
    )

    assert fake_machine.instances[-1].serial_number == "DEFAULT"
    assert fake_machine.instances[-1].calls == [("power", True)]
    assert capsys.readouterr().out == "Power set to on for DEFAULT.\n"

    run(
        cli.set_power(
            args_for(
                tmp_path,
                key_file=key_file,
                config_file=config_file,
                state="off",
                json=True,
            )
        )
    )

    assert read_output_json(capsys) == {
        "serial": "DEFAULT",
        "command": "power",
        "state": "off",
        "success": True,
    }

    run(
        cli.set_steam(
            args_for(
                tmp_path,
                key_file=key_file,
                config_file=config_file,
                serial="EXPLICIT",
                state="off",
            )
        )
    )

    assert fake_machine.instances[-1].serial_number == "EXPLICIT"
    assert fake_machine.instances[-1].calls == [("steam", False)]
    assert capsys.readouterr().out == "Steam set to off for EXPLICIT.\n"


def test_run_machine_command_prints_failure_then_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_cloud: type[FakeCloudClient],
    fake_machine: type[FakeMachine],
) -> None:
    key_file = tmp_path / "key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file)
    write_config(config_file, {"username": "saved-user"})
    monkeypatch.setenv("LMCTL_PASSWORD", "pass")
    fake_machine.command_results["power"] = False
    args = args_for(tmp_path, key_file=key_file, config_file=config_file)

    with pytest.raises(cli.CliError, match="power command did not succeed"):
        run(
            cli.run_machine_command(
                "SERIAL",
                "power",
                "off",
                lambda machine: machine.set_power(False),
                args,
            )
        )

    assert fake_machine.instances[-1].calls == [("power", False)]
    assert capsys.readouterr().out == ""


def test_cloud_client_resolves_credentials_key_and_closes_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_cloud: type[FakeCloudClient],
) -> None:
    key_file = tmp_path / "key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file, "cloud-context-key")
    write_config(config_file, {"username": "config-user"})
    monkeypatch.setenv("LMCTL_PASSWORD", "env-pass")
    args = args_for(tmp_path, key_file=key_file, config_file=config_file)

    async def exercise_context() -> FakeCloudClient:
        async with cli.cloud_client(args) as client:
            assert isinstance(client, FakeCloudClient)
            assert FakeSession.instances[0].closed is False
            return client

    client = run(exercise_context())

    assert client.username == "config-user"
    assert client.password == "env-pass"
    assert client.installation_key.installation_id == "cloud-context-key"
    assert client.client is FakeSession.instances[0]
    assert FakeSession.instances[0].closed is True


def test_cloud_client_uses_saved_password_when_no_arg_or_env(
    tmp_path: Path,
    fake_cloud: type[FakeCloudClient],
    fake_keyring: dict[tuple[str, str], str],
) -> None:
    key_file = tmp_path / "key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file, "cloud-context-key")
    write_config(config_file, {"username": "config-user"})
    fake_keyring[(cli.KEYRING_SERVICE, "config-user")] = "saved-pass"
    args = args_for(tmp_path, key_file=key_file, config_file=config_file)

    async def exercise_context() -> Any:
        async with cli.cloud_client(args) as client:
            return client

    client = run(exercise_context())

    assert client.username == "config-user"
    assert client.password == "saved-pass"


def test_password_commands_manage_keychain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fake_keyring: dict[tuple[str, str], str],
) -> None:
    config_file = tmp_path / "config.json"
    write_config(config_file, {"username": "config-user"})
    monkeypatch.setenv("LMCTL_PASSWORD", "env-pass")

    cli.save_password(args_for(tmp_path, config_file=config_file))

    assert fake_keyring[(cli.KEYRING_SERVICE, "config-user")] == "env-pass"
    assert capsys.readouterr().out == (
        f"Saved password for config-user in keychain service {cli.KEYRING_SERVICE}.\n"
    )

    cli.password_status(args_for(tmp_path, config_file=config_file))
    assert capsys.readouterr().out == (
        f"Password saved for config-user in keychain service {cli.KEYRING_SERVICE}.\n"
    )

    cli.forget_password(args_for(tmp_path, config_file=config_file))
    assert (cli.KEYRING_SERVICE, "config-user") not in fake_keyring
    assert capsys.readouterr().out == (
        f"Deleted saved password for config-user from keychain service "
        f"{cli.KEYRING_SERVICE}.\n"
    )

    cli.forget_password(args_for(tmp_path, config_file=config_file))
    assert capsys.readouterr().out == (
        f"No saved password for config-user in keychain service {cli.KEYRING_SERVICE}.\n"
    )


@pytest.mark.parametrize(
    ("func", "message"),
    [
        (cli.save_password, "cannot save password"),
        (cli.password_status, "cannot read password status"),
        (cli.forget_password, "cannot forget password"),
    ],
)
def test_password_commands_reject_no_keyring(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    func: Any,
    message: str,
) -> None:
    config_file = tmp_path / "config.json"
    write_config(config_file, {"username": "config-user"})
    monkeypatch.setenv("LMCTL_PASSWORD", "env-pass")

    with pytest.raises(cli.CliError, match=message):
        func(args_for(tmp_path, config_file=config_file, no_keyring=True))
