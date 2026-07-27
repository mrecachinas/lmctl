from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from lmctl import _water as water_module
from lmctl import cli


class FakeCloudContext:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args

    async def __aenter__(self) -> object:
        return object()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        return None


class FakeCounter:
    def __init__(self, total_coffee: int, total_flush: int) -> None:
        self.total_coffee = total_coffee
        self.total_flush = total_flush

    def to_dict(self) -> dict[str, int]:
        return {
            "totalCoffee": self.total_coffee,
            "totalFlush": self.total_flush,
        }


class FakeMachine:
    total_coffee = 100
    total_flush = 10
    no_water_alarm = False
    instances: list[FakeMachine] = []

    def __init__(self, serial_number: str, cloud_client: object) -> None:
        self.serial_number = serial_number
        self.cloud_client = cloud_client
        self.dashboard: dict[str, Any] = {}
        FakeMachine.instances.append(self)

    async def get_dashboard(self) -> None:
        self.dashboard = {
            "config": {
                "CMNoWater": {
                    "allarm": self.no_water_alarm,
                },
            },
        }

    async def get_coffee_and_flush_counter(self) -> FakeCounter:
        return FakeCounter(self.total_coffee, self.total_flush)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def args_for(tmp_path: Path, **overrides: Any) -> argparse.Namespace:
    defaults: dict[str, Any] = {
        "config_file": tmp_path / "config.json",
        "serial": "SERIAL",
        "state_file": None,
        "json": False,
        "tank_ml": None,
        "reserve_ml": None,
        "shot_ml": None,
        "flush_ml": None,
        "extra_ml": 0.0,
        "amount_ml": None,
        "note": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def write_config(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def read_output_json(capsys: pytest.CaptureFixture[str]) -> Any:
    return json.loads(capsys.readouterr().out)


@pytest.fixture(autouse=True)
def fake_water_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeMachine.total_coffee = 100
    FakeMachine.total_flush = 10
    FakeMachine.no_water_alarm = False
    FakeMachine.instances = []
    monkeypatch.setattr(water_module, "cloud_client", FakeCloudContext)
    monkeypatch.setattr(water_module, "LaMarzoccoMachine", FakeMachine)


def test_refill_water_records_experimental_baseline(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_file = tmp_path / "config.json"
    write_config(config_file, {"default_serial": "SERIAL"})

    run(
        cli.refill_water(
            args_for(
                tmp_path,
                config_file=config_file,
                serial=None,
                tank_ml=1800.0,
                reserve_ml=200.0,
                shot_ml=50.0,
                flush_ml=20.0,
            )
        )
    )

    state = json.loads((tmp_path / "water.json").read_text(encoding="utf-8"))
    assert state["version"] == cli.WATER_STATE_VERSION
    assert state["machines"]["SERIAL"] | {"refilled_at": "ignored"} == {
        "refilled_at": "ignored",
        "baseline_total_coffee": 100,
        "baseline_total_flush": 10,
        "manual_usage_ml": 0.0,
        "tank_ml": 1800.0,
        "reserve_ml": 200.0,
        "shot_ml": 50.0,
        "flush_ml": 20.0,
    }
    output = capsys.readouterr().out
    assert "EXPERIMENTAL water estimate reset" in output
    assert cli.EXPERIMENTAL_WARNING in output


def test_estimate_water_uses_counters_manual_usage_and_extra_ml(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_file = tmp_path / "config.json"
    write_config(config_file, {"default_serial": "SERIAL"})
    write_config(
        tmp_path / "water.json",
        {
            "version": cli.WATER_STATE_VERSION,
            "machines": {
                "SERIAL": {
                    "refilled_at": "2026-07-26T00:00:00+00:00",
                    "baseline_total_coffee": 100,
                    "baseline_total_flush": 10,
                    "manual_usage_ml": 75.0,
                    "tank_ml": 2000.0,
                    "reserve_ml": 250.0,
                    "shot_ml": 50.0,
                    "flush_ml": 20.0,
                },
            },
        },
    )
    FakeMachine.total_coffee = 105
    FakeMachine.total_flush = 12

    run(
        cli.estimate_water(
            args_for(
                tmp_path,
                config_file=config_file,
                serial=None,
                json=True,
                extra_ml=25.0,
            )
        )
    )

    payload = read_output_json(capsys)
    assert payload["experimental"] is True
    assert payload["status"] == "ok"
    assert payload["estimated_remaining_ml"] == 1610.0
    assert payload["estimated_remaining_percent"] == 80.5
    assert payload["usage"] == {
        "coffee_count": 5,
        "coffee_ml": 250.0,
        "flush_count": 2,
        "flush_ml": 40.0,
        "manual_ml": 75.0,
        "extra_ml": 25.0,
    }


def test_estimate_water_clamps_to_reserve_when_low_water_alarm_is_active(
    tmp_path: Path,
) -> None:
    write_config(
        tmp_path / "water.json",
        {
            "version": cli.WATER_STATE_VERSION,
            "machines": {
                "SERIAL": {
                    "refilled_at": "2026-07-26T00:00:00+00:00",
                    "baseline_total_coffee": 100,
                    "baseline_total_flush": 10,
                    "manual_usage_ml": 0.0,
                    "tank_ml": 2000.0,
                    "reserve_ml": 250.0,
                    "shot_ml": 45.0,
                    "flush_ml": 30.0,
                },
            },
        },
    )
    FakeMachine.no_water_alarm = True

    payload = run(cli.water_estimate_payload(args_for(tmp_path)))

    assert payload["status"] == "needs_refill"
    assert payload["no_water_alarm"] is True
    assert payload["estimated_remaining_ml"] == 250.0


def test_log_water_use_adds_manual_usage(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_config(
        tmp_path / "water.json",
        {
            "version": cli.WATER_STATE_VERSION,
            "machines": {
                "SERIAL": {
                    "refilled_at": "2026-07-26T00:00:00+00:00",
                    "baseline_total_coffee": 100,
                    "baseline_total_flush": 10,
                    "manual_usage_ml": 75.0,
                },
            },
        },
    )

    cli.log_water_use(args_for(tmp_path, amount_ml=40.0, note="steam"))

    state = json.loads((tmp_path / "water.json").read_text(encoding="utf-8"))
    machine_state = state["machines"]["SERIAL"]
    assert machine_state["manual_usage_ml"] == 115.0
    assert machine_state["last_manual_usage_note"] == "steam"
    output = capsys.readouterr().out
    assert "EXPERIMENTAL water usage logged" in output


def test_estimate_water_requires_refill_baseline(tmp_path: Path) -> None:
    with pytest.raises(cli.CliError, match="missing water baseline"):
        run(cli.water_estimate_payload(args_for(tmp_path)))


def test_water_helpers_extract_alarm_and_counters() -> None:
    assert cli.no_water_alarm(
        {"widgets": [{"code": "CMNoWater", "output": {"allarm": True}}]}
    )
    assert cli.counter_totals(FakeCounter(12, 3)) == {
        "total_coffee": 12,
        "total_flush": 3,
    }
