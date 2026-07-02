"""Grove DHT11/22 temperature & humidity sensor via GrovePi."""

from __future__ import annotations

import logging
import threading
import time

from modules.common.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)

# If a manual override console is publishing cabin temp/humidity, this sensor steps
# aside for this many seconds after each "active" control message. The console
# re-sends ~1/s, so the sensor auto-resumes within this window if the console stops.
_OVERRIDE_TTL_S = 5.0

try:
    import grovepi
    _GROVEPI_AVAILABLE = True
except ImportError:
    _GROVEPI_AVAILABLE = False
    logger.warning("grovepi not available — DHT sensor running in demo mode (constant values)")


class DHTSensor:
    def __init__(self, cfg: dict, mqtt: MQTTClient):
        self._mqtt = mqtt
        self._topics = cfg["topics"]
        grove = cfg["grovepi"]
        self._port: int = grove["dht_port"]
        # 0 = DHT11 (GrovePi starter kit), 1 = DHT22 — set dht_type in config.yaml
        self._dht_type: int = int(grove.get("dht_type", 0))
        self._poll_interval_s: float = grove["dht_poll_interval_s"]
        self._stop_event = threading.Event()

        # Manual-override "step aside": when an override console is publishing cabin
        # temp/humidity, stop publishing here to avoid two writers on the same topic.
        self._override_until: float = 0.0
        override_topic = self._topics.get("control", {}).get("dht_override")
        if override_topic:
            self._mqtt.subscribe(override_topic, self._on_override)

    def _on_override(self, topic: str, payload: dict) -> None:
        if isinstance(payload, dict) and payload.get("active"):
            self._override_until = time.time() + _OVERRIDE_TTL_S
        else:
            self._override_until = 0.0

    def start(self) -> None:
        t = threading.Thread(target=self._loop, daemon=True, name="dht-sensor")
        t.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._read_and_publish()
            self._stop_event.wait(self._poll_interval_s)

    def _read_and_publish(self) -> None:
        if time.time() < self._override_until:
            return  # an override console owns cabin temp/humidity right now — step aside
        temp, humidity = self._read()
        if temp is None:
            return

        ts = int(time.time())
        self._mqtt.publish(
            self._topics["sensors"]["cabin_temp"],
            {"value": round(temp, 1), "unit": "C", "ts": ts, "source": "grove_dht"},
        )
        self._mqtt.publish(
            self._topics["sensors"]["cabin_humidity"],
            {"value": round(humidity, 1), "unit": "%", "ts": ts},
        )
        logger.debug("DHT: temp=%.1f°C, humidity=%.1f%%", temp, humidity)

    def _read(self) -> tuple[float | None, float | None]:
        if not _GROVEPI_AVAILABLE:
            # Constant demo values so the system shows sensor activity without hardware
            return 21.5, 55.0
        try:
            # grovepi.dht() may return [temp, humidity] or [temp, humidity, crc]
            # depending on the library version; use indexing to avoid unpack errors
            result = grovepi.dht(self._port, self._dht_type)
            temp = float(result[0])
            humidity = float(result[1])
            return temp, humidity
        except Exception as exc:
            logger.error("DHT read error: %s", exc)
            return None, None
