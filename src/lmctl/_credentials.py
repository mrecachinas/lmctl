"""Credential and keychain helpers."""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path
from typing import Any

import keyring
from keyring.errors import KeyringError

from ._config import expand_path, load_config
from ._constants import APP_NAME, KEYRING_SERVICE, PASSWORD_ENV_VARS
from ._errors import CliError


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
            raise CliError(f"{expand_path(config_file)} has an invalid {config_key}")

    if sys.stdin.isatty():
        if prompt_secret:
            value = getpass.getpass(f"La Marzocco {label}: ")
        else:
            value = input(f"La Marzocco {label}: ")
        if value:
            return value

    names = ", ".join(env_vars)
    raise CliError(f"missing {label}; pass --{label} or set one of: {names}")


def password_credential(
    args: Any,
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
    args: Any,
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
    args: Any,
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
    args: Any,
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


def delete_saved_password(username: str, args: Any) -> bool:
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


def keyring_disabled(args: Any) -> bool:
    """Return whether keyring access is disabled for this invocation."""
    return bool(getattr(args, "no_keyring", False))
