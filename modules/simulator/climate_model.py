"""Cabin temperature simulation via Newton's law of cooling + heater delta."""

import logging
import time

from modules.common.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)


class ClimateModel:
    def __init__(self, cfg: dict, mqtt: MQTTClient):
        self._mqtt = mqtt
        self._topics = cfg["topics"]
        climate = cfg["climate"]
        hvac_cfg = cfg["hvac"]

        self.cabin_temp: float = climate["initial_cabin_temp"]
        self._k: float = climate["cooling_coefficient"]
        self._heater_delta: float = climate["heater_delta_per_min"]
        self._seat_warmer_power_w: float = climate["seat_warmer_power_w"]
        self._hvac_power_w: float = hvac_cfg["power_w"]

        self._outside_temp: float = cfg["weather"]["default_outside_temp"]
        self._is_heating: bool = False
        self._seat_warmer_on: bool = False

    def update_outside_temp(self, temp: float) -> None:
        self._outside_temp = temp

    @property
    def outside_temp(self) -> float:
        return self._outside_temp

    @property
    def is_heating(self) -> bool:
        return self._is_heating

    @property
    def seat_warmer_on(self) -> bool:
        return self._seat_warmer_on

    def setup_subscriptions(self) -> None:
        self._mqtt.subscribe(self._topics["actuators"]["cabin_heater_cmd"], self._on_heater_cmd)
        self._mqtt.subscribe(self._topics["actuators"]["seat_warmer_cmd"], self._on_seat_warmer_cmd)

    def tick(self, dt_sim_minutes: float) -> None:
        """Advance climate simulation by dt_sim_minutes of virtual time."""
        # Newton cooling: passive drift toward outside temperature
        dt = dt_sim_minutes
        self.cabin_temp += self._k * (self._outside_temp - self.cabin_temp) * dt

        # Active heating from HVAC
        if self._is_heating:
            self.cabin_temp += self._heater_delta * dt

        self._publish()

    def _publish(self) -> None:
        self._mqtt.publish(
            self._topics["sensors"]["cabin_temp"],
            {"value": round(self.cabin_temp, 2), "unit": "C", "ts": int(time.time()), "source": "simulator"},
        )

    def _on_heater_cmd(self, topic: str, payload: dict) -> None:
        action = payload.get("action", "")
        self._is_heating = action == "on"
        logger.info("Climate: HVAC %s (cabin=%.1f°C)", "started" if self._is_heating else "stopped", self.cabin_temp)
        self._mqtt.publish(
            self._topics["actuators"]["cabin_heater_status"],
            {"state": "on" if self._is_heating else "off", "ts": int(time.time())},
        )

    def _on_seat_warmer_cmd(self, topic: str, payload: dict) -> None:
        action = payload.get("action", "")
        self._seat_warmer_on = action in ("on", "start")
        logger.info("Climate: seat warmer %s", "on" if self._seat_warmer_on else "off")
        self._mqtt.publish(
            self._topics["actuators"]["seat_warmer_status"],
            {"state": "on" if self._seat_warmer_on else "off", "ts": int(time.time())},
        )
