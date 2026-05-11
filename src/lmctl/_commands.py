"""Command implementations for lmctl."""

from __future__ import annotations

import argparse
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from aiohttp import ClientSession
from pylamarzocco import LaMarzoccoCloudClient, LaMarzoccoMachine
from pylamarzocco.util import generate_installation_key

from ._client import cloud_client
from ._config import expand_path, load_config, resolve_serial, save_config
from ._constants import (
    DEFAULT_SERIAL_KEY,
    KEYRING_SERVICE,
    USERNAME_ENV_VARS,
    USERNAME_KEY,
)
from ._credentials import (
    credential,
    delete_saved_password,
    keyring_disabled,
    password_credential,
    set_saved_password,
    try_set_login_password,
)
from ._errors import CliError
from ._keys import ensure_installation_key
from ._output import (
    json_text,
    print_json,
    print_key_values,
    print_machine_sections,
    print_table,
    wants_json,
)
from ._selector import choose_thing, describe_thing


class MachineDataResource(Protocol):
    """Machine methods used by data-fetch commands."""

    dashboard: Any
    settings: Any
    statistics: Any
    schedule: Any

    def get_dashboard(self) -> Awaitable[None]: ...

    def get_settings(self) -> Awaitable[None]: ...

    def get_statistics(self) -> Awaitable[None]: ...

    def get_schedule(self) -> Awaitable[None]: ...

    def get_firmware(self) -> Awaitable[Any]: ...


def show_config(args: argparse.Namespace) -> None:
    """Show the current lmctl configuration."""
    config_file = expand_path(args.config_file)
    config = load_config(config_file)
    payload = {
        "config_file": config_file,
        USERNAME_KEY: config.get(USERNAME_KEY),
        DEFAULT_SERIAL_KEY: config.get(DEFAULT_SERIAL_KEY),
    }
    if wants_json(args):
        print_json(payload)
    else:
        print_key_values(payload)


def set_default_serial(args: argparse.Namespace) -> None:
    """Set the default machine serial number."""
    config_file = expand_path(args.config_file)
    config = load_config(config_file)
    config[DEFAULT_SERIAL_KEY] = args.serial
    save_config(config_file, config)
    payload = {
        "config_file": config_file,
        DEFAULT_SERIAL_KEY: args.serial,
    }
    if wants_json(args):
        print_json(payload)
    else:
        print(f"Default serial set to {args.serial} in {config_file}.")


def clear_default_serial(args: argparse.Namespace) -> None:
    """Clear the default machine serial number."""
    config_file = expand_path(args.config_file)
    config = load_config(config_file)
    config.pop(DEFAULT_SERIAL_KEY, None)
    save_config(config_file, config)
    payload = {
        "config_file": config_file,
        DEFAULT_SERIAL_KEY: None,
    }
    if wants_json(args):
        print_json(payload)
    else:
        print(f"Default serial cleared in {config_file}.")


async def login(args: argparse.Namespace) -> None:
    """Authenticate, choose a machine, and save CLI defaults."""
    key_file = expand_path(args.key_file)
    installation_key, generated_key = ensure_installation_key(key_file)
    username = credential(
        args.username,
        USERNAME_ENV_VARS,
        "username",
        config_file=args.config_file,
        config_key=USERNAME_KEY,
    )
    password = password_credential(args, username)

    async with ClientSession() as session:
        client = LaMarzoccoCloudClient(
            username=username,
            password=password,
            installation_key=installation_key,
            client=session,
        )
        if generated_key:
            await client.async_register_client()
        things = await client.list_things()

    if args.save_password:
        password_saved = try_set_login_password(username, password, args)
    else:
        password_saved = False

    selected = choose_thing(things, args.serial)

    config_file = expand_path(args.config_file)
    config = load_config(config_file)
    config[USERNAME_KEY] = username
    config[DEFAULT_SERIAL_KEY] = selected.serial_number
    save_config(config_file, config)

    payload = {
        "config_file": config_file,
        "key_file": key_file,
        "generated_key": generated_key,
        "password_saved": password_saved,
        USERNAME_KEY: username,
        DEFAULT_SERIAL_KEY: selected.serial_number,
    }
    if wants_json(args):
        print_json(payload)
    else:
        print(f"Logged in as {username}.")
        print(f"Default machine set to {describe_thing(selected)}.")
        if generated_key:
            print(f"Generated installation key at {key_file}.")
        if password_saved:
            print("Saved password to the OS keychain.")
        else:
            print("Password not saved.")


