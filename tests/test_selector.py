from __future__ import annotations

import sys
import types
from dataclasses import dataclass
from typing import Any

import pytest

from lmctl import _selector as selector
from lmctl import cli


@dataclass
class Machine:
    serial_number: str
    name: str = ""
    model_name: Any = None


class EnumLike:
    def __init__(self, value: str) -> None:
        self.value = value


class TTYInput:
    def __init__(self, *, is_tty: bool = True, fd: int = 42) -> None:
        self._is_tty = is_tty
        self.fd = fd

    def isatty(self) -> bool:
        return self._is_tty

    def fileno(self) -> int:
        return self.fd


class TTYOutput:
    def __init__(self, *, is_tty: bool = True) -> None:
        self._is_tty = is_tty
        self.chunks: list[str] = []
        self.flushed = False

    def isatty(self) -> bool:
        return self._is_tty

    def write(self, text: str) -> int:
        self.chunks.append(text)
        return len(text)

    def flush(self) -> None:
        self.flushed = True

    def getvalue(self) -> str:
        return "".join(self.chunks)


class ReadableInput:
    def __init__(self, text: str) -> None:
        self.chars = list(text)

    def read(self, size: int) -> str:
        assert size == 1
        return self.chars.pop(0) if self.chars else ""

    def has_pending(self) -> bool:
        return bool(self.chars)


class FakeSelect:
    def __init__(self, readable: ReadableInput) -> None:
        self.readable = readable
        self.calls: list[tuple[Any, Any, Any, float]] = []

    def select(self, readers: Any, writers: Any, errors: Any, timeout: float) -> tuple[list[Any], list[Any], list[Any]]:
        self.calls.append((readers, writers, errors, timeout))
        if self.readable.has_pending():
            return [self.readable], [], []
        return [], [], []


def install_terminal_fakes(monkeypatch: pytest.MonkeyPatch, keys: list[str]) -> dict[str, Any]:
    stdin = TTYInput()
    stderr = TTYOutput()
    previous_settings = ["previous-terminal-settings"]
    state: dict[str, Any] = {
        "stdin": stdin,
        "stderr": stderr,
        "previous_settings": previous_settings,
        "tcgetattr": [],
        "tcsetattr": [],
        "setcbreak": [],
        "read_key_select_modules": [],
    }

    termios_module = types.ModuleType("termios")
    setattr(termios_module, "TCSADRAIN", 7)

    def tcgetattr(fd: int) -> list[str]:
        state["tcgetattr"].append(fd)
        return previous_settings

    def tcsetattr(fd: int, when: int, settings: list[str]) -> None:
        state["tcsetattr"].append((fd, when, settings))

    setattr(termios_module, "tcgetattr", tcgetattr)
    setattr(termios_module, "tcsetattr", tcsetattr)

    tty_module = types.ModuleType("tty")

    def setcbreak(fd: int) -> None:
        state["setcbreak"].append(fd)

    setattr(tty_module, "setcbreak", setcbreak)

    select_module = types.ModuleType("select")

    monkeypatch.setattr(selector.sys, "stdin", stdin)
    monkeypatch.setattr(selector.sys, "stderr", stderr)
    monkeypatch.setitem(sys.modules, "termios", termios_module)
    monkeypatch.setitem(sys.modules, "tty", tty_module)
    monkeypatch.setitem(sys.modules, "select", select_module)

    key_iter = iter(keys)

    def fake_read_key(select_arg: Any) -> str:
        state["read_key_select_modules"].append(select_arg)
        try:
            return next(key_iter)
        except StopIteration as exc:
            raise AssertionError("read_key called more often than expected") from exc

    monkeypatch.setattr(selector, "read_key", fake_read_key)
    state["termios"] = termios_module
    state["select"] = select_module
    return state


def assert_terminal_cleanup(state: dict[str, Any]) -> None:
    stdin = state["stdin"]
    termios_module = state["termios"]
    assert state["tcgetattr"] == [stdin.fd]
    assert state["setcbreak"] == [stdin.fd]
    assert state["tcsetattr"] == [
        (stdin.fd, termios_module.TCSADRAIN, state["previous_settings"])
    ]
    output = state["stderr"].getvalue()
    assert "\033[?25l" in output
    assert output.endswith("\033[?25h")
    assert state["stderr"].flushed is True


def test_choose_thing_empty_list_error() -> None:
    with pytest.raises(cli.CliError, match="no machines found for this account"):
        selector.choose_thing([])


def test_choose_thing_explicit_serial_success() -> None:
    machines = [Machine("LM001"), Machine("LM002")]

    assert selector.choose_thing(machines, serial="LM002") is machines[1]


def test_choose_thing_explicit_serial_not_found_lists_known_serials() -> None:
    machines = [Machine("LM001"), Machine("LM002")]

    with pytest.raises(cli.CliError) as exc_info:
        selector.choose_thing(machines, serial="LM404")

    assert str(exc_info.value) == "serial LM404 not found; known serials: LM001, LM002"


def test_choose_thing_single_machine_auto_selects() -> None:
    machine = Machine("LM001")

    assert selector.choose_thing([machine]) is machine


def test_choose_thing_single_machine_can_force_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    machine = Machine("LM001", "Kitchen")
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(selector.sys, "stdin", TTYInput())

    def fake_select_option(prompt: str, options: list[str]) -> int:
        calls.append((prompt, options))
        return 0

    monkeypatch.setattr(selector, "select_option", fake_select_option)

    assert selector.choose_thing([machine], always_select=True) is machine
    assert calls == [("Choose a machine:", ["LM001 - Kitchen"])]


def test_choose_thing_multiple_machines_non_tty_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(selector.sys, "stdin", TTYInput(is_tty=False))

    with pytest.raises(cli.CliError, match="pass --serial"):
        selector.choose_thing([Machine("LM001"), Machine("LM002")])


