"""Problem Generator — renders PDDL 2.1 problem files from current world state."""

import logging
import os
import signal
import threading
import time
from datetime import datetime, timezone

from jinja2 import Environment, FileSystemLoader

from modules.common.config_loader import load_config
from modules.common.mqtt_client import MQTTClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [problem_gen] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_PDDL_DIR = os.path.join(_PROJECT_ROOT, "pddl")

# Thresholds for "meaningful change" debouncing
_SOC_THRESHOLD = 1.0       # %
_TEMP_THRESHOLD = 0.5      # °C
_TIME_THRESHOLD = 0.5      # sim-minutes


class ProblemGenerator:
    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._topics = cfg["topics"]
        broker = cfg["broker"]
        bat = cfg["battery"]
        climate_cfg = cfg["climate"]
        hvac = cfg["hvac"]
        power = cfg["power"]

        self._mqtt = MQTTClient("ev-problem-gen", broker["host"], broker["port"], broker["keepalive"])

        self._jinja_env = Environment(
            loader=FileSystemLoader(_PDDL_DIR),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        self._world: dict = {}
        self._last_generated: dict = {}
        self._force_replan: bool = False

        # Static parameters used in every problem
        self._hvac_power_w: float = hvac["power_w"]
        self._seat_warmer_power_w: float = climate_cfg["seat_warmer_power_w"]
        self._charger_power_w: float = bat["charge_rate_kw"] * 1000.0
        self._max_power_w: float = power["max_power_w"]
        self._cooling_coeff: float = climate_cfg["cooling_coefficient"]
        self._heater_delta: float = climate_cfg["heater_delta_per_min"]
        self._fast_charge_pct_per_min: float = (bat["charge_rate_kw"] / 60.0 / bat["capacity_kwh"]) * 100.0
        self._slow_charge_pct_per_min: float = (bat["slow_charge_rate_kw"] / 60.0 / bat["capacity_kwh"]) * 100.0
        self._taper_threshold: float = bat["taper_threshold"]

    def run(self) -> None:
        self._mqtt.connect()
        self._mqtt.subscribe(self._topics["state"]["current"], self._on_state)
        self._mqtt.subscribe_wildcard("events/#", self._on_event)

        logger.info("Problem generator running")

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

    def _on_state(self, topic: str, payload: dict) -> None:
        self._world = payload
        if self._force_replan or self._state_changed_meaningfully():
            self._generate_and_publish()
            self._force_replan = False

    def _on_event(self, topic: str, payload: dict) -> None:
        logger.info("ProblemGen: event received on %s — forcing replan", topic)
        self._force_replan = True

    def _state_changed_meaningfully(self) -> bool:
        if not self._last_generated:
            return True
        soc_diff = abs(self._world.get("battery_soc", 0) - self._last_generated.get("battery_soc", 0))
        temp_diff = abs(self._world.get("cabin_temp", 0) - self._last_generated.get("cabin_temp", 0))
        time_diff = abs(self._world.get("minutes_remaining", 0) - self._last_generated.get("minutes_remaining", 0))
        # charger_available only flips on fault/restore (not on normal on/off cycling),
        # so reacting to it is safe (no plan thrashing) and ensures a fresh plan when
        # the charger faults or is reconnected — independent of the force_replan race.
        charger_changed = (
            self._world.get("charger_available", True) != self._last_generated.get("charger_available", True)
        )
        return (
            soc_diff >= _SOC_THRESHOLD
            or temp_diff >= _TEMP_THRESHOLD
            or time_diff >= _TIME_THRESHOLD
            or charger_changed
        )

    def _generate_and_publish(self) -> None:
        w = self._world
        soc = w.get("battery_soc", 0.0)

        # Select effective charge rate based on current SoC
        if soc < self._taper_threshold:
            charge_rate = self._fast_charge_pct_per_min
        else:
            fraction = 1.0 - (soc - self._taper_threshold) / (100.0 - self._taper_threshold)
            charge_rate = self._slow_charge_pct_per_min * max(0.0, fraction)

        # Compute current total power draw from active states
        total_power = 0.0
        if w.get("charging"):
            total_power += self._charger_power_w
        if w.get("hvac_on"):
            total_power += self._hvac_power_w
        if w.get("seat_warmer_on"):
            total_power += self._seat_warmer_power_w

        # The PDDL run-hvac effect adds duration * heater-delta with no cooling term,
        # so render an *effective* (net) heater delta that subtracts the worst-case
        # passive cooling loss. Otherwise ENHSP under-runs HVAC and the cabin never
        # actually reaches target in the simulator (which does model cooling).
        outside_temp = w.get("outside_temp", 5.0)
        target_cabin = w.get("target_cabin_temp", 22.0)
        effective_heater_delta = max(
            0.1, self._heater_delta - self._cooling_coeff * (target_cabin - outside_temp)
        )

        context = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ts": int(time.time()),
            "battery_soc": max(0.0, min(100.0, soc)),
            "target_soc": w.get("target_soc", 80.0),
            "cabin_temp": w.get("cabin_temp", 20.0),
            "target_cabin_temp": w.get("target_cabin_temp", 22.0),
            "outside_temp": w.get("outside_temp", 5.0),
            "time_remaining": max(1.0, w.get("minutes_remaining", 60.0)),
            "total_power_draw": total_power,
            "max_power": self._max_power_w,
            "charge_rate_pct_per_min": charge_rate,
            "hvac_power_w": self._hvac_power_w,
            "seat_warmer_power_w": self._seat_warmer_power_w,
            "charger_power_w": self._charger_power_w,
            "cooling_coeff": self._cooling_coeff,
            "heater_delta_per_min": effective_heater_delta,
            "charging": w.get("charging", False),
            "hvac_on": w.get("hvac_on", False),
            "seat_warmer_on": w.get("seat_warmer_on", False),
            "lights_on": w.get("lights_on", False),
            "route_loaded": w.get("route_loaded", False),
            "charger_available": w.get("charger_available", True),
        }

        try:
            template = self._jinja_env.get_template("problem_template.pddl")
            pddl_str = template.render(**context)
            self._mqtt.publish(self._topics["planning"]["problem"], {"pddl": pddl_str, "ts": int(time.time())})
            self._last_generated = dict(self._world)
            logger.info(
                "Problem published (SoC=%.1f%%, cabin=%.1f°C, t_rem=%.1f min)",
                soc, w.get("cabin_temp", 0), context["time_remaining"],
            )
        except Exception as exc:
            logger.error("Failed to render PDDL problem: %s", exc)


def main() -> None:
    cfg = load_config()
    ProblemGenerator(cfg).run()


if __name__ == "__main__":
    main()
