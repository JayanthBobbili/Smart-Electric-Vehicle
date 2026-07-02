"""Unit tests for the PDDL problem generator."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _make_cfg():
    return {
        "broker": {"host": "localhost", "port": 1883, "keepalive": 60},
        "battery": {
            "initial_soc": 50.0,
            "charge_rate_kw": 3.7,
            "slow_charge_rate_kw": 1.85,
            "capacity_kwh": 10.0,
            "taper_threshold": 80.0,
        },
        "climate": {
            "initial_cabin_temp": 10.0,
            "cooling_coefficient": 0.02,
            "heater_delta_per_min": 0.8,
            "seat_warmer_power_w": 150,
        },
        "hvac": {"power_w": 2000},
        "power": {"max_power_w": 5750},
        "topics": {
            "sensors": {},
            "state": {"current": "state/current"},
            "planning": {"problem": "planning/problem"},
            "actuators": {},
            "events": {},
        },
    }


class TestProblemGenerator(unittest.TestCase):

    def _make_generator(self):
        from modules.problem_generator.main import ProblemGenerator
        cfg = _make_cfg()
        with patch("modules.problem_generator.main.MQTTClient"):
            gen = ProblemGenerator(cfg)
        return gen

    def test_state_changed_first_time(self):
        gen = self._make_generator()
        gen._world = {"battery_soc": 40.0, "cabin_temp": 10.0, "minutes_remaining": 60.0}
        self.assertTrue(gen._state_changed_meaningfully())

    def test_no_meaningful_change_within_threshold(self):
        gen = self._make_generator()
        gen._world = {"battery_soc": 40.5, "cabin_temp": 10.1, "minutes_remaining": 60.3}
        gen._last_generated = {"battery_soc": 40.0, "cabin_temp": 10.0, "minutes_remaining": 60.0}
        self.assertFalse(gen._state_changed_meaningfully())

    def test_soc_change_triggers_new_problem(self):
        gen = self._make_generator()
        gen._world         = {"battery_soc": 42.0, "cabin_temp": 10.0, "minutes_remaining": 60.0}
        gen._last_generated = {"battery_soc": 40.0, "cabin_temp": 10.0, "minutes_remaining": 60.0}
        self.assertTrue(gen._state_changed_meaningfully())

    def test_charge_rate_taper_below_80(self):
        gen = self._make_generator()
        gen._world = {"battery_soc": 60.0, "target_soc": 80.0, "cabin_temp": 15.0,
                      "target_cabin_temp": 22.0, "outside_temp": 5.0, "minutes_remaining": 45.0,
                      "charging": False, "hvac_on": False, "seat_warmer_on": False,
                      "lights_on": False, "route_loaded": False, "charger_available": True}
        gen._mqtt = MagicMock()
        gen._generate_and_publish()
        call_args = gen._mqtt.publish.call_args
        pddl = call_args[0][1]["pddl"]
        # Rate at 60% SoC should match fast rate
        expected_rate = gen._fast_charge_pct_per_min
        self.assertIn(str(round(expected_rate, 4)), pddl)

    def test_pddl_contains_goal(self):
        gen = self._make_generator()
        gen._world = {"battery_soc": 40.0, "target_soc": 80.0, "cabin_temp": 10.0,
                      "target_cabin_temp": 22.0, "outside_temp": 5.0, "minutes_remaining": 60.0,
                      "charging": False, "hvac_on": False, "seat_warmer_on": False,
                      "lights_on": False, "route_loaded": False, "charger_available": True}
        gen._mqtt = MagicMock()
        gen._generate_and_publish()
        pddl = gen._mqtt.publish.call_args[0][1]["pddl"]
        self.assertIn("(:goal", pddl)
        self.assertIn("battery-soc", pddl)
        self.assertIn("route-loaded", pddl)


if __name__ == "__main__":
    unittest.main()
