"""Battery SoC simulation with CC-CV charging taper above 80% SoC."""

import logging
import time

from modules.common.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)


class BatteryModel:
    def __init__(self, cfg: dict, mqtt: MQTTClient):
        self._mqtt = mqtt
        self._topics = cfg["topics"]
        sim = cfg["simulation"]
        bat = cfg["battery"]

        self.soc: float = bat["initial_soc"]
        self._taper_threshold: float = bat["taper_threshold"]
        self._capacity_kwh: float = bat["capacity_kwh"]

        # Convert charge rate from kW to % SoC gain per simulation-minute
        # kW → kWh per sim-minute = kW / 60
        # kWh per sim-minute → % SoC per sim-minute = (kWh / capacity) * 100
        self._fast_rate_pct_per_min: float = (bat["charge_rate_kw"] / 60.0 / bat["capacity_kwh"]) * 100.0
        self._slow_rate_pct_per_min: float = (bat["slow_charge_rate_kw"] / 60.0 / bat["capacity_kwh"]) * 100.0

        self._time_scale: int = sim["time_scale"]
        self._is_charging: bool = False
        self._charger_available: bool = True

    def setup_subscriptions(self) -> None:
        self._mqtt.subscribe(self._topics["actuators"]["charging_plug_cmd"], self._on_charging_cmd)
        self._mqtt.subscribe(self._topics["events"]["charger_fault"], self._on_charger_fault)
        self._mqtt.subscribe(self._topics["events"]["replan"], self._on_replan)

    def tick(self, dt_sim_minutes: float) -> None:
        """Advance simulation by dt_sim_minutes of virtual time."""
        if self._is_charging and self._charger_available and self.soc < 100.0:
            rate = self._charge_rate_pct_per_min()
            self.soc = min(100.0, self.soc + rate * dt_sim_minutes)

        self._publish()

    def current_charge_rate_pct_per_min(self) -> float:
        """Return the effective charge rate for PDDL problem generation."""
        return self._charge_rate_pct_per_min()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _charge_rate_pct_per_min(self) -> float:
        if self.soc < self._taper_threshold:
            return self._fast_rate_pct_per_min
        # Linear taper: full rate at 80%, zero rate at 100%
        fraction = 1.0 - (self.soc - self._taper_threshold) / (100.0 - self._taper_threshold)
        return self._slow_rate_pct_per_min * fraction

    def _publish(self) -> None:
        self._mqtt.publish(
            self._topics["sensors"]["battery_soc"],
            {"value": round(self.soc, 2), "unit": "%", "ts": int(time.time()), "source": "simulator"},
        )

    def _on_charging_cmd(self, topic: str, payload: dict) -> None:
        action = payload.get("action", "")
        if action == "on":
            self._is_charging = True
            logger.info("Battery: charging started (SoC=%.1f%%)", self.soc)
        elif action == "off":
            self._is_charging = False
            logger.info("Battery: charging stopped (SoC=%.1f%%)", self.soc)
        self._mqtt.publish(
            self._topics["actuators"]["charging_plug_status"],
            {"state": "on" if self._is_charging else "off", "ts": int(time.time())},
        )

    def _on_charger_fault(self, topic: str, payload: dict) -> None:
        self._is_charging = False
        self._charger_available = False
        logger.warning("Battery: charger fault received — charging disabled")
        self._mqtt.publish(
            self._topics["actuators"]["charging_plug_status"],
            {"state": "fault", "ts": int(time.time())},
        )

    def _on_replan(self, topic: str, payload: dict) -> None:
        # A replan request doubles as "charger reconnected": clear any latched fault
        # so the planner can schedule charging again. Republishing an "off" (i.e. not
        # faulted) status lets the StateManager set charger_available back to True.
        if not self._charger_available:
            self.restore_charger()
            logger.info("Battery: charger restored on replan request")
            self._mqtt.publish(
                self._topics["actuators"]["charging_plug_status"],
                {"state": "on" if self._is_charging else "off", "ts": int(time.time())},
            )

    @property
    def is_charging(self) -> bool:
        return self._is_charging

    @property
    def charger_available(self) -> bool:
        return self._charger_available

    def restore_charger(self) -> None:
        """Re-enable the charger after a fault. Wired to the `events/replan` event
        via `_on_replan`, which treats a replan request as 'charger reconnected'."""
        self._charger_available = True
