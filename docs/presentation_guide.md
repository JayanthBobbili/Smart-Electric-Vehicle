# What Is This Project? — Presenter's Guide

**Smart EV Charging & Cabin Prep · Group 22 · University of Stuttgart**

This guide explains the project in simple language. Use it to understand what to say during the presentation. You don't need to know programming — just understand the story and what each part does.

---

## The Big Idea (Say This First)

> "Imagine you own an electric car. Every morning you need to leave by 8 AM. But every morning you have to:
> manually check if the battery is charged enough, manually turn on the heater so the cabin isn't freezing,
> manually load the navigation route, and manually turn on the lights.
>
> What if the car could do all of this by itself — automatically — while you were still sleeping?
>
> That's exactly what our system does."

The system watches the car overnight, decides what needs to happen before you leave, builds a schedule (called a **plan**), and then executes it — all without any human input. It even adapts if something goes wrong, like the charger breaking.

---

## Two Machines Working Together

The project runs on **two physical devices** connected over a Wi-Fi network. This is what "distributed IoT system" means.

```
┌─────────────────────────┐        Wi-Fi         ┌──────────────────────────┐
│   Raspberry Pi          │ ◄──────────────────► │   Laptop                 │
│   (the "car's brain")   │                      │   (the "cloud server")   │
│                         │                      │                          │
│  Reads real sensors:    │                      │  Does the smart work:    │
│  • How hot is the cabin?│                      │  • Simulates battery     │
│  • Is someone sitting   │                      │  • Gets weather data     │
│    in the car?          │                      │  • Makes the AI plan     │
│                         │                      │  • Shows live dashboard  │
│  Controls real things:  │                      │                          │
│  • Turns LED on/off     │                      │                          │
│  • Triggers relay       │                      │                          │
└─────────────────────────┘                      └──────────────────────────┘
```

They talk to each other using **MQTT** — a messaging system designed specifically for IoT devices. Think of it like a group chat where every device can send messages and listen for messages at the same time.

---

## The Sensors (What the System Can "Feel")

A **sensor** is a device that measures something from the real world.

| Sensor | Hardware | What It Measures | Where |
|---|---|---|---|
| Temperature & Humidity | Grove DHT11/22 | How hot/cold and humid the cabin is | Raspberry Pi |
| Motion/Occupancy | Grove PIR | Whether someone is sitting in the car | Raspberry Pi |
| Battery Level | Software simulation | How charged the battery is (0–100%) | Laptop |
| Outside Temperature | Open-Meteo weather API | Real Stuttgart weather from the internet | Laptop |
| Time to Departure | Schedule file | How many minutes until you need to leave | Laptop |

**Why are some sensors "software simulations"?**
Because we can't connect a real battery or weather thermometer to a demo setup. So the laptop runs a physics-based program that behaves exactly like a real battery would (it charges faster when empty, slows down above 80% charge — just like a real EV) and fetches real weather data from the internet.

---

## The Actuators (What the System Can "Do")

An **actuator** is a device that the system can control — it makes something happen in the real world.

| Actuator | Hardware | What It Does | Where |
|---|---|---|---|
| Ambient Light | Grove LED | Turns the cabin light on/off | Raspberry Pi |
| Cabin Heater | Grove Relay | Switches the heater on/off | Raspberry Pi |
| EV Charger | Plugwise Circle (simulated) | Starts/stops charging (visual prop) | Dashboard |
| Seat Warmer | Software simulation | Heats the seat (shown in dashboard) | Dashboard |
| Infotainment | Software simulation | Loads the navigation route | Dashboard |

**About the Plugwise plugs:** The Plugwise smart plugs are shown as physical props during the demo. They appear on the dashboard and animate when charging or heating is active. This is our "synthetic widget" — a visual simulation for hardware we can't fully connect.

---

## The 6 Software Modules (What Each Program Does)

The laptop runs 6 separate programs (modules) at the same time. Each module has one job. They all talk to each other through MQTT messages.

### Module 1: Simulator
**Job:** Acts as a fake-but-realistic EV.

