"""CLI for La Marzocco Home machines via pylamarzocco."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sys
import uuid
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

import keyring
from keyring.errors import KeyringError
from aiohttp import ClientError, ClientSession
from pylamarzocco import LaMarzoccoCloudClient, LaMarzoccoMachine
from pylamarzocco.exceptions import LaMarzoccoError
from pylamarzocco.util import InstallationKey, generate_installation_key


APP_NAME = "lmctl"
KEYRING_SERVICE = APP_NAME
USERNAME_ENV_VARS = ("LMCTL_USERNAME", "LAMARZOCCO_USERNAME")
PASSWORD_ENV_VARS = ("LMCTL_PASSWORD", "LAMARZOCCO_PASSWORD")
USERNAME_KEY = "username"
DEFAULT_SERIAL_KEY = "default_serial"


class CliError(Exception):
    """A user-correctable CLI error."""


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


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Control La Marzocco Home machines using pylamarzocco.",
    )
    parser.add_argument(
        "--username",
        help=(
            "La Marzocco Home username. Defaults to LMCTL_USERNAME or "
            "LAMARZOCCO_USERNAME, then saved config."
        ),
    )
    parser.add_argument(
        "--password",
        help=(
            "La Marzocco Home password. Defaults to LMCTL_PASSWORD, "
            "LAMARZOCCO_PASSWORD, saved keychain password, or an interactive prompt."
        ),
    )
    parser.add_argument(
        "--no-keyring",
        action="store_true",
        help="Do not read from or write to the OS keychain for this invocation.",
    )
    parser.add_argument(
        "--key-file",
        type=Path,
        default=default_key_file(),
        help=(
            "Installation key JSON file. Defaults to LMCTL_KEY_FILE or "
            f"{default_key_file()}."
        ),
    )
    parser.add_argument(
        "--config-file",
        type=Path,
        default=default_config_file(),
        help=(
            "Configuration JSON file. Defaults to LMCTL_CONFIG_FILE or "
            f"{default_config_file()}."
        ),
    )

    subcommands = parser.add_subparsers(dest="command", required=True)

    login_parser = subcommands.add_parser(
        "login",
        help="Authenticate, choose a machine, and save defaults.",
    )
    login_parser.add_argument(
        "--serial",
        help="Select this machine serial instead of prompting.",
    )
    login_parser.add_argument(
        "--save-password",
        dest="save_password",
        action="store_true",
        default=True,
        help="Save the authenticated password in the OS keychain (default).",
    )
    login_parser.add_argument(
        "--no-save-password",
        dest="save_password",
        action="store_false",
        help="Do not save the authenticated password in the OS keychain.",
    )
    login_parser.set_defaults(func=login)

    switch_parser = subcommands.add_parser(
        "switch",
        help="Choose a different default machine.",
    )
    switch_parser.add_argument(
        "--serial",
        help="Select this machine serial instead of prompting.",
    )
    switch_parser.set_defaults(func=switch_machine)

    password_parser = subcommands.add_parser(
        "password", help="Manage the saved keychain password."
    )
    password_subcommands = password_parser.add_subparsers(
        dest="password_command", required=True
    )
    password_save_parser = password_subcommands.add_parser(
        "save", help="Save a password in the OS keychain."
    )
    password_save_parser.set_defaults(func=save_password)
    password_status_parser = password_subcommands.add_parser(
        "status", help="Show whether a password is saved."
    )
    password_status_parser.set_defaults(func=password_status)
    password_forget_parser = password_subcommands.add_parser(
        "forget", help="Delete the saved keychain password."
    )
    password_forget_parser.set_defaults(func=forget_password)

    config_parser = subcommands.add_parser("config", help="Manage lmctl defaults.")
    config_subcommands = config_parser.add_subparsers(
        dest="config_command", required=True
    )
    config_show_parser = config_subcommands.add_parser(
        "show", help="Show the current lmctl configuration."
    )
    config_show_parser.set_defaults(func=show_config)
    config_set_serial_parser = config_subcommands.add_parser(
        "set-serial", help="Set the default machine serial number."
    )
    config_set_serial_parser.add_argument("serial", help="Default machine serial number.")
    config_set_serial_parser.set_defaults(func=set_default_serial)
    config_clear_serial_parser = config_subcommands.add_parser(
        "clear-serial", help="Clear the default machine serial number."
    )
    config_clear_serial_parser.set_defaults(func=clear_default_serial)

    key_parser = subcommands.add_parser("key", help="Manage installation keys.")
    key_subcommands = key_parser.add_subparsers(dest="key_command", required=True)
    generate_key_parser = key_subcommands.add_parser(
        "generate", help="Generate an installation key JSON file."
    )
    generate_key_parser.add_argument(
        "--output",
        type=Path,
        help="Output file. Defaults to --key-file.",
    )
    generate_key_parser.add_argument(
        "--installation-id",
        help="Installation ID to embed in the key. Defaults to a random UUID.",
    )
    generate_key_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    generate_key_parser.set_defaults(func=generate_key)

    register_parser = subcommands.add_parser(
        "register", help="Register the current installation key with La Marzocco."
    )
    register_parser.set_defaults(func=register)

    things_parser = subcommands.add_parser("things", help="List account devices.")
    things_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the device list as JSON instead of a table.",
    )
    things_parser.set_defaults(func=list_things)

    show_parser = subcommands.add_parser(
        "show", help="Fetch dashboard, settings, statistics, schedule, and firmware."
    )
    add_serial_argument(show_parser)
    show_parser.set_defaults(func=show_machine)

    for name, description in (
        ("dashboard", "Fetch a machine dashboard."),
        ("settings", "Fetch machine settings."),
        ("statistics", "Fetch machine statistics."),
        ("schedule", "Fetch a machine schedule."),
        ("firmware", "Fetch firmware information."),
    ):
        command_parser = subcommands.add_parser(name, help=description)
        add_serial_argument(command_parser)
        command_parser.set_defaults(func=fetch_machine_data, data_name=name)

    power_parser = subcommands.add_parser("power", help="Turn a machine on or off.")
    add_stateful_command_arguments(power_parser)
    power_parser.set_defaults(func=set_power)

    steam_parser = subcommands.add_parser("steam", help="Turn steam on or off.")
    add_stateful_command_arguments(steam_parser)
    steam_parser.set_defaults(func=set_steam)

    return parser


def add_serial_argument(parser: argparse.ArgumentParser) -> None:
    """Add a serial number argument to a subcommand parser."""
    parser.add_argument(
        "serial",
        nargs="?",
        help="Machine serial number. Defaults to `lmctl config set-serial SERIAL`.",
    )


def add_stateful_command_arguments(parser: argparse.ArgumentParser) -> None:
    """Add serial/state arguments for commands that support a default serial."""
    parser.add_argument(
        "serial_or_state",
        help="Machine serial number, or state when a default serial is configured.",
    )
    parser.add_argument(
        "state",
        nargs="?",
        choices=("on", "off"),
        help="Desired state.",
    )


def default_key_file() -> Path:
    """Return the default installation key path."""
    configured = os.environ.get("LMCTL_KEY_FILE")
    if configured:
        return Path(configured).expanduser()

    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / APP_NAME / "installation_key.json"


def default_config_file() -> Path:
    """Return the default lmctl config path."""
    configured = os.environ.get("LMCTL_CONFIG_FILE")
    if configured:
        return Path(configured).expanduser()

    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / APP_NAME / "config.json"


def show_config(args: argparse.Namespace) -> None:
    """Show the current lmctl configuration."""
    config_file = expand_path(args.config_file)
    config = load_config(config_file)
    print_json(
        {
            "config_file": config_file,
            USERNAME_KEY: config.get(USERNAME_KEY),
            DEFAULT_SERIAL_KEY: config.get(DEFAULT_SERIAL_KEY),
        }
    )


def set_default_serial(args: argparse.Namespace) -> None:
    """Set the default machine serial number."""
    config_file = expand_path(args.config_file)
    config = load_config(config_file)
    config[DEFAULT_SERIAL_KEY] = args.serial
    save_config(config_file, config)
    print_json(
        {
            "config_file": config_file,
            DEFAULT_SERIAL_KEY: args.serial,
        }
    )


def clear_default_serial(args: argparse.Namespace) -> None:
    """Clear the default machine serial number."""
    config_file = expand_path(args.config_file)
    config = load_config(config_file)
    config.pop(DEFAULT_SERIAL_KEY, None)
    save_config(config_file, config)
    print_json(
        {
            "config_file": config_file,
            DEFAULT_SERIAL_KEY: None,
        }
    )


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

    print_json(
        {
            "config_file": config_file,
            "key_file": key_file,
            "generated_key": generated_key,
            "password_saved": password_saved,
            USERNAME_KEY: username,
            DEFAULT_SERIAL_KEY: selected.serial_number,
        }
    )


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
    print_json(
        {
            "service": KEYRING_SERVICE,
            USERNAME_KEY: username,
            "password_saved": True,
        }
    )


def password_status(args: argparse.Namespace) -> None:
    """Show whether a password is saved in the OS keychain."""
    if keyring_disabled(args):
        raise CliError("cannot read password status when --no-keyring is set")

    username = credential(
        args.username,
        USERNAME_ENV_VARS,
        "username",
        config_file=args.config_file,
        config_key=USERNAME_KEY,
    )
    print_json(
        {
            "service": KEYRING_SERVICE,
            USERNAME_KEY: username,
            "password_saved": get_saved_password(username, args, required=True)
            is not None,
        }
    )


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
    print_json(
        {
            "service": KEYRING_SERVICE,
            USERNAME_KEY: username,
            "password_deleted": deleted,
        }
    )


async def switch_machine(args: argparse.Namespace) -> None:
    """Choose a different default machine."""
    async with cloud_client(args) as client:
        things = await client.list_things()

    selected = choose_thing(things, args.serial)
    config_file = expand_path(args.config_file)
    config = load_config(config_file)
    config[DEFAULT_SERIAL_KEY] = selected.serial_number
    save_config(config_file, config)

    print_json(
        {
            "config_file": config_file,
            DEFAULT_SERIAL_KEY: selected.serial_number,
        }
    )


def generate_key(args: argparse.Namespace) -> None:
    """Generate installation key material."""
    output = expand_path(args.output or args.key_file)
    if output.exists() and not args.force:
        raise CliError(f"{output} already exists; pass --force to overwrite it")

    installation_id = args.installation_id or str(uuid.uuid4()).lower()
    installation_key = generate_installation_key(installation_id)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json_text(installation_key.to_json()), encoding="utf-8")
    print_json(
        {
            "installation_id": installation_id,
            "key_file": str(output),
        }
    )


async def register(args: argparse.Namespace) -> None:
    """Register the current installation key."""
    async with cloud_client(args) as client:
        await client.async_register_client()
    print_json({"registered": True, "key_file": str(expand_path(args.key_file))})


async def list_things(args: argparse.Namespace) -> None:
    """List account devices."""
    async with cloud_client(args) as client:
        things = await client.list_things()

    if args.json:
        print_json(things)
        return

    rows = [
        (
            thing.serial_number,
            display_value(thing.name),
            display_value(thing.model_name),
            display_value(thing.connected),
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
    print_json(payload)


async def fetch_machine_data(args: argparse.Namespace) -> None:
    """Fetch one machine data resource."""
    serial = resolve_serial(args)
    async with cloud_client(args) as client:
        machine = LaMarzoccoMachine(serial, client)
        data = await fetch_data_resource(machine, args.data_name)

    print_json(data)


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

    print_json(
        {
            "serial": serial,
            "command": command,
            "state": state,
            "success": success,
        }
    )
    if not success:
        raise CliError(f"{command} command did not succeed")


class cloud_client:
    """Async context manager for an authenticated cloud client."""

    def __init__(self, args: argparse.Namespace) -> None:
        self._args = args
        self._session: ClientSession | None = None

    async def __aenter__(self) -> LaMarzoccoCloudClient:
        self._session = ClientSession()
        username = credential(
            self._args.username,
            USERNAME_ENV_VARS,
            "username",
            config_file=self._args.config_file,
            config_key=USERNAME_KEY,
        )
        return LaMarzoccoCloudClient(
            username=username,
            password=password_credential(self._args, username),
            installation_key=load_installation_key(self._args.key_file),
            client=self._session,
        )

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        if self._session is not None:
            await self._session.close()


def load_installation_key(path: Path) -> InstallationKey:
    """Load an installation key from disk."""
    key_file = expand_path(path)
    if not key_file.exists():
        raise CliError(
            f"{key_file} does not exist; run `lmctl key generate` first"
        )
    try:
        return InstallationKey.from_json(key_file.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise CliError(f"{key_file} is not a valid installation key") from exc


def ensure_installation_key(path: Path) -> tuple[InstallationKey, bool]:
    """Load an installation key, or create one when missing."""
    key_file = expand_path(path)
    if key_file.exists():
        return load_installation_key(key_file), False

    installation_key = generate_installation_key(str(uuid.uuid4()).lower())
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(json_text(installation_key.to_json()), encoding="utf-8")
    return installation_key, True


def json_text(value: str | bytes | bytearray) -> str:
    """Return JSON data as text."""
    if isinstance(value, str):
        return value
    return bytes(value).decode("utf-8")


def load_config(path: Path) -> dict[str, Any]:
    """Load lmctl configuration from disk."""
    config_file = expand_path(path)
    if not config_file.exists():
        return {}

    try:
        config = json.loads(config_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"{config_file} is not valid JSON") from exc

    if not isinstance(config, dict):
        raise CliError(f"{config_file} must contain a JSON object")

    return config


def save_config(path: Path, config: dict[str, Any]) -> None:
    """Save lmctl configuration to disk."""
    config_file = expand_path(path)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def resolve_serial(args: argparse.Namespace) -> str:
    """Resolve a serial number from args or the configured default."""
    explicit_serial = getattr(args, "serial", None)
    if explicit_serial:
        return explicit_serial

    config = load_config(args.config_file)
    configured_serial = config.get(DEFAULT_SERIAL_KEY)
    if configured_serial is None:
        raise CliError(
            "missing serial; pass SERIAL or run `lmctl config set-serial SERIAL`"
        )
    if not isinstance(configured_serial, str) or configured_serial == "":
        raise CliError(
            f"{expand_path(args.config_file)} has an invalid {DEFAULT_SERIAL_KEY}"
        )
    return configured_serial


def resolve_stateful_command(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve serial/state for power and steam commands."""
    if args.state is None:
        if args.serial_or_state not in {"on", "off"}:
            raise CliError(
                "missing state; use `on` or `off`, or configure a default serial "
                "to omit SERIAL"
            )
        return resolve_serial(args), args.serial_or_state

    return args.serial_or_state, args.state


