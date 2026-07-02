"""Grove LED actuator — responds to ambient_light/cmd."""

import logging
import time

from modules.common.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)

try:
    import grovepi
    _GROVEPI_AVAILABLE = True
except ImportError:
    _GROVEPI_AVAILABLE = False
    logger.warning("grovepi not available — LED actuator in demo mode (logs only)")


class LEDActuator:
    def __init__(self, cfg: dict, mqtt: MQTTClient):
        self._mqtt = mqtt
        self._topics = cfg["topics"]
        self._port: int = cfg["grovepi"]["led_port"]
        self._state: bool = False

        if _GROVEPI_AVAILABLE:
            try:
                grovepi.pinMode(self._port, "OUTPUT")
            except Exception as exc:
                logger.warning("LED pinMode failed: %s", exc)

    def setup_subscriptions(self) -> None:
        self._mqtt.subscribe(self._topics["actuators"]["ambient_light_cmd"], self._on_cmd)

    def _on_cmd(self, topic: str, payload: dict) -> None:
        action = payload.get("action", "off")
        self._state = action == "on"
        self._apply()
        self._mqtt.publish(
            self._topics["actuators"]["ambient_light_status"],
            {"state": "on" if self._state else "off", "ts": int(time.time())},
        )

    def _apply(self) -> None:
        if _GROVEPI_AVAILABLE:
            try:
                grovepi.digitalWrite(self._port, 1 if self._state else 0)
            except Exception as exc:
                logger.error("LED write error: %s", exc)
        logger.info("LED: %s", "ON" if self._state else "OFF")