def save_password(args: argparse.Namespace) -> None:
    """Save a password in the OS keychain."""
    if keyring_disabled(args):
        raise CliError("cannot save password when --no-keyring is set")

    username = credential(
        args.username,
        USERNAME_ENV_VARS,
        "username",
        config_file=args.config_file,
        config_key=USERNAME_KEY,
    )
    password = password_credential(args, username, allow_saved=False)
    set_saved_password(username, password, args)
    payload = {
        "service": KEYRING_SERVICE,
        USERNAME_KEY: username,
        "password_saved": True,
    }
    if wants_json(args):
        print_json(payload)
    else:
        print(f"Saved password for {username} in keychain service {KEYRING_SERVICE}.")


def password_status(args: argparse.Namespace) -> None:
    """Show whether a password is saved in the OS keychain."""
    if keyring_disabled(args):
        raise CliError("cannot read password status when --no-keyring is set")

    from ._credentials import get_saved_password

    username = credential(
        args.username,
        USERNAME_ENV_VARS,
        "username",
        config_file=args.config_file,
        config_key=USERNAME_KEY,
    )
    password_saved = get_saved_password(username, args, required=True) is not None
    payload = {
        "service": KEYRING_SERVICE,
        USERNAME_KEY: username,
        "password_saved": password_saved,
    }
    if wants_json(args):
        print_json(payload)
    elif password_saved:
        print(f"Password saved for {username} in keychain service {KEYRING_SERVICE}.")
    else:
        print(f"No password saved for {username} in keychain service {KEYRING_SERVICE}.")


def forget_password(args: argparse.Namespace) -> None:
    """Delete the saved password from the OS keychain."""
    if keyring_disabled(args):
        raise CliError("cannot forget password when --no-keyring is set")

    username = credential(
        args.username,
        USERNAME_ENV_VARS,
        "username",
        config_file=args.config_file,
        config_key=USERNAME_KEY,
    )
    deleted = delete_saved_password(username, args)
    payload = {
        "service": KEYRING_SERVICE,
        USERNAME_KEY: username,
        "password_deleted": deleted,
    }
    if wants_json(args):
        print_json(payload)
    elif deleted:
        print(
            f"Deleted saved password for {username} from keychain service "
            f"{KEYRING_SERVICE}."
        )
    else:
        print(f"No saved password for {username} in keychain service {KEYRING_SERVICE}.")


async def switch_machine(args: argparse.Namespace) -> None:
    """Choose a different default machine."""
    async with cloud_client(args) as client:
        things = await client.list_things()

    selected = choose_thing(things, args.serial, always_select=True)
    config_file = expand_path(args.config_file)
    config = load_config(config_file)
    config[DEFAULT_SERIAL_KEY] = selected.serial_number
    save_config(config_file, config)

    payload = {
        "config_file": config_file,
        DEFAULT_SERIAL_KEY: selected.serial_number,
    }
    if wants_json(args):
        print_json(payload)
    else:
        print(f"Default machine set to {describe_thing(selected)}.")


def generate_key(args: argparse.Namespace) -> None:
    """Generate installation key material."""
    output = expand_path(args.output or args.key_file)
    if output.exists() and not args.force:
        raise CliError(f"{output} already exists; pass --force to overwrite it")

    installation_id = args.installation_id or str(uuid.uuid4()).lower()
    installation_key = generate_installation_key(installation_id)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json_text(installation_key.to_json()), encoding="utf-8")
    payload = {
        "installation_id": installation_id,
        "key_file": str(output),
    }
    if wants_json(args):
        print_json(payload)
    else:
        print(f"Generated installation key {installation_id} at {output}.")


