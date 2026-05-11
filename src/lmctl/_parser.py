"""Argument parser construction."""

from __future__ import annotations

import argparse
from pathlib import Path

from ._commands import (
    clear_default_serial,
    fetch_machine_data,
    forget_password,
    generate_key,
    list_things,
    login,
    password_status,
    register,
    save_password,
    set_default_serial,
    set_power,
    set_steam,
    show_config,
    show_machine,
    switch_machine,
)
from ._config import default_config_file, default_key_file
from ._constants import APP_NAME


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    json_parent = argparse.ArgumentParser(add_help=False)
    add_json_argument(json_parent, default=argparse.SUPPRESS)

    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="Control La Marzocco Home machines using pylamarzocco.",
    )
    add_json_argument(parser, default=False)
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
        parents=[json_parent],
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
        parents=[json_parent],
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
        "save",
        help="Save a password in the OS keychain.",
        parents=[json_parent],
    )
    password_save_parser.set_defaults(func=save_password)
    password_status_parser = password_subcommands.add_parser(
        "status",
        help="Show whether a password is saved.",
        parents=[json_parent],
    )
    password_status_parser.set_defaults(func=password_status)
    password_forget_parser = password_subcommands.add_parser(
        "forget",
        help="Delete the saved keychain password.",
        parents=[json_parent],
    )
    password_forget_parser.set_defaults(func=forget_password)

    config_parser = subcommands.add_parser("config", help="Manage lmctl defaults.")
    config_subcommands = config_parser.add_subparsers(
        dest="config_command", required=True
    )
    config_show_parser = config_subcommands.add_parser(
        "show",
        help="Show the current lmctl configuration.",
        parents=[json_parent],
    )
    config_show_parser.set_defaults(func=show_config)
    config_set_serial_parser = config_subcommands.add_parser(
        "set-serial",
        help="Set the default machine serial number.",
        parents=[json_parent],
    )
    config_set_serial_parser.add_argument(
        "serial", help="Default machine serial number."
    )
    config_set_serial_parser.set_defaults(func=set_default_serial)
    config_clear_serial_parser = config_subcommands.add_parser(
        "clear-serial",
        help="Clear the default machine serial number.",
        parents=[json_parent],
    )
    config_clear_serial_parser.set_defaults(func=clear_default_serial)

    key_parser = subcommands.add_parser("key", help="Manage installation keys.")
    key_subcommands = key_parser.add_subparsers(dest="key_command", required=True)
    generate_key_parser = key_subcommands.add_parser(
        "generate",
        help="Generate an installation key JSON file.",
        parents=[json_parent],
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
        "register",
        help="Register the current installation key with La Marzocco.",
        parents=[json_parent],
    )
    register_parser.set_defaults(func=register)

    things_parser = subcommands.add_parser(
        "things",
        help="List account devices.",
        parents=[json_parent],
    )
    things_parser.set_defaults(func=list_things)

    show_parser = subcommands.add_parser(
        "show",
        help="Fetch dashboard, settings, statistics, schedule, and firmware.",
        parents=[json_parent],
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
        command_parser = subcommands.add_parser(
            name,
            help=description,
            parents=[json_parent],
        )
        add_serial_argument(command_parser)
        command_parser.set_defaults(func=fetch_machine_data, data_name=name)

    power_parser = subcommands.add_parser(
        "power",
        help="Turn a machine on or off.",
        parents=[json_parent],
    )
    add_stateful_command_arguments(power_parser)
    power_parser.set_defaults(func=set_power)

    steam_parser = subcommands.add_parser(
        "steam",
        help="Turn steam on or off.",
        parents=[json_parent],
    )
    add_stateful_command_arguments(steam_parser)
    steam_parser.set_defaults(func=set_steam)

    return parser


def add_json_argument(parser: argparse.ArgumentParser, *, default: bool | str) -> None:
    """Add the common JSON output option."""
    parser.add_argument(
        "--json",
        action="store_true",
        default=default,
        help="Print JSON instead of human-readable output.",
    )


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
        "--serial",
        help="Machine serial number. Defaults to the configured default machine.",
    )
    parser.add_argument(
        "state",
        choices=("on", "off"),
        help="Desired state.",
    )
