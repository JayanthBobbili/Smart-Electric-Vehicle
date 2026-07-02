"""Terminal override console — a presentation fail-safe for the Pi sensors.

If the Grove DHT11 misbehaves, run this to manually feed the cabin temperature,
humidity, and occupancy that get published to the laptop, overriding whatever the
real sensor reports.

How it stays conflict-free:
  * While an override is active this console publishes the sensor topic itself and
    tells the matching sensor module (dht_sensor / pir_sensor) to *step aside* via
    `control/dht_override` / `control/occupancy_override`.
  * That signal is re-sent ~1/s and the sensors honour it for only 5s, so if this
    console stops or crashes the real sensors resume automatically.
  * It also works with the IoT node NOT running — then this console is your manual
    sensor source.

Temperature overrides are published with source "grove_dht" so the laptop's
StateManager treats them as a real reading (the simulator cannot overwrite them).

Run it on the Pi (over SSH) or on the laptop — it only needs to reach the broker:

    python -m modules.iot_node.override_console            # curses TUI (default)
    python -m modules.iot_node.override_console --simple    # line-based fallback

TUI keys:
    e            toggle DHT (temp + humidity) override on/off
    + / -        temperature  +/- 0.5 C   (UP / DOWN arrows also work)
    ] / [        humidity      +/- 1 %
    t            type an exact temperature, then Enter
    c            toggle occupancy override on/off
    space        flip occupied YES / NO
    r            reset — clear all overrides (back to the live sensors)
    q            quit (clears overrides on the way out)
"""

from __future__ import annotations

import argparse
import threading
import time

from modules.common.config_loader import load_config
from modules.common.mqtt_client import MQTTClient


