"""Seat warmer state machine: OFF → WARMING → WARM."""

import logging
import time
from enum import Enum

from modules.common.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)


class SeatState(Enum):
    OFF = "off"
    WARMING = "warming"
    WARM = "warm"


_WARMUP_DURATION_SIM_MIN = 5.0  # sim-minutes to reach WARM from WARMING


class SeatWarmer:
    def __init__(self, cfg: dict, mqtt: MQTTClient):
        self._mqtt = mqtt
        self._topics = cfg["topics"]
        self._state = SeatState.OFF
        self._warmup_elapsed_sim_min: float = 0.0

    def setup_subscriptions(self) -> None:
        self._mqtt.subscribe(self._topics["actuators"]["seat_warmer_cmd"], self._on_cmd)

    def tick(self, dt_sim_minutes: float) -> None:
        if self._state == SeatState.WARMING:
            self._warmup_elapsed_sim_min += dt_sim_minutes
            if self._warmup_elapsed_sim_min >= _WARMUP_DURATION_SIM_MIN:
                self._state = SeatState.WARM
                logger.info("Seat warmer: WARM")
                self._publish()

    @property
    def state(self) -> SeatState:
        return self._state

    def _on_cmd(self, topic: str, payload: dict) -> None:
        action = payload.get("action", "")
        if action in ("on", "start") and self._state == SeatState.OFF:
            self._state = SeatState.WARMING
            self._warmup_elapsed_sim_min = 0.0
            logger.info("Seat warmer: OFF → WARMING")
        elif action in ("off", "stop"):
            self._state = SeatState.OFF
            self._warmup_elapsed_sim_min = 0.0
            logger.info("Seat warmer: → OFF")
        self._publish()

    def _publish(self) -> None:
        self._mqtt.publish(
            self._topics["actuators"]["seat_warmer_status"],
            {"state": self._state.value, "ts": int(time.time())},
        )
