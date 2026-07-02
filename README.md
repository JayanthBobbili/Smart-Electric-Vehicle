# Smart EV Charging & Cabin Prep

**Group 22 — Smart Cities & Internet of Things · University of Stuttgart · Summer 2026**

An IoT system that autonomously prepares a parked EV for departure by managing battery charging, cabin climate, seat warming, ambient lighting, and route loading — all orchestrated by a PDDL 2.1 AI planner running on a laptop while physical sensors on a Raspberry Pi 3B+ provide real-world data.

---

## Architecture

```
┌─────────────────────────────┐       MQTT       ┌──────────────────────────────────────────────┐
│   Raspberry Pi 3B+          │◄────────────────►│  Laptop                                      │
│   (modules/iot_node)        │                  │                                              │
│                             │                  │  Mosquitto broker (Docker)                   │
│  • Grove DHT — cabin temp   │                  │  modules/simulator    — battery/climate/etc  │
│  • Grove PIR — occupancy    │                  │  modules/state_manager — digital twin        │
│  • Grove LED — ambient light│                  │  modules/problem_generator — PDDL problems  │
│  • Grove Relay — heater     │                  │  modules/planner     — ENHSP + fallback      │
└─────────────────────────────┘                  │  modules/executor    — plan dispatch         │
                                                 │  modules/dashboard   — Flask + SocketIO UI  │
                                                 └──────────────────────────────────────────────┘
```

**Simulation time**: 1 real second = 60 simulation seconds. Configurable via `config/config.yaml → simulation.time_scale`.

---

## Course Requirements Mapping

| Requirement | Implementation |
|---|---|
| System distribution (2+ machines) | Pi runs `iot_node`; laptop runs all other modules |
| System integration (MQTT pub/sub) | All modules communicate exclusively via Mosquitto MQTT |
| AI planning (PDDL 2.1 + ENHSP) | `problem_generator` renders numeric PDDL; `planner` invokes ENHSP |
| IoT (4+ sensors, 4+ actuators) | Sensors: DHT (temp+humidity), PIR, battery SoC, weather API; Actuators: LED, relay, charging plug, seat warmer, infotainment |
| Modular system design | 8 independent modules with single responsibilities |
| Visualisation | Live state gauges + EV cockpit SVG widget + Gantt plan timeline |

---

## Prerequisites

### Laptop
- Python 3.11+
- Docker Desktop (for Mosquitto broker)
- Java 11+ (for ENHSP planner)

### Raspberry Pi
- Raspberry Pi 3B+ with GrovePi+ hat
- Python 3.9+ (pre-installed on Raspberry Pi OS)
- GrovePi Python library (system install)

---

## Setup

### 1 — Clone the repository

```bash
git clone https://github.com/<your-org>/smart-ev-cabin.git
cd smart-ev-cabin
```

### 2 — Download ENHSP

ENHSP is not committed to the repository because of its size. Download the latest release from the official repository and place it at `planner/enhsp.jar`:

```bash
# Download ENHSP-20 (or later)
curl -L https://enricos83.github.io/ENHSP/enhsp.jar -o planner/enhsp.jar
```

If ENHSP or Java is unavailable, the system automatically falls back to the rule-based planner.

### 3 — Start Mosquitto broker

```bash
docker compose up -d
```

Verify: `docker logs ev-mosquitto`

### 4 — Set up laptop Python environment

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-laptop.txt
```

### 5 — Configure departure schedule

Edit `config/schedule.json` to set your desired departure time and targets:

```json
{
  "departure_time": "2026-06-24T08:00:00",
  "sim_minutes_until_departure": 60.0,
  "target_soc": 80.0,
  "target_cabin_temp": 22.0,
  "destination": "Stuttgart HBF"
}
```

### 6 — Set up Raspberry Pi

```bash
# On the Pi — install GrovePi
sudo apt-get update && sudo apt-get install -y python3-pip
sudo pip3 install grovepi paho-mqtt pyyaml

# Copy the repo or just iot_node module to the Pi, then:
python3 -m modules.iot_node.main
```

Edit `config/config.yaml → broker.host` to point at the laptop's IP address.

---

## Running (Laptop)

### Quick start (recommended)

Start the broker and all six laptop modules with a single command:

```bash
python run_all.py --start-broker
```

`run_all.py` streams every module's output (tagged by name) into one window, verifies the
MQTT broker is reachable before starting, and stops everything cleanly on `Ctrl+C`. If any
module crashes it names which one and stops the rest, so failures are never silent. Then open
the dashboard at http://localhost:5000. (Omit `--start-broker` if the broker is already up.)

### Manual (one terminal per module)

Alternatively, open **6 terminals** (or use tmux/screen):

```bash
# Terminal 1 — Simulator (battery, climate, weather, calendar)
python -m modules.simulator.main

