"""Public CLI entry point for lmctl."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from aiohttp import ClientError
from pylamarzocco.exceptions import LaMarzoccoError

from ._client import cloud_client
from ._commands import (
    MachineDataResource,
    clear_default_serial,
    fetch_data_resource,
    fetch_machine_data,
    forget_password,
    generate_key,
    list_things,
    login,
    password_status,
    register,
    run_machine_command,
    save_password,
    set_default_serial,
    set_power,
    set_steam,
    show_config,
    show_machine,
    switch_machine,
)
from ._config import (
    default_config_file,
    default_key_file,
    expand_path,
    load_config,
    resolve_serial,
    resolve_stateful_command,
    save_config,
)
from ._constants import (
    APP_NAME,
    DEFAULT_SERIAL_KEY,
    KEYRING_SERVICE,
    PASSWORD_ENV_VARS,
    USERNAME_ENV_VARS,
    USERNAME_KEY,
)
from ._credentials import (
    KeyringError,
    credential,
    delete_saved_password,
    get_saved_password,
    getpass,
    keyring,
    keyring_disabled,
    password_credential,
    set_saved_password,
    sys,
    try_set_login_password,
)
from ._errors import CliError
from ._keys import ensure_installation_key, load_installation_key
from ._mcp import (
    McpServerConfig,
    create_mcp_server,
    is_loopback_host,
    parse_mcp_url,
    run_mcp_server,
)
from ._output import (
    display_value,
    flatten_key_values,
    json_text,
    print_json,
    print_key_values,
    print_machine_sections,
    print_table,
    to_jsonable,
    wants_json,
)
from ._parser import (
    add_json_argument,
    add_serial_argument,
    add_stateful_command_arguments,
    add_water_calibration_arguments,
    add_water_state_argument,
    build_parser,
)
from ._selector import (
    choose_thing,
    describe_thing,
    read_key,
    render_selector,
    select_option,
)
from ._water import (
    EXPERIMENTAL_WARNING,
    WATER_STATE_VERSION,
    calibration_from_args,
    counter_totals,
    estimate_water,
    fetch_water_inputs,
    format_ml,
    load_water_state,
    log_water_use,
    log_water_use_payload,
    no_water_alarm,
    refill_water,
    refill_water_payload,
    resolve_water_state_file,
    water_estimate_payload,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        result = args.func(args)
        if asyncio.iscoroutine(result):
            asyncio.run(result)
    except (CliError, LaMarzoccoError, ClientError, OSError) as exc:
        parser.exit(1, f"{APP_NAME}: error: {exc}\n")

    return 0


__all__ = [
    "APP_NAME",
    "DEFAULT_SERIAL_KEY",
    "KEYRING_SERVICE",
    "KeyringError",
    "MachineDataResource",
    "McpServerConfig",
    "PASSWORD_ENV_VARS",
    "USERNAME_ENV_VARS",
    "USERNAME_KEY",
    "CliError",
    "add_serial_argument",
    "add_json_argument",
    "add_stateful_command_arguments",
    "add_water_calibration_arguments",
    "add_water_state_argument",
    "build_parser",
    "calibration_from_args",
    "choose_thing",
    "clear_default_serial",
    "cloud_client",
    "credential",
    "create_mcp_server",
    "counter_totals",
    "default_config_file",
    "default_key_file",
    "delete_saved_password",
    "describe_thing",
    "display_value",
    "ensure_installation_key",
    "estimate_water",
    "EXPERIMENTAL_WARNING",
    "expand_path",
    "fetch_data_resource",
    "fetch_machine_data",
    "fetch_water_inputs",
    "flatten_key_values",
    "forget_password",
    "format_ml",
    "generate_key",
    "get_saved_password",
    "getpass",
    "json_text",
    "is_loopback_host",
    "keyring",
    "keyring_disabled",
    "list_things",
    "load_config",
    "load_installation_key",
    "load_water_state",
    "login",
    "log_water_use",
    "log_water_use_payload",
    "main",
    "no_water_alarm",
    "password_credential",
    "password_status",
    "parse_mcp_url",
    "print_json",
    "print_key_values",
    "print_machine_sections",
    "print_table",
    "read_key",
    "refill_water",
    "refill_water_payload",
    "register",
    "render_selector",
    "resolve_serial",
    "resolve_stateful_command",
    "resolve_water_state_file",
    "run_machine_command",
    "run_mcp_server",
    "save_config",
    "save_password",
    "select_option",
    "set_default_serial",
    "set_power",
    "set_saved_password",
    "set_steam",
    "show_config",
    "show_machine",
    "switch_machine",
    "sys",
    "to_jsonable",
    "try_set_login_password",
    "water_estimate_payload",
    "WATER_STATE_VERSION",
    "wants_json",
]
