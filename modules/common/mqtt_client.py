"""Thin wrapper around paho-mqtt for consistent connect/publish/subscribe patterns."""

from __future__ import annotations

import json
import logging
import time
from typing import Callable

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTClient:
    def __init__(self, client_id: str, broker_host: str, broker_port: int = 1883, keepalive: int = 60):
        self._host = broker_host
        self._port = broker_port
        self._keepalive = keepalive
        self._client = mqtt.Client(client_id=client_id)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._subscriptions: list[tuple[str, Callable]] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self, retries: int = 5, retry_delay_s: float = 2.0) -> None:
        for attempt in range(1, retries + 1):
            try:
                self._client.connect(self._host, self._port, self._keepalive)
                self._client.loop_start()
                return
            except Exception as exc:
                logger.warning("MQTT connect attempt %d/%d failed: %s", attempt, retries, exc)
                if attempt < retries:
                    time.sleep(retry_delay_s)
        raise ConnectionError(f"Could not connect to MQTT broker at {self._host}:{self._port}")

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    # ------------------------------------------------------------------
    # Publish / Subscribe
    # ------------------------------------------------------------------

    def publish(self, topic: str, payload: dict | str, qos: int = 0, retain: bool = False) -> None:
        if isinstance(payload, dict):
            payload = json.dumps(payload)
        result = self._client.publish(topic, payload, qos=qos, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.error("Publish failed on topic %s (rc=%d)", topic, result.rc)

    def subscribe(self, topic: str, callback: Callable[[str, dict | str], None], qos: int = 0) -> None:
        """Subscribe to an exact topic; callback receives (topic, parsed_payload)."""
        self._subscriptions.append((topic, callback))
        self._client.subscribe(topic, qos)
        self._client.message_callback_add(topic, self._make_handler(callback))

    def subscribe_wildcard(self, pattern: str, callback: Callable[[str, dict | str], None], qos: int = 0) -> None:
        """Subscribe to an MQTT wildcard pattern (e.g. 'events/#').

        paho's message_callback_add supports wildcards in 1.x but behaviour is
        implementation-defined. We register a global on_message handler that
        explicitly checks the topic against the pattern using paho's built-in
        topic_matches_sub() so only matching messages reach the callback.
        """
        self._subscriptions.append((pattern, callback))
        self._client.subscribe(pattern, qos)

        old_on_message = self._client.on_message

        def new_on_message(client, userdata, msg):
            if old_on_message:
                old_on_message(client, userdata, msg)
            if mqtt.topic_matches_sub(pattern, msg.topic):
                payload = MQTTClient._parse(msg.payload)
                callback(msg.topic, payload)

        self._client.on_message = new_on_message

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_handler(callback: Callable) -> Callable:
        def handler(client, userdata, msg):
            payload = MQTTClient._parse(msg.payload)
            callback(msg.topic, payload)
        return handler

    @staticmethod
    def _parse(raw: bytes) -> dict | str:
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return raw.decode("utf-8", errors="replace")

    def _on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            logger.info("Connected to MQTT broker at %s:%d", self._host, self._port)
            # Re-subscribe after reconnect
            for pattern, _ in self._subscriptions:
                self._client.subscribe(pattern)
        else:
            logger.error("MQTT connection refused (rc=%d)", rc)

    def _on_disconnect(self, client, userdata, rc) -> None:
        if rc != 0:
            logger.warning("Unexpected MQTT disconnect (rc=%d); paho will retry", rc)