It runs physics equations to simulate:
- Battery charging (including the taper effect above 80% — this is how real lithium batteries work)
- Cabin temperature (uses Newton's Law of Cooling — the same physics your coffee uses when it cools down)
- Countdown timer to departure
- Real Stuttgart weather from the internet

Without this module, we'd need an actual EV in the room.

### Module 2: State Manager
**Job:** Keeps track of everything happening right now. It's the system's memory.

It listens to all sensor messages and maintains one big dictionary of the current world:
- "Battery is at 42%"
- "Cabin is 10°C"
- "Departure is in 47 minutes"
- "Charger is ON"
- etc.

Every other module reads from this "world state" to know what's going on.

### Module 3: Problem Generator
**Job:** Translates the current world state into a formal AI planning problem.

It takes the world state (e.g., "battery 42%, target 80%, 47 minutes left") and writes it as a **PDDL file** — a special language that AI planners can read.

Think of it like writing a task list for the AI: "Given these starting conditions and these goals, here's the problem."

### Module 4: Planner (The AI Part)
**Job:** Solves the planning problem and creates a schedule.

This is the most academically interesting part. It uses **ENHSP** — a real AI planning engine from academic research — that reads the PDDL problem and figures out the best schedule.

For example: "Start charging now, turn on the heater at T+34 minutes because by then there is enough headroom within the power budget, start the seat warmer at T+52, lights on at T+59, load the route at T+60."

**What if ENHSP is not available?** There's a built-in fallback: a rule-based planner that applies simple logic ("if battery < target, schedule charging; if cabin < target temp, schedule HVAC"). This ensures the demo never breaks.

### Module 5: Executor
**Job:** Watches the clock and sends commands when it's time.

It reads the plan ("at T+34 minutes, turn on HVAC") and waits. When the time comes, it publishes a command message over MQTT: "cabin_heater → ON". The Raspberry Pi receives this and physically activates the relay.

The system also watches for fault events. If the charger breaks (triggered via the dashboard), the event-driven MQTT architecture automatically requests a new plan — ProblemGenerator detects the event, forces a replan, and the Planner produces a revised schedule without charging.

### Module 6: Dashboard
**Job:** Shows everything happening live in a web browser.

Open `http://localhost:5000` and you'll see:
1. **Live State** panel: battery gauge, cabin temperature bar, countdown timer
2. **EV Cockpit Widget**: an animated top-down view of the car — the charging cable glows when charging, the seat glows when warming, the LED strips light up
3. **Plan Timeline**: a Gantt chart showing the current schedule
4. **Event Log**: every MQTT message in real-time

The dashboard also has buttons to trigger demo events.

---

## The Communication System (MQTT)

MQTT is a lightweight messaging protocol. Think of it like a **message bus** where:
- Any device can **publish** a message to a "topic" (like posting in a chat channel)
- Any device can **subscribe** to topics and receive all messages on that topic

Examples of our topics:
- `sensors/battery_soc` — simulator publishes battery level every second
- `actuators/cabin_heater/cmd` — executor publishes "turn on heater" command
- `planning/plan` — planner publishes the schedule it computed
- `events/charger_fault` — dashboard publishes "something broke" when you press a button

The **Mosquitto broker** (runs in Docker on the laptop) is like the post office — all messages go through it.

---

## The AI Planning (The Clever Part)

This is what makes the project more than just "if battery low, charge battery."

**PDDL (Planning Domain Definition Language)** is a formal language used in AI research. We define:
- **The domain**: What actions are possible, their preconditions (requirements) and effects
  - e.g., "start charging" requires charger to be available AND power budget has room; effect is that charging starts and power draw increases
- **The problem**: Current state + goal state
  - e.g., "battery is 50%, target is 80%, 60 minutes left, max power 5750W"

The AI planner finds a valid sequence of actions that:
1. Respects all constraints (e.g., total power draw must stay below 5750W)
2. Achieves all goals (battery ≥ 80%, cabin ≥ 22°C, route loaded)
3. Fits within the time deadline

This is much more powerful than hardcoded rules. If you change the departure time or power limit, the planner automatically finds a new, valid schedule.

---

## The Demo Events (What to Show)

### Normal Operation (show this first)
1. Start the system → simulator shows battery at 50%, cabin at 10°C
2. Planner generates a schedule
3. Gantt chart shows: `charge-ev` 0→49 min overlapping `run-hvac` 34→49 min, then `warm-seat` 52→59 min, `load-route` at 59 min
4. Watch the battery gauge rise in real-time — should hit 80% in about 1 real minute

### Demo Event 1: Charger Fault
- Click "Charger Fault" on the dashboard
- The charger turns off (shown in cockpit widget)
- Fault event propagates via MQTT → ProblemGenerator forces a replan
- New plan appears: charging removed, HVAC moved earlier, power budget rebalanced
- Dashboard event log shows the replan; Gantt chart updates to reflect the new schedule

### Demo Event 2: Shift Departure -30 Minutes
- Click "Shift -30 min" button
- Departure is now 30 simulation-minutes earlier
- Planner must find a faster schedule
- Some tasks may run in parallel (but total power must stay within limit)
- Interesting trade-offs appear in the Gantt chart

### Demo Event 3: User Arrives Early
- Click "User Arrives" button
- The PIR (motion) sensor reports occupancy
- System can trigger early seat warming or lighting
- Occupancy dot turns green on the dashboard

---

## How to Explain the Raspberry Pi's Role

During the presentation, point to the Pi and say:

> "The Raspberry Pi is our IoT edge device. It's running at the 'edge' of the network — right where the physical world meets the digital world.
>
> It has real sensors plugged in: this DHT sensor measures the temperature inside the car's cabin. This PIR sensor detects motion — it tells us when someone sits in the driver's seat.
>
> And it controls real things: this LED represents the car's ambient lighting. This relay can switch on a real heater.
>
> The Pi talks to our laptop over Wi-Fi using MQTT messages — the same protocol used in millions of real smart home and industrial IoT systems."

---

## How to Explain the Simulation

> "For things we can't physically connect to a demo — like the battery — we run a software simulation on the laptop.
>
> This simulation uses the same physics equations that describe how a real lithium-ion EV battery charges. It's not just a random number — it follows the charging curve: fast at first, then slowing down above 80% charge to protect the battery cells. This is called CC-CV charging (Constant Current / Constant Voltage) and is the actual method used by Tesla and other EV manufacturers.
>
> For cabin temperature, we use Newton's Law of Cooling — the same equation that describes how your coffee cools down. The cabin loses heat to the outside air at a rate proportional to the temperature difference."

---

## Key Numbers for Q&A

| Parameter | Value | Why |
|---|---|---|
| Time acceleration | 60× | 1 real second = 1 simulation minute; lets us demo a 60-minute plan in 1 real minute |
| Starting SoC | 50% | Realistic overnight partial charge; needs to reach 80% before departure |
| Battery capacity | 10 kWh | Small demo EV so charging completes visibly within 1 real minute |
| Charge rate | 3.7 kW | Standard 16A Type-2 home AC charger (16A × 230V = 3680W) |
| Max power budget | 5750W | 25A single-phase circuit; charger (3700W) + HVAC (2000W) = 5700W just fits |
| Taper threshold | 80% SoC | CC-CV boundary in lithium battery charging |
| ENHSP timeout | 10 seconds | After which the rule-based fallback activates |
| PDDL actions | 5 | charge-ev, run-hvac, warm-seat, set-lights-on, load-route |

---

## Common Questions and Answers

**Q: Why use PDDL? Isn't a simple if-else enough?**
A: If-else works for fixed conditions. PDDL lets the system find optimal schedules under changing constraints — different departure times, different battery levels, power budgets. The AI planner explores many possible orderings and picks the best one. It's the difference between a GPS (plans a route) and a person walking straight to where they think the exit is.

**Q: What happens if the Pi disconnects?**
A: The system degrades gracefully. The simulator continues publishing sensor data. The state manager will stop receiving real DHT readings and after 10 seconds, the simulator's cabin temp readings take over. No crash.

**Q: What happens if the internet is down (weather API fails)?**
A: The weather sensor falls back to a configurable default temperature (5°C, which is a typical Stuttgart winter morning). This is logged but the system keeps running.

**Q: Is this a real product?**
A: No, it's a research and educational prototype. But the same architecture — MQTT, edge sensors, cloud planning — is used in real smart grid and vehicle-to-grid (V2G) systems. Our approach scales to real IoT deployments.

**Q: Why is the Plugwise just a prop?**
A: The Plugwise uses a proprietary Zigbee-based protocol that requires a complex driver. Setting it up reliably for a demo was too risky. Instead, we show it visually on the dashboard and hold it as a physical prop to demonstrate understanding of the hardware. The same MQTT command that would activate the Plugwise also activates the relay on the Pi — same interface, different hardware.
