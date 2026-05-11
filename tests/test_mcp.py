from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

import pytest
from pylamarzocco.util import generate_installation_key

from lmctl import _client as client_module
from lmctl import _mcp
from lmctl import cli


class FakeSession:
    instances: list[FakeSession] = []

    def __init__(self) -> None:
        self.closed = False
        FakeSession.instances.append(self)

    async def close(self) -> None:
        self.closed = True


class FakeThing:
    def __init__(self, serial_number: str, name: str | None = None) -> None:
        self.serial_number = serial_number
        self.name = name
        self.model_name = "Linea Micra"
        self.connected = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "serial_number": self.serial_number,
            "name": self.name,
            "model_name": self.model_name,
            "connected": self.connected,
        }


class FakeCloudClient:
    things = [FakeThing("DEFAULT", "Kitchen")]

    def __init__(
        self,
        *,
        username: str,
        password: str,
        installation_key: Any,
        client: FakeSession,
    ) -> None:
        self.username = username
        self.password = password
        self.installation_key = installation_key
        self.client = client

    async def list_things(self) -> list[FakeThing]:
        return self.things


class FakeMachine:
    def __init__(
        self, serial_number: str, cloud_client: FakeCloudClient | object
    ) -> None:
        self.serial_number = serial_number
        self.cloud_client = cloud_client
        self.dashboard: dict[str, Any] | None = None
        self.settings: dict[str, Any] | None = None
        self.statistics: dict[str, Any] | None = None
        self.schedule: dict[str, Any] | None = None

    async def get_firmware(self) -> dict[str, Any]:
        return {"serial": self.serial_number, "version": "1.2.3"}

    async def get_dashboard(self) -> None:
        self.dashboard = {"resource": "dashboard", "serial": self.serial_number}

    async def get_settings(self) -> None:
        self.settings = {"resource": "settings", "serial": self.serial_number}

    async def get_statistics(self) -> None:
        self.statistics = {"resource": "statistics", "serial": self.serial_number}

    async def get_schedule(self) -> None:
        self.schedule = {"resource": "schedule", "serial": self.serial_number}

    async def set_power(self, enabled: bool) -> bool:
        return enabled

    async def set_steam(self, enabled: bool) -> bool:
        return enabled

    def to_dict(self) -> dict[str, Any]:
        return {
            "serial_number": self.serial_number,
            "dashboard": self.dashboard,
            "settings": self.settings,
            "statistics": self.statistics,
        }


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def write_key(path: Path) -> None:
    key = generate_installation_key("mcp-test-key")
    path.write_text(cli.json_text(key.to_json()), encoding="utf-8")


def write_config(path: Path) -> None:
    path.write_text(
        '{"username": "config-user", "default_serial": "DEFAULT"}',
        encoding="utf-8",
    )


@pytest.fixture
def mcp_args(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> argparse.Namespace:
    key_file = tmp_path / "key.json"
    config_file = tmp_path / "config.json"
    write_key(key_file)
    write_config(config_file)
    monkeypatch.setenv("LMCTL_PASSWORD", "env-pass")
    return argparse.Namespace(
        username=None,
        password=None,
        key_file=key_file,
        config_file=config_file,
        no_keyring=False,
        url="stdio",
        allow_remote=False,
    )


@pytest.fixture(autouse=True)
def fake_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSession.instances = []
    monkeypatch.setattr(client_module, "ClientSession", FakeSession)
    monkeypatch.setattr(client_module, "LaMarzoccoCloudClient", FakeCloudClient)
    monkeypatch.setattr(_mcp, "LaMarzoccoMachine", FakeMachine)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, _mcp.McpServerConfig(transport="stdio")),
        ("stdio", _mcp.McpServerConfig(transport="stdio")),
        (
            "http://127.0.0.1:9000/custom",
            _mcp.McpServerConfig(
                transport="streamable-http",
                host="127.0.0.1",
                port=9000,
                path="/custom",
            ),
        ),
        (
            "localhost:9001",
            _mcp.McpServerConfig(
                transport="streamable-http",
                host="localhost",
                port=9001,
                path="/mcp",
            ),
        ),
    ],
)
def test_parse_mcp_url(value: str | None, expected: _mcp.McpServerConfig) -> None:
    assert _mcp.parse_mcp_url(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1:9000/mcp",
        "http://127.0.0.1:9000/mcp?token=secret",
        "http://0.0.0.0:9000/mcp",
    ],
)
def test_parse_mcp_url_rejects_unsafe_or_unsupported_urls(value: str) -> None:
    with pytest.raises(cli.CliError):
        _mcp.parse_mcp_url(value)


def test_parse_mcp_url_can_allow_remote_bind() -> None:
    assert _mcp.parse_mcp_url(
        "http://0.0.0.0:9000/mcp",
        allow_remote=True,
    ) == _mcp.McpServerConfig(
        transport="streamable-http",
        host="0.0.0.0",
        port=9000,
        path="/mcp",
    )


def test_create_mcp_server_registers_expected_tools(
    mcp_args: argparse.Namespace,
) -> None:
    server = _mcp.create_mcp_server(mcp_args)

    tool_names = {tool.name for tool in run(server.list_tools())}

    assert tool_names == {
        "get_dashboard",
        "get_firmware",
        "get_machine",
        "get_schedule",
        "get_settings",
        "get_statistics",
        "list_machines",
        "set_power",
        "set_steam",
    }


def test_mcp_payloads_use_default_serial_and_close_session(
    mcp_args: argparse.Namespace,
) -> None:
    payload = run(_mcp.machine_payload(mcp_args, None))

    assert payload["serial_number"] == "DEFAULT"
    assert payload["dashboard"] == {"resource": "dashboard", "serial": "DEFAULT"}
    assert payload["firmware"] == {"serial": "DEFAULT", "version": "1.2.3"}
    assert FakeSession.instances[-1].closed is True


def test_mcp_state_tool_can_override_serial(mcp_args: argparse.Namespace) -> None:
    payload = run(_mcp.set_machine_state(mcp_args, "power", "on", "EXPLICIT"))

    assert payload == {
        "serial": "EXPLICIT",
        "command": "power",
        "state": "on",
        "success": True,
    }


def test_call_mcp_tool_redirects_accidental_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    async def callback() -> dict[str, bool]:
        print("debug print")
        return {"ok": True}

    assert run(_mcp.call_mcp_tool(callback)) == {"ok": True}
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "debug print\n"


def test_tool_args_disable_interactive_prompts(mcp_args: argparse.Namespace) -> None:
    tool_args = _mcp.tool_args(mcp_args)

    assert tool_args.no_prompt is True
