"""MCP server support for agent integrations."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Awaitable, Callable
from contextlib import redirect_stdout
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from aiohttp import ClientError
from pylamarzocco import LaMarzoccoMachine
from pylamarzocco.exceptions import LaMarzoccoError

from ._client import cloud_client
from ._commands import fetch_data_resource
from ._config import resolve_serial
from ._constants import APP_NAME
from ._errors import CliError
from ._output import to_jsonable
from . import _water

MCP_DEFAULT_HOST = "127.0.0.1"
MCP_DEFAULT_PORT = 8000
MCP_DEFAULT_PATH = "/mcp"


@dataclass(frozen=True)
class McpServerConfig:
    """Resolved MCP server transport configuration."""

    transport: Literal["stdio", "streamable-http"]
    host: str = MCP_DEFAULT_HOST
    port: int = MCP_DEFAULT_PORT
    path: str = MCP_DEFAULT_PATH

    @property
    def endpoint(self) -> str:
        """Return the local HTTP endpoint for streamable HTTP mode."""
        return f"http://{self.host}:{self.port}{self.path}"


def parse_mcp_url(value: str | None, *, allow_remote: bool = False) -> McpServerConfig:
    """Parse an optional MCP URL into a server configuration."""
    if value is None or value == "" or value == "stdio":
        return McpServerConfig(transport="stdio")

    raw_url = value if "://" in value else f"http://{value}"
    parsed = urlparse(raw_url)
    if parsed.scheme != "http":
        raise CliError("MCP HTTP mode serves plain HTTP; use an http:// URL")
    if parsed.params or parsed.query or parsed.fragment:
        raise CliError("MCP URL must not include params, query, or fragment")

    host = parsed.hostname or MCP_DEFAULT_HOST
    try:
        port = parsed.port or MCP_DEFAULT_PORT
    except ValueError as exc:
        raise CliError(f"invalid MCP URL port: {exc}") from exc
    path = parsed.path if parsed.path not in {"", "/"} else MCP_DEFAULT_PATH
    if not path.startswith("/"):
        path = f"/{path}"

    if not allow_remote and not is_loopback_host(host):
        raise CliError(
            "refusing to bind MCP server to a non-loopback host; pass "
            "--allow-remote only if you understand this exposes machine control"
        )

    return McpServerConfig(
        transport="streamable-http",
        host=host,
        port=port,
        path=path,
    )


def is_loopback_host(host: str) -> bool:
    """Return whether a host is loopback-only."""
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def create_mcp_server(
    args: argparse.Namespace, config: McpServerConfig | None = None
) -> Any:
    """Create the FastMCP server with lmctl tools registered."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise CliError(
            "MCP support requires the `mcp` package to be installed"
        ) from exc

    resolved_config = config or parse_mcp_url(
        args.url,
        allow_remote=getattr(args, "allow_remote", False),
    )
    server = FastMCP(
        APP_NAME,
        instructions=(
            "Control La Marzocco Home machines. Omit serial to use the lmctl "
            "configured default machine."
        ),
        host=resolved_config.host,
        port=resolved_config.port,
        streamable_http_path=resolved_config.path,
    )

    @server.tool(
        name="list_machines",
        description="List La Marzocco machines available to the account.",
    )
    async def list_machines() -> list[dict[str, Any]]:
        return await call_mcp_tool(lambda: list_machines_payload(args))

    @server.tool(
        name="get_machine",
        description=(
            "Fetch dashboard, settings, statistics, schedule, and firmware for a "
            "machine. Omit serial to use the configured default."
        ),
    )
    async def get_machine(serial: str | None = None) -> dict[str, Any]:
        return await call_mcp_tool(lambda: machine_payload(args, serial))

    @server.tool(
        name="get_dashboard",
        description="Fetch a machine dashboard. Omit serial to use the configured default.",
    )
    async def get_dashboard(serial: str | None = None) -> Any:
        return await call_mcp_tool(
            lambda: machine_data_payload(args, "dashboard", serial)
        )

    @server.tool(
        name="get_settings",
        description="Fetch machine settings. Omit serial to use the configured default.",
    )
    async def get_settings(serial: str | None = None) -> Any:
        return await call_mcp_tool(
            lambda: machine_data_payload(args, "settings", serial)
        )

    @server.tool(
        name="get_statistics",
        description="Fetch machine statistics. Omit serial to use the configured default.",
    )
    async def get_statistics(serial: str | None = None) -> Any:
        return await call_mcp_tool(
            lambda: machine_data_payload(args, "statistics", serial)
        )

    @server.tool(
        name="get_schedule",
        description="Fetch a machine schedule. Omit serial to use the configured default.",
    )
    async def get_schedule(serial: str | None = None) -> Any:
        return await call_mcp_tool(
            lambda: machine_data_payload(args, "schedule", serial)
        )

    @server.tool(
        name="get_firmware",
        description="Fetch machine firmware. Omit serial to use the configured default.",
    )
    async def get_firmware(serial: str | None = None) -> Any:
        return await call_mcp_tool(
            lambda: machine_data_payload(args, "firmware", serial)
        )

    @server.tool(
        name="set_power",
        description=(
            "Turn machine power on or off. This changes physical machine state. "
            "Omit serial to use the configured default."
        ),
    )
    async def set_power(
        state: Literal["on", "off"], serial: str | None = None
    ) -> dict[str, Any]:
        return await call_mcp_tool(
            lambda: set_machine_state(args, "power", state, serial)
        )

    @server.tool(
        name="set_steam",
        description=(
            "Turn machine steam on or off. This changes physical machine state. "
            "Omit serial to use the configured default."
        ),
    )
    async def set_steam(
        state: Literal["on", "off"], serial: str | None = None
    ) -> dict[str, Any]:
        return await call_mcp_tool(
            lambda: set_machine_state(args, "steam", state, serial)
        )

    @server.tool(
        name="get_water_estimate",
        description=(
            "EXPERIMENTAL: estimate remaining reservoir water from coffee and flush "
            "counters. This is not a continuous tank sensor reading. Omit serial to "
            "use the configured default."
        ),
    )
    async def get_water_estimate(
        serial: str | None = None,
        extra_ml: float = 0.0,
        tank_ml: float | None = None,
        reserve_ml: float | None = None,
        shot_ml: float | None = None,
        flush_ml: float | None = None,
        state_file: str | None = None,
    ) -> dict[str, Any]:
        return await call_mcp_tool(
            lambda: get_water_estimate_payload(
                args,
                serial=serial,
                extra_ml=extra_ml,
                tank_ml=tank_ml,
                reserve_ml=reserve_ml,
                shot_ml=shot_ml,
                flush_ml=flush_ml,
                state_file=state_file,
            )
        )

    @server.tool(
        name="mark_water_refill",
        description=(
            "EXPERIMENTAL: mark the reservoir as full and reset the water-estimate "
            "baseline. This writes local lmctl water state. Omit serial to use the "
            "configured default."
        ),
    )
    async def mark_water_refill(
        serial: str | None = None,
        tank_ml: float | None = None,
        reserve_ml: float | None = None,
        shot_ml: float | None = None,
        flush_ml: float | None = None,
        state_file: str | None = None,
    ) -> dict[str, Any]:
        return await call_mcp_tool(
            lambda: mark_water_refill_payload(
                args,
                serial=serial,
                tank_ml=tank_ml,
                reserve_ml=reserve_ml,
                shot_ml=shot_ml,
                flush_ml=flush_ml,
                state_file=state_file,
            )
        )

    @server.tool(
        name="log_water_use",
        description=(
            "EXPERIMENTAL: log untracked reservoir water use, such as steaming, so "
            "future estimates subtract it. Omit serial to use the configured default."
        ),
    )
    async def log_water_use(
        amount_ml: float,
        note: str | None = None,
        serial: str | None = None,
        state_file: str | None = None,
    ) -> dict[str, Any]:
        return await call_mcp_tool(
            lambda: log_water_use_payload(
                args,
                amount_ml=amount_ml,
                note=note,
                serial=serial,
                state_file=state_file,
            )
        )

    return server


