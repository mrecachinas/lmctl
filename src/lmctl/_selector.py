"""Interactive machine selector."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any

from ._errors import CliError
from ._output import display_value


def choose_thing(
    things: Sequence[Any],
    serial: str | None = None,
    *,
    always_select: bool = False,
) -> Any:
    """Choose a machine from a list returned by pylamarzocco."""
    if not things:
        raise CliError("no machines found for this account")

    if serial is not None:
        for thing in things:
            if thing.serial_number == serial:
                return thing
        known_serials = ", ".join(thing.serial_number for thing in things)
        raise CliError(f"serial {serial} not found; known serials: {known_serials}")

    if len(things) == 1 and not always_select:
        return things[0]

    if not sys.stdin.isatty():
        raise CliError("pass --serial to choose a machine")

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
            if key in {"\x04", "q"}:
                raise CliError("selection cancelled")
            if key in {"\x1b[A", "k"}:
                next_selected = (selected - 1) % len(options)
                if next_selected != selected:
                    selected = next_selected
                    render_selector(prompt, options, selected)
            elif key in {"\x1b[B", "j"}:
                next_selected = (selected + 1) % len(options)
                if next_selected != selected:
                    selected = next_selected
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

    while select_module.select([sys.stdin], [], [], 0.05)[0]:
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
        prefix = "●" if index == selected else "○"
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
