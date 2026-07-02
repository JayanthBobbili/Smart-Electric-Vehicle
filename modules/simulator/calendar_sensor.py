"""Counts down sim-minutes until departure and publishes the sensor reading."""

import logging
import time

from modules.common.config_loader import load_schedule, save_schedule
from modules.common.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)


class CalendarSensor:
    """
    Tracks simulation time remaining until departure.

    The schedule defines `sim_minutes_until_departure` — the number of
    simulation-minutes from simulator start to departure.  Each tick
    decrements the counter by dt_sim_minutes (tick_interval × time_scale / 60).

    `departure_time` in schedule.json is kept as a human-readable label;
    the countdown itself is purely simulation-relative.
    """

    def __init__(self, cfg: dict, mqtt: MQTTClient):
        self._mqtt = mqtt
        self._topics = cfg["topics"]
        self._time_scale: int = cfg["simulation"]["time_scale"]

        schedule = load_schedule()
        self._sim_minutes_remaining: float = float(schedule.get("sim_minutes_until_departure", 60.0))
        self._departure_str: str = schedule.get("departure_time", "")

        self._mqtt.subscribe(self._topics["events"]["calendar_shift"], self._on_calendar_shift)

    def tick(self, dt_sim_minutes: float) -> float:
        """Decrement counter and publish; returns current sim-minutes remaining."""
        self._sim_minutes_remaining = max(0.0, self._sim_minutes_remaining - dt_sim_minutes)
        self._publish()
        return self._sim_minutes_remaining

    def get_minutes_remaining(self) -> float:
        return self._sim_minutes_remaining

    def _publish(self) -> None:
        self._mqtt.publish(
            self._topics["sensors"]["departure_time"],
            {
                "value": self._departure_str,
                "minutes_remaining": round(self._sim_minutes_remaining, 2),
                "ts": int(time.time()),
            },
        )

    def _on_calendar_shift(self, topic: str, payload: dict) -> None:
        # shift_sim_minutes: signed sim-minute delta (negative = earlier departure)
        shift_sim = payload.get("shift_sim_minutes", 0)
        if shift_sim:
            self._sim_minutes_remaining = max(0.0, self._sim_minutes_remaining + shift_sim)
            logger.info(
                "Calendar: departure shifted by %+.0f sim-min → %.1f sim-min remaining",
                shift_sim, self._sim_minutes_remaining,
            )
            schedule = load_schedule()
            schedule["sim_minutes_until_departure"] = self._sim_minutes_remaining
            save_schedule(schedule)
            self._publish()  # propagate updated time immediately, not waiting for next tick
