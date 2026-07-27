"""Experimental water reservoir estimation."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pylamarzocco import LaMarzoccoMachine

from ._client import cloud_client
from ._config import expand_path, load_config, resolve_serial, save_config
from ._errors import CliError
from ._output import print_json, to_jsonable, wants_json

DEFAULT_TANK_ML = 2000.0
DEFAULT_RESERVE_ML = 250.0
DEFAULT_SHOT_ML = 45.0
DEFAULT_FLUSH_ML = 30.0

WATER_STATE_VERSION = 1
EXPERIMENTAL_WARNING = (
    "Experimental estimate: La Marzocco exposes only a low-water alarm, not a "
    "continuous tank sensor. Steam and manual water use must be logged or "
    "estimated separately."
)


async def refill_water(args: argparse.Namespace) -> None:
    """Record a full-tank baseline for experimental water estimates."""
    payload = await refill_water_payload(args)
    if wants_json(args):
        print_json(payload)
        return

    print(f"EXPERIMENTAL water estimate reset for {payload['serial']}.")
    print(f"Stored a full-tank baseline in {payload['state_file']}.")
    print(EXPERIMENTAL_WARNING)


async def refill_water_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Record a full-tank baseline and return the experimental water payload."""
    serial = resolve_serial(args)
    state_file = resolve_water_state_file(args)
    calibration = calibration_from_args(args)
    no_water_alarm, counter = await fetch_water_inputs(args, serial)
    now = datetime.now(UTC).isoformat()

    state = load_water_state(state_file)
    machines = water_state_machines(state, state_file)
    machines[serial] = {
        "refilled_at": now,
        "baseline_total_coffee": counter["total_coffee"],
        "baseline_total_flush": counter["total_flush"],
        "manual_usage_ml": 0.0,
        **calibration,
    }
    save_config(state_file, state)

    payload = {
        "experimental": True,
        "warning": EXPERIMENTAL_WARNING,
        "serial": serial,
        "state_file": str(state_file),
        "refilled_at": now,
        "no_water_alarm": no_water_alarm,
        "baseline": counter,
        **calibration,
    }
    return payload


async def estimate_water(args: argparse.Namespace) -> None:
    """Estimate remaining reservoir water from counters since the last refill."""
    payload = await water_estimate_payload(args)
    if wants_json(args):
        print_json(payload)
        return

    print(f"EXPERIMENTAL water estimate for {payload['serial']}")
    print(
        "Estimated remaining: "
        f"{format_ml(payload['estimated_remaining_ml'])} "
        f"({payload['estimated_remaining_percent']}%)"
    )
    print(f"Status: {payload['status']}")
    print(
        "Used since refill: "
        f"{format_ml(payload['usage']['coffee_ml'])} coffee "
        f"({payload['usage']['coffee_count']}), "
        f"{format_ml(payload['usage']['flush_ml'])} flush "
        f"({payload['usage']['flush_count']}), "
        f"{format_ml(payload['usage']['manual_ml'])} logged manual, "
        f"{format_ml(payload['usage']['extra_ml'])} one-off extra"
    )
    if payload["no_water_alarm"]:
        print("Machine low-water alarm is active; refill now.")
    print(f"State file: {payload['state_file']}")
    print(EXPERIMENTAL_WARNING)


def log_water_use(args: argparse.Namespace) -> None:
    """Record unobservable water usage, such as steaming or manual flushing."""
    payload = log_water_use_payload(args)
    if wants_json(args):
        print_json(payload)
        return

    note = f" ({payload['note']})" if payload["note"] else ""
    print(
        f"EXPERIMENTAL water usage logged for {payload['serial']}: "
        f"{format_ml(payload['logged_usage_ml'])}{note}."
    )
    print(f"Manual usage since refill: {format_ml(payload['manual_usage_ml'])}.")
    print(EXPERIMENTAL_WARNING)


