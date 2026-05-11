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
    build_parser,
)
from ._selector import (
    choose_thing,
    describe_thing,
    read_key,
    render_selector,
    select_option,
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
    "PASSWORD_ENV_VARS",
    "USERNAME_ENV_VARS",
    "USERNAME_KEY",
    "CliError",
    "add_serial_argument",
    "add_json_argument",
    "add_stateful_command_arguments",
    "build_parser",
    "choose_thing",
    "clear_default_serial",
    "cloud_client",
    "credential",
    "default_config_file",
    "default_key_file",
    "delete_saved_password",
    "describe_thing",
    "display_value",
    "ensure_installation_key",
    "expand_path",
    "fetch_data_resource",
    "fetch_machine_data",
    "flatten_key_values",
    "forget_password",
    "generate_key",
    "get_saved_password",
    "getpass",
    "json_text",
    "keyring",
    "keyring_disabled",
    "list_things",
    "load_config",
    "load_installation_key",
    "login",
    "main",
    "password_credential",
    "password_status",
    "print_json",
    "print_key_values",
    "print_machine_sections",
    "print_table",
    "read_key",
    "register",
    "render_selector",
    "resolve_serial",
    "resolve_stateful_command",
    "run_machine_command",
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
    "wants_json",
]
