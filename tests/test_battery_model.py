"""Unit tests for BatteryModel physics."""

import types
import unittest
from unittest.mock import MagicMock


def _make_cfg(initial_soc=50.0, charge_rate_kw=3.7, slow_kw=1.85, capacity=10.0, taper=80.0, time_scale=60):
    return {
        "battery": {
            "initial_soc": initial_soc,
            "charge_rate_kw": charge_rate_kw,
            "slow_charge_rate_kw": slow_kw,
            "capacity_kwh": capacity,
            "taper_threshold": taper,
        },
        "simulation": {"time_scale": time_scale, "tick_interval_s": 1.0},
        "topics": {
            "sensors": {"battery_soc": "sensors/battery_soc"},
            "actuators": {
                "charging_plug_cmd": "actuators/charging_plug/cmd",
                "charging_plug_status": "actuators/charging_plug/status",
            },
            "events": {"charger_fault": "events/charger_fault"},
        },
    }


class TestBatteryModel(unittest.TestCase):

    def _make_model(self, initial_soc=40.0):
        from modules.simulator.battery_model import BatteryModel
        cfg = _make_cfg(initial_soc=initial_soc)
        mqtt = MagicMock()
        return BatteryModel(cfg, mqtt)

    def test_no_charge_when_idle(self):
        model = self._make_model(40.0)
        model.tick(1.0)
        self.assertAlmostEqual(model.soc, 40.0, places=4)

    def test_charge_increases_soc(self):
        model = self._make_model(40.0)
        model._on_charging_cmd("actuators/charging_plug/cmd", {"action": "on"})
        before = model.soc
        model.tick(5.0)
        self.assertGreater(model.soc, before)

    def test_taper_above_80(self):
        model = self._make_model(85.0)
        model._on_charging_cmd("", {"action": "on"})
        fast_rate = model._fast_rate_pct_per_min
        rate_at_85 = model._charge_rate_pct_per_min()
        self.assertLess(rate_at_85, fast_rate)

    def test_taper_full_at_threshold(self):
        model = self._make_model(80.0)
        rate_at_80 = model._charge_rate_pct_per_min()
        self.assertAlmostEqual(rate_at_80, model._slow_rate_pct_per_min, places=4)

    def test_soc_caps_at_100(self):
        model = self._make_model(99.9)
        model._on_charging_cmd("", {"action": "on"})
        model.tick(100.0)
        self.assertLessEqual(model.soc, 100.0)

    def test_charger_fault_stops_charging(self):
        model = self._make_model(50.0)
        model._on_charging_cmd("", {"action": "on"})
        self.assertTrue(model.is_charging)
        model._on_charger_fault("events/charger_fault", {})
        self.assertFalse(model.is_charging)
        self.assertFalse(model.charger_available)

    def test_stop_charging_cmd(self):
        model = self._make_model(50.0)
        model._on_charging_cmd("", {"action": "on"})
        model._on_charging_cmd("", {"action": "off"})
        before = model.soc
        model.tick(10.0)
        self.assertAlmostEqual(model.soc, before, places=4)

    def test_restore_charger(self):
        model = self._make_model(50.0)
        model._on_charger_fault("", {})
        self.assertFalse(model.charger_available)
        model.restore_charger()
        self.assertTrue(model.charger_available)


if __name__ == "__main__":
    unittest.main()
