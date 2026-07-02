"""Grove Relay actuator — responds to cabin_heater/cmd.

Includes a software fallback mode for unreliable relay hardware.
When relay_soft_fallback is enabled in config, commands are accepted and
status is published, but no GPIO write is attempted.
"""

import logging
import time

from modules.common.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)

try:
    import grovepi
    _GROVEPI_AVAILABLE = True
except ImportError:
    _GROVEPI_AVAILABLE = False
    logger.warning("grovepi not available — relay actuator in demo mode")


class RelayActuator:
    def __init__(self, cfg: dict, mqtt: MQTTClient):
        self._mqtt = mqtt
        self._topics = cfg["topics"]
        grove = cfg["grovepi"]
        self._port: int = grove["relay_port"]
        self._soft_fallback: bool = grove.get("relay_soft_fallback", True)
        self._state: bool = False

        if _GROVEPI_AVAILABLE and not self._soft_fallback:
            try:
                grovepi.pinMode(self._port, "OUTPUT")
                logger.info("Relay: GPIO port %d configured", self._port)
            except Exception as exc:
                logger.warning("Relay pinMode failed (%s) — enabling soft fallback", exc)
                self._soft_fallback = True

    def setup_subscriptions(self) -> None:
        self._mqtt.subscribe(self._topics["actuators"]["cabin_heater_cmd"], self._on_cmd)

    def _on_cmd(self, topic: str, payload: dict) -> None:
        action = payload.get("action", "off")
        self._state = action == "on"
        self._apply()
        self._mqtt.publish(
            self._topics["actuators"]["cabin_heater_status"],
            {
                "state": "on" if self._state else "off",
                "mode": "soft_fallback" if self._soft_fallback else "hardware",
                "ts": int(time.time()),
            },
        )

    def _apply(self) -> None:
        if self._soft_fallback:
            logger.info("Relay [soft]: %s (no GPIO write)", "ON" if self._state else "OFF")
            return
        if _GROVEPI_AVAILABLE:
            try:
                grovepi.digitalWrite(self._port, 1 if self._state else 0)
                logger.info("Relay: %s", "ON" if self._state else "OFF")
            except Exception as exc:
                logger.error("Relay write error (%s) — switching to soft fallback", exc)
                self._soft_fallback = True
