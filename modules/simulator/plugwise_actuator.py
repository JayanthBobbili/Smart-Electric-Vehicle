"""Simulated Plugwise smart plug actuator (visual prop — no real Zigbee driver)."""

from __future__ import annotations

import logging
import time

from modules.common.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)


class PlugwiseActuator:
    """
    Represents two Plugwise Circle smart plugs held as visual props during the demo.
    Subscribes to the same command topic as the charger and mirrors state visually
    in the dashboard. No python-plugwise driver is used.
    """

    def __init__(self, cfg: dict, mqtt: MQTTClient):
        self._mqtt = mqtt
        self._topics = cfg["topics"]
        self._state: dict[str, str] = {
            "circle_1": "off",  # EV charger plug
            "circle_2": "off",  # Cabin heater plug (proxy)
        }

    def setup_subscriptions(self) -> None:
        self._mqtt.subscribe(self._topics["actuators"]["charging_plug_cmd"], self._on_charger_cmd)
        self._mqtt.subscribe(self._topics["actuators"]["cabin_heater_cmd"], self._on_heater_cmd)

    def _on_charger_cmd(self, topic: str, payload: dict) -> None:
        action = payload.get("action", "off")
        self._state["circle_1"] = "on" if action == "on" else "off"
        logger.info("Plugwise Circle 1 (charger): %s", self._state["circle_1"])
        self._publish_status()

    def _on_heater_cmd(self, topic: str, payload: dict) -> None:
        action = payload.get("action", "off")
        self._state["circle_2"] = "on" if action == "on" else "off"
        logger.info("Plugwise Circle 2 (heater): %s", self._state["circle_2"])
        self._publish_status()

    def _publish_status(self) -> None:
        self._mqtt.publish(
            self._topics["actuators"]["plugwise_status"],
            {"circle_1": self._state["circle_1"], "circle_2": self._state["circle_2"], "ts": int(time.time())},
        )
