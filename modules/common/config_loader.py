"""Loads config.yaml and schedule.json, resolves paths relative to project root."""

from __future__ import annotations

import json
import os
import yaml

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _project_path(*parts: str) -> str:
    return os.path.join(_PROJECT_ROOT, *parts)


def load_config(path: str | None = None) -> dict:
    config_path = path or _project_path("config", "config.yaml")
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)
    # Make planner paths absolute if they are relative
    planner = cfg.get("planner", {})
    for key in ("jar_path", "domain_path"):
        if not os.path.isabs(planner.get(key, "")):
            planner[key] = _project_path(planner[key])
    return cfg


def load_schedule(path: str | None = None) -> dict:
    schedule_path = path or _project_path("config", "schedule.json")
    with open(schedule_path, "r") as f:
        return json.load(f)


def save_schedule(data: dict, path: str | None = None) -> None:
    schedule_path = path or _project_path("config", "schedule.json")
    with open(schedule_path, "w") as f:
        json.dump(data, f, indent=2)
