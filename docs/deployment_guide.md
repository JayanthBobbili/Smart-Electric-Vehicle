# Deployment Guide — Step by Step

**Smart EV Charging & Cabin Prep · Group 22**

This guide assumes:
- The **laptop** is a fresh **Windows 11 or macOS** machine with nothing installed
- The **Raspberry Pi** is a brand-new Pi 3 Model B+ with a freshly flashed SD card
- Both devices are on the same Wi-Fi network

Read everything before starting. Do the laptop setup first.

> ### Windows vs macOS quick reference
> The steps below show **Windows** commands by default. If you are on a **Mac**, translate
> them using this table (the rest of the guide works the same on both):
>
> | Task | Windows | macOS |
> |---|---|---|
> | Open a terminal | Command Prompt (Win key → `cmd`) | Terminal.app (⌘+Space → "Terminal") |
> | Package manager (optional) | `winget` | [Homebrew](https://brew.sh) (`brew`) |
> | Go to the Desktop | `cd C:\Users\%USERNAME%\Desktop` | `cd ~/Desktop` |
> | Project folder | `C:\Users\%USERNAME%\Desktop\smart-ev-cabin` | `~/Desktop/smart-ev-cabin` |
> | Python (before the venv) | `python` | `python3` |
> | Create the venv | `python -m venv .venv` | `python3 -m venv .venv` |
> | Activate the venv | `.venv\Scripts\activate` | `source .venv/bin/activate` |
> | Find your Wi-Fi IP | `ipconfig` | `ipconfig getifaddr en0` |
> | Edit a text file | Notepad | `nano <file>` (or open in TextEdit) |
>
> **Inside an activated venv, `python` works on both platforms** — so `python run_all.py`,
> `python -m pytest`, etc. are identical once the venv is active.

---

## Part 1: Laptop Setup

### Step 1.1 — Install Python 3.11+

**Windows:**
1. Open your browser and go to: `https://www.python.org/downloads/`
2. Click **"Download Python 3.11.x"** (or newer — 3.12/3.13 are fine)
3. Run the downloaded installer
4. **IMPORTANT**: On the first screen, check the box that says **"Add Python to PATH"**
5. Click "Install Now"
6. When done, open **Command Prompt** (press Windows key, type `cmd`, press Enter)
7. Type: `python --version`
8. You should see something like: `Python 3.11.9`
   - If you see an error, restart your computer and try again

**macOS:**
- Easiest with [Homebrew](https://brew.sh) (recommended). If you don't have Homebrew, install
  it first (one command from brew.sh), then:
  ```bash
  brew install python
  python3 --version          # expect Python 3.11 or newer
  ```
- Or download the **macOS 64-bit universal2 installer** from `https://www.python.org/downloads/`
  and run the `.pkg`.

> On macOS the command is **`python3`** (and `pip3`). Once you create and activate the project's
> virtual environment (Step 1.6), plain `python` works there too.

### Step 1.2 — Install Git

**Windows:**
1. Go to: `https://git-scm.com/download/win`
2. Download the installer and run it
3. Click "Next" through all screens (defaults are fine)
4. Open a new Command Prompt and type: `git --version`
5. You should see: `git version 2.x.x`

**macOS:**
- Git is usually already there. Open Terminal and run `git --version`. If it isn't installed,
  macOS will prompt to install the Xcode Command Line Tools — accept it. Or install via Homebrew:
  ```bash
  brew install git
  ```

### Step 1.3 — Install Docker Desktop

Docker is used to run the Mosquitto MQTT broker (the messaging server).

**Windows:**
1. Go to: `https://www.docker.com/products/docker-desktop/`
2. Click "Download Docker Desktop for Windows"
3. Run the installer. It may ask you to install WSL 2 (Windows Subsystem for Linux) — click Yes/Install
4. Restart your computer when prompted
5. Docker Desktop will start automatically (you'll see a whale icon in the system tray)
6. Wait until Docker shows **"Engine running"** (green dot in the bottom left of Docker Desktop)
7. Open Command Prompt and type: `docker --version`
8. You should see: `Docker version 24.x.x` or similar

**macOS:**
1. Go to `https://www.docker.com/products/docker-desktop/` and download **Docker Desktop for Mac**.
   Pick the build for your chip — **Apple Silicon** (M1/M2/M3) or **Intel** (check  → "About This Mac").
2. Open the downloaded `.dmg` and drag **Docker** to Applications, then launch it.
3. Wait until the whale icon in the menu bar shows Docker is running.
4. In Terminal: `docker --version` → `Docker version 24.x.x` or similar.

> No Docker? You can instead run Mosquitto natively: `brew install mosquitto` (macOS) and start it
> with `mosquitto -c mosquitto.conf` from the project folder. The rest of the guide is unchanged.

### Step 1.4 — Install Java 11+ (for ENHSP planner)

**Windows:**
1. Go to: `https://adoptium.net/` (click "Latest LTS Release")
2. Download the **Windows x64 .msi installer** for Temurin 21 LTS
3. Run the installer, click Next through all defaults
4. Open a **new** Command Prompt and type: `java -version`
5. You should see: `openjdk version "21.x.x"`

**macOS:**
- With Homebrew:
  ```bash
  brew install --cask temurin
  java -version            # expect openjdk version "21.x.x"
  ```
- Or download the **macOS .pkg** (pick aarch64 for Apple Silicon, x64 for Intel) from
  `https://adoptium.net/` and run it.

> Java is only needed for the optional ENHSP planner. If you skip it, the system automatically
> uses the built-in rule-based fallback planner.

### Step 1.5 — Clone the project

Open Command Prompt and run these commands one by one:

```
cd C:\Users\%USERNAME%\Desktop
git clone https://github.com/YOUR-ORG/smart-ev-cabin.git
cd smart-ev-cabin
```

> Replace `YOUR-ORG/smart-ev-cabin` with your actual GitHub repository URL.

### Step 1.6 — Create a Python virtual environment

Still in the `smart-ev-cabin` folder:

**Windows:**
```
python -m venv .venv
.venv\Scripts\activate
```

**macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

You should now see `(.venv)` at the start of your prompt. This means the virtual environment is
active — from here on, `python` and `pip` refer to the venv on both platforms.

### Step 1.7 — Install Python packages

```
pip install -r requirements-laptop.txt
```

This installs: paho-mqtt (MQTT client), flask (web server), flask-socketio (live updates), requests (weather API), pyyaml (config files), jinja2 (template engine).

Wait for all packages to install. You'll see a lot of text. When it shows `Successfully installed ...`, you're done.

### Step 1.8 — Download ENHSP (AI Planner)

ENHSP is the AI planning engine. The JAR file is not included in the repository because it's too large.

1. Go to: `https://sites.google.com/view/enhsp/`  
   *(or search Google for "ENHSP planner download")*
2. Download `enhsp-20.jar` (or the latest version)
3. Rename it to `enhsp.jar`
4. Place it in the `planner\` folder inside the project:
   ```
   C:\Users\...\Desktop\smart-ev-cabin\planner\enhsp.jar
   ```

> **If you cannot download ENHSP:** That's OK. The system has a built-in fallback planner. Everything will still work. You just won't be able to say "this uses ENHSP" — you'll say "this uses our rule-based fallback".

### Step 1.9 — Find your laptop's IP address

The Raspberry Pi needs to know your laptop's IP address to connect.

**Windows:**
1. Open Command Prompt
2. Type: `ipconfig`
3. Look for "Wireless LAN adapter Wi-Fi" section
4. Note the **IPv4 Address** — it looks like `192.168.x.x`

**macOS:**
1. Open Terminal and type: `ipconfig getifaddr en0` (Wi-Fi is usually `en0`; if that prints nothing,
   try `en1`). It prints your IP directly, e.g. `192.168.x.x`.
2. Or: System Settings → Network → Wi-Fi → **Details…** → IP Address.

**Write this down** — you'll need it when setting up the Pi.

### Step 1.10 — Configure the project

Open the file `config\config.yaml` with Notepad (right-click → Open with → Notepad).

The first few lines look like this:
```yaml
broker:
  host: "localhost"
  port: 1883
```

**On the laptop**, leave `host: "localhost"` as-is.

Also open `config\schedule.json`:
```json
{
  "departure_time": "2026-06-24T08:00:00",
  "sim_minutes_until_departure": 60.0,
  "target_soc": 80.0,
  "target_cabin_temp": 22.0,
  "destination": "Stuttgart HBF"
}
```

Change `sim_minutes_until_departure` to how many simulation-minutes you want for the demo. At time_scale=60 (default), `60.0` means departure in 1 real minute. For a longer demo, use `120.0` (2 real minutes).

### Step 1.11 — Start Mosquitto broker

In Command Prompt (in the smart-ev-cabin folder):

```
docker compose up -d
```

You should see:
```
[+] Running 1/1
 ✔ Container ev-mosquitto  Started
```

Verify it's running:
```
docker ps
```

You should see a row with `ev-mosquitto` in the NAME column and "Up" in the STATUS column.

> **Windows Firewall — REQUIRED for Raspberry Pi connectivity:**  
> Windows Firewall blocks incoming connections on port 1883 by default. The Raspberry Pi will not be able to reach the broker unless you open this port.  
> 1. Press Windows key, type **"Windows Defender Firewall"**, press Enter  
> 2. Click **"Advanced Settings"** on the left  
> 3. Click **"Inbound Rules"** → **"New Rule…"** on the right  
> 4. Select **"Port"** → Next → **TCP** → Specific local port: **1883** → Next  
> 5. Select **"Allow the connection"** → Next → Check all three (Domain, Private, Public) → Next  
> 6. Name it **"MQTT Broker 1883"** → Finish  
>
> You only need to do this once. Without this step the Pi will fail to connect.

> **macOS firewall:**
> The macOS Application Firewall is **off by default**, so usually nothing is needed. If you have
> turned it on (System Settings → Network → Firewall), the first time Docker/Mosquitto opens the
> port macOS will pop up *"Do you want the application to accept incoming network connections?"* —
> click **Allow**. (macOS firewalls by application, not by port number, so there is no per-port rule
> to add.) Confirm the Pi can reach the broker; if not, temporarily turn the firewall off to test.

---

## Part 2: Raspberry Pi Setup

### Step 2.1 — Flash the SD card

You need to put Raspberry Pi OS on the SD card.

1. On your **laptop**, download **Raspberry Pi Imager** from: `https://www.raspberrypi.com/software/`
2. Insert the microSD card into your laptop (using a card reader)
3. Open Raspberry Pi Imager
4. Click **"CHOOSE DEVICE"** → Select "Raspberry Pi 3"
5. Click **"CHOOSE OS"** → Select **"Raspberry Pi OS (64-bit)"**
6. Click **"CHOOSE STORAGE"** → Select your SD card
7. Click **"NEXT"**
8. When asked "Would you like to apply OS customisation settings?", click **"EDIT SETTINGS"**
9. In the settings window:
   - Check "Set hostname" → type `ev-cabin-pi`
   - Check "Set username and password" → username: `pi`, password: choose something you'll remember
   - Check "Configure wireless LAN" → enter your Wi-Fi network name and password
   - Check "Enable SSH" → Select "Use password authentication"
10. Click "SAVE", then "YES", then "YES" again
11. Wait for the write to complete (5–10 minutes)
12. Remove the SD card and insert it into the Raspberry Pi

### Step 2.2 — First boot and SSH connection

1. Connect the Pi to power using the Goobay adapter
2. Wait about 60 seconds for it to boot
3. On your **laptop**, open Command Prompt and type:
   ```
   ssh pi@ev-cabin-pi.local
   ```
4. Type "yes" when asked about authenticity
5. Enter the password you set in Step 2.1
6. You should now see a prompt like: `pi@ev-cabin-pi:~ $`

> If `ev-cabin-pi.local` doesn't work, you need to find the Pi's IP address. Log into your Wi-Fi router (usually at `192.168.1.1`) and look for a device named `ev-cabin-pi`.

### Step 2.3 — Update the Pi

In the SSH terminal:

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

This takes 5–10 minutes. Just wait.

### Step 2.4 — Install Python and pip

```bash
sudo apt-get install -y python3 python3-pip python3-venv git
python3 --version
```

You should see Python 3.9 or higher. If you flashed **Raspberry Pi OS (64-bit, Bookworm)** as recommended in Step 2.1, you will see **Python 3.11** which is ideal.

> **Note on Python versions:** Python 3.11 (Bookworm) is preferred. Python 3.9 (Bullseye) also works — the code is written to be compatible with Python 3.9+.

### Step 2.5 — Install the I2C system libraries and GrovePi

The GrovePi library lets Python talk to the Grove sensors connected to the GrovePi+ hat.
It communicates with the hat's ATmega chip over **I2C**, so install the I2C system
packages **first**:

```bash
sudo apt update
sudo apt install -y python3-smbus i2c-tools
```

> **Why this matters:** the `grovepi` library does `import smbus`. Without
> `python3-smbus`, that import fails at runtime and the IoT node silently falls back to
> demo mode (fake 21.5 °C, no GPIO) — so the Pi *looks* like it's running but posts fake
> data. `i2c-tools` provides the `i2cdetect` command used to verify the hat in Step E.

Now install the GrovePi library. Pin the known-good version for reproducibility:

```bash
sudo pip3 install grovepi==1.0.4
```

> **If you see an error about "externally-managed-environment" (Bookworm only):** add
> `--break-system-packages`:
> ```bash
> sudo pip3 install grovepi==1.0.4 --break-system-packages
> ```
>
> **Notes — GrovePi is old (last released 2018) and unmaintained:**
> - If `pip3 install grovepi` fails on Bookworm, install it from the Dexter Industries
>   source instead (clone the GrovePi repo and run its Python 3 setup).
> - If `import smbus` still fails after installing `python3-smbus`, install the modern
>   replacement (`pip3 install smbus2`) and patch grovepi's `import smbus` to
>   `import smbus2 as smbus`.
> - Do **not** substitute the `grove.py` library — it targets Seeed's Grove Base Hat, a
>   different board, and will **not** talk to the GrovePi+ ATmega.

Also enable I2C (the communication protocol GrovePi uses):

```bash
sudo raspi-config
```

A blue menu will appear:
1. Select **"Interface Options"**
2. Select **"I2C"**
3. Select **"Yes"** to enable
4. Select **"OK"**, then **"Finish"**
5. The Pi will ask to reboot — select **"Yes"**

Wait 30 seconds, then SSH back in:
```bash
ssh pi@ev-cabin-pi.local
```

**Check I2C permissions** — the `pi` user must be in the `i2c` group so the IoT node can
reach the hat **without `sudo`** (the GrovePi uses I2C, not direct GPIO, so the `gpio`
group is not required):

```bash
groups | grep -o i2c     # should print: i2c
```

If it prints nothing, add the user to the group and reboot:
```bash
sudo usermod -aG i2c pi
sudo reboot
```

### Step 2.6 — Copy the project to the Pi

**Option A (if you have the project on GitHub):**
```bash
cd ~
git clone https://github.com/YOUR-ORG/smart-ev-cabin.git
cd smart-ev-cabin
```

**Option B (copy from laptop using SCP):**

On **Windows** (Command Prompt):
```
scp -r C:\Users\%USERNAME%\Desktop\smart-ev-cabin pi@ev-cabin-pi.local:~/
```

On **macOS** (Terminal):
```bash
scp -r ~/Desktop/smart-ev-cabin pi@ev-cabin-pi.local:~/
```
Enter the Pi's password when prompted.

> `ssh` and `scp` are built into both Windows 11 and macOS, and Raspberry Pi Imager (Step 2.1) has
> a native macOS download — so the entire Pi setup is identical from either laptop.

### Step 2.7 — Install Python packages on the Pi

In the Pi SSH terminal:
```bash
cd ~/smart-ev-cabin
pip3 install -r requirements-pi.txt
```

> **If you see an error about "externally-managed-environment" (Bookworm only):** Use this instead:
> ```bash
> pip3 install -r requirements-pi.txt --break-system-packages
> ```

> **Note — `paho-mqtt` is intentionally pinned to `<2.0`.** The code uses the paho-mqtt
> 1.x callback API (e.g. `on_connect(client, userdata, flags, rc)`); paho-mqtt 2.x is a
> breaking change, so do **not** "upgrade" it. `PyYAML` is pinned to the minimum `>=6.0`
> and will install the current release (6.0.3+).

### Step 2.8 — Configure the broker IP on the Pi

The Pi needs to connect to the MQTT broker running on your laptop.

```bash
nano config/config.yaml
```

Find this line:
```yaml
broker:
  host: "localhost"
```

Change `"localhost"` to your laptop's IP address (the one you noted in Step 1.9):
```yaml
broker:
  host: "192.168.x.x"   ← replace with your actual laptop IP
```

To save: press `Ctrl+X`, then `Y`, then `Enter`.

### Step 2.9 — Wire up the GrovePi sensors

#### How the GrovePi+ works (read this first)

The GrovePi+ is an expansion board (a "hat") that sits on top of the Raspberry Pi. It contains a small **ATmega328P microcontroller** (the same chip used in Arduino Uno boards). This ATmega handles all the low-level sensor communication so that:
- The Pi does **not** need direct GPIO connections to sensors
- All sensors connect to the GrovePi+ board via standard Grove cables
- The Pi communicates with the GrovePi+ ATmega over **I2C** (which is why you enabled I2C in Step 2.5)

Think of it as: Pi ↔ I2C bus ↔ GrovePi+ ATmega ↔ Grove sensors

#### Step A: Mount the GrovePi+ hat onto the Raspberry Pi

1. Power off the Raspberry Pi (unplug the power cable)
2. Lay the Pi flat on a table with the GPIO header (the row of metal pins) facing up
3. Hold the GrovePi+ hat with its **component side facing UP** (you should see the labelled Grove ports D2-D8 along the edges)
4. Look at the **underside of the GrovePi+** — you will see a **40-pin female socket** (black plastic block with holes)
5. Align this socket over the Pi's 40-pin GPIO header (the metal pins)
6. The GrovePi+ should overhang toward the USB/Ethernet ports of the Pi (the hat is sized to fit the Pi exactly)
7. Press the GrovePi+ **straight down** with even pressure across the entire board until the socket is fully seated — all 40 pins should be engaged. Do **not** push at an angle.
8. The GrovePi+ should sit flat and level. If it is tilted, a pin is bent or not aligned — remove it carefully, straighten the pins, and try again.

```
Cross-section view (side view):
┌─────────────────────────────────────────┐  ← GrovePi+ board (sensors face UP)
│ D2  D3  D4  D5  D6  D7  D8  A0  A1  A2 │
│           [ATmega328P chip]              │
└───────────────┬─────────────────────────┘
                │ 40-pin socket (pressed onto Pi header)
                ▼
┌─────────────────────────────────────────┐  ← Raspberry Pi 3B+
│ ████████████████████████████████████    │
│  [USB]  [USB]  [Ethernet]  [microUSB]   │
└─────────────────────────────────────────┘
```

#### Step B: Raspberry Pi 40-pin GPIO header reference

The Pi's GPIO header is the 40-pin connector that the GrovePi+ plugs onto. The pin layout (looking down at the Pi from above, with the GPIO header at the top):

```
                3.3V  [1]  [2]  5V
    I2C SDA → GPIO2  [3]  [4]  5V
    I2C SCL → GPIO3  [5]  [6]  GND
               GPIO4  [7]  [8]  GPIO14
                 GND  [9] [10]  GPIO15
              GPIO17 [11] [12]  GPIO18
              GPIO27 [13] [14]  GND
              GPIO22 [15] [16]  GPIO23
               3.3V [17] [18]  GPIO24
              GPIO10 [19] [20]  GND
               GPIO9 [21] [22]  GPIO25
              GPIO11 [23] [24]  GPIO8
                 GND [25] [26]  GPIO7
               GPIO0 [27] [28]  GPIO1
               GPIO5 [29] [30]  GND
               GPIO6 [31] [32]  GPIO12
              GPIO13 [33] [34]  GND
              GPIO19 [35] [36]  GPIO16
              GPIO26 [37] [38]  GPIO20
                 GND [39] [40]  GPIO21
```

> Pin 1 is the corner closest to the SD card slot.  
> **GrovePi+ uses I2C on pins 3 (SDA) and 5 (SCL).** All 40 pins are taken by the GrovePi+ hat — you do not need to think about individual GPIO numbers. The ATmega handles everything.

#### Step C: Connect Grove sensors to GrovePi+ ports

The GrovePi+ board has labelled ports along its edges. Find ports **D2, D6, D7, D8** (the "D" means digital port). Each port is a white 4-pin Grove connector.

**Wiring table:**

| Sensor / Actuator | GrovePi+ Port Label | config.yaml key | Notes |
|---|---|---|---|
| DHT Temp & Humidity sensor | **D7** | `dht_port: 7` | See "Which DHT?" below |
| PIR Motion Sensor | **D8** | `pir_port: 8` | Face the sensor dome toward the driver's seat area |
| Grove LED module | **D2** | `led_port: 2` | Represents cabin ambient light |
| Grove Relay module | **D6** | `relay_port: 6` | Represents cabin heater switch |

**To connect each sensor:**
1. Take a Grove cable (4-wire, white connector at each end)
2. Plug one end into the **sensor module** connector (it is keyed — only fits one way, no force needed)
3. Plug the other end into the **matching port on the GrovePi+** board (again, keyed — only fits one way)
4. A good connection will seat flush with a slight click

> **Grove connectors are polarised — they cannot be inserted backwards.** The connector has a small notch/key that ensures correct orientation. Never force a connector.

#### Step D: Identify your DHT sensor type

The DHT sensor measures temperature and humidity. There are two versions:

| Sensor | Housing colour | `dht_type` setting | Accuracy |
|---|---|---|---|
| **DHT11** | Blue | `0` ← **default in config** | ±2°C, ±5% RH |
| **DHT22** | White | `1` | ±0.5°C, ±2% RH |

The GrovePi starter kit includes a **DHT11 (blue)**. The config already has `dht_type: 0` which matches this.

**If your sensor is white (DHT22):** edit `config/config.yaml` on the Pi:
```bash
nano config/config.yaml
```
Find the line `dht_type: 0` and change it to `dht_type: 1`. Save with Ctrl+X, Y, Enter.

#### Step E: Verify the GrovePi+ is detected

Power the Pi back on, wait 30 seconds, SSH in, then run:

```bash
sudo i2cdetect -y 1
```

You should see **04** appear in the grid output — this is the GrovePi+ ATmega's I2C address:

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:                04
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
...
```

If you do not see `04`, the GrovePi+ hat is not fully seated. Power off, press it down firmly, and try again.

#### Completed wiring diagram

```
Raspberry Pi 3B+
┌─────────────────────────────┐
│  [40-pin GPIO header]       │◄── GrovePi+ hat plugged on here
└─────────────────────────────┘

GrovePi+ hat (top view, ports along edges):
┌─────────────────────────────────────────────┐
│                                              │
│  [D2]──────────────────── Grove LED         │
│  [D3]  [D4]  [D5]                           │
│  [D6]──────────────────── Grove Relay       │
│  [D7]──────────────────── DHT11/DHT22       │
│  [D8]──────────────────── PIR sensor        │
│                                              │
│         [ATmega328P]  [I2C connector]        │
│                                              │
│  [A0]  [A1]  [A2]  ← analog (unused here)  │
└─────────────────────────────────────────────┘
```

#### What each component represents in the demo

| Hardware | Represents | Expected behaviour during demo |
|---|---|---|
| DHT sensor | Cabin air temperature sensor | Publishes real temperature to dashboard |
| PIR sensor | Seat occupancy sensor | Goes HIGH when you wave your hand in front of it |
| Grove LED | Cabin ambient light | Lights up when plan reaches "set-lights-on" action (~1 min into demo) |
| Grove Relay | Cabin heater switch | Clicks ON when plan reaches "run-hvac" action |

---

## Part 3: Running the Full System

You have two ways to start the six laptop modules. **Option A (recommended)** uses a
single launcher script. **Option B** starts each module in its own terminal (handy when
you want to watch or restart one module in isolation). Either way, the Raspberry Pi IoT
node is started separately on the Pi (see the SSH step at the end of this part).

---

### Option A — One command (recommended)

The launcher `run_all.py` starts all six laptop modules, streams their combined output
into one window (each line tagged with the module name), checks that the MQTT broker is
reachable before starting, and stops everything cleanly when you press **Ctrl+C**.

1. Open **one** terminal and activate the virtual environment:
   ```
   # Windows:
   cd C:\Users\%USERNAME%\Desktop\smart-ev-cabin
   .venv\Scripts\activate
   # macOS:
   cd ~/Desktop/smart-ev-cabin
   source .venv/bin/activate
   ```
2. Start the broker (if it isn't already running) and the modules:
   ```
   python run_all.py --start-broker
   ```
   `--start-broker` runs `docker compose up -d` for you first. If the broker is already
   up, omit it and just run `python run_all.py`.
3. You should see output like:
   ```
   [run_all] Broker reachable at localhost:1883. Launching 6 modules.
   [run_all] started simulator (pid 12345)
   ...
   [run_all] All modules running. Dashboard -> http://localhost:5000

   simulator     | ... INFO: Simulator started: 1 real second = 60 sim seconds
   state_manager | ... INFO: State manager running — listening for sensor data
   problem_gen   | ... INFO: Problem published (SoC=50.0%, cabin=10.0°C, t_rem=60.0 min)
   planner       | ... INFO: Plan published: 5 actions (source=fallback)
   executor      | ... INFO: Executor: new plan received (5 actions)
   dashboard     | ... INFO: Dashboard starting on http://0.0.0.0:5000
   ```
4. **Open a web browser and go to: `http://localhost:5000`**

If the launcher prints `ERROR: MQTT broker not reachable`, start the broker with
`docker compose up -d` (or re-run with `--start-broker`). If any module crashes, the
launcher prints which one and its error and then stops the rest — failures are never
silent. To stop everything, press **Ctrl+C** in the launcher window.

Then start the IoT node on the Pi (jump to the **SSH Terminal (on Pi)** step below).

---

### Option B — Manual (one terminal per module)

Open **7 terminal windows** on your laptop. You can use Windows Terminal, which lets you have multiple tabs. 

**First**, activate the virtual environment in EACH terminal before running any module:
```
# Windows:
cd C:\Users\%USERNAME%\Desktop\smart-ev-cabin
.venv\Scripts\activate
# macOS:
cd ~/Desktop/smart-ev-cabin
source .venv/bin/activate
```

### Terminal 1 — Start the MQTT broker (if not already running)

```
docker compose up
```

Leave this running. You'll see log messages. Don't close it.

### Terminal 2 — Simulator

```
python -m modules.simulator.main
```

You should see messages like:
```
[simulator] INFO: Simulator started: 1 real second = 60 sim seconds
[simulator] INFO: Weather: outside temp = 12.5°C
```

### Terminal 3 — State Manager

```
python -m modules.state_manager.main
```

You should see:
```
[state_manager] INFO: State manager running — listening for sensor data
```

### Terminal 4 — Problem Generator

```
python -m modules.problem_generator.main
```

You should see:
```
[problem_gen] INFO: Problem generator running
[problem_gen] INFO: Problem published (SoC=50.0%, cabin=10.0°C, t_rem=60.0 min)
```

### Terminal 5 — Planner

```
python -m modules.planner.main
```

You should see either:
```
[planner] INFO: Planner running (jar=planner/enhsp.jar, timeout=10s)
[planner] INFO: Plan published: 5 actions (source=enhsp)
```
Or if ENHSP is not installed:
```
[planner] WARNING: ENHSP jar not found — rule-based fallback will be used
[planner] INFO: Plan published: 5 actions (source=fallback)
```

Both are fine.

### Terminal 6 — Executor

```
python -m modules.executor.main
```

You should see:
```
[executor] INFO: Executor running
[executor] INFO: Executor: new plan received (5 actions)
```

### Terminal 7 — Dashboard

```
python -m modules.dashboard.app
```

You should see:
```
[dashboard] INFO: Dashboard MQTT bridge connected to localhost:1883
[dashboard] INFO: Dashboard starting on http://0.0.0.0:5000
```

**Open a web browser and go to: `http://localhost:5000`**

You should see the live dashboard with the battery gauge, EV cockpit, and plan timeline.

### SSH Terminal (on Pi) — IoT Node

```bash
cd ~/smart-ev-cabin
python3 -m modules.iot_node.main
```

You should see:
```
[iot_node] INFO: IoT node started — sensors polling, actuators waiting for commands
```

On the laptop's dashboard, the real temperature reading from the Grove DHT sensor should appear (labelled `source: grove_dht`).

---

## Part 3.5: Sensor Override Console (DHT/occupancy fail-safe)

The Grove **DHT11 is the least reliable part of the demo** (slow, low precision, and it
occasionally returns errors). If it misbehaves during a presentation, run the **override
console** to manually feed the cabin temperature, humidity, and occupancy that get sent to
the laptop — overriding whatever the real sensor reports.

It is safe to run alongside the IoT node: while an override is active, the real
`dht_sensor`/`pir_sensor` automatically **step aside** so there is never a conflict, and they
**auto-resume within ~5 seconds** if the console stops or crashes. It also works even if the
IoT node is not running — then the console is your manual sensor source.

### Run it

Run it in a spare terminal — on the **Pi over SSH** (recommended) or on the **laptop**; it
only needs to reach the broker:

```bash
# On the Pi:
cd ~/smart-ev-cabin
python3 -m modules.iot_node.override_console

# On the laptop (inside the venv):
python -m modules.iot_node.override_console
```

> The default view is a small terminal UI (curses). On **macOS** (and the Pi/Linux) curses is
> built in — nothing extra to install. On **Windows** it needs `pip install windows-curses`.
> Either way you can add `--simple` for a plain command-line version that works everywhere with no
> extra packages:
> ```
> python -m modules.iot_node.override_console --simple
> ```

### Using it (TUI)

The screen shows the **live** values arriving on the broker (so you can see whether the DHT is
still updating — it flags `STALE` if nothing arrives for >5s) and the current **override**
state. Keys:

| Key | Action |
|---|---|
| `e` | Toggle the DHT (temperature + humidity) override on/off |
| `+` / `-` (or ↑ / ↓) | Nudge temperature ±0.5 °C |
| `]` / `[` | Nudge humidity ±1 % |
| `t` | Type an exact temperature, then Enter |
| `c` | Toggle the occupancy override on/off |
| `space` | Flip occupied YES / NO |
| `r` | Reset — clear all overrides (back to the live sensors) |
| `q` | Quit (clears overrides on the way out) |

In `--simple` mode the equivalent commands are `t 22.5`, `h 55`, `e on|off`, `o on|off`,
`c yes|no`, `status`, `r`, and `q` (type `help` for the list).

When an override is on, the value the laptop receives is **your** value (it is published as
`source: grove_dht` so the simulator cannot overwrite it). Turn the override off (or press
`r`/`q`) to hand control back to the real sensor.

---

## Part 4: Verify Everything Is Working

### Quick sanity check with mosquitto_sub

Open another terminal on the laptop:
```
docker exec ev-mosquitto mosquitto_sub -t "#" -v
```

You should see a continuous stream of messages like:
```
sensors/battery_soc {"value": 50.12, "unit": "%", "ts": 1234567890, "source": "simulator"}
sensors/cabin_temp {"value": 10.02, "unit": "C", "ts": 1234567890, "source": "simulator"}
sensors/outside_temp {"value": 12.5, "unit": "C", "ts": 1234567890, "source": "open_meteo"}
state/current {"battery_soc": 50.12, "cabin_temp": 10.02, ...}
planning/plan {"actions": [...], "ts": ..., "source": "fallback"}
```

Press `Ctrl+C` to stop.

### Check the dashboard
- Battery SoC arc gauge should show a number and animate upward once charging starts
- Cabin temperature bar should show ~10°C
- Plan timeline (Gantt chart) should show horizontal bars for the scheduled actions
- Event log (right side) should have scrolling messages

### Test a trigger button
Click **"Charger Fault"** in the dashboard. You should see:
- The charging cable glow in the EV cockpit disappear
- A new plan appear in the Gantt chart within a few seconds
- The event log show `events/charger_fault`

---

## Part 5: Troubleshooting

### Problem: "Cannot connect to broker" errors
**Cause:** Mosquitto isn't running, the laptop firewall is blocking port 1883, or the IP address is wrong on the Pi.
**Fix:**
- Run `docker ps` on the laptop — check ev-mosquitto shows "Up"
- Firewall: **Windows** — open port 1883 (see the firewall note in Step 1.11). **macOS** — if the
  Application Firewall is on, allow incoming connections for Docker/Mosquitto when prompted, or turn
  it off to test
- Double-check the IP in the Pi's `config/config.yaml` matches your laptop's current Wi-Fi IP —
  `ipconfig` (Windows) or `ipconfig getifaddr en0` (macOS)

### Problem: GrovePi sensors not reading
**Cause:** I2C not enabled, `python3-smbus` missing, GrovePi hat not fully seated, the `pi` user not in the `i2c` group, or the `grovepi` library not installed.
**Fix:**
- Confirm I2C is enabled: `sudo raspi-config` → Interface Options → I2C → Yes → reboot
- Run `sudo i2cdetect -y 1` — you should see **`04`** in the grid. If not, power off the Pi and press the GrovePi+ hat down more firmly until all 40 pins engage
- Verify the I2C libs and imports: `python3 -c "import smbus, grovepi; print('OK')"`. If it fails on `smbus`, run `sudo apt install -y python3-smbus i2c-tools`
- Check group membership: `groups | grep i2c` — if empty, `sudo usermod -aG i2c pi && sudo reboot`
- Re-install if needed: `sudo pip3 install grovepi==1.0.4` (add `--break-system-packages` on Bookworm)

> **Note:** if `grovepi` cannot import, the IoT node does not crash — it runs in demo
> mode and publishes constant placeholder values. So "sensors show fake/constant data"
> is the symptom of a broken grovepi/smbus install, not a network problem.

### Problem: "Module not found" errors
**Cause:** Virtual environment not activated, or wrong directory.
**Fix:**
- Make sure you activated the venv in that terminal — `.venv\Scripts\activate` (Windows) or
  `source .venv/bin/activate` (macOS)
- Make sure you're in the `smart-ev-cabin` folder and can see the `modules` folder: `dir` (Windows)
  or `ls` (macOS)

### Problem: Dashboard shows nothing
**Cause:** Simulator or state_manager isn't running.
**Fix:**
- Make sure Terminal 2 (simulator) and Terminal 3 (state_manager) are running and show no errors
- Refresh the browser page (`F5`)
- Check that `http://localhost:5000` is the correct URL

### Problem: Plan never appears / Gantt chart is empty
**Cause:** Problem generator or planner isn't running, or ENHSP isn't found.
**Fix:**
- Check Terminal 4 (problem_generator) for error messages
- Check Terminal 5 (planner) — "rule-based fallback" is OK, errors are not
- The planner only runs when a new problem is published. Wait 5–10 seconds after all modules start.

### Problem: "Port 5000 already in use"
**Fix:** Another program is using port 5000. Either close it, or change the port in `modules/dashboard/app.py` (last line, change `port=5000` to `port=5001`), then open `http://localhost:5001`.

### Problem: Python won't import modules correctly
**Fix:** Make sure you run modules with `python -m` (the `-m` flag) not `python modules/simulator/main.py`:
```
# CORRECT:
python -m modules.simulator.main

# WRONG (will fail with import errors):
python modules/simulator/main.py
```

---

## Part 6: Demo Preparation Checklist

Before the presentation, do this checklist:

- [ ] Mosquitto is running (`docker ps` shows ev-mosquitto Up)
- [ ] `config/schedule.json` has `"sim_minutes_until_departure": 60.0`
- [ ] All 6 laptop modules are running and showing no errors
- [ ] Pi is running IoT node and connected
- [ ] Dashboard is open at `http://localhost:5000`
- [ ] Battery gauge shows ~50%
- [ ] Gantt chart shows a plan
- [ ] "Charger Fault" button was tested and caused a replan
- [ ] Grove DHT sensor shows a real temperature reading (different from simulated)
- [ ] Grove LED physically turns on when the plan reaches "lights on" time
- [ ] **Fail-safe ready:** the override console (Part 3.5) was tested — `e` overrides cabin temp, `c`/`space` overrides occupancy — in case the DHT11 acts up live

### Resetting for a new demo run

To reset back to the starting state (battery 50%, cabin 10°C):

**If you used the launcher (Option A):**
1. Press `Ctrl+C` in the `run_all.py` window to stop all modules
2. Edit `config/schedule.json`: set `"sim_minutes_until_departure": 60.0`
3. Re-run `python run_all.py` (the broker can stay running)

**If you used manual terminals (Option B):** you only need to restart the simulator:
1. Press `Ctrl+C` in Terminal 2 (simulator) to stop it
2. Edit `config/schedule.json`: set `"sim_minutes_until_departure": 60.0`
3. Restart Terminal 2: `python -m modules.simulator.main`
4. The state manager and problem generator will automatically detect the fresh state and replan

---

## Part 7: Understanding the File Structure

```
smart-ev-cabin/
├── run_all.py               ← One-command launcher for all 6 laptop modules (Option A)
├── config/
│   ├── config.yaml          ← Main settings (ports, thresholds, sensor config)
│   └── schedule.json        ← Departure time, targets (edit before each demo)
├── pddl/
│   ├── domain.pddl          ← AI planner: what actions exist (DO NOT EDIT)
│   └── problem_template.pddl ← AI planner: template filled with current state
├── planner/
│   └── enhsp.jar            ← Download separately (see Step 1.8)
├── modules/
│   ├── common/              ← Shared code (MQTT client, config loader)
│   ├── iot_node/            ← Runs on Raspberry Pi
│   ├── simulator/           ← Runs on laptop (simulated EV physics)
│   ├── state_manager/       ← Runs on laptop (tracks world state)
│   ├── problem_generator/   ← Runs on laptop (writes PDDL problems)
│   ├── planner/             ← Runs on laptop (calls ENHSP or fallback)
│   ├── executor/            ← Runs on laptop (sends commands at right time)
│   └── dashboard/           ← Runs on laptop (web UI at localhost:5000)
├── tests/                   ← Unit tests (run with: python -m pytest tests/)
├── docs/                    ← This guide and the presentation guide
├── requirements-laptop.txt  ← Install with pip on laptop
├── requirements-pi.txt      ← Install with pip3 on Pi
└── docker-compose.yml       ← Start with: docker compose up -d
```

---

## Dependency Summary

### Laptop dependencies

Install column shows **Windows** / **macOS** options.

| What | How to install (Windows / macOS) | Version needed |
|---|---|---|
| Python | python.org installer / `brew install python` | 3.11 or newer |
| Git | git-scm.com installer / `brew install git` (or Xcode CLT) | Any recent version |
| Docker Desktop | docker.com installer (either OS) / or `brew install mosquitto` for a native broker | Any recent version |
| Java (JDK) | adoptium.net installer / `brew install --cask temurin` | 11 or newer |
| paho-mqtt | `pip install -r requirements-laptop.txt` | ≥1.6, <2.0 |
| Flask | same | ≥3.0 |
| flask-socketio | same | ≥5.3 |
| simple-websocket | same | ≥0.10 |
| requests | same | ≥2.31 |
| pyyaml | same | ≥6.0 |
| jinja2 | same | ≥3.1 |
| ENHSP jar | Download from enhsp website | 20 or newer |

### Raspberry Pi dependencies

| What | How to install | Version needed |
|---|---|---|
| Raspberry Pi OS | Flashed via Raspberry Pi Imager | Bullseye or Bookworm (64-bit) |
| Python 3 | Pre-installed on Pi OS | 3.9 or newer |
| pip3 | Pre-installed on Pi OS | Any |
| git | `sudo apt-get install git` | Any |
| I2C system libs | `sudo apt install python3-smbus i2c-tools` | from apt |
| GrovePi library | `sudo pip3 install grovepi==1.0.4` | 1.0.4 (last release, 2018) |
| paho-mqtt | `pip3 install -r requirements-pi.txt` | ≥1.6, **<2.0** (pin is deliberate) |
| pyyaml | same | ≥6.0 (installs 6.0.3+) |

### Hardware

| Item | Used for |
|---|---|
| Raspberry Pi 3 Model B+ | Main IoT node |
| GrovePi+ hat | Connects Grove sensors to Pi GPIO |
| Grove DHT11 or DHT22 sensor | Cabin temperature + humidity |
| Grove PIR sensor | Seat occupancy detection |
| Grove LED module | Ambient lighting actuator |
| Grove Relay | Cabin heater proxy actuator |
| Plugwise Circle × 2 + USB stick | Visual prop (not software-controlled) |
| MicroSD card (≥16GB) | Pi OS storage |
| Goobay power adapter | Pi power supply |
| Grove cables | Connect sensors to GrovePi+ |
