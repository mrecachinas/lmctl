"""Output formatting helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def json_text(value: str | bytes | bytearray) -> str:
    """Return JSON data as text."""
    if isinstance(value, str):
        return value
    return bytes(value).decode("utf-8")


def print_json(value: Any) -> None:
    """Print a value as pretty JSON."""
    print(json.dumps(to_jsonable(value), indent=2, sort_keys=True))


def wants_json(args: Any) -> bool:
    """Return whether this invocation requested JSON output."""
    return bool(getattr(args, "json", False))


def print_key_values(value: Any, *, title: str | None = None) -> None:
    """Print a nested value as a two-column field/value table."""
    if title:
        print(title)
    print_table(("field", "value"), list(flatten_key_values(to_jsonable(value))))


def print_machine_sections(value: Any) -> None:
    """Print a machine payload with top-level sections."""
    payload = to_jsonable(value)
    if not isinstance(payload, dict):
        print_key_values(payload)
        return

    scalar_rows: list[tuple[str, Any]] = []
    sections: list[tuple[str, Any]] = []
    for key, item in payload.items():
        if isinstance(item, dict | list):
            sections.append((display_value(key), item))
        else:
            scalar_rows.append((display_value(key), item))

    wrote_section = False
    if scalar_rows:
        print_table(("field", "value"), scalar_rows)
        wrote_section = True

    for title, section in sections:
        if wrote_section:
            print()
        print_key_values(section, title=title)
        wrote_section = True


def flatten_key_values(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Flatten nested JSON-compatible values into table rows."""
    if isinstance(value, dict):
        if not value and prefix:
            return [(prefix, "{}")]

        rows: list[tuple[str, str]] = []
        for key, item in value.items():
            field = display_value(key)
            nested_prefix = f"{prefix}.{field}" if prefix else field
            rows.extend(flatten_key_values(item, nested_prefix))
        return rows

    if isinstance(value, list):
        if not value:
            return [(prefix, "[]")]

        rows = []
        for index, item in enumerate(value):
            nested_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            rows.extend(flatten_key_values(item, nested_prefix))
        return rows

    return [(prefix, display_value(value))]


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

    print(
        "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers))
    )
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