async def register(args: argparse.Namespace) -> None:
    """Register the current installation key."""
    async with cloud_client(args) as client:
        await client.async_register_client()
    payload = {"registered": True, "key_file": str(expand_path(args.key_file))}
    if wants_json(args):
        print_json(payload)
    else:
        print(f"Registered installation key {expand_path(args.key_file)}.")


async def list_things(args: argparse.Namespace) -> None:
    """List account devices."""
    async with cloud_client(args) as client:
        things = await client.list_things()

    if wants_json(args):
        print_json(things)
        return

    rows = [
        (
            thing.serial_number,
            thing.name,
            thing.model_name,
            thing.connected,
        )
        for thing in things
    ]
    print_table(("serial", "name", "model", "connected"), rows)


async def show_machine(args: argparse.Namespace) -> None:
    """Fetch a combined machine snapshot."""
    serial = resolve_serial(args)
    async with cloud_client(args) as client:
        machine = LaMarzoccoMachine(serial, client)
        firmware = await machine.get_firmware()
        await machine.get_dashboard()
        await machine.get_settings()
        await machine.get_statistics()
        await machine.get_schedule()

    payload = {
        **machine.to_dict(),
        "schedule": machine.schedule,
        "firmware": firmware,
    }
    if wants_json(args):
        print_json(payload)
    else:
        print_machine_sections(payload)


async def fetch_machine_data(args: argparse.Namespace) -> None:
    """Fetch one machine data resource."""
    serial = resolve_serial(args)
    async with cloud_client(args) as client:
        machine = LaMarzoccoMachine(serial, client)
        data = await fetch_data_resource(machine, args.data_name)

    if wants_json(args):
        print_json(data)
    else:
        print_key_values(data, title=args.data_name)


async def fetch_data_resource(machine: MachineDataResource, data_name: str) -> Any:
    """Fetch one data resource from a machine."""
    if data_name == "dashboard":
        await machine.get_dashboard()
        return machine.dashboard
    if data_name == "settings":
        await machine.get_settings()
        return machine.settings
    if data_name == "statistics":
        await machine.get_statistics()
        return machine.statistics
    if data_name == "schedule":
        await machine.get_schedule()
        return machine.schedule
    if data_name == "firmware":
        return await machine.get_firmware()

    raise CliError(f"unknown data resource: {data_name}")


async def set_power(args: argparse.Namespace) -> None:
    """Set machine power."""
    from ._config import resolve_stateful_command

    serial, state = resolve_stateful_command(args)
    await run_machine_command(
        serial,
        "power",
        state,
        lambda machine: machine.set_power(state == "on"),
        args,
    )


async def set_steam(args: argparse.Namespace) -> None:
    """Set machine steam."""
    from ._config import resolve_stateful_command

    serial, state = resolve_stateful_command(args)
    await run_machine_command(
        serial,
        "steam",
        state,
        lambda machine: machine.set_steam(state == "on"),
        args,
    )


async def run_machine_command(
    serial: str,
    command: str,
    state: str,
    callback: Callable[[LaMarzoccoMachine], Awaitable[bool]],
    args: argparse.Namespace,
) -> None:
    """Run a command against a machine and report the result."""
    async with cloud_client(args) as client:
        machine = LaMarzoccoMachine(serial, client)
        success = await callback(machine)

    payload = {
        "serial": serial,
        "command": command,
        "state": state,
        "success": success,
    }
    if not success:
        if wants_json(args):
            print_json(payload)
        raise CliError(f"{command} command did not succeed")

    if wants_json(args):
        print_json(payload)
    else:
        print(f"{command.capitalize()} set to {state} for {serial}.")


__all__ = [
    "MachineDataResource",
    "clear_default_serial",
    "fetch_data_resource",
    "fetch_machine_data",
    "forget_password",
    "generate_key",
    "list_things",
    "login",
    "password_status",
    "register",
    "run_machine_command",
    "save_password",
    "set_default_serial",
    "set_power",
    "set_steam",
    "show_config",
    "show_machine",
    "switch_machine",
]
