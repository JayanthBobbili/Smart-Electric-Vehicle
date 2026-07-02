"""Grove PIR motion sensor — publishes seat occupancy."""

from __future__ import annotations

import logging
import threading
import time

from modules.common.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)

# Seconds this sensor steps aside after each "active" occupancy-override message
# (the override console re-sends ~1/s, so it auto-resumes if the console stops).
_OVERRIDE_TTL_S = 5.0

try:
    import grovepi
    _GROVEPI_AVAILABLE = True
except ImportError:
    _GROVEPI_AVAILABLE = False
    logger.warning("grovepi not available — PIR sensor running in demo mode")


class PIRSensor:
    def __init__(self, cfg: dict, mqtt: MQTTClient):
        self._mqtt = mqtt
        self._topics = cfg["topics"]
        grove = cfg["grovepi"]
        self._port: int = grove["pir_port"]
        self._poll_interval_s: float = grove["pir_poll_interval_s"]
        self._last_state: bool | None = None
        self._stop_event = threading.Event()
        self._simulated_occupied: bool = False

        # Manual-override "step aside": while an override console owns occupancy, this
        # sensor stops publishing so the console is the sole writer on the topic.
        self._override_until: float = 0.0

        if _GROVEPI_AVAILABLE:
            try:
                grovepi.pinMode(self._port, "INPUT")
            except Exception as exc:
                logger.warning("PIR pinMode failed: %s", exc)

        # Listen for dashboard-injected "user arrives early" trigger (topic from config)
        self._mqtt.subscribe(self._topics["events"]["user_arrives"], self._on_user_arrives)
        # Listen for the override console's "step aside" signal (topic from config)
        occ_override_topic = self._topics.get("control", {}).get("occupancy_override")
        if occ_override_topic:
            self._mqtt.subscribe(occ_override_topic, self._on_occ_override)

    def _on_occ_override(self, topic: str, payload: dict) -> None:
        if isinstance(payload, dict) and payload.get("active"):
            self._override_until = time.time() + _OVERRIDE_TTL_S
        else:
            self._override_until = 0.0
            self._last_state = None  # force a republish of the true state on resume

    def start(self) -> None:
        t = threading.Thread(target=self._loop, daemon=True, name="pir-sensor")
        t.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            if time.time() < self._override_until:
                # an override console owns occupancy right now — step aside
                self._stop_event.wait(self._poll_interval_s)
                continue
            state = self._read()
            if state != self._last_state:
                self._last_state = state
                self._publish(state)
            self._stop_event.wait(self._poll_interval_s)

    def _read(self) -> bool:
        if self._simulated_occupied:
            return True
        if not _GROVEPI_AVAILABLE:
            return False
        try:
            return bool(grovepi.digitalRead(self._port))
        except Exception as exc:
            logger.error("PIR read error: %s", exc)
            return False

    def _publish(self, occupied: bool) -> None:
        self._mqtt.publish(
            self._topics["sensors"]["occupancy"],
            {"value": occupied, "ts": int(time.time()), "source": "grove_pir"},
        )
        logger.info("PIR: occupancy = %s", occupied)

    def _on_user_arrives(self, topic: str, payload: dict) -> None:
        self._simulated_occupied = payload.get("occupied", True)
        logger.info("PIR: simulated occupancy set to %s", self._simulated_occupied)
