"""Executor — steps through the current plan and dispatches actuator commands."""

from __future__ import annotations

import logging
import signal
import threading
import time

from modules.common.config_loader import load_config, load_schedule
from modules.common.mqtt_client import MQTTClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [executor] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

class Executor:
    def __init__(self, cfg: dict, mqtt: MQTTClient):
        self._cfg = cfg
        self._mqtt = mqtt
        self._topics = cfg["topics"]
        sim = cfg["simulation"]
        self._time_scale: int = sim["time_scale"]
        self._tick_s: float = sim["tick_interval_s"]

        # Build dispatch maps from config so topic changes propagate automatically
        t = cfg["topics"]["actuators"]
        self._map_start: dict[str, tuple[str, dict]] = {
            "charge-ev":  (t["charging_plug_cmd"], {"action": "on"}),
            "run-hvac":   (t["cabin_heater_cmd"],  {"action": "on"}),
            "warm-seat":  (t["seat_warmer_cmd"],   {"action": "start"}),
        }
        self._map_end: dict[str, tuple[str, dict]] = {
            "charge-ev":     (t["charging_plug_cmd"], {"action": "off"}),
            "run-hvac":      (t["cabin_heater_cmd"],  {"action": "off"}),
            "warm-seat":     (t["seat_warmer_cmd"],   {"action": "stop"}),
            "set-lights-on": (t["ambient_light_cmd"], {"action": "on"}),
            "load-route":    (t["infotainment_cmd"],  {"action": "load_route"}),
        }

        self._plan: list[dict] = []
        self._plan_start_real: float = 0.0
        self._world: dict = {}
        self._lock = threading.Lock()
        self._executor_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def setup_subscriptions(self) -> None:
        self._mqtt.subscribe(self._topics["planning"]["plan"], self._on_plan)
        self._mqtt.subscribe(self._topics["state"]["current"], self._on_state)

    def _on_plan(self, topic: str, payload: dict) -> None:
        actions = payload.get("actions", [])
        if not actions:
            return
        with self._lock:
            self._plan = actions
            self._plan_start_real = time.time()
        logger.info("Executor: new plan received (%d actions)", len(actions))

        if self._executor_thread and self._executor_thread.is_alive():
            self._stop_event.set()
            self._executor_thread.join(timeout=2)
        self._stop_event.clear()
        self._executor_thread = threading.Thread(
            target=self._execute_plan, daemon=True, name="executor-worker"
        )
        self._executor_thread.start()

    def _on_state(self, topic: str, payload: dict) -> None:
        if isinstance(payload, dict):
            self._world = payload

    def _execute_plan(self) -> None:
        with self._lock:
            plan = list(self._plan)
            plan_start = self._plan_start_real

        logger.info("Executor: starting plan execution (%d actions)", len(plan))
        dispatched_start: set[int] = set()
        dispatched_end: set[int] = set()

        while not self._stop_event.is_set():
            now_real = time.time()
            elapsed_real_s = now_real - plan_start
            elapsed_sim_min = (elapsed_real_s * self._time_scale) / 60.0

            for i, action in enumerate(plan):
                # Dispatch action START
                if i not in dispatched_start and elapsed_sim_min >= action["start"]:
                    self._dispatch(action, at_end=False)
                    dispatched_start.add(i)

                # Dispatch action END (off commands, completion effects)
                action_end = action["start"] + action.get("duration", 1)
                if i not in dispatched_end and elapsed_sim_min >= action_end:
                    self._dispatch(action, at_end=True)
                    dispatched_end.add(i)

            # Check if all goals are satisfied
            if dispatched_end == set(range(len(plan))):
                if self._goals_met():
                    logger.info("Executor: all goals satisfied — plan complete")
                else:
                    logger.info("Executor: all actions dispatched")
                return

            self._stop_event.wait(self._tick_s)

    def _dispatch(self, action: dict, *, at_end: bool) -> None:
        name = action["action"]
        ts = int(time.time())
        mapping = (self._map_end if at_end else self._map_start).get(name)

        if not mapping or mapping[0] is None:
            label = "end" if at_end else "start"
            logger.debug("Executor: action '%s' %s — no actuator command", name, label)
            return

        topic, base_payload = mapping
        payload = {**base_payload, "ts": ts}

        if name == "load-route":
            try:
                payload["destination"] = load_schedule().get("destination", "Stuttgart HBF")
            except Exception:
                payload["destination"] = "Stuttgart HBF"

        self._mqtt.publish(topic, payload)
        label = "END" if at_end else "START"
        logger.info("Executor: [%s] '%s' → %s %s", label, name, topic, base_payload)

    def _goals_met(self) -> bool:
        w = self._world
        return (
            w.get("battery_soc", 0) >= w.get("target_soc", 80)
            and w.get("cabin_temp", 0) >= w.get("target_cabin_temp", 22)
            and w.get("route_loaded", False)
        )

    def stop(self) -> None:
        self._stop_event.set()


def main() -> None:
    cfg = load_config()
    broker = cfg["broker"]
    mqtt = MQTTClient("ev-executor", broker["host"], broker["port"], broker["keepalive"])
    mqtt.connect()

    executor = Executor(cfg, mqtt)
    executor.setup_subscriptions()
    logger.info("Executor running")

    stop = threading.Event()

    def _handler(sig, frame):
        stop.set()

    signal.signal(signal.SIGINT, _handler)
    try:
        signal.signal(signal.SIGTERM, _handler)
    except (OSError, AttributeError):
        pass
    stop.wait()

    executor.stop()
    mqtt.disconnect()
    logger.info("Executor stopped.")


if __name__ == "__main__":
    main()
