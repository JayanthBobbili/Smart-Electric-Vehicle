# Project Context — Smart EV Charging & Cabin Prep

**Group 22 · Smart Cities & IoT · University of Stuttgart · Summer 2026**

This document is a single consolidated reference for the entire project. It covers every module, every file, every design decision, every MQTT topic, every config key, and all the physics and AI planning concepts involved. Read this before touching any code.

---

## 1. What This Project Does

An electric vehicle is parked at home overnight. The owner needs to leave at 8:00 AM. Instead of manually checking the battery, turning on the heater, loading the navigation route, and switching on lights — the system does all of this automatically.

The system:
1. **Reads sensors** continuously (battery level, cabin temperature, occupancy, outside temperature, time until departure)
2. **Builds an AI plan** using a PDDL 2.1 planner (ENHSP), specifying exactly when to start each action so all goals are met before departure within the home power budget
3. **Executes the plan** by sending MQTT commands to actuators at the right times
4. **Replans** when something changes (charger fault, departure shift, early user arrival)
5. **Shows everything live** on a web dashboard with an animated EV cockpit widget

**What makes this more than if-else logic:** The planner reasons about time, power constraints, and simultaneous goals. If the departure shifts earlier, the planner might have to run HVAC and charging in parallel (possible if their combined draw ≤ 5750W). If the charger breaks, the planner removes charging from the schedule and redistributes everything else. These trade-offs are solved automatically.

---

## 2. Physical Architecture — Two Machines

```
┌─────────────────────────────────┐     Wi-Fi / MQTT      ┌──────────────────────────────────────┐
│   Raspberry Pi 3B+              │ ◄───────────────────► │   Laptop (Windows 11)                │
│   "IoT Edge Node"               │                        │   "Cloud + Planner"                  │
│                                 │                        │                                      │
│  Runs: modules/iot_node/        │                        │  Runs: everything else               │
│                                 │                        │                                      │
│  Real sensors:                  │                        │  Software-defined EV:                │
│  • Grove DHT11/22 → cabin temp  │                        │  • BatteryModel (CC-CV physics)      │
│  • Grove PIR → occupancy        │                        │  • ClimateModel (Newton cooling)     │
│                                 │                        │  • CalendarSensor (countdown)        │
│  Real actuators:                │                        │  • WeatherSensor (Open-Meteo API)    │
│  • Grove LED → ambient light    │                        │  • SeatWarmer (state machine)        │
│  • Grove Relay → heater switch  │                        │  • Infotainment (route loader)       │
│                                 │                        │  • PlugwiseActuator (visual prop)    │
│  Communicates via MQTT          │                        │                                      │
│  Broker host = laptop IP        │                        │  AI planning:                        │
│                                 │                        │  • StateManager (digital twin)       │
│                                 │                        │  • ProblemGenerator (PDDL renderer)  │
│                                 │                        │  • Planner (ENHSP + fallback)        │
│                                 │                        │  • Executor (timed dispatch)         │
│                                 │                        │                                      │
│                                 │                        │  Dashboard: Flask + SocketIO         │
│                                 │                        │  http://localhost:5000               │
└─────────────────────────────────┘                        └──────────────────────────────────────┘
                                          ▲
                              MQTT Broker │ (Eclipse Mosquitto in Docker)
                              localhost:1883 on laptop
```

The **Mosquitto MQTT broker** runs in Docker on the laptop. All modules — both on the laptop and on the Pi — connect to it. The Pi's `config.yaml` has the broker host set to the laptop's Wi-Fi IP. The laptop's `config.yaml` has `localhost`.

---

## 3. Repository Structure

```
smart-ev-cabin/
├── README.md
├── .gitignore
├── requirements-laptop.txt         # Flask, paho-mqtt, requests, pyyaml, flask-socketio, etc.
├── requirements-pi.txt             # paho-mqtt, pyyaml (grovepi installed system-wide)
├── docker-compose.yml              # Eclipse Mosquitto 2.0 broker, ports 1883 + 9001
├── mosquitto.conf                  # Allow anonymous connections on all interfaces
├── config/
│   ├── config.yaml                 # All runtime config: broker, topics, physics params, ports
│   └── schedule.json               # Departure time, targets — editable at runtime
├── pddl/
│   ├── domain.pddl                 # PDDL 2.1 numeric domain (5 durative actions)
│   └── problem_template.pddl       # Jinja2 template filled by ProblemGenerator
├── planner/
│   └── enhsp.jar                   # NOT in repo — download separately (see deployment guide)
├── modules/
│   ├── common/
│   │   ├── mqtt_client.py          # Paho-mqtt wrapper: connect, publish, subscribe, wildcard
│   │   └── config_loader.py        # Loads config.yaml + schedule.json; resolves absolute paths
│   ├── simulator/
│   │   ├── main.py                 # Entry point; tick loop; orchestrates all sub-simulators
│   │   ├── battery_model.py        # CC-CV SoC physics; subscribes charging_plug_cmd
│   │   ├── climate_model.py        # Newton cooling + heater delta; subscribes heater/seat cmds
│   │   ├── calendar_sensor.py      # Countdown; subscribes calendar_shift; persists to schedule.json
│   │   ├── weather_sensor.py       # Open-Meteo API; refreshes every 5 min; publishes outside_temp
│   │   ├── plugwise_actuator.py    # Visual prop; mirrors charger+heater state; no real Zigbee driver
│   │   ├── seat_warmer.py          # OFF→WARMING→WARM state machine (5 sim-min warmup)
│   │   └── infotainment.py         # Virtual route loader; responds to load_route command
│   ├── iot_node/
│   │   ├── main.py                 # Pi entry point; starts sensors + actuators; clean shutdown
│   │   ├── sensors/
│   │   │   ├── dht_sensor.py       # Grove DHT11/22; polls every 2s; publishes cabin_temp + humidity
│   │   │   └── pir_sensor.py       # Grove PIR; polls every 0.5s; publishes occupancy
│   │   └── actuators/
│   │       ├── led_actuator.py     # Grove LED on D2; subscribes ambient_light_cmd
│   │       └── relay_actuator.py   # Grove Relay on D6; subscribes cabin_heater_cmd; soft fallback
│   ├── state_manager/
│   │   └── main.py                 # Subscribes sensors/# + actuator statuses; maintains world dict
│   ├── problem_generator/
│   │   └── main.py                 # Subscribes state/current; renders PDDL via Jinja2; debounces
│   ├── planner/
│   │   ├── main.py                 # Subscribes planning/problem; calls ENHSP via subprocess
│   │   └── fallback_planner.py     # Rule-based fallback when ENHSP unavailable or times out
│   ├── executor/
│   │   └── main.py                 # Subscribes planning/plan; dispatches actuator cmds at right time
│   └── dashboard/
│       ├── app.py                  # Flask + Flask-SocketIO; bridges MQTT → WebSocket
│       ├── templates/
│       │   └── index.html          # Single-page dashboard with 4 panels
│       └── static/
│           ├── css/style.css       # Dark theme
│           └── js/
│               ├── dashboard.js    # SocketIO listener; state machine; updates all panels
│               ├── gantt.js        # Chart.js horizontal bar Gantt for plan timeline
│               └── cockpit.js      # SVG EV cockpit animations (battery fill, cable glow, etc.)
├── tests/
│   ├── test_battery_model.py       # 8 unit tests: charging physics, taper, fault handling
│   ├── test_climate_model.py       # Climate physics tests
│   ├── test_problem_generator.py   # PDDL rendering, debouncing, charge rate tests
│   └── test_state_manager.py       # World state update tests
└── docs/
    ├── deployment_guide.md         # Step-by-step setup for laptop + Pi
    ├── presentation_guide.md       # Simple language explanation for presenters
    └── context.md                  # This file
```