def password_credential(
    args: argparse.Namespace,
    username: str,
    *,
    allow_saved: bool = True,
) -> str:
    """Resolve a password from args, env, keychain, or prompt."""
    if args.password:
        return args.password

    for env_var in PASSWORD_ENV_VARS:
        value = os.environ.get(env_var)
        if value:
            return value

    if allow_saved:
        saved_password = get_saved_password(username, args)
        if saved_password is not None:
            return saved_password

    if sys.stdin.isatty():
        value = getpass.getpass("La Marzocco password: ")
        if value:
            return value

    names = ", ".join(PASSWORD_ENV_VARS)
    raise CliError(
        "missing password; pass --password, set one of: "
        f"{names}, or run `lmctl password save`"
    )


def get_saved_password(
    username: str,
    args: argparse.Namespace,
    *,
    required: bool = False,
) -> str | None:
    """Return a saved password from the OS keychain."""
    if keyring_disabled(args):
        if required:
            raise CliError("keyring is disabled by --no-keyring")
        return None

    try:
        return keyring.get_password(KEYRING_SERVICE, username)
    except KeyringError as exc:
        if required:
            raise CliError(f"keyring unavailable: {exc}") from exc
        print(
            f"{APP_NAME}: warning: keyring unavailable; prompting for password",
            file=sys.stderr,
        )
        return None


