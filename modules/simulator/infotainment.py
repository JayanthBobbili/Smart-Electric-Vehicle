"""Virtual infotainment / route loader actuator."""

import logging
import time

from modules.common.config_loader import load_schedule
from modules.common.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)


class Infotainment:
    def __init__(self, cfg: dict, mqtt: MQTTClient):
        self._mqtt = mqtt
        self._topics = cfg["topics"]
        self._route_loaded: bool = False
        self._destination: str = load_schedule().get("destination", "Unknown")

    def setup_subscriptions(self) -> None:
        self._mqtt.subscribe(self._topics["actuators"]["infotainment_cmd"], self._on_cmd)

    @property
    def route_loaded(self) -> bool:
        return self._route_loaded

    def _on_cmd(self, topic: str, payload: dict) -> None:
        action = payload.get("action", "")
        if action == "load_route":
            destination = payload.get("destination", self._destination)
            self._route_loaded = True
            logger.info("Infotainment: route loaded → %s", destination)
            self._mqtt.publish(
                self._topics["actuators"]["infotainment_status"],
                {"state": "route_loaded", "destination": destination, "ts": int(time.time())},
            )
        elif action == "off":
            self._route_loaded = False
            self._mqtt.publish(
                self._topics["actuators"]["infotainment_status"],
                {"state": "off", "ts": int(time.time())},
            )