---

## 4. Configuration

### `config/config.yaml` — canonical values

```yaml
broker:
  host: "localhost"     # Pi copies must change this to laptop's IP
  port: 1883
  keepalive: 60

simulation:
  time_scale: 60        # 1 real second = 60 simulation seconds
  tick_interval_s: 1.0  # real seconds between ticks

battery:
  initial_soc: 50.0         # % — start at 50% for demo
  charge_rate_kw: 3.7       # 16A × 230V Type-2 home charger = 3700W
  slow_charge_rate_kw: 1.85 # taper phase rate (above 80% SoC)
  capacity_kwh: 10.0        # compact demo EV — charging finishes in ~49 sim-min
  taper_threshold: 80.0     # % SoC where CC→CV transition happens

climate:
  initial_cabin_temp: 10.0  # °C — cold morning
  cooling_coefficient: 0.02 # Newton k factor per sim-minute
  heater_delta_per_min: 0.8 # °C rise per sim-minute when HVAC on
  seat_warmer_power_w: 150  # W

hvac:
  power_w: 2000             # W

power:
  max_power_w: 5750         # 25A × 230V circuit limit
  # charger (3700W) + HVAC (2000W) = 5700W ≤ 5750W → can run together
  # charger + HVAC + seat warmer = 5850W > 5750W → cannot all three

weather:
  api_url: "https://api.open-meteo.com/v1/forecast"
  latitude: 48.78           # Stuttgart
  longitude: 9.18
  default_outside_temp: 5.0 # °C fallback when API unavailable
  refresh_interval_s: 300   # 5 real minutes

grovepi:
  dht_port: 7               # GrovePi+ D7 port
  dht_type: 0               # 0=DHT11 (blue, starter kit default), 1=DHT22 (white)
  pir_port: 8               # GrovePi+ D8 port
  led_port: 2               # GrovePi+ D2 port
  relay_port: 6             # GrovePi+ D6 port
  dht_poll_interval_s: 2.0
  pir_poll_interval_s: 0.5
  relay_soft_fallback: true # publish state but skip GPIO write (safe default)

planner:
  jar_path: "planner/enhsp.jar"
  domain_path: "pddl/domain.pddl"
  timeout_s: 10
```

### `config/schedule.json` — runtime editable

```json
{
  "departure_time": "2026-06-24T08:00:00",
  "sim_minutes_until_departure": 60.0,
  "target_soc": 80.0,
  "target_cabin_temp": 22.0,
  "destination": "Stuttgart HBF"
}
```

Edit `sim_minutes_until_departure` before each demo run. At `time_scale=60`, a value of `60.0` means the demo plays out in 1 real minute.

---

## 5. MQTT Topic Schema

All topics are defined in `config.yaml` under `topics:`. No module hard-codes a topic string directly — everything reads from config.

| Topic (config key) | Publisher | Subscriber(s) | Payload shape |
|---|---|---|---|
| `sensors/cabin_temp` (sensors.cabin_temp) | IoT node (real) OR Simulator (sim) | StateManager | `{"value": 18.5, "unit": "C", "ts": 1234, "source": "grove_dht"}` |
| `sensors/cabin_humidity` (sensors.cabin_humidity) | IoT node DHT | StateManager | `{"value": 65.0, "unit": "%", "ts": 1234}` |
| `sensors/occupancy` (sensors.occupancy) | IoT node PIR | StateManager | `{"value": false, "ts": 1234, "source": "grove_pir"}` |
| `sensors/battery_soc` (sensors.battery_soc) | Simulator BatteryModel | StateManager | `{"value": 42.3, "unit": "%", "ts": 1234, "source": "simulator"}` |
| `sensors/outside_temp` (sensors.outside_temp) | Simulator WeatherSensor | StateManager | `{"value": 5.2, "unit": "C", "ts": 1234, "source": "open_meteo"}` |
| `sensors/departure_time` (sensors.departure_time) | Simulator CalendarSensor | StateManager | `{"value": "2026-06-24T08:00:00", "minutes_remaining": 47.3, "ts": 1234}` |
| `state/current` (state.current) | StateManager | ProblemGenerator, Planner, Executor, Dashboard | Full world dict (see Section 7) |
| `planning/problem` (planning.problem) | ProblemGenerator | Planner | `{"pddl": "(define (problem ...) ...)", "ts": 1234}` |
| `planning/plan` (planning.plan) | Planner | Executor, Dashboard | `{"actions": [...], "ts": 1234, "source": "enhsp"}` |
| `actuators/charging_plug/cmd` (actuators.charging_plug_cmd) | Executor | BatteryModel, PlugwiseActuator | `{"action": "on"/"off", "ts": 1234}` |
| `actuators/charging_plug/status` (actuators.charging_plug_status) | BatteryModel | StateManager | `{"state": "on"/"off"/"fault", "ts": 1234}` |
| `actuators/cabin_heater/cmd` (actuators.cabin_heater_cmd) | Executor | ClimateModel, RelayActuator, PlugwiseActuator | `{"action": "on"/"off", "ts": 1234}` |
| `actuators/cabin_heater/status` (actuators.cabin_heater_status) | ClimateModel / RelayActuator | StateManager | `{"state": "on"/"off", "ts": 1234}` |
| `actuators/ambient_light/cmd` (actuators.ambient_light_cmd) | Executor | LEDActuator | `{"action": "on"/"off", "ts": 1234}` |
| `actuators/ambient_light/status` (actuators.ambient_light_status) | LEDActuator | StateManager | `{"state": "on"/"off", "ts": 1234}` |
| `actuators/seat_warmer/cmd` (actuators.seat_warmer_cmd) | Executor | SeatWarmer, ClimateModel | `{"action": "start"/"stop", "ts": 1234}` |
| `actuators/seat_warmer/status` (actuators.seat_warmer_status) | SeatWarmer | StateManager | `{"state": "off"/"warming"/"warm", "ts": 1234}` |
| `actuators/infotainment/cmd` (actuators.infotainment_cmd) | Executor | Infotainment | `{"action": "load_route", "destination": "Stuttgart HBF", "ts": 1234}` |
| `actuators/infotainment/status` (actuators.infotainment_status) | Infotainment | StateManager | `{"state": "route_loaded"/"off", "ts": 1234}` |
| `actuators/plugwise/status` (actuators.plugwise_status) | PlugwiseActuator | Dashboard | `{"circle_1": "on"/"off", "circle_2": "on"/"off", "ts": 1234}` |
| `events/replan` (events.replan) | Executor / Dashboard | ProblemGenerator | `{"reason": "charger_fault", "ts": 1234, "source": "executor"}` |
| `events/calendar_shift` (events.calendar_shift) | Dashboard | CalendarSensor | `{"shift_sim_minutes": -30, "ts": 1234, "source": "dashboard"}` |
| `events/charger_fault` (events.charger_fault) | Dashboard | BatteryModel, StateManager | `{"reason": "simulated_fault", "ts": 1234}` |
| `events/user_arrives` (events.user_arrives) | Dashboard | PIRSensor | `{"occupied": true, "ts": 1234, "source": "dashboard"}` |

