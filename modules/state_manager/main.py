"""State Manager — subscribes to all sensor topics and maintains the digital twin."""

import json
import logging
import signal
import threading
import time

from modules.common.config_loader import load_config, load_schedule
from modules.common.mqtt_client import MQTTClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [state_manager] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _default_world(schedule: dict) -> dict:
    """Initial world state drawn from schedule defaults."""
    return {
        "battery_soc": 0.0,
        "target_soc": schedule.get("target_soc", 80.0),
        "cabin_temp": 20.0,
        "target_cabin_temp": schedule.get("target_cabin_temp", 22.0),
        "cabin_humidity": 50.0,
        "outside_temp": 5.0,
        "occupancy": False,
        "departure_time": schedule.get("departure_time"),
        "minutes_remaining": 60.0,
        "charging": False,
        "hvac_on": False,
        "seat_warmer_on": False,
        "lights_on": False,
        "route_loaded": False,
        "charger_available": True,
        "last_event": None,
        "last_updated": time.time(),
    }


class StateManager:
    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._topics = cfg["topics"]
        broker = cfg["broker"]

        schedule = load_schedule()
        self._world: dict = _default_world(schedule)

        self._mqtt = MQTTClient("ev-state-manager", broker["host"], broker["port"], broker["keepalive"])

    def run(self) -> None:
        self._mqtt.connect()
        self._setup_subscriptions()
        logger.info("State manager running — listening for sensor data")

        stop = threading.Event()

        def _handler(sig, frame):
            stop.set()

        signal.signal(signal.SIGINT, _handler)
        try:
            signal.signal(signal.SIGTERM, _handler)
        except (OSError, AttributeError):
            pass
        stop.wait()

        self._mqtt.disconnect()
        logger.info("State manager stopped.")

    def _setup_subscriptions(self) -> None:
        t = self._topics
        self._mqtt.subscribe(t["sensors"]["battery_soc"], self._on_battery_soc)
        self._mqtt.subscribe(t["sensors"]["cabin_temp"], self._on_cabin_temp)
        self._mqtt.subscribe(t["sensors"]["cabin_humidity"], self._on_cabin_humidity)
        self._mqtt.subscribe(t["sensors"]["occupancy"], self._on_occupancy)
        self._mqtt.subscribe(t["sensors"]["outside_temp"], self._on_outside_temp)
        self._mqtt.subscribe(t["sensors"]["departure_time"], self._on_departure_time)
        self._mqtt.subscribe(t["actuators"]["charging_plug_status"], self._on_charging_status)
        self._mqtt.subscribe(t["actuators"]["cabin_heater_status"], self._on_heater_status)
        self._mqtt.subscribe(t["actuators"]["seat_warmer_status"], self._on_seat_warmer_status)
        self._mqtt.subscribe(t["actuators"]["ambient_light_status"], self._on_lights_status)
        self._mqtt.subscribe(t["actuators"]["infotainment_status"], self._on_infotainment_status)
        self._mqtt.subscribe_wildcard("events/#", self._on_event)

    # ------------------------------------------------------------------
    # Sensor handlers
    # ------------------------------------------------------------------

    def _on_battery_soc(self, topic: str, payload: dict) -> None:
        self._update("battery_soc", payload.get("value"))

    def _on_cabin_temp(self, topic: str, payload: dict) -> None:
        source = payload.get("source", "unknown")
        value = payload.get("value")
        if value is None:
            return
        # Prefer real Grove DHT reading; suppress simulator if real reading is fresh (< 10s)
        existing = self._world.get("cabin_temp_source")
        if existing == "grove_dht" and source == "simulator":
            age = time.time() - self._world.get("cabin_temp_ts", 0)
            if age < 10:
                return
        # Update all fields before a single publish
        self._world["cabin_temp"] = value
        self._world["cabin_temp_source"] = source
        self._world["cabin_temp_ts"] = time.time()
        self._world["last_updated"] = time.time()
        self._publish()

    def _on_cabin_humidity(self, topic: str, payload: dict) -> None:
        self._update("cabin_humidity", payload.get("value"))

    def _on_occupancy(self, topic: str, payload: dict) -> None:
        self._update("occupancy", payload.get("value"))

    def _on_outside_temp(self, topic: str, payload: dict) -> None:
        self._update("outside_temp", payload.get("value"))

    def _on_departure_time(self, topic: str, payload: dict) -> None:
        self._world["departure_time"] = payload.get("value")
        self._world["minutes_remaining"] = payload.get("minutes_remaining", self._world["minutes_remaining"])
        self._world["last_updated"] = time.time()
        self._publish()

    # ------------------------------------------------------------------
    # Actuator status handlers
    # ------------------------------------------------------------------

    def _on_charging_status(self, topic: str, payload: dict) -> None:
        state = payload.get("state", "off")
        self._world["charging"] = state == "on"
        self._world["charger_available"] = state != "fault"
        self._publish()

    def _on_heater_status(self, topic: str, payload: dict) -> None:
        self._world["hvac_on"] = payload.get("state") == "on"
        self._publish()

    def _on_seat_warmer_status(self, topic: str, payload: dict) -> None:
        self._world["seat_warmer_on"] = payload.get("state") in ("on", "warming", "warm")
        self._publish()

    def _on_lights_status(self, topic: str, payload: dict) -> None:
        self._world["lights_on"] = payload.get("state") == "on"
        self._publish()

    def _on_infotainment_status(self, topic: str, payload: dict) -> None:
        self._world["route_loaded"] = payload.get("state") == "route_loaded"
        self._publish()

    def _on_event(self, topic: str, payload: dict) -> None:
        self._world["last_event"] = {"topic": topic, "payload": payload, "ts": time.time()}
        self._publish()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update(self, key: str, value) -> None:
        if value is not None:
            self._world[key] = value
            self._world["last_updated"] = time.time()
            self._publish()

    def _publish(self) -> None:
        self._mqtt.publish(self._topics["state"]["current"], self._world)


def main() -> None:
    cfg = load_config()
    StateManager(cfg).run()


if __name__ == "__main__":
    main()