def run_mcp_server(args: argparse.Namespace) -> None:
    """Run lmctl as an MCP server."""
    config = parse_mcp_url(
        args.url,
        allow_remote=getattr(args, "allow_remote", False),
    )
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    server = create_mcp_server(args, config)

    if config.transport == "streamable-http":
        if not is_loopback_host(config.host):
            print(
                "lmctl: warning: MCP HTTP server can control physical machine state "
                f"and is listening on {config.host}",
                file=sys.stderr,
            )
        print(f"lmctl: MCP server listening on {config.endpoint}", file=sys.stderr)

    server.run(transport=config.transport)


async def call_mcp_tool(callback: Callable[[], Awaitable[Any]]) -> Any:
    """Run an MCP tool body without leaking accidental prints to stdout."""
    try:
        with redirect_stdout(sys.stderr):
            return await callback()
    except (CliError, LaMarzoccoError, ClientError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc


def tool_args(
    base_args: argparse.Namespace, serial: str | None = None
) -> argparse.Namespace:
    """Build non-interactive args for MCP tool calls."""
    return argparse.Namespace(
        username=base_args.username,
        password=base_args.password,
        key_file=base_args.key_file,
        config_file=base_args.config_file,
        serial=serial,
        no_keyring=base_args.no_keyring,
        no_prompt=True,
    )


def water_tool_args(
    base_args: argparse.Namespace,
    *,
    serial: str | None = None,
    state_file: str | None = None,
    tank_ml: float | None = None,
    reserve_ml: float | None = None,
    shot_ml: float | None = None,
    flush_ml: float | None = None,
    extra_ml: float = 0.0,
    amount_ml: float | None = None,
    note: str | None = None,
) -> argparse.Namespace:
    """Build args for experimental water estimator MCP tool calls."""
    args = tool_args(base_args, serial)
    args.json = True
    args.state_file = Path(state_file).expanduser() if state_file else None
    args.tank_ml = tank_ml
    args.reserve_ml = reserve_ml
    args.shot_ml = shot_ml
    args.flush_ml = flush_ml
    args.extra_ml = extra_ml
    args.amount_ml = amount_ml
    args.note = note
    return args


async def list_machines_payload(base_args: argparse.Namespace) -> list[dict[str, Any]]:
    """Return account machines as JSON-compatible dictionaries."""
    async with cloud_client(tool_args(base_args)) as client:
        things = await client.list_things()
    return to_jsonable(things)


async def machine_payload(
    base_args: argparse.Namespace,
    serial: str | None,
) -> dict[str, Any]:
    """Return a combined machine payload."""
    args = tool_args(base_args, serial)
    resolved_serial = resolve_serial(args)
    async with cloud_client(args) as client:
        machine = LaMarzoccoMachine(resolved_serial, client)
        firmware = await machine.get_firmware()
        await machine.get_dashboard()
        await machine.get_settings()
        await machine.get_statistics()
        await machine.get_schedule()

    return to_jsonable(
        {
            **machine.to_dict(),
            "schedule": machine.schedule,
            "firmware": firmware,
        }
    )


async def machine_data_payload(
    base_args: argparse.Namespace,
    data_name: str,
    serial: str | None,
) -> Any:
    """Return one machine data resource."""
    args = tool_args(base_args, serial)
    resolved_serial = resolve_serial(args)
    async with cloud_client(args) as client:
        machine = LaMarzoccoMachine(resolved_serial, client)
        data = await fetch_data_resource(machine, data_name)
    return to_jsonable(data)


async def set_machine_state(
    base_args: argparse.Namespace,
    command: Literal["power", "steam"],
    state: Literal["on", "off"],
    serial: str | None,
) -> dict[str, Any]:
    """Set one machine state."""
    args = tool_args(base_args, serial)
    resolved_serial = resolve_serial(args)
    async with cloud_client(args) as client:
        machine = LaMarzoccoMachine(resolved_serial, client)
        if command == "power":
            success = await machine.set_power(state == "on")
        else:
            success = await machine.set_steam(state == "on")

    if not success:
        raise CliError(f"{command} command did not succeed")

    return {
        "serial": resolved_serial,
        "command": command,
        "state": state,
        "success": success,
    }


async def get_water_estimate_payload(
    base_args: argparse.Namespace,
    *,
    serial: str | None,
    extra_ml: float,
    tank_ml: float | None,
    reserve_ml: float | None,
    shot_ml: float | None,
    flush_ml: float | None,
    state_file: str | None,
) -> dict[str, Any]:
    """Return an experimental reservoir water estimate."""
    args = water_tool_args(
        base_args,
        serial=serial,
        extra_ml=extra_ml,
        tank_ml=tank_ml,
        reserve_ml=reserve_ml,
        shot_ml=shot_ml,
        flush_ml=flush_ml,
        state_file=state_file,
    )
    return await _water.water_estimate_payload(args)


async def mark_water_refill_payload(
    base_args: argparse.Namespace,
    *,
    serial: str | None,
    tank_ml: float | None,
    reserve_ml: float | None,
    shot_ml: float | None,
    flush_ml: float | None,
    state_file: str | None,
) -> dict[str, Any]:
    """Mark the reservoir as full for experimental water estimates."""
    args = water_tool_args(
        base_args,
        serial=serial,
        tank_ml=tank_ml,
        reserve_ml=reserve_ml,
        shot_ml=shot_ml,
        flush_ml=flush_ml,
        state_file=state_file,
    )
    return await _water.refill_water_payload(args)


async def log_water_use_payload(
    base_args: argparse.Namespace,
    *,
    amount_ml: float,
    note: str | None,
    serial: str | None,
    state_file: str | None,
) -> dict[str, Any]:
    """Log untracked water usage for experimental water estimates."""
    args = water_tool_args(
        base_args,
        serial=serial,
        amount_ml=amount_ml,
        note=note,
        state_file=state_file,
    )
    return _water.log_water_use_payload(args)


__all__ = [
    "MCP_DEFAULT_HOST",
    "MCP_DEFAULT_PATH",
    "MCP_DEFAULT_PORT",
    "McpServerConfig",
    "create_mcp_server",
    "get_water_estimate_payload",
    "is_loopback_host",
    "list_machines_payload",
    "log_water_use_payload",
    "machine_data_payload",
    "machine_payload",
    "mark_water_refill_payload",
    "parse_mcp_url",
    "run_mcp_server",
    "set_machine_state",
    "tool_args",
    "water_tool_args",
]