class _Shared:
    """Mutable state shared between the MQTT thread, publisher thread, and UI."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.connected = False
        # latest live readings seen on the broker (value, unix-ts, source, is_override)
        self.live_temp: tuple[float, float, str, bool] | None = None
        self.live_hum: tuple[float, float] | None = None
        self.live_occ: tuple[bool, float, str, bool] | None = None
        # override state (what we send while active)
        self.dht_active = False
        self.temp = 22.0
        self.hum = 50.0
        self.occ_active = False
        self.occupied = False


def _build(cfg: dict):
    t = cfg["topics"]
    ctl = t.get("control", {})
    return {
        "temp": t["sensors"]["cabin_temp"],
        "hum": t["sensors"]["cabin_humidity"],
        "occ": t["sensors"]["occupancy"],
        "ctl_dht": ctl.get("dht_override", "control/dht_override"),
        "ctl_occ": ctl.get("occupancy_override", "control/occupancy_override"),
    }


def _start_mqtt(cfg: dict, topics: dict, shared: _Shared) -> MQTTClient:
    broker = cfg["broker"]
    mqtt = MQTTClient("ev-override-console", broker["host"], broker["port"], broker["keepalive"])
    mqtt.connect()
    shared.connected = True

    def on_temp(_topic: str, payload: dict) -> None:
        if isinstance(payload, dict) and payload.get("value") is not None:
            with shared.lock:
                shared.live_temp = (
                    float(payload["value"]), time.time(),
                    str(payload.get("source", "?")), bool(payload.get("override")),
                )

    def on_hum(_topic: str, payload: dict) -> None:
        if isinstance(payload, dict) and payload.get("value") is not None:
            with shared.lock:
                shared.live_hum = (float(payload["value"]), time.time())

    def on_occ(_topic: str, payload: dict) -> None:
        if isinstance(payload, dict) and payload.get("value") is not None:
            with shared.lock:
                shared.live_occ = (
                    bool(payload["value"]), time.time(),
                    str(payload.get("source", "?")), bool(payload.get("override")),
                )

    mqtt.subscribe(topics["temp"], on_temp)
    mqtt.subscribe(topics["hum"], on_hum)
    mqtt.subscribe(topics["occ"], on_occ)
    return mqtt


def _publisher(mqtt: MQTTClient, topics: dict, shared: _Shared, stop: threading.Event, interval: float) -> None:
    """Continuously broadcast the current override state (and 'step aside' signals)."""
    while not stop.is_set():
        with shared.lock:
            dht_active, temp, hum = shared.dht_active, shared.temp, shared.hum
            occ_active, occupied = shared.occ_active, shared.occupied
        ts = int(time.time())

        # Tell the sensors whether to step aside (re-sent every interval; TTL-based).
        mqtt.publish(topics["ctl_dht"], {"active": dht_active, "ts": ts})
        mqtt.publish(topics["ctl_occ"], {"active": occ_active, "ts": ts})

        if dht_active:
            mqtt.publish(topics["temp"], {"value": round(temp, 1), "unit": "C", "ts": ts,
                                          "source": "grove_dht", "override": True})
            mqtt.publish(topics["hum"], {"value": round(hum, 1), "unit": "%", "ts": ts,
                                         "source": "grove_dht", "override": True})
        if occ_active:
            mqtt.publish(topics["occ"], {"value": bool(occupied), "ts": ts,
                                         "source": "manual_override", "override": True})

        stop.wait(interval)


def _send_clear(mqtt: MQTTClient, topics: dict) -> None:
    """Tell the sensors to resume (used on exit)."""
    ts = int(time.time())
    mqtt.publish(topics["ctl_dht"], {"active": False, "ts": ts})
    mqtt.publish(topics["ctl_occ"], {"active": False, "ts": ts})


# ======================================================================
# curses TUI
# ======================================================================

def _run_curses(stdscr, cfg: dict, topics: dict, shared: _Shared, mqtt: MQTTClient, stop: threading.Event) -> None:
    import curses

    try:
        curses.curs_set(0)
    except curses.error:
        pass
    stdscr.timeout(200)  # getch() waits up to 200ms, so the live view refreshes ~5/s
    host = cfg["broker"]["host"]
    port = cfg["broker"]["port"]

    def line(row: int, text: str, attr: int = 0) -> None:
        try:
            stdscr.move(row, 0)
            stdscr.clrtoeol()
            stdscr.addstr(row, 0, text[: curses.COLS - 1], attr)
        except curses.error:
            pass

    def fmt_age(ts: float) -> str:
        age = time.time() - ts
        return f"{age:4.1f}s" + ("  STALE" if age > 5 else "")

    def prompt_float(row: int, label: str, current: float) -> float:
        stdscr.timeout(-1)
        buf = ""
        while True:
            line(row, f"{label} (Enter=ok, Esc=cancel): {buf}")
            stdscr.refresh()
            ch = stdscr.getch()
            if ch in (curses.KEY_ENTER, 10, 13):
                break
            if ch == 27:  # Esc
                buf = None
                break
            if ch in (curses.KEY_BACKSPACE, 127, 8):
                buf = buf[:-1]
            elif 0 <= ch < 256 and (chr(ch).isdigit() or chr(ch) in ".-"):
                buf += chr(ch)
        stdscr.timeout(200)
        if not buf:
            return current
        try:
            return float(buf)
        except ValueError:
            return current

    while not stop.is_set():
        with shared.lock:
            lt, lh, lo = shared.live_temp, shared.live_hum, shared.live_occ
            dht_active, temp, hum = shared.dht_active, shared.temp, shared.hum
            occ_active, occupied = shared.occ_active, shared.occupied
            connected = shared.connected

        status = "connected" if connected else "DISCONNECTED"
        line(0, f" EV Cabin — Sensor Override Console      broker {host}:{port} [{status}]", curses.A_BOLD)
        line(2, " LIVE on broker", curses.A_BOLD | curses.A_UNDERLINE)
        if lt:
            tag = " (your override)" if lt[3] else f" src={lt[2]}"
            line(3, f"   Cabin temp : {lt[0]:6.1f} C  {tag}   age {fmt_age(lt[1])}")
        else:
            line(3, "   Cabin temp : --   (nothing received yet)")
        line(4, f"   Humidity   : {lh[0]:6.1f} %                 age {fmt_age(lh[1])}" if lh
                else "   Humidity   : --")
        if lo:
            tag = " (your override)" if lo[3] else f" src={lo[2]}"
            line(5, f"   Occupancy  : {'OCCUPIED' if lo[0] else 'EMPTY':9}{tag}   age {fmt_age(lo[1])}")
        else:
            line(5, "   Occupancy  : --")

        line(7, " OVERRIDE  (what is sent to the laptop)", curses.A_BOLD | curses.A_UNDERLINE)
        a1 = curses.A_REVERSE if dht_active else curses.A_DIM
        line(8, f"   [{'ON ' if dht_active else 'OFF'}] DHT   temp={temp:5.1f} C   hum={hum:4.1f} %", a1)
        a2 = curses.A_REVERSE if occ_active else curses.A_DIM
        line(9, f"   [{'ON ' if occ_active else 'OFF'}] Occupancy   occupied={'YES' if occupied else 'NO'}", a2)

        line(11, " e DHT on/off   +/- temp   ]/[ hum   t type-temp", curses.A_DIM)
        line(12, " c occ on/off   space toggle occupied   r reset   q quit", curses.A_DIM)
        stdscr.refresh()

        ch = stdscr.getch()
        if ch == -1:
            continue
        with shared.lock:
            if ch in (ord("q"), ord("Q")):
                stop.set()
            elif ch in (ord("e"), ord("E")):
                shared.dht_active = not shared.dht_active
            elif ch in (ord("c"), ord("C")):
                shared.occ_active = not shared.occ_active
            elif ch == ord(" "):
                shared.occupied = not shared.occupied
                shared.occ_active = True
            elif ch in (ord("+"), ord("="), curses.KEY_UP):
                shared.temp = round(shared.temp + 0.5, 1)
                shared.dht_active = True
            elif ch in (ord("-"), ord("_"), curses.KEY_DOWN):
                shared.temp = round(shared.temp - 0.5, 1)
                shared.dht_active = True
            elif ch == ord("]"):
                shared.hum = min(100.0, round(shared.hum + 1, 1))
                shared.dht_active = True
            elif ch == ord("["):
                shared.hum = max(0.0, round(shared.hum - 1, 1))
                shared.dht_active = True
            elif ch in (ord("r"), ord("R")):
                shared.dht_active = False
                shared.occ_active = False
            elif ch in (ord("t"), ord("T")):
                cur = shared.temp
                shared.lock.release()
                try:
                    new = prompt_float(14, "Temperature C", cur)
                finally:
                    shared.lock.acquire()
                shared.temp = new
                shared.dht_active = True


# ======================================================================
# simple line-based fallback (no curses; works anywhere)
# ======================================================================

_SIMPLE_HELP = """
Commands:
  t <value>     set temperature override (turns DHT override ON)
  h <value>     set humidity override (turns DHT override ON)
  e on|off      DHT override on/off
  o on|off      occupancy override on/off
  c yes|no      set occupied yes/no (turns occupancy override ON)
  status        show latest live readings + current override state
  r             reset all overrides (back to live sensors)
  q             quit
