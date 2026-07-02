"""Unit tests for StateManager world state updates."""

import os
import sys
import time
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def _make_cfg():
    return {
        "broker": {"host": "localhost", "port": 1883, "keepalive": 60},
        "topics": {
            "sensors": {
                "battery_soc": "sensors/battery_soc",
                "cabin_temp": "sensors/cabin_temp",
                "cabin_humidity": "sensors/cabin_humidity",
                "occupancy": "sensors/occupancy",
                "outside_temp": "sensors/outside_temp",
                "departure_time": "sensors/departure_time",
            },
            "actuators": {
                "charging_plug_status": "actuators/charging_plug/status",
                "cabin_heater_status": "actuators/cabin_heater/status",
                "seat_warmer_status": "actuators/seat_warmer/status",
                "ambient_light_status": "actuators/ambient_light/status",
                "infotainment_status": "actuators/infotainment/status",
            },
            "state": {"current": "state/current"},
        },
    }


def _make_schedule():
    return {"departure_time": "2026-06-24T08:00:00", "target_soc": 80.0, "target_cabin_temp": 22.0}


class TestStateManager(unittest.TestCase):

    def _make_sm(self):
        from modules.state_manager.main import StateManager
        cfg = _make_cfg()
        with patch("modules.state_manager.main.MQTTClient"), \
             patch("modules.state_manager.main.load_schedule", return_value=_make_schedule()):
            sm = StateManager(cfg)
            sm._mqtt = MagicMock()
        return sm

    def test_battery_soc_update(self):
        sm = self._make_sm()
        sm._on_battery_soc("sensors/battery_soc", {"value": 55.3, "ts": int(time.time())})
        self.assertAlmostEqual(sm._world["battery_soc"], 55.3)

    def test_cabin_temp_real_priority(self):
        sm = self._make_sm()
        # First a real reading
        sm._on_cabin_temp("sensors/cabin_temp", {"value": 18.0, "ts": int(time.time()), "source": "grove_dht"})
        self.assertEqual(sm._world["cabin_temp_source"], "grove_dht")
        # Simulator reading should be ignored within 10s
        sm._on_cabin_temp("sensors/cabin_temp", {"value": 25.0, "ts": int(time.time()), "source": "simulator"})
        self.assertAlmostEqual(sm._world["cabin_temp"], 18.0)

    def test_occupancy_update(self):
        sm = self._make_sm()
        sm._on_occupancy("sensors/occupancy", {"value": True, "ts": int(time.time())})
        self.assertTrue(sm._world["occupancy"])

    def test_charger_fault_sets_unavailable(self):
        sm = self._make_sm()
        sm._on_charging_status("actuators/charging_plug/status", {"state": "fault", "ts": int(time.time())})
        self.assertFalse(sm._world["charger_available"])
        self.assertFalse(sm._world["charging"])

    def test_hvac_status_update(self):
        sm = self._make_sm()
        sm._on_heater_status("actuators/cabin_heater/status", {"state": "on", "ts": int(time.time())})
        self.assertTrue(sm._world["hvac_on"])
        sm._on_heater_status("actuators/cabin_heater/status", {"state": "off", "ts": int(time.time())})
        self.assertFalse(sm._world["hvac_on"])

    def test_route_loaded(self):
        sm = self._make_sm()
        sm._on_infotainment_status("actuators/infotainment/status", {"state": "route_loaded"})
        self.assertTrue(sm._world["route_loaded"])

    def test_event_recorded(self):
        sm = self._make_sm()
        sm._on_event("events/charger_fault", {"reason": "test"})
        self.assertIsNotNone(sm._world["last_event"])
        self.assertEqual(sm._world["last_event"]["topic"], "events/charger_fault")

    def test_publish_called_on_update(self):
        sm = self._make_sm()
        sm._on_battery_soc("sensors/battery_soc", {"value": 42.0})
        sm._mqtt.publish.assert_called()


if __name__ == "__main__":
    unittest.main()