def log_water_use_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Record unobservable water usage and return the experimental payload."""
    serial = resolve_serial(args)
    state_file = resolve_water_state_file(args)
    amount_ml = positive_float(args.amount_ml, "amount_ml")
    state = load_water_state(state_file)
    machine_state = require_machine_water_state(state, state_file, serial)
    manual_usage_ml = numeric_state_value(
        machine_state,
        "manual_usage_ml",
        state_file,
        default=0.0,
    )
    machine_state["manual_usage_ml"] = manual_usage_ml + amount_ml
    machine_state["last_manual_usage_at"] = datetime.now(UTC).isoformat()
    if args.note:
        machine_state["last_manual_usage_note"] = args.note
    save_config(state_file, state)

    payload = {
        "experimental": True,
        "warning": EXPERIMENTAL_WARNING,
        "serial": serial,
        "state_file": str(state_file),
        "logged_usage_ml": amount_ml,
        "manual_usage_ml": machine_state["manual_usage_ml"],
        "note": args.note,
    }
    return payload


async def water_estimate_payload(args: argparse.Namespace) -> dict[str, Any]:
    """Build the experimental water estimate payload."""
    serial = resolve_serial(args)
    state_file = resolve_water_state_file(args)
    state = load_water_state(state_file)
    machine_state = require_machine_water_state(state, state_file, serial)
    calibration = calibration_from_args(args, machine_state)
    manual_usage_ml = numeric_state_value(
        machine_state,
        "manual_usage_ml",
        state_file,
        default=0.0,
    )
    extra_ml = non_negative_float(getattr(args, "extra_ml", 0.0), "extra_ml")
    baseline_total_coffee = int_state_value(
        machine_state,
        "baseline_total_coffee",
        state_file,
    )
    baseline_total_flush = int_state_value(
        machine_state,
        "baseline_total_flush",
        state_file,
    )
    no_water_alarm, counter = await fetch_water_inputs(args, serial)

    coffee_count = counter["total_coffee"] - baseline_total_coffee
    flush_count = counter["total_flush"] - baseline_total_flush
    if coffee_count < 0 or flush_count < 0:
        raise CliError(
            "water counters are lower than the stored refill baseline; "
            "fill the tank and run `lmctl water refill` again"
        )

    coffee_ml = coffee_count * calibration["shot_ml"]
    flush_ml = flush_count * calibration["flush_ml"]
    used_ml = coffee_ml + flush_ml + manual_usage_ml + extra_ml
    raw_remaining_ml = max(calibration["tank_ml"] - used_ml, 0.0)
    estimated_remaining_ml = raw_remaining_ml
    if no_water_alarm:
        estimated_remaining_ml = min(estimated_remaining_ml, calibration["reserve_ml"])

    if no_water_alarm or estimated_remaining_ml <= 0:
        status = "needs_refill"
    elif estimated_remaining_ml <= calibration["reserve_ml"]:
        status = "low"
    else:
        status = "ok"

    return {
        "experimental": True,
        "warning": EXPERIMENTAL_WARNING,
        "serial": serial,
        "state_file": str(state_file),
        "refilled_at": machine_state["refilled_at"],
        "status": status,
        "no_water_alarm": no_water_alarm,
        "tank_ml": round_ml(calibration["tank_ml"]),
        "reserve_ml": round_ml(calibration["reserve_ml"]),
        "shot_ml": round_ml(calibration["shot_ml"]),
        "flush_ml": round_ml(calibration["flush_ml"]),
        "estimated_remaining_ml": round_ml(estimated_remaining_ml),
        "raw_estimated_remaining_ml": round_ml(raw_remaining_ml),
        "estimated_remaining_percent": round(
            estimated_remaining_ml / calibration["tank_ml"] * 100,
            1,
        ),
        "used_ml": round_ml(used_ml),
        "usage": {
            "coffee_count": coffee_count,
            "coffee_ml": round_ml(coffee_ml),
            "flush_count": flush_count,
            "flush_ml": round_ml(flush_ml),
            "manual_ml": round_ml(manual_usage_ml),
            "extra_ml": round_ml(extra_ml),
        },
        "baseline": {
            "total_coffee": baseline_total_coffee,
            "total_flush": baseline_total_flush,
        },
        "counter": counter,
    }


async def fetch_water_inputs(
    args: argparse.Namespace,
    serial: str,
) -> tuple[bool | None, dict[str, int]]:
    """Fetch low-water alarm and coffee/flush counters for a machine."""
    async with cloud_client(args) as client:
        machine = LaMarzoccoMachine(serial, client)
        await machine.get_dashboard()
        counter = await machine.get_coffee_and_flush_counter()

    return no_water_alarm(machine.dashboard), counter_totals(counter)


def resolve_water_state_file(args: argparse.Namespace) -> Path:
    """Resolve the water estimator state file path."""
    state_file = getattr(args, "state_file", None)
    if state_file is not None:
        return expand_path(state_file)
    return expand_path(args.config_file).parent / "water.json"


def load_water_state(path: Path) -> dict[str, Any]:
    """Load water estimator state."""
    state_file = expand_path(path)
    if not state_file.exists():
        return {"version": WATER_STATE_VERSION, "machines": {}}

    state = load_config(state_file)
    version = state.get("version", WATER_STATE_VERSION)
    if version != WATER_STATE_VERSION:
        raise CliError(f"{state_file} has unsupported water state version {version}")
    state.setdefault("version", WATER_STATE_VERSION)
    state.setdefault("machines", {})
    water_state_machines(state, state_file)
    return state


def water_state_machines(state: dict[str, Any], state_file: Path) -> dict[str, Any]:
    """Return the machines mapping from water state."""
    machines = state.get("machines")
    if not isinstance(machines, dict):
        raise CliError(f"{state_file} has invalid water machines state")
    return machines


def require_machine_water_state(
    state: dict[str, Any],
    state_file: Path,
    serial: str,
) -> dict[str, Any]:
    """Return a machine water state or raise a helpful setup error."""
    machines = water_state_machines(state, state_file)
    machine_state = machines.get(serial)
    if not isinstance(machine_state, dict):
        raise CliError(
            f"missing water baseline for {serial}; fill the tank and run "
            "`lmctl water refill` first"
        )
    if not isinstance(machine_state.get("refilled_at"), str):
        raise CliError(f"{state_file} has invalid water baseline for {serial}")
    return machine_state


def calibration_from_args(
    args: argparse.Namespace,
    state: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Resolve water estimator calibration values."""
    state = state or {}
    calibration = {
        "tank_ml": calibration_value(args, state, "tank_ml", DEFAULT_TANK_ML),
        "reserve_ml": calibration_value(args, state, "reserve_ml", DEFAULT_RESERVE_ML),
        "shot_ml": calibration_value(args, state, "shot_ml", DEFAULT_SHOT_ML),
        "flush_ml": calibration_value(args, state, "flush_ml", DEFAULT_FLUSH_ML),
    }
    if calibration["reserve_ml"] >= calibration["tank_ml"]:
        raise CliError("reserve_ml must be less than tank_ml")
    return calibration