---

## 6. Module Details

### 6.1 Simulator (`modules/simulator/`)

The simulator runs entirely on the laptop. It models all parts of the EV that cannot be physical in a demo:

**`main.py` — tick loop:**
- Loads config, creates all subsystem objects, calls `setup_subscriptions()` on each
- Starts `WeatherSensor.start()` (background thread, not in tick loop)
- Calculates `dt_sim_minutes = tick_interval_s * time_scale / 60 = 1.0 * 60 / 60 = 1.0`
- Every real second: calls `climate.update_outside_temp(weather.current_temp)` first, then advances `BatteryModel.tick(1.0)`, `ClimateModel.tick(1.0)`, `SeatWarmer.tick(1.0)`, `CalendarSensor.tick(1.0)`
- Note: ClimateModel receives outside temp via direct method call, not MQTT — that is why `sensors/outside_temp` lists only StateManager as an MQTT subscriber

**`battery_model.py` — CC-CV charging physics:**
- Converts charge rate: `fast_rate = (3.7 kW / 60 / 10 kWh) × 100 = 0.617 %/sim-min`
- Below 80% SoC: charges at full rate (Constant Current phase)
- Above 80% SoC: linear taper → `rate = slow_rate × (1 - (soc - 80) / 20)` (Constant Voltage phase)
- Responds to `charging_plug_cmd`: action="on" starts charging, action="off" stops
- Responds to `charger_fault`: sets `_charger_available = False`, stops charging
- Every tick: publishes `sensors/battery_soc`
- Math: from 50% to 80% = 30% ÷ 0.617 = 48.6 sim-minutes = 48.6 real seconds at 60× scale

**`climate_model.py` — Newton's Law of Cooling:**
- Every tick: `cabin_temp += k × (outside_temp - cabin_temp) × dt`
  - With k=0.02 and dt=1 sim-min: cabin drifts 2% of temp differential per sim-minute
- When HVAC on: additionally `cabin_temp += heater_delta × dt = 0.8°C/sim-min`
- Responds to `cabin_heater_cmd` and `seat_warmer_cmd`
- Publishes `sensors/cabin_temp` with `source: "simulator"`
  - StateManager prefers `source: "grove_dht"` when fresh (< 10 seconds old)

**`calendar_sensor.py`:**
- Holds `sim_minutes_remaining`, decrements by `dt_sim_minutes` each tick
- Publishes `sensors/departure_time` with `minutes_remaining` field
- Responds to `events/calendar_shift`: `shift_sim_minutes` is a signed delta; persists to `schedule.json`

**`weather_sensor.py`:**
- On start and every 5 real minutes: calls Open-Meteo API at lat=48.78, lon=9.18 (Stuttgart)
- Falls back to `default_outside_temp: 5.0°C` if API unavailable
- Publishes `sensors/outside_temp` with `source: "open_meteo"`

**`plugwise_actuator.py`:**
- Mirrors charger state (`circle_1`) and heater state (`circle_2`)
- No real Zigbee/python-plugwise driver — visual prop only
- Publishes `actuators/plugwise/status` whenever commanded

**`seat_warmer.py`:**
- OFF → WARMING (on "on"/"start" command) → WARM (after 5 sim-minutes)
- Publishes `actuators/seat_warmer/status` with state string

**`infotainment.py`:**
- Responds to `action: "load_route"` → publishes `state: "route_loaded"` with destination
- Responds to `action: "off"` → publishes `state: "off"`

---

### 6.2 IoT Node (`modules/iot_node/`)

Runs only on the Raspberry Pi. All Grove hardware connects via the GrovePi+ hat.

**`main.py`:**
- Creates all sensors and actuators, calls `setup_subscriptions()` on actuators, calls `start()` on sensors
- Registers `SIGINT`/`SIGTERM` handlers; blocks on `stop.wait()`
- On shutdown: calls `stop()` on sensors, `disconnect()` on MQTT

**`sensors/dht_sensor.py`:**
- Polls `grovepi.dht(port=7, dht_type=0)` every 2 real seconds
- `dht_type=0` = DHT11 (blue housing, starter kit); `dht_type=1` = DHT22 (white housing)
- Type is read from config: `cfg["grovepi"]["dht_type"]`
- On `grovepi` import failure: returns constant `(21.5, 55.0)` so the system still shows activity
- Publishes both `sensors/cabin_temp` (source: "grove_dht") and `sensors/cabin_humidity`

**`sensors/pir_sensor.py`:**
- Polls `grovepi.digitalRead(port=8)` every 0.5 real seconds
- Only publishes on state change (edge detection, not continuous)
- Can be simulated by `events/user_arrives` message from dashboard (for demo button)
- On `grovepi` import failure: always reports not occupied (False) unless simulated