def set_saved_password(
    username: str,
    password: str,
    args: argparse.Namespace,
) -> None:
    """Save a password in the OS keychain."""
    if keyring_disabled(args):
        raise CliError("keyring is disabled by --no-keyring")

    try:
        keyring.set_password(KEYRING_SERVICE, username, password)
    except KeyringError as exc:
        raise CliError(f"keyring unavailable: {exc}") from exc


def try_set_login_password(
    username: str,
    password: str,
    args: argparse.Namespace,
) -> bool:
    """Best-effort password save for login."""
    if keyring_disabled(args):
        return False

    try:
        set_saved_password(username, password, args)
    except CliError as exc:
        print(f"{APP_NAME}: warning: {exc}", file=sys.stderr)
        return False
    return True


def delete_saved_password(username: str, args: argparse.Namespace) -> bool:
    """Delete a saved password from the OS keychain."""
    if keyring_disabled(args):
        raise CliError("keyring is disabled by --no-keyring")

    if get_saved_password(username, args, required=True) is None:
        return False

    try:
        keyring.delete_password(KEYRING_SERVICE, username)
    except KeyringError as exc:
        raise CliError(f"keyring unavailable: {exc}") from exc
    return True


def keyring_disabled(args: argparse.Namespace) -> bool:
    """Return whether keyring access is disabled for this invocation."""
    return bool(getattr(args, "no_keyring", False))