def calibration_value(
    args: argparse.Namespace,
    state: dict[str, Any],
    name: str,
    default: float,
) -> float:
    """Return one positive calibration value from args, state, or defaults."""
    value = getattr(args, name, None)
    if value is None:
        value = state.get(name, default)
    return positive_float(value, name)


def positive_float(value: Any, name: str) -> float:
    """Return a positive float or raise a CLI error."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CliError(f"{name} must be a number") from exc
    if number <= 0:
        raise CliError(f"{name} must be greater than 0")
    return number


def non_negative_float(value: Any, name: str) -> float:
    """Return a non-negative float or raise a CLI error."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CliError(f"{name} must be a number") from exc
    if number < 0:
        raise CliError(f"{name} must be greater than or equal to 0")
    return number


def int_state_value(state: dict[str, Any], name: str, state_file: Path) -> int:
    """Read an integer value from machine water state."""
    value = state.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CliError(f"{state_file} has invalid water state field {name}")
    return value


def numeric_state_value(
    state: dict[str, Any],
    name: str,
    state_file: Path,
    *,
    default: float | None = None,
) -> float:
    """Read a numeric value from machine water state."""
    value = state.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CliError(f"{state_file} has invalid water state field {name}")
    return float(value)


def counter_totals(counter: Any) -> dict[str, int]:
    """Extract coffee and flush counters from pylamarzocco output."""
    payload = to_jsonable(counter)
    if not isinstance(payload, dict):
        raise CliError("coffee and flush counter response was not an object")

    return {
        "total_coffee": counter_value(payload, counter, "total_coffee", "totalCoffee"),
        "total_flush": counter_value(payload, counter, "total_flush", "totalFlush"),
    }


def counter_value(
    payload: dict[str, Any],
    source: Any,
    snake_name: str,
    alias: str,
) -> int:
    """Read one integer counter from a payload or object attribute."""
    if snake_name in payload:
        value = payload[snake_name]
    elif alias in payload:
        value = payload[alias]
    elif hasattr(source, snake_name):
        value = getattr(source, snake_name)
    else:
        raise CliError(f"coffee and flush counter response is missing {snake_name}")

    if isinstance(value, bool) or not isinstance(value, int):
        raise CliError(f"coffee and flush counter field {snake_name} was not an integer")
    return value


def no_water_alarm(dashboard: Any) -> bool | None:
    """Extract the binary low-water alarm when present."""
    payload = to_jsonable(dashboard)
    if not isinstance(payload, dict):
        return None

    config = payload.get("config")
    if isinstance(config, dict):
        alarm = no_water_alarm_from_widget(config.get("CMNoWater"))
        if alarm is not None:
            return alarm

    widgets = payload.get("widgets")
    if isinstance(widgets, list):
        for widget in widgets:
            if not isinstance(widget, dict):
                continue
            if widget.get("code") == "CMNoWater":
                alarm = no_water_alarm_from_widget(widget.get("output"))
                if alarm is not None:
                    return alarm

    alarm = no_water_alarm_from_widget(payload.get("CMNoWater"))
    if alarm is not None:
        return alarm
    return no_water_alarm_from_widget(payload)


def no_water_alarm_from_widget(widget: Any) -> bool | None:
    """Extract the low-water alarm flag from a widget payload."""
    if not isinstance(widget, dict):
        return None
    alarm = widget.get("allarm")
    return alarm if isinstance(alarm, bool) else None


def round_ml(value: float) -> float:
    """Round milliliter amounts for stable display and JSON output."""
    return round(value, 1)


def format_ml(value: float) -> str:
    """Format a milliliter amount for terminal output."""
    rounded = round_ml(value)
    if rounded.is_integer():
        return f"{int(rounded)} ml"
    return f"{rounded:.1f} ml"


__all__ = [
    "DEFAULT_FLUSH_ML",
    "DEFAULT_RESERVE_ML",
    "DEFAULT_SHOT_ML",
    "DEFAULT_TANK_ML",
    "EXPERIMENTAL_WARNING",
    "WATER_STATE_VERSION",
    "calibration_from_args",
    "counter_totals",
    "estimate_water",
    "fetch_water_inputs",
    "format_ml",
    "load_water_state",
    "log_water_use",
    "log_water_use_payload",
    "no_water_alarm",
    "refill_water",
    "refill_water_payload",
    "resolve_water_state_file",
    "water_estimate_payload",
]