**`actuators/led_actuator.py`:**
- Subscribes `actuators/ambient_light/cmd`
- Calls `grovepi.digitalWrite(port=2, value)` — port D2
- Graceful degradation if grovepi unavailable (logs only)
- Publishes `actuators/ambient_light/status`

**`actuators/relay_actuator.py`:**
- Subscribes `actuators/cabin_heater/cmd`
- Port D6; includes `relay_soft_fallback` mode (publishes state, skips GPIO write)
- Soft fallback is default (`relay_soft_fallback: true` in config) for demo safety
- Publishes `actuators/cabin_heater/status` with `mode: "soft_fallback"/"hardware"`

---

### 6.3 State Manager (`modules/state_manager/`)

The digital twin — maintains one dict of the complete current world state.

**World state dict keys:**
```python
{
  "battery_soc": float,          # % (0-100)
  "target_soc": float,           # % (from schedule.json)
  "cabin_temp": float,           # °C
  "cabin_temp_source": str,      # "grove_dht" or "simulator"
  "cabin_temp_ts": float,        # unix timestamp of last cabin_temp update
  "target_cabin_temp": float,    # °C (from schedule.json)
  "cabin_humidity": float,       # %
  "outside_temp": float,         # °C
  "occupancy": bool,
  "departure_time": str,         # ISO8601 string
  "minutes_remaining": float,    # sim-minutes until departure
  "charging": bool,
  "hvac_on": bool,
  "seat_warmer_on": bool,
  "lights_on": bool,
  "route_loaded": bool,
  "charger_available": bool,
  "last_event": dict | None,     # {"topic": ..., "payload": ..., "ts": ...}
  "last_updated": float,         # unix timestamp
}
```

**Cabin temp priority rule:** If the source is `"grove_dht"` and the last update is < 10 seconds old, simulator readings are suppressed. This ensures real hardware takes precedence when connected.

**Event handler:** Any `events/#` message updates `last_event` and triggers a publish. This propagates event context to the problem generator without needing a direct subscription chain.

---

### 6.4 Problem Generator (`modules/problem_generator/`)

Translates the world state into a PDDL problem file using Jinja2.

**Debouncing logic:** Only re-generates a problem if:
- This is the first problem (`_last_generated` is empty), OR
- SoC changed by ≥ 1%, OR
- Cabin temp changed by ≥ 0.5°C, OR
- Minutes remaining changed by ≥ 0.5 min, OR
- A `force_replan` flag is set (triggered by any `events/#` message)

**Charge rate selection:**
- Below 80% SoC: `fast_rate = (3.7 / 60 / 10) × 100 = 0.617 %/min`
- Above 80% SoC: `slow_rate × (1 - (soc - 80) / 20)` — tapers to 0 at 100%

**Total power draw computation:** Sums `charger_power_w` (if charging), `hvac_power_w` (if hvac_on), `seat_warmer_power_w` (if seat_warmer_on). This becomes the initial `total-power-draw` in the PDDL problem.

**Template rendering:** Loads `pddl/problem_template.pddl` via Jinja2 `FileSystemLoader`. The rendered string is published to `planning/problem` as `{"pddl": "...", "ts": ...}`.

---

### 6.5 Planner (`modules/planner/`)

**`main.py` — ENHSP wrapper:**
- Subscribes to `planning/problem`; also subscribes to `state/current` to keep `_last_world` current for the fallback planner
- On each problem: acquires `_planning_lock` (non-blocking — skips if already planning)
- Spawns a daemon thread to call `_solve(pddl_str)` without blocking the MQTT loop
- `_solve()`: tries ENHSP if jar exists; on failure/timeout, calls `make_plan(self._last_world)`
- ENHSP command: `java -jar planner/enhsp.jar -o pddl/domain.pddl -f /tmp/ev_problem_XXXX.pddl`
- Timeout: 10 real seconds
- Output parsing regex: `r"^(\d+\.?\d*):\s+\(([^)]+)\)\s+\[(\d+\.?\d*)\]"` — matches lines like `0.0: (charge-ev) [48.6]`
- Publishes `{"actions": [...], "ts": ..., "source": "enhsp"/"fallback"}` to `planning/plan`

**`fallback_planner.py` — rule-based planner:**
- Takes `world` dict, reads SoC, target SoC, temps, time_remaining, power limits
- Charging: `charge_duration = min((target_soc - soc) / 0.617, time_remaining - 2)` (capped to leave 2 min buffer)
- HVAC: tries to overlap with the end of charging (`hvac_start = charge_duration - hvac_duration`) when `charger_power + hvac_power ≤ max_power`
- Seat warmer: starts 8 sim-min before departure (7 sim-min duration), skipped if power budget violated
- Lights: 2 sim-min before departure (1 sim-min duration)
- Route: 1 sim-min before departure (1 sim-min duration), skipped if already loaded
- Returns a sorted list of action dicts with `action`, `start`, `duration`, `power_w` keys

**Fallback plan for default scenario (50% SoC, 10°C, 60 sim-min window):**
- `charge-ev`: 0.0 → 48.6 min
- `run-hvac`: 33.6 → 48.6 min (overlaps charging, saves 15 min)
- `warm-seat`: 52.0 → 59.0 min
- `set-lights-on`: 58.0 → 59.0 min
- `load-route`: 59.0 → 60.0 min

---

### 6.6 Executor (`modules/executor/`)

Watches the clock and dispatches actuator commands at the right simulation times.

**Action dispatch maps (built in `__init__` from `cfg["topics"]["actuators"]`):**

```python
t = cfg["topics"]["actuators"]
self._map_start = {
    "charge-ev":  (t["charging_plug_cmd"], {"action": "on"}),
    "run-hvac":   (t["cabin_heater_cmd"],  {"action": "on"}),
    "warm-seat":  (t["seat_warmer_cmd"],   {"action": "start"}),
    # set-lights-on and load-route have no start command
}
self._map_end = {
    "charge-ev":     (t["charging_plug_cmd"], {"action": "off"}),
    "run-hvac":      (t["cabin_heater_cmd"],  {"action": "off"}),
    "warm-seat":     (t["seat_warmer_cmd"],   {"action": "stop"}),
    "set-lights-on": (t["ambient_light_cmd"], {"action": "on"}),  # light turns on at end
    "load-route":    (t["infotainment_cmd"],  {"action": "load_route"}),
}
```

**Execution loop:**
- On new plan: kills old executor thread, starts new one
- Tracks `dispatched_start: set[int]` and `dispatched_end: set[int]`
- Elapsed sim-minutes: `(time.time() - plan_start_real) * time_scale / 60`
- At each tick (every 1 real second): checks all undispatched actions; dispatches START if `elapsed ≥ action["start"]`; dispatches END if `elapsed ≥ action["start"] + action["duration"]`
- When all actions dispatched: checks `_goals_met()` (SoC ≥ target, cabin_temp ≥ target, route_loaded)
- `load-route` dispatch: reads `schedule.json` to get `destination` and adds it to payload

