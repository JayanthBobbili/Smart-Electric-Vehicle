"""Planner — invokes ENHSP for PDDL 2.1 numeric planning; falls back to rule-based."""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import tempfile
import threading
import time

from modules.common.config_loader import load_config
from modules.common.mqtt_client import MQTTClient
from modules.planner.fallback_planner import make_plan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [planner] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ENHSP output pattern: "X.XXX: (action-name) [D.DDD]"
_ENHSP_ACTION_RE = re.compile(r"^(\d+\.?\d*):\s+\(([^)]+)\)\s+\[(\d+\.?\d*)\]", re.MULTILINE)


class Planner:
    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._topics = cfg["topics"]
        planner_cfg = cfg["planner"]
        broker = cfg["broker"]

        self.jar_path: str = planner_cfg["jar_path"]
        self.domain_path: str = planner_cfg["domain_path"]
        self.timeout_s: int = planner_cfg["timeout_s"]

        self._mqtt = MQTTClient("ev-planner", broker["host"], broker["port"], broker["keepalive"])
        self._last_world: dict = {}
        self._planning_lock = threading.Lock()

    def run(self) -> None:
        self._mqtt.connect()
        self._mqtt.subscribe(self._topics["planning"]["problem"], self._on_problem)
        self._mqtt.subscribe(self._topics["state"]["current"], self._on_state)

        if not os.path.exists(self.jar_path):
            logger.warning("ENHSP jar not found at %s — rule-based fallback will be used", self.jar_path)
        logger.info("Planner running (jar=%s, timeout=%ds)", self.jar_path, self.timeout_s)

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
        logger.info("Planner stopped.")

    def _on_state(self, topic: str, payload: dict) -> None:
        if isinstance(payload, dict):
            self._last_world = payload

    def _on_problem(self, topic: str, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        pddl_str = payload.get("pddl", "")
        if not pddl_str:
            return

        if not self._planning_lock.acquire(blocking=False):
            logger.debug("Planner busy — skipping problem")
            return

        def _plan():
            try:
                plan, source = self._solve(pddl_str)
                self._mqtt.publish(
                    self._topics["planning"]["plan"],
                    {"actions": plan, "ts": int(time.time()), "source": source},
                )
                logger.info("Plan published: %d actions (source=%s)", len(plan), source)
            finally:
                self._planning_lock.release()

        threading.Thread(target=_plan, daemon=True, name="planner-worker").start()

    def _solve(self, pddl_str: str) -> tuple[list[dict], str]:
        if os.path.exists(self.jar_path):
            plan = self._run_enhsp(pddl_str)
            if plan:  # None on error; empty list means ENHSP found no plan — both fall back
                return plan, "enhsp"
            logger.warning("ENHSP returned no actions or failed — using fallback planner")
        return make_plan(self._last_world), "fallback"

    def _run_enhsp(self, pddl_str: str) -> list[dict] | None:
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".pddl", prefix="ev_problem_", delete=False
            ) as tmp:
                tmp.write(pddl_str)
                tmp_path = tmp.name

            cmd = [
                "java", "-jar", self.jar_path,
                "-o", self.domain_path,
                "-f", tmp_path,
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
            )

            if result.returncode != 0:
                logger.warning("ENHSP exit code %d:\n%s", result.returncode, result.stderr[:500])
                return None

            return self._parse_enhsp_output(result.stdout)

        except subprocess.TimeoutExpired:
            logger.warning("ENHSP timed out after %ds", self.timeout_s)
            return None
        except FileNotFoundError:
            logger.error("Java not found — ensure JRE 11+ is installed")
            return None
        except Exception as exc:
            logger.error("ENHSP error: %s", exc)
            return None
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    @staticmethod
    def _parse_enhsp_output(output: str) -> list[dict]:
        actions = []
        for match in _ENHSP_ACTION_RE.finditer(output):
            start = float(match.group(1))
            action_name = match.group(2).strip()
            duration = float(match.group(3))
            actions.append({"action": action_name, "start": start, "duration": duration, "power_w": 0})
        actions.sort(key=lambda a: a["start"])
        return actions


def main() -> None:
    cfg = load_config()
    Planner(cfg).run()


if __name__ == "__main__":
    main()
