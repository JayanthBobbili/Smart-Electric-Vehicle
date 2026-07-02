"""One-command launcher for the laptop-side Smart EV Cabin modules.

Starts all six laptop modules as subprocesses, tags and streams their combined
output into this one console, performs an MQTT broker reachability pre-check, and
shuts everything down cleanly on Ctrl+C or if any module exits unexpectedly.

The Raspberry Pi `iot_node` is NOT started here — it runs on the Pi over SSH.

Usage:
    python run_all.py                 # broker must already be running
    python run_all.py --start-broker  # also runs `docker compose up -d` first

Press Ctrl+C in this window to stop every module.
"""

from __future__ import annotations

import argparse
import os
import signal
import socket
import subprocess
import sys
import threading
import time

from modules.common.config_loader import load_config

_ROOT = os.path.dirname(os.path.abspath(__file__))

# (tag, module import path) in logical start order. MQTT is decoupled so the order
# is not strict, but starting producers before consumers minimises missed first
# messages and keeps the combined log readable.
_MODULES = [
    ("simulator",     "modules.simulator.main"),
    ("state_manager", "modules.state_manager.main"),
    ("problem_gen",   "modules.problem_generator.main"),
    ("planner",       "modules.planner.main"),
    ("executor",      "modules.executor.main"),
    ("dashboard",     "modules.dashboard.app"),
]

_TAG_WIDTH = max(len(tag) for tag, _ in _MODULES)
_STAGGER_S = 0.6   # small delay between starts so logs stay readable
_GRACE_S = 8.0     # how long to wait for graceful child shutdown before forcing


def _check_broker(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _start_broker() -> None:
    print("[run_all] Starting MQTT broker via `docker compose up -d` ...")
    try:
        subprocess.run(["docker", "compose", "up", "-d"], cwd=_ROOT, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"[run_all] Could not start broker with docker compose: {exc}")


def _pump_output(tag: str, proc: subprocess.Popen) -> None:
    """Read a child's combined stdout/stderr line-by-line and print it tagged."""
    prefix = f"{tag.ljust(_TAG_WIDTH)} | "
    if proc.stdout is None:
        return
    for line in proc.stdout:
        sys.stdout.write(prefix + line)
        sys.stdout.flush()


def _shutdown(procs: list[tuple[str, subprocess.Popen]], *, send_signal: bool) -> None:
    """Stop all child processes.

    On Ctrl+C the console already delivered the interrupt to the children (they
    share this console/process group), so `send_signal=False` simply waits for
    them to exit and forces any straggler. On an unexpected child exit nothing
    signalled the siblings, so `send_signal=True` actively stops them first.
    """
    if send_signal:
        for tag, p in procs:
            if p.poll() is None:
                try:
                    if os.name == "posix":
                        p.send_signal(signal.SIGINT)
                    else:
                        p.terminate()
                except OSError:
                    pass

    deadline = time.time() + _GRACE_S
    for _tag, p in procs:
        remaining = deadline - time.time()
        if remaining > 0 and p.poll() is None:
            try:
                p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                pass

    for tag, p in procs:
        if p.poll() is None:
            print(f"[run_all] Forcing '{tag}' to stop...")
            p.terminate()
    for _tag, p in procs:
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch all laptop-side EV cabin modules.")
    parser.add_argument(
        "--start-broker", action="store_true",
        help="Run `docker compose up -d` to start Mosquitto before launching modules.",
    )
    args = parser.parse_args()

    cfg = load_config()
    host = cfg["broker"]["host"]
    port = int(cfg["broker"]["port"])

    if args.start_broker:
        _start_broker()
        for _ in range(15):  # wait up to ~15s for the broker to accept connections
            if _check_broker(host, port):
                break
            time.sleep(1.0)

    if not _check_broker(host, port):
        print(f"[run_all] ERROR: MQTT broker not reachable at {host}:{port}.")
        print("[run_all] Start it first:   docker compose up -d")
        print("[run_all] ...or re-run with: python run_all.py --start-broker")
        return 1

    print(f"[run_all] Broker reachable at {host}:{port}. Launching {len(_MODULES)} modules.")
    print("[run_all] Press Ctrl+C to stop everything.\n")

    procs: list[tuple[str, subprocess.Popen]] = []
    stop_reason: str | None = None

    try:
        for tag, spec in _MODULES:
            p = subprocess.Popen(
                [sys.executable, "-u", "-m", spec],
                cwd=_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            procs.append((tag, p))
            threading.Thread(target=_pump_output, args=(tag, p), daemon=True).start()
            print(f"[run_all] started {tag} (pid {p.pid})")
            time.sleep(_STAGGER_S)

        print("\n[run_all] All modules running. Dashboard -> http://localhost:5000\n")

        # Supervise: if a module exits on its own, report it and tear the rest down.
        while stop_reason is None:
            for tag, p in procs:
                rc = p.poll()
                if rc is not None:
                    stop_reason = f"module '{tag}' exited unexpectedly (code {rc})"
                    break
            time.sleep(0.5)

    except KeyboardInterrupt:
        stop_reason = "Ctrl+C received"

    graceful = stop_reason == "Ctrl+C received"
    print(f"\n[run_all] {stop_reason} — stopping all modules...")
    _shutdown(procs, send_signal=not graceful)
    print("[run_all] All modules stopped.")
    return 0 if graceful else 1


if __name__ == "__main__":
    raise SystemExit(main())
