"""IoT Node entry point — runs on Raspberry Pi 3B+."""

import logging
import signal
import threading

from modules.common.config_loader import load_config
from modules.common.mqtt_client import MQTTClient
from modules.iot_node.actuators.led_actuator import LEDActuator
from modules.iot_node.actuators.relay_actuator import RelayActuator
from modules.iot_node.sensors.dht_sensor import DHTSensor
from modules.iot_node.sensors.pir_sensor import PIRSensor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [iot_node] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    cfg = load_config()
    broker = cfg["broker"]

    mqtt = MQTTClient("ev-iot-node", broker["host"], broker["port"], broker["keepalive"])
    mqtt.connect()

    dht = DHTSensor(cfg, mqtt)
    pir = PIRSensor(cfg, mqtt)
    led = LEDActuator(cfg, mqtt)
    relay = RelayActuator(cfg, mqtt)

    led.setup_subscriptions()
    relay.setup_subscriptions()

    dht.start()
    pir.start()

    logger.info("IoT node started — sensors polling, actuators waiting for commands")

    stop = threading.Event()

    def _handler(sig, frame):
        logger.info("Received signal %s — shutting down IoT node", sig)
        stop.set()

    signal.signal(signal.SIGINT, _handler)
    try:
        signal.signal(signal.SIGTERM, _handler)
    except (OSError, AttributeError):
        pass

    stop.wait()

    dht.stop()
    pir.stop()
    mqtt.disconnect()
    logger.info("IoT node stopped.")


if __name__ == "__main__":
    main()
