"""Unit tests for ClimateModel physics."""

import unittest
from unittest.mock import MagicMock


def _make_cfg(initial_temp=10.0, k=0.02, heater_delta=0.8, outside_temp=5.0):
    return {
        "climate": {
            "initial_cabin_temp": initial_temp,
            "cooling_coefficient": k,
            "heater_delta_per_min": heater_delta,
            "seat_warmer_power_w": 150,
        },
        "hvac": {"power_w": 2000},
        "weather": {"default_outside_temp": outside_temp},
        "topics": {
            "sensors": {"cabin_temp": "sensors/cabin_temp"},
            "actuators": {
                "cabin_heater_cmd": "actuators/cabin_heater/cmd",
                "cabin_heater_status": "actuators/cabin_heater/status",
                "seat_warmer_cmd": "actuators/seat_warmer/cmd",
                "seat_warmer_status": "actuators/seat_warmer/status",
            },
        },
    }


class TestClimateModel(unittest.TestCase):

    def _make_model(self, initial_temp=10.0, outside_temp=5.0):
        from modules.simulator.climate_model import ClimateModel
        cfg = _make_cfg(initial_temp=initial_temp, outside_temp=outside_temp)
        mqtt = MagicMock()
        model = ClimateModel(cfg, mqtt)
        model.update_outside_temp(outside_temp)
        return model

    def test_passive_cooling_toward_outside(self):
        model = self._make_model(initial_temp=20.0, outside_temp=5.0)
        before = model.cabin_temp
        model.tick(10.0)
        self.assertLess(model.cabin_temp, before)

    def test_heater_warms_cabin(self):
        model = self._make_model(initial_temp=10.0, outside_temp=5.0)
        model._on_heater_cmd("", {"action": "on"})
        model.tick(5.0)
        # With heater delta 0.8 °C/min and k=0.02 cooling, should still be warmer
        self.assertGreater(model.cabin_temp, 10.0)

    def test_equilibrium_without_heater(self):
        model = self._make_model(initial_temp=5.0, outside_temp=5.0)
        before = model.cabin_temp
        model.tick(10.0)
        # At equilibrium, temp should barely change (Newton's law: delta = 0)
        self.assertAlmostEqual(model.cabin_temp, before, places=3)

    def test_heater_off_stops_warming(self):
        model = self._make_model(initial_temp=10.0, outside_temp=0.0)
        model._on_heater_cmd("", {"action": "on"})
        model.tick(5.0)
        warm = model.cabin_temp
        model._on_heater_cmd("", {"action": "off"})
        model.tick(100.0)
        self.assertLess(model.cabin_temp, warm)

    def test_seat_warmer_state(self):
        model = self._make_model()
        self.assertFalse(model.seat_warmer_on)
        model._on_seat_warmer_cmd("", {"action": "on"})
        self.assertTrue(model.seat_warmer_on)
        model._on_seat_warmer_cmd("", {"action": "off"})
        self.assertFalse(model.seat_warmer_on)

    def test_outside_temp_update(self):
        model = self._make_model(initial_temp=20.0, outside_temp=5.0)
        model.update_outside_temp(30.0)
        self.assertEqual(model.outside_temp, 30.0)


if __name__ == "__main__":
    unittest.main()