---

### 6.7 Dashboard (`modules/dashboard/`)

**`app.py` — Flask + Flask-SocketIO:**
- `async_mode="threading"` — required for background thread compatibility
- MQTT bridge: separate `paho.mqtt.Client` instance subscribes to `sensors/#`, `state/current`, `planning/plan`, `actuators/+/status`, `actuators/plugwise/status`, `events/#`
- On each MQTT message: appends to `_event_log` (capped at 200), calls `socketio.emit("mqtt_message", entry, broadcast=True)` — `broadcast=True` is required when emitting from a non-SocketIO callback thread
- REST trigger endpoints (POST):
  - `/api/trigger/calendar_shift` → publishes `events/calendar_shift` with `shift_sim_minutes: -30`
  - `/api/trigger/charger_fault` → publishes `events/charger_fault`
  - `/api/trigger/user_arrives` → publishes `events/user_arrives`
  - `/api/trigger/replan` → publishes `events/replan`
- On WebSocket connect: emits last 50 log entries as `log_history`

**`dashboard.js`:**
- Listens for `mqtt_message` events over SocketIO
- Maintains client-side state object with battery SoC, charging status, HVAC on/off, etc.
- Calls `updateCockpit(state)`, `updateGantt(actions, minutesRemaining, planTs, source)`

**`gantt.js`:**
- Chart.js horizontal bar chart; `indexAxis: 'y'` makes bars horizontal
- Action color map: `charge-ev` → green, `run-hvac` → blue, `warm-seat` → orange, `set-lights-on` → yellow, `load-route` → cyan
- Completed actions (elapsed time > action end): grey
- In-progress (elapsed time between start and end): bright green
- Filter: only shows actions with `duration ≥ 1`
- Tracks replan events: when a new plan arrives after the first, draws a vertical "Replan" marker

**`cockpit.js`:**
- SVG top-down car view animated by `updateCockpit(state)`:
  - `updateBatteryFill(soc)` — scales battery fill bar width proportional to SoC; color: green ≥70%, orange ≥40%, red below
  - `updateChargingCable(isCharging)` — shows/hides cable SVG with `charging-pulse` CSS animation
  - `updateSeatGlow(isOn)` — ellipse opacity at driver seat
  - `updateLedStrip(isOn)` — LED strips on both sides of car body
  - `updateDashScreen(routeLoaded)` — dashboard screen text/color changes
  - `updateHvacVents(hvacOn)` — vent rectangles animate horizontally when HVAC on

---

## 7. PDDL Domain and Planning

### Domain (`pddl/domain.pddl`)

PDDL 2.1 numeric planning, compatible with ENHSP.

**Requirements:** `:durative-actions :numeric-fluents :negative-preconditions`

**Predicates (boolean state):**
- `charging` — charger is actively supplying current
- `hvac-on` — HVAC/heater is running
- `seat-warmer-on` — seat warmer is active
- `lights-on` — ambient LED lighting is on
- `route-loaded` — navigation route has been loaded
- `charger-available` — physical charger is connected and not faulted

**Numeric fluents:**
- `battery-soc`, `target-soc` — state of charge [%]
- `cabin-temp`, `target-cabin-temp`, `outside-temp` — temperatures [°C]
- `time-remaining` — simulation minutes until departure
- `total-power-draw`, `max-power` — aggregate power draw and circuit limit [W]
- `charge-rate-pct-per-min` — SoC gain per sim-minute while charging
- `hvac-power-w`, `seat-warmer-power-w`, `charger-power-w` — individual loads [W]
- `cooling-coeff`, `heater-delta-per-min` — thermal physics parameters

**5 durative actions:**

| Action | Duration bounds | Start conditions | Start effects | End effects |
|---|---|---|---|---|
| `charge-ev` | 1–120 min | not charging, charger-available, soc < target-soc, power fits | charging=true, total-power += charger-power | charging=false, total-power -= charger-power, soc += duration × rate |
| `run-hvac` | 1–60 min | not hvac-on, cabin < target, power fits | hvac-on=true, total-power += hvac-power | hvac-on=false, total-power -= hvac-power, cabin += duration × heater-delta |
| `warm-seat` | 1–15 min | not seat-warmer-on, power fits | seat-warmer-on=true, total-power += seat-power | seat-warmer-on=false, total-power -= seat-power |
| `set-lights-on` | exactly 1 min | not lights-on | (none) | lights-on=true |
| `load-route` | exactly 1 min | not route-loaded | (none) | route-loaded=true |

**Design decision — combined actions:** Earlier versions had separate `start-charging`/`charge-battery`/`stop-charging` triplets. This created complex temporal ordering constraints that ENHSP struggled with. The combined single-action design gives ENHSP a smaller search space and avoids temporal gaps.

**Metric:** `(:metric minimize (total-time))` — minimize plan makespan. Previous design used `minimize (total-power-draw)` which was always 0 at plan end (all actuators off), making it useless.

### Problem Template (`pddl/problem_template.pddl`)

Jinja2 template populated by `ProblemGenerator._generate_and_publish()`:
- Boolean predicates use CWA (Closed-World Assumption): only positive literals in `:init`
- Numeric fluents initialized with values from world state
- Goal: `battery-soc ≥ target-soc AND cabin-temp ≥ target-cabin-temp AND route-loaded`
- Metric: `minimize (total-time)`

---

## 8. GrovePi+ Hardware Architecture

### Why GrovePi+ (not direct GPIO)

Direct GPIO on the Pi requires pull-up resistors, logic level shifters, and careful pin management. The GrovePi+ eliminates all of this:

```
Pi GPIO header (40 pins)
       ↕ I2C bus (Pi pins 3=SDA, 5=SCL)
GrovePi+ ATmega328P (I2C address 0x04)
       ↕ digital/analog port drivers
Grove sensor connectors (D2, D3, D4, D5, D6, D7, D8, A0, A1, A2)
       ↕ Grove cables (4-wire, keyed)
Sensors and actuators
```

The `grovepi` Python library talks to the ATmega over I2C. Port numbers in code (`dht_port: 7`) correspond to ATmega Arduino pin numbers (D7 = Arduino digital pin 7).

### Wiring Table