def choose_thing(things: Sequence[Any], serial: str | None = None) -> Any:
    """Choose a machine from a list returned by pylamarzocco."""
    if not things:
        raise CliError("no machines found for this account")

    if serial is not None:
        for thing in things:
            if thing.serial_number == serial:
                return thing
        known_serials = ", ".join(thing.serial_number for thing in things)
        raise CliError(f"serial {serial} not found; known serials: {known_serials}")

    if len(things) == 1:
        return things[0]

    if not sys.stdin.isatty():
        raise CliError("multiple machines found; pass --serial to choose one")

    options = [describe_thing(thing) for thing in things]
    return things[select_option("Choose a machine:", options)]


def select_option(prompt: str, options: Sequence[str]) -> int:
    """Select an option with arrow keys and return its index."""
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise CliError("multiple machines found; pass --serial to choose one")

    try:
        import select
        import termios
        import tty
    except ImportError as exc:
        raise CliError(
            "arrow-key selection requires a POSIX terminal; pass --serial to choose one"
        ) from exc

    selected = 0
    stdin_fd = sys.stdin.fileno()
    previous_terminal_settings = termios.tcgetattr(stdin_fd)

    try:
        tty.setcbreak(stdin_fd)
        sys.stderr.write("\033[?25l")
        render_selector(prompt, options, selected, first_render=True)

        while True:
            key = read_key(select)
            if key in {"\r", "\n"}:
                sys.stderr.write("\n")
                return selected
            if key in {"\x03"}:
                raise KeyboardInterrupt
            if key in {"\x04", "\x1b", "q"}:
                raise CliError("selection cancelled")
            if key in {"\x1b[A", "k"}:
                selected = (selected - 1) % len(options)
                render_selector(prompt, options, selected)
            elif key in {"\x1b[B", "j"}:
                selected = (selected + 1) % len(options)
                render_selector(prompt, options, selected)
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, previous_terminal_settings)
        sys.stderr.write("\033[?25h")
        sys.stderr.flush()


