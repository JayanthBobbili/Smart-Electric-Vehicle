"""Simulator entry point — runs all software-defined EV subsystems."""

import logging
import signal
import threading
import time

from modules.common.config_loader import load_config
from modules.common.mqtt_client import MQTTClient
from modules.simulator.battery_model import BatteryModel
from modules.simulator.calendar_sensor import CalendarSensor
from modules.simulator.climate_model import ClimateModel
from modules.simulator.infotainment import Infotainment
from modules.simulator.plugwise_actuator import PlugwiseActuator
from modules.simulator.seat_warmer import SeatWarmer
from modules.simulator.weather_sensor import WeatherSensor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [simulator] %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    cfg = load_config()
    broker = cfg["broker"]
    sim = cfg["simulation"]

    mqtt = MQTTClient("ev-simulator", broker["host"], broker["port"], broker["keepalive"])
    mqtt.connect()

    battery = BatteryModel(cfg, mqtt)
    climate = ClimateModel(cfg, mqtt)
    weather = WeatherSensor(cfg, mqtt)
    calendar = CalendarSensor(cfg, mqtt)
    plugwise = PlugwiseActuator(cfg, mqtt)
    seat = SeatWarmer(cfg, mqtt)
    infotainment = Infotainment(cfg, mqtt)

    battery.setup_subscriptions()
    climate.setup_subscriptions()
    plugwise.setup_subscriptions()
    seat.setup_subscriptions()
    infotainment.setup_subscriptions()

    weather.start()

    tick_interval_real_s: float = sim["tick_interval_s"]
    dt_sim_minutes: float = (tick_interval_real_s * sim["time_scale"]) / 60.0

    logger.info(
        "Simulator started: 1 real second = %d sim seconds, tick = %.1fs real / %.2f sim-min",
        sim["time_scale"], tick_interval_real_s, dt_sim_minutes,
    )

    stop = threading_stop_event()

    try:
        while not stop.is_set():
            tick_start = time.time()

            # Push outside temp into climate model
            climate.update_outside_temp(weather.current_temp)

            # Advance physics models
            battery.tick(dt_sim_minutes)
            climate.tick(dt_sim_minutes)
            seat.tick(dt_sim_minutes)
            calendar.tick(dt_sim_minutes)

            elapsed = time.time() - tick_start
            sleep_time = max(0.0, tick_interval_real_s - elapsed)
            stop.wait(sleep_time)

    except KeyboardInterrupt:
        pass
    finally:
        weather.stop()
        mqtt.disconnect()
        logger.info("Simulator stopped.")


def threading_stop_event():
    stop = threading.Event()

    def _handler(sig, frame):
        logger.info("Received signal %s — shutting down", sig)
        stop.set()

    signal.signal(signal.SIGINT, _handler)
    try:
        signal.signal(signal.SIGTERM, _handler)
    except (OSError, AttributeError):
        pass  # SIGTERM not reliably supported on Windows
    return stop


if __name__ == "__main__":
    main()