| Sensor/Actuator | GrovePi+ Port | Config key | Code location |
|---|---|---|---|
| DHT11/22 temp+humidity | **D7** | `grovepi.dht_port: 7` | `dht_sensor.py` |
| PIR motion sensor | **D8** | `grovepi.pir_port: 8` | `pir_sensor.py` |
| Grove LED | **D2** | `grovepi.led_port: 2` | `led_actuator.py` |
| Grove Relay | **D6** | `grovepi.relay_port: 6` | `relay_actuator.py` |

### DHT Sensor Type

- **Blue housing** = DHT11 → `dht_type: 0` (default in config — GrovePi starter kit)
- **White housing** = DHT22 → `dht_type: 1` (more accurate; change in config if using this)

### Verification

After mounting the hat and enabling I2C (`sudo raspi-config` → Interface Options → I2C), verify with:

```bash
sudo i2cdetect -y 1
```

Expected output shows `04` at address 0x04. If absent, the hat is not fully seated.

---

## 9. Physics Models

### CC-CV Battery Charging

Real lithium-ion batteries charge in two phases:
1. **Constant Current (CC):** Full charge rate until ~80% SoC → fast, linear SoC rise
2. **Constant Voltage (CV):** Rate tapers linearly from 80% to 0% at 100% → slower, protects cells

Implementation in `battery_model.py`:
```python
def _charge_rate_pct_per_min(self) -> float:
    if self.soc < self._taper_threshold:     # below 80%
        return self._fast_rate_pct_per_min   # 0.617 %/min
    fraction = 1.0 - (self.soc - 80) / 20   # 1.0 at 80%, 0.0 at 100%
    return self._slow_rate_pct_per_min * fraction
```

**Charge time math:**
- Fast rate: 3.7 kW / 60 min / 10 kWh × 100% = **0.617 %/min**
- Slow rate (taper phase): 1.85 kW / 60 / 10 × 100% = **0.308 %/min** (max, tapers to 0)
- From 50% to 80% = 30% ÷ 0.617 = **48.6 sim-minutes** ≈ 48.6 real seconds at 60× scale

### Newton's Law of Cooling

The cabin temperature evolves as:
```
cabin_temp(t + dt) = cabin_temp(t) + k × (outside_temp - cabin_temp(t)) × dt
                   + heater_delta × is_heating × dt
```

With `k=0.02` per sim-minute and `dt=1.0` sim-min:
- Passive cooling: cabin loses 2% of the temperature differential per sim-minute
- Active heating: cabin gains 0.8°C per sim-minute when HVAC is on

### Power Budget Constraints

| Combination | Total power | Within limit? |
|---|---|---|
| Charger only | 3700W | ✓ (3700 ≤ 5750) |
| HVAC only | 2000W | ✓ (2000 ≤ 5750) |
| Charger + HVAC | 5700W | ✓ (5700 ≤ 5750) — can run simultaneously |
| Charger + HVAC + Seat | 5850W | ✗ (5850 > 5750) — cannot all three at once |

The PDDL planner enforces this via the power budget check in each action's `:condition`. The fallback planner enforces it programmatically.

---

## 10. Time Acceleration

`time_scale: 60` means 1 real second = 60 simulation seconds = 1 simulation minute.

So a 60-minute plan plays out in **60 real seconds (1 real minute)**.

This affects:
- `dt_sim_minutes = tick_interval_s × time_scale / 60 = 1.0 × 60 / 60 = 1.0 sim-min/tick`
- Executor: `elapsed_sim_min = elapsed_real_s × time_scale / 60`
- Calendar: counts down 1 sim-minute per real second

For a longer demo, increase `sim_minutes_until_departure` in `schedule.json` (e.g., `120.0` for a 2-minute demo).

---

## 11. MQTTClient Implementation Details

`modules/common/mqtt_client.py` wraps paho-mqtt 1.x (pinned `<2.0` to avoid breaking API changes).

**Exact-topic subscriptions:** Uses `message_callback_add(topic, handler)` — paho internally matches and routes the message.

**Wildcard subscriptions (`subscribe_wildcard`):** Registers a `client.on_message` handler that explicitly calls `mqtt.topic_matches_sub(pattern, msg.topic)` before invoking the callback. This is necessary because paho 1.x `message_callback_add` with wildcards has undefined behavior.

**Reconnect re-subscription:** `_on_connect` iterates `self._subscriptions` and re-subscribes to all patterns after every connection (including reconnects).

---

## 12. Python Compatibility

All files using `X | Y` union type hints (Python 3.10+) or `list[T]`/`dict[K,V]` in type annotations (Python 3.9+) include:
```python
from __future__ import annotations
```

This makes the annotations lazy-evaluated strings, compatible with Python 3.9. The Pi runs Python 3.9 on Bullseye or Python 3.11 on Bookworm.

Affected files: `config_loader.py`, `mqtt_client.py`, `dht_sensor.py`, `pir_sensor.py`, `planner/main.py`, `fallback_planner.py`, `executor/main.py`, `dashboard/app.py`, `plugwise_actuator.py`.

---

## 13. Running the System

### Laptop — recommended: one command

```bash
python run_all.py --start-broker     # starts the broker + all 6 laptop modules
```

`run_all.py` (project root) spawns the six laptop modules as subprocesses, tags and
streams their combined output into one window, pre-checks broker reachability before
starting, supervises them (printing which module exited if one dies and then stopping
the rest), and shuts them all down cleanly on Ctrl+C. `--start-broker` runs
`docker compose up -d` first; omit it if the broker is already running. The manual
per-terminal flow below is equivalent and useful for debugging one module in isolation.

### Laptop — manual: 7 terminal windows (all need `(.venv)` active)

```bash
# Activate venv first in each terminal:
cd smart-ev-cabin
.venv\Scripts\activate

# Terminal 1 — MQTT broker
docker compose up

# Terminal 2 — Simulator
python -m modules.simulator.main

# Terminal 3 — State Manager
python -m modules.state_manager.main

# Terminal 4 — Problem Generator
python -m modules.problem_generator.main

# Terminal 5 — Planner
python -m modules.planner.main

# Terminal 6 — Executor
python -m modules.executor.main

# Terminal 7 — Dashboard (then open http://localhost:5000)
python -m modules.dashboard.app
```

### Raspberry Pi — SSH terminal

```bash
cd ~/smart-ev-cabin
python3 -m modules.iot_node.main
```

### Verify with mosquitto_sub

```bash
docker exec ev-mosquitto mosquitto_sub -t "#" -v
```

Expected stream: `sensors/battery_soc`, `sensors/cabin_temp`, `state/current`, `planning/plan`, actuator commands.

---

## 14. Demo Scenario

### Setup before each demo