def read_key(select_module: Any) -> str:
    """Read a key or escape sequence from stdin."""
    key = sys.stdin.read(1)
    if key != "\x1b":
        return key

    while select_module.select([sys.stdin], [], [], 0.01)[0]:
        key += sys.stdin.read(1)
        if len(key) >= 3:
            break
    return key


def render_selector(
    prompt: str,
    options: Sequence[str],
    selected: int,
    *,
    first_render: bool = False,
) -> None:
    """Render an arrow-key selector."""
    if first_render:
        sys.stderr.write(f"{prompt} (use arrow keys, enter to select)\n")
    else:
        sys.stderr.write(f"\033[{len(options)}F")

    for index, option in enumerate(options):
        prefix = ">" if index == selected else " "
        sys.stderr.write(f"\r\033[K{prefix} {option}\n")
    sys.stderr.flush()


def describe_thing(thing: Any) -> str:
    """Return a concise human-readable thing description."""
    parts = [thing.serial_number]
    if thing.name:
        parts.append(thing.name)
    if thing.model_name:
        parts.append(display_value(thing.model_name))
    return " - ".join(parts)


def credential(
    explicit_value: str | None,
    env_vars: tuple[str, ...],
    label: str,
    *,
    prompt_secret: bool = False,
    config_file: Path | None = None,
    config_key: str | None = None,
) -> str:
    """Resolve a credential from args, environment, or an interactive prompt."""
    if explicit_value:
        return explicit_value

    for env_var in env_vars:
        value = os.environ.get(env_var)
        if value:
            return value

    if config_file is not None and config_key is not None:
        config = load_config(config_file)
        configured_value = config.get(config_key)
        if isinstance(configured_value, str) and configured_value:
            return configured_value
        if configured_value is not None:
            raise CliError(
                f"{expand_path(config_file)} has an invalid {config_key}"
            )

    if sys.stdin.isatty():
        if prompt_secret:
            value = getpass.getpass(f"La Marzocco {label}: ")
        else:
            value = input(f"La Marzocco {label}: ")
        if value:
            return value

    names = ", ".join(env_vars)
    raise CliError(f"missing {label}; pass --{label} or set one of: {names}")


def print_json(value: Any) -> None:
    """Print a value as pretty JSON."""
    print(json.dumps(to_jsonable(value), indent=2, sort_keys=True))


def to_jsonable(value: Any) -> Any:
    """Convert pylamarzocco models into JSON-compatible structures."""
    if hasattr(value, "to_dict"):
        return to_jsonable(value.to_dict())
    if isinstance(value, dict):
        return {display_value(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value


def print_table(headers: tuple[str, ...], rows: list[tuple[Any, ...]]) -> None:
    """Print a simple left-aligned table."""
    text_rows = [tuple(display_value(cell) for cell in row) for row in rows]
    widths = [len(header) for header in headers]
    for row in text_rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in text_rows:
        print("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)))


def display_value(value: Any) -> str:
    """Format a value for human-readable output."""
    if hasattr(value, "value"):
        value = value.value
    if value is None:
        return ""
    return str(value)


def expand_path(path: Path) -> Path:
    """Expand and resolve a user-facing path."""
    return path.expanduser().resolve()