def test_choose_thing_multiple_machines_delegates_to_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    machines = [Machine("LM001", "Kitchen"), Machine("LM002", "Office", EnumLike("Linea Micra"))]
    calls: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(selector.sys, "stdin", TTYInput())

    def fake_select_option(prompt: str, options: list[str]) -> int:
        calls.append((prompt, options))
        return 1

    monkeypatch.setattr(selector, "select_option", fake_select_option)

    assert selector.choose_thing(machines) is machines[1]
    assert calls == [
        ("Choose a machine:", ["LM001 - Kitchen", "LM002 - Office - Linea Micra"])
    ]


@pytest.mark.parametrize(
    ("machine", "expected"),
    [
        (Machine("LM001"), "LM001"),
        (Machine("LM001", "Kitchen"), "LM001 - Kitchen"),
        (Machine("LM001", "Kitchen", EnumLike("Linea Micra")), "LM001 - Kitchen - Linea Micra"),
    ],
)
def test_describe_thing(machine: Machine, expected: str) -> None:
    assert selector.describe_thing(machine) == expected


def test_read_key_normal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    stdin = ReadableInput("x")
    select_module = FakeSelect(stdin)
    monkeypatch.setattr(selector.sys, "stdin", stdin)

    assert selector.read_key(select_module) == "x"
    assert select_module.calls == []


def test_read_key_escape_key_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    stdin = ReadableInput("\x1b")
    select_module = FakeSelect(stdin)
    monkeypatch.setattr(selector.sys, "stdin", stdin)

    assert selector.read_key(select_module) == "\x1b"
    assert select_module.calls == [([stdin], [], [], 0.05)]


@pytest.mark.parametrize("sequence", ["\x1b[A", "\x1b[B"])
def test_read_key_arrow_key_escape_sequences(monkeypatch: pytest.MonkeyPatch, sequence: str) -> None:
    stdin = ReadableInput(sequence)
    select_module = FakeSelect(stdin)
    monkeypatch.setattr(selector.sys, "stdin", stdin)

    assert selector.read_key(select_module) == sequence
    assert len(select_module.calls) == 2


def test_render_selector_first_render(monkeypatch: pytest.MonkeyPatch) -> None:
    stderr = TTYOutput()
    monkeypatch.setattr(selector.sys, "stderr", stderr)

    selector.render_selector("Pick one:", ["alpha", "beta"], 1, first_render=True)

    assert stderr.getvalue() == (
        "Pick one: (use arrow keys, enter to select)\n"
        "\r\033[K○ alpha\n"
        "\r\033[K● beta\n"
    )
    assert stderr.flushed is True


def test_render_selector_subsequent_render(monkeypatch: pytest.MonkeyPatch) -> None:
    stderr = TTYOutput()
    monkeypatch.setattr(selector.sys, "stderr", stderr)

    selector.render_selector("Pick one:", ["alpha", "beta"], 0)

    assert stderr.getvalue() == (
        "\033[2F"
        "\r\033[K● alpha\n"
        "\r\033[K○ beta\n"
    )
    assert stderr.flushed is True


def test_select_option_non_tty_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(selector.sys, "stdin", TTYInput(is_tty=False))
    monkeypatch.setattr(selector.sys, "stderr", TTYOutput())

    with pytest.raises(cli.CliError, match="multiple machines found; pass --serial"):
        selector.select_option("Pick:", ["alpha", "beta"])


def test_select_option_down_up_enter_terminal_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    state = install_terminal_fakes(monkeypatch, ["\x1b[B", "\x1b[B", "\x1b[A", "\n"])

    assert selector.select_option("Pick:", ["alpha", "beta", "gamma"]) == 1

    assert_terminal_cleanup(state)
    assert state["read_key_select_modules"] == [state["select"]] * 4
    output = state["stderr"].getvalue()
    assert output.startswith("\033[?25lPick: (use arrow keys, enter to select)\n")
    assert output.count("\033[3F") == 3
    assert output.endswith("\n\033[?25h")


def test_select_option_j_k_shortcuts(monkeypatch: pytest.MonkeyPatch) -> None:
    state = install_terminal_fakes(monkeypatch, ["j", "j", "k", "\r"])

    assert selector.select_option("Pick:", ["alpha", "beta", "gamma"]) == 1

    assert_terminal_cleanup(state)


def test_select_option_ignores_bare_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    state = install_terminal_fakes(monkeypatch, ["\x1b", "\n"])

    assert selector.select_option("Pick:", ["alpha", "beta"]) == 0

    assert_terminal_cleanup(state)


def test_select_option_single_option_arrow_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    state = install_terminal_fakes(monkeypatch, ["\x1b[B", "\n"])

    assert selector.select_option("Pick:", ["alpha"]) == 0

    assert "\033[1F" not in state["stderr"].getvalue()
    assert_terminal_cleanup(state)


@pytest.mark.parametrize(
    "key",
    [pytest.param("q", id="q"), pytest.param("\x04", id="ctrl-d")],
)
def test_select_option_cancel_keys_cleanup(monkeypatch: pytest.MonkeyPatch, key: str) -> None:
    state = install_terminal_fakes(monkeypatch, [key])

    with pytest.raises(cli.CliError, match="selection cancelled"):
        selector.select_option("Pick:", ["alpha", "beta"])

    assert_terminal_cleanup(state)


def test_select_option_ctrl_c_propagates_and_cleans_up(monkeypatch: pytest.MonkeyPatch) -> None:
    state = install_terminal_fakes(monkeypatch, ["\x03"])

    with pytest.raises(KeyboardInterrupt):
        selector.select_option("Pick:", ["alpha", "beta"])

    assert_terminal_cleanup(state)