1. In `config/schedule.json`, set `sim_minutes_until_departure: 60.0`
2. Start all 7 laptop terminals + Pi SSH terminal
3. Open browser to `http://localhost:5000`

### Normal operation (show first)

- Dashboard shows battery SoC gauge rising from 50%
- Cabin temp at 10°C
- Gantt chart: `charge-ev` 0→48.6 min, `run-hvac` 33.6→48.6 min (overlapping), `warm-seat` 52→59 min, `set-lights-on` 58→59 min, `load-route` 59→60 min

Real-time sequence (1 sim-minute = 1 real second at 60× scale):
- **T=0s**: charging starts (START of `charge-ev`); cable glow appears in cockpit widget
- **T=33.6s**: HVAC starts (START of `run-hvac`); cabin heater badge turns on
- **T=48.6s**: charging stops (END of `charge-ev`); HVAC stops (END of `run-hvac`)
- **T=52s**: seat warmer starts (START of `warm-seat`); seat glow appears in cockpit
- **T=59s**: seat warmer stops (END of `warm-seat`); LED lights on (END of `set-lights-on`); LED strips glow in cockpit
- **T=60s**: route loads (END of `load-route`); dashboard screen shows "Route Ready"

### Demo Event 1 — Charger Fault

Click **"Charger Fault"** button on dashboard:
- `events/charger_fault` published → BatteryModel sets `charger_available=False`, stops charging
- StateManager propagates to world state
- ProblemGenerator detects the `events/#` trigger → forces replan
- New plan: no `charge-ev` action; HVAC and comfort actions rescheduled
- Executor shows "Replan" marker on Gantt chart

### Demo Event 2 — Shift Departure -30 min

Click **"Shift -30 min"** button:
- `events/calendar_shift` with `shift_sim_minutes: -30` → CalendarSensor decrements by 30
- New `minutes_remaining` triggers problem regeneration
- Planner must fit everything into 30 min instead of 60 min
- Power constraint forces HVAC + charger to overlap (possible at 5700W ≤ 5750W)

### Demo Event 3 — User Arrives Early

Click **"User Arrives"** button:
- `events/user_arrives` published → PIRSensor sets `_simulated_occupied=True`
- `sensors/occupancy` publishes `{"value": true}`
- Dashboard occupancy dot turns green

---

## 15. Key Numbers Table

| Parameter | Value | Explanation |
|---|---|---|
| Time scale | 60× | 1 real second = 1 simulation minute |
| Initial SoC | 50% | Realistic overnight partial charge |
| Target SoC | 80% | Standard smart charging limit |
| Battery capacity | 10 kWh | Small demo EV; charging finishes visibly in ~49 seconds |
| Charge rate (CC) | 3.7 kW = 0.617%/min | Standard 16A Type-2 home charger |
| Charge rate (CV) | 1.85 kW max, tapers | CC-CV boundary at 80% SoC |
| Charging time (50→80%) | 48.6 sim-min = 48.6 real seconds | 30% ÷ 0.617 %/min |
| HVAC power | 2000W | |
| Seat warmer power | 150W | |
| Max power budget | 5750W | 25A × 230V circuit |
| Charger + HVAC | 5700W | Just fits (≤5750W), can overlap |
| Charger + HVAC + Seat | 5850W | Exceeds limit, cannot all run at once |
| ENHSP timeout | 10 real seconds | After which rule-based fallback activates |
| PDDL actions | 5 | charge-ev, run-hvac, warm-seat, set-lights-on, load-route |
| Cooling coefficient (k) | 0.02 per sim-min | Newton's Law — cabin loses 2% of temp differential per min |
| Heater delta | 0.8°C per sim-min | HVAC heating rate |
| Taper threshold | 80% SoC | CC→CV transition point |
| DHT poll interval | 2 real seconds | |
| PIR poll interval | 0.5 real seconds | |
| Weather refresh | 300 real seconds (5 min) | |

---

## 16. Dependencies

### Laptop (`requirements-laptop.txt`)

| Package | Version | Purpose |
|---|---|---|
| paho-mqtt | ≥1.6, <2.0 | MQTT client; pinned <2.0 to avoid API breaking changes |
| flask | ≥3.0 | Dashboard web server |
| flask-socketio | ≥5.3 | WebSocket bridge for live dashboard updates |
| simple-websocket | ≥0.10 | Required by Flask-SocketIO in threading mode |
| requests | ≥2.31 | Open-Meteo weather API calls |
| pyyaml | ≥6.0 | config.yaml loading |
| jinja2 | ≥3.1 | PDDL problem template rendering |

### Raspberry Pi (`requirements-pi.txt`)

| Package | Version | Purpose |
|---|---|---|
| paho-mqtt | ≥1.6, <2.0 | MQTT client |
| pyyaml | ≥6.0 | config.yaml loading |
| grovepi | system-wide | Grove sensor drivers; installed with `sudo pip3 install grovepi [--break-system-packages]` |

### Infrastructure

| Tool | Version | Purpose |
|---|---|---|
| Eclipse Mosquitto | 2.0 (Docker) | MQTT broker |
| Java JRE | 11+ (21 LTS recommended) | ENHSP planner runtime |
| Docker Desktop | 24.x | Runs Mosquitto container |

---

## 17. Known Bugs Fixed During Development

