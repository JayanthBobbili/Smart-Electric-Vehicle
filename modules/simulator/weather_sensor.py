"""Fetches outside temperature from Open-Meteo free API for Stuttgart."""

import logging
import threading
import time

import requests

from modules.common.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)


class WeatherSensor:
    def __init__(self, cfg: dict, mqtt: MQTTClient):
        self._mqtt = mqtt
        self._topics = cfg["topics"]
        weather = cfg["weather"]
        self._api_url: str = weather["api_url"]
        self._lat: float = weather["latitude"]
        self._lon: float = weather["longitude"]
        self._default_temp: float = weather["default_outside_temp"]
        self._refresh_interval_s: float = weather["refresh_interval_s"]
        self._current_temp: float = self._default_temp
        self._stop_event = threading.Event()

    @property
    def current_temp(self) -> float:
        return self._current_temp

    def start(self) -> None:
        self._fetch_and_publish()
        t = threading.Thread(target=self._loop, daemon=True, name="weather-sensor")
        t.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(self._refresh_interval_s)
            if not self._stop_event.is_set():
                self._fetch_and_publish()

    def _fetch_and_publish(self) -> None:
        temp = self._fetch()
        self._current_temp = temp
        self._mqtt.publish(
            self._topics["sensors"]["outside_temp"],
            {"value": round(temp, 1), "unit": "C", "ts": int(time.time()), "source": "open_meteo"},
        )

    def _fetch(self) -> float:
        try:
            resp = requests.get(
                self._api_url,
                params={
                    "latitude": self._lat,
                    "longitude": self._lon,
                    "current_weather": "true",
                    "temperature_unit": "celsius",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            temp = data["current_weather"]["temperature"]
            logger.info("Weather: outside temp = %.1f°C", temp)
            return float(temp)
        except Exception as exc:
            logger.warning("Weather API unavailable (%s); using default %.1f°C", exc, self._default_temp)
            return self._default_temp
