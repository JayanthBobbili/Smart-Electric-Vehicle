"""Dashboard — Flask + SocketIO app; bridges MQTT → WebSocket for live visualisation."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit

import paho.mqtt.client as mqtt_lib

from modules.common.config_loader import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [dashboard] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_FORWARD_TOPICS = [
    "sensors/#",
    "state/current",
    "planning/plan",
    "actuators/+/status",   # covers all actuator status topics including plugwise
    "events/#",
]

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)
app.config["SECRET_KEY"] = "ev-cabin-prep-secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

_cfg = load_config()
_mqtt_client: mqtt_lib.Client | None = None
_event_log: list[dict] = []


# ------------------------------------------------------------------
# MQTT → SocketIO bridge
# ------------------------------------------------------------------

def _start_mqtt_bridge() -> None:
    global _mqtt_client
    broker = _cfg["broker"]
    client = mqtt_lib.Client(client_id="ev-dashboard")
    client.on_connect = _on_mqtt_connect
    client.on_message = _on_mqtt_message

    try:
        client.connect(broker["host"], broker["port"], broker["keepalive"])
        client.loop_start()
        _mqtt_client = client
        logger.info("Dashboard MQTT bridge connected to %s:%d", broker["host"], broker["port"])
    except Exception as exc:
        logger.error("MQTT bridge failed to connect: %s", exc)


def _on_mqtt_connect(client, userdata, flags, rc) -> None:
    if rc == 0:
        for pattern in _FORWARD_TOPICS:
            client.subscribe(pattern)
        logger.info("Dashboard subscribed to MQTT topics")
    else:
        logger.error("Dashboard MQTT connect failed (rc=%d)", rc)


def _on_mqtt_message(client, userdata, msg) -> None:
    try:
        raw = msg.payload.decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw

        entry = {"topic": msg.topic, "payload": payload, "ts": int(time.time())}

        # Append to event log (cap at 200 entries)
        _event_log.append(entry)
        if len(_event_log) > 200:
            _event_log.pop(0)

        # Emit to all connected WebSocket clients. SocketIO.emit() broadcasts to the
        # whole namespace by default; a `broadcast` kwarg is not part of its signature.
        socketio.emit("mqtt_message", entry)
    except Exception as exc:
        logger.error("MQTT message handling error: %s", exc)


def _mqtt_publish(topic: str, payload: dict) -> None:
    if _mqtt_client:
        _mqtt_client.publish(topic, json.dumps(payload))
    else:
        logger.warning("Cannot publish — MQTT bridge not connected")


# ------------------------------------------------------------------
# Flask routes
# ------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/log")
def api_log():
    return jsonify(_event_log[-50:])


@app.route("/api/trigger/calendar_shift", methods=["POST"])
def trigger_calendar_shift():
    data = request.get_json(silent=True) or {}
    # shift_sim_minutes: positive = later departure, negative = earlier departure
    shift_sim_minutes = int(data.get("shift_sim_minutes", -30))
    _mqtt_publish(
        _cfg["topics"]["events"]["calendar_shift"],
        {"shift_sim_minutes": shift_sim_minutes, "ts": int(time.time()), "source": "dashboard"},
    )
    logger.info("Trigger: calendar shifted by %d sim-minutes", shift_sim_minutes)
    return jsonify({"status": "ok", "shift_sim_minutes": shift_sim_minutes})


@app.route("/api/trigger/charger_fault", methods=["POST"])
def trigger_charger_fault():
    _mqtt_publish(
        _cfg["topics"]["events"]["charger_fault"],
        {"reason": "simulated_fault", "ts": int(time.time()), "source": "dashboard"},
    )
    logger.info("Trigger: charger fault injected")
    return jsonify({"status": "ok"})


@app.route("/api/trigger/user_arrives", methods=["POST"])
def trigger_user_arrives():
    data = request.get_json(silent=True) or {}
    occupied = bool(data.get("occupied", True))
    _mqtt_publish(
        _cfg["topics"]["events"]["user_arrives"],
        {"occupied": occupied, "ts": int(time.time()), "source": "dashboard"},
    )
    logger.info("Trigger: user arrives early (occupied=%s)", occupied)
    return jsonify({"status": "ok", "occupied": occupied})


@app.route("/api/trigger/replan", methods=["POST"])
def trigger_replan():
    data = request.get_json(silent=True) or {}
    reason = data.get("reason", "manual")
    _mqtt_publish(
        _cfg["topics"]["events"]["replan"],
        {"reason": reason, "ts": int(time.time()), "source": "dashboard"},
    )
    logger.info("Trigger: manual replan (%s)", reason)
    return jsonify({"status": "ok"})


# ------------------------------------------------------------------
# SocketIO events
# ------------------------------------------------------------------

@socketio.on("connect")
def on_ws_connect():
    logger.debug("WebSocket client connected")
    emit("log_history", _event_log[-50:])


@socketio.on("disconnect")
def on_ws_disconnect():
    logger.debug("WebSocket client disconnected")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main() -> None:
    _start_mqtt_bridge()
    logger.info("Dashboard starting on http://0.0.0.0:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