1. **`calendar.tick()` TypeError** — called with 0 args; signature requires `dt_sim_minutes: float`. Fixed in `simulator/main.py`.
2. **Power budget deadlock** — config had `charge_rate_kw: 7.4` (7400W) > `max_power_w: 3700W`. PDDL precondition always false → charging could never start. Fixed: `charge_rate_kw: 3.7`, `capacity_kwh: 10.0`, `max_power_w: 5750`.
3. **PDDL temporal planning gap** — separate start/charge/stop triplet caused ENHSP to struggle. Fixed: rewrote to 5 combined durative actions.
4. **Useless PDDL metric** — `minimize (total-power-draw)` is always 0 at plan end. Fixed: `minimize (total-time)`.
5. **Executor never sent "off" commands** — only dispatched at action START. Fixed: added `_MAP_END` dict and `dispatched_end` set.
6. **Fallback planner used old action names** — `start-charging`, `charge-battery`, etc. don't exist in simplified domain. Fixed: complete rewrite with new names.
7. **Wildcard subscription bug** — `subscribe_wildcard` called callback for ALL messages. Fixed: added `mqtt.topic_matches_sub(pattern, msg.topic)` check.
8. **`events/user_arrives` hardcoded** — not in config.yaml. Fixed: added to config; both pir_sensor and dashboard now use config-driven topic.
9. **`actuators/plugwise/status` hardcoded** — not in config. Fixed: added as `actuators.plugwise_status`; plugwise_actuator now uses config.
10. **DHT type hardcoded as 1 (DHT22)** — starter kits ship DHT11. Fixed: `dht_type: 0` in config; dht_sensor reads from config.
11. **Python 3.9/3.10 incompatible type hints** — `X | Y` requires 3.10+. Fixed: `from __future__ import annotations` in all 9 affected files.
12. **Missing `simple-websocket`** — Flask-SocketIO threading mode requires it. Fixed: added to requirements-laptop.txt.
13. **Old action names in gantt.js** — COLOR/LABEL maps used old action names. Fixed: updated to new 5-action names.
14. **`modules/__init__.py` missing** — `modules/` directory lacked `__init__.py`, breaking `from modules.X import Y` style imports when tests or scripts were run outside the project root. Fixed: created empty `modules/__init__.py`.
15. **Executor dispatch maps hardcoded topic strings** — `_MAP_START`/`_MAP_END` were module-level constants with literal topic strings (e.g. `"actuators/charging_plug/cmd"`). If any topic key changes in `config.yaml`, the executor would silently dispatch to the wrong topic. Fixed: moved both maps into `Executor.__init__`, built from `cfg["topics"]["actuators"]`.
16. **Dashboard duplicate plugwise subscription** — `_FORWARD_TOPICS` listed both `"actuators/+/status"` and `"actuators/plugwise/status"`; the `+` wildcard already covers plugwise. With some MQTT broker configurations this causes the broker to deliver the message twice per publish, creating duplicate event log entries. Fixed: removed the explicit `"actuators/plugwise/status"` entry.
17. **`weather_sensor.py` ignored `config.yaml` api_url** — A hardcoded module constant `_OPEN_METEO_URL` overrode `cfg["weather"]["api_url"]`, making the config key a no-op. Fixed: removed the constant; constructor reads `self._api_url = weather["api_url"]` and `_fetch()` uses `self._api_url`.
18. **`dht_sensor.py` DHT read unpack crash** — `[temp, humidity] = grovepi.dht(...)` uses destructuring that requires exactly 2 values. Some grovepi library versions return `[temp, humidity, crc]` (3 values), causing `ValueError: too many values to unpack` on every read. Caught by try/except, but silently disabled the sensor for the entire demo. Fixed: use `result = grovepi.dht(...); temp = float(result[0]); humidity = float(result[1])`.
19. **`planner/main.py` temp file leak** — `_run_enhsp()` called `os.unlink(tmp_path)` only on normal subprocess return. On `TimeoutExpired` and `FileNotFoundError` exceptions the temp file was never deleted. Fixed: initialise `tmp_path = None`; move cleanup into a `finally` clause.
20. **`README.md` wrong initial SoC** — demo scenario said "battery 40%" but config has `initial_soc: 50.0`. Fixed to "battery 50%".
21. **`README.md` wrong plan timing in demo scenario** — HVAC listed at T≈40 (actual T≈34); seat warmer at T≈55 (actual T≈52); lights/route steps in wrong order. Fixed all timings.
22. **`README.md` DHT hardware mismatch** — hardware table said "DHT22" but config default is `dht_type: 0` (DHT11). Fixed to "DHT11/22".
23. **`README.md` schedule.json example missing field** — `sim_minutes_until_departure` was absent, confusing readers who create their own schedule.json from the example. Fixed: added the field.
24. **`docs/deployment_guide.md` wrong executor log example** — showed "(8 actions)" but 5 combined durative actions produce 5 plan entries. Fixed to "(5 actions)".
25. **`calendar_sensor.py` missing immediate publish after shift** — `_on_calendar_shift` updated `_sim_minutes_remaining` and saved to file but did NOT call `self._publish()`. The updated remaining time only propagated on the next tick (≤1s delay). During that gap, ProblemGenerator (triggered by `force_replan=True` from the same event) generated a problem using the OLD `minutes_remaining` from StateManager, producing a stale plan that was immediately replaced by the correct one. Fixed: added `self._publish()` after `save_schedule()`.
26. **`planner/main.py` empty ENHSP plan bypasses fallback** — `if plan is not None:` passed an empty list `[]` through as a valid plan. When ENHSP exits 0 but finds no solution (e.g. problem infeasible), `_parse_enhsp_output` returns `[]`, executor receives empty action list and exits immediately, leaving the system in a stall with no active plan and no fallback triggered. Fixed: changed to `if plan:` so an empty list also falls through to the rule-based fallback.
27. **`docs/presentation_guide.md` wrong HVAC start time** — Module 4 description said "turn on the heater at T+40 minutes"; actual fallback-planner output is T+34 minutes (same value corrected in README Bug 21). Also said "seat warmer at T+55, load route at T+59" — actual values are T+52 and T+60 respectively. Fixed all three to match the actual plan.
28. **`docs/presentation_guide.md` executor fault description inaccurate** — Module 5 section said "the executor notices and asks for a new plan" when a charger breaks. The executor does not detect faults; replanning is triggered by the event-driven MQTT chain (dashboard → `events/charger_fault` → ProblemGenerator `force_replan`). Fixed: corrected to describe the actual MQTT event flow.
29. **`docs/presentation_guide.md` Demo Event 1 wrong mechanism** — Said "Executor detects precondition failure → triggers replan" and "Dashboard shows a replan marker on the Gantt chart". Both are inaccurate: replan is event-driven (not executor-detected), and replan markers are tracked in gantt.js but never rendered (annotation plugin returns `{}`). Fixed: replaced with accurate event-chain description; Gantt update phrased as "Gantt chart updates to reflect the new schedule".

---

## 18. Course Requirements Coverage

This project satisfies all 6 Smart Cities & IoT course requirements:

| Requirement | How satisfied |
|---|---|
| IoT Sensors | Grove DHT11/22 (real temperature + humidity), Grove PIR (real occupancy), Open-Meteo weather API (real data) |
| IoT Actuators | Grove LED (real GPIO), Grove Relay (real GPIO), simulated seat warmer + infotainment + charging plug |
| Distributed system | Two physical devices (Pi + Laptop) communicating over MQTT |
| AI/Smart reasoning | PDDL 2.1 numeric planning with ENHSP; constraint-aware scheduling under power budget and time deadline |
| Real-time monitoring | Flask + SocketIO dashboard; Gantt plan timeline; EV cockpit SVG widget; live sensor gauges |
| Simulation/Digital twin | StateManager as digital twin; BatteryModel + ClimateModel as physics-based virtual EV; time-accelerated simulation |