# Terminal 2 — State manager (digital twin)
python -m modules.state_manager.main

# Terminal 3 — Problem generator (PDDL rendering)
python -m modules.problem_generator.main

# Terminal 4 — Planner (ENHSP + fallback)
python -m modules.planner.main

# Terminal 5 — Executor (plan dispatch)
python -m modules.executor.main

# Terminal 6 — Dashboard (open browser at http://localhost:5000)
python -m modules.dashboard.app
```

On the Raspberry Pi (separate terminal):

```bash
python -m modules.iot_node.main
```

---

## Demo Scenario

Default state: battery **50%**, cabin 10°C, departure in 60 sim-minutes (= 1 real minute), target SoC 80%, target cabin 22°C.

**Expected plan** (fallback planner; ENHSP may vary slightly):
1. Start charging at T=0 sim-min
2. Start HVAC at T≈34 sim-min (overlaps end of charge — stays within 5750W budget)
3. Both charging and HVAC stop at T≈49 sim-min (SoC reaches 80%)
4. Start seat warmer at T≈52 sim-min
5. Seat warmer stops + **lights on** at T=59 sim-min
6. **Route loaded** at T=60 sim-min

**Demo trigger 1** — Click **"Charger Fault"** at T≈20 sim-min:
- Executor detects fault → publishes `events/replan`
- Problem generator re-renders PDDL with `charger_available=false`
- Planner generates new plan (HVAC-first, no charging)
- Gantt chart updates with a replan marker

**Demo trigger 2** — Click **"Shift -30 min"**:
- Departure moves 30 sim-minutes earlier
- Power constraint forces interesting parallel scheduling
- Gantt shows compressed plan

**Demo trigger 3** — Click **"User Arrives"**:
- PIR occupancy toggled → triggers early-arrival handling
- Plan may reschedule seat warmer / lights to "now"

---

## Project Structure

```
smart-ev-cabin/
├── config/
│   ├── config.yaml          — broker, sensors, simulation settings
│   └── schedule.json        — departure time, targets (editable at runtime)
├── pddl/
│   ├── domain.pddl           — PDDL 2.1 numeric domain (static)
│   └── problem_template.pddl — Jinja2 template for problem files
├── planner/
│   └── enhsp.jar            — Download separately (see Setup)
├── modules/
│   ├── common/              — shared MQTT client and config loader
│   ├── iot_node/            — Raspberry Pi sensors & actuators
│   ├── simulator/           — software-defined EV (battery, climate, virtual actuators)
│   ├── state_manager/       — digital twin
│   ├── problem_generator/   — PDDL problem renderer
│   ├── planner/             — ENHSP wrapper + rule-based fallback
│   ├── executor/            — plan step dispatch
│   └── dashboard/           — Flask + SocketIO live dashboard
└── tests/                   — unit tests for physics and state models
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## MQTT Topic Reference

| Topic | Publisher | Description |
|---|---|---|
| `sensors/cabin_temp` | iot_node (real) / simulator | Cabin temperature °C |
| `sensors/cabin_humidity` | iot_node | Relative humidity % |
| `sensors/occupancy` | iot_node | Seat occupancy boolean |
| `sensors/battery_soc` | simulator | Battery state of charge % |
| `sensors/outside_temp` | simulator | Ambient temperature from Open-Meteo API |
| `sensors/departure_time` | simulator | ISO-8601 departure + minutes remaining |
| `state/current` | state_manager | Full world state JSON |
| `planning/problem` | problem_generator | PDDL problem string |
| `planning/plan` | planner | JSON action list |
| `actuators/*/cmd` | executor | Actuator command payloads |
| `actuators/*/status` | each actuator | Current actuator state |
| `events/replan` | executor / dashboard | Replan trigger |
| `events/calendar_shift` | dashboard | New departure time |
| `events/charger_fault` | dashboard | Simulated charger failure |

---

## Hardware Wiring (GrovePi+)

| Component | Grove Port | Config key |
|---|---|---|
| DHT11/22 temp/humidity | D7 | `grovepi.dht_port` (`dht_type: 0` = DHT11, `1` = DHT22) |
| PIR motion sensor | D8 | `grovepi.pir_port` |
| Grove LED | D2 | `grovepi.led_port` |
| Grove Relay | D6 | `grovepi.relay_port` |

The relay has a software fallback mode (`relay_soft_fallback: true` in config). When enabled, relay commands are accepted and status is published without any GPIO writes — useful if the relay hardware is unreliable.

---

## License

MIT