"""


def _run_simple(cfg: dict, topics: dict, shared: _Shared, mqtt: MQTTClient, stop: threading.Event) -> None:
    print("EV Cabin — Sensor Override Console (simple mode)")
    print(_SIMPLE_HELP)

    def show_status() -> None:
        with shared.lock:
            lt, lh, lo = shared.live_temp, shared.live_hum, shared.live_occ
            print(f"  connected     : {shared.connected}")
            print(f"  live temp     : {lt[0]:.1f} C (src={lt[2]}, {time.time()-lt[1]:.1f}s ago)"
                  if lt else "  live temp     : --")
            print(f"  live humidity : {lh[0]:.1f} %" if lh else "  live humidity : --")
            print(f"  live occupancy: {'OCCUPIED' if lo[0] else 'EMPTY'} ({time.time()-lo[1]:.1f}s ago)"
                  if lo else "  live occupancy: --")
            print(f"  OVERRIDE DHT  : {'ON' if shared.dht_active else 'off'}  "
                  f"temp={shared.temp:.1f}C hum={shared.hum:.1f}%")
            print(f"  OVERRIDE OCC  : {'ON' if shared.occ_active else 'off'}  "
                  f"occupied={'YES' if shared.occupied else 'NO'}")

    show_status()
    while not stop.is_set():
        try:
            raw = input("override> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw:
            continue
        parts = raw.split()
        cmd, arg = parts[0].lower(), (parts[1].lower() if len(parts) > 1 else "")
        with shared.lock:
            if cmd in ("q", "quit", "exit"):
                break
            elif cmd == "t":
                try:
                    shared.temp = float(arg); shared.dht_active = True
                except ValueError:
                    print("  ? usage: t 22.5")
            elif cmd == "h":
                try:
                    shared.hum = float(arg); shared.dht_active = True
                except ValueError:
                    print("  ? usage: h 55")
            elif cmd == "e":
                shared.dht_active = arg in ("on", "1", "true", "yes")
            elif cmd == "o":
                shared.occ_active = arg in ("on", "1", "true", "yes")
            elif cmd == "c":
                shared.occupied = arg in ("yes", "y", "1", "true", "on")
                shared.occ_active = True
            elif cmd in ("r", "reset"):
                shared.dht_active = False; shared.occ_active = False
            elif cmd in ("s", "status"):
                pass  # printed below outside the lock branch
            elif cmd in ("?", "help"):
                print(_SIMPLE_HELP)
            else:
                print("  ? unknown command — type 'help'")
        if cmd in ("s", "status", "t", "h", "e", "o", "c", "r", "reset"):
            show_status()
    stop.set()


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual override console for the Pi DHT/PIR sensors.")
    parser.add_argument("--simple", action="store_true", help="Use the line-based UI (no curses).")
    parser.add_argument("--interval", type=float, default=1.0, help="Publish interval in seconds (default 1.0).")
    args = parser.parse_args()

    cfg = load_config()
    topics = _build(cfg)
    shared = _Shared()
    stop = threading.Event()

    try:
        mqtt = _start_mqtt(cfg, topics, shared)
    except Exception as exc:
        print(f"Could not connect to MQTT broker at {cfg['broker']['host']}:{cfg['broker']['port']}: {exc}")
        return 1

    pub = threading.Thread(target=_publisher, args=(mqtt, topics, shared, stop, args.interval),
                           daemon=True, name="override-publisher")
    pub.start()

    use_curses = not args.simple
    if use_curses:
        try:
            import curses  # noqa: F401
        except ImportError:
            print("curses not available (on Windows: `pip install windows-curses`, or use --simple).")
            print("Falling back to simple mode.\n")
            use_curses = False

    try:
        if use_curses:
            import curses
            curses.wrapper(_run_curses, cfg, topics, shared, mqtt, stop)
        else:
            _run_simple(cfg, topics, shared, mqtt, stop)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        _send_clear(mqtt, topics)   # tell sensors to resume
        time.sleep(0.2)             # let the clear messages flush
        mqtt.disconnect()
        print("Override console stopped — sensors resumed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
