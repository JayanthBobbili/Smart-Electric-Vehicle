"""Rule-based fallback planner used when ENHSP is unavailable or times out."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def make_plan(world: dict) -> list[dict]:
    """Generate a rule-based plan aligned with the simplified PDDL domain actions:
    charge-ev, run-hvac, warm-seat, set-lights-on, load-route.
    """
    soc = world.get("battery_soc", 0.0)
    target_soc = world.get("target_soc", 80.0)
    cabin_temp = world.get("cabin_temp", 20.0)
    target_cabin_temp = world.get("target_cabin_temp", 22.0)
    time_remaining = max(2.0, world.get("minutes_remaining", 60.0))
    charger_available = world.get("charger_available", True)
    route_loaded = world.get("route_loaded", False)

    max_power = world.get("max_power", 5750.0)
    charger_power = world.get("charger_power_w", 3700.0)
    hvac_power = world.get("hvac_power_w", 2000.0)
    seat_warmer_power = world.get("seat_warmer_power_w", 150.0)
    charge_rate = world.get("charge_rate_pct_per_min", 0.617)
    heater_delta = world.get("heater_delta_per_min", 0.8)

    plan: list[dict] = []

    # --- Charging ---
    charge_duration = 0.0
    if soc < target_soc and charger_available and charger_power <= max_power:
        soc_needed = target_soc - soc
        charge_duration = min(
            soc_needed / charge_rate if charge_rate > 0 else time_remaining,
            time_remaining - 2,
        )
        if charge_duration > 0:
            plan.append({
                "action": "charge-ev",
                "start": 0.0,
                "duration": round(charge_duration, 1),
                "power_w": charger_power,
            })

    # --- HVAC ---
    # The cabin loses heat to the outside (Newton cooling) the whole time, so the
    # *net* heating rate is heater_delta minus the cooling loss. Sizing HVAC against
    # the raw heater_delta under-runs it and the cabin never reaches target in the
    # simulator. Subtract the worst-case cooling loss (evaluated at the target temp)
    # and schedule HVAC to finish *at departure* so the cabin is warm when it matters.
    cooling_coeff = world.get("cooling_coeff", 0.02)
    outside_temp = world.get("outside_temp", 5.0)
    if cabin_temp < target_cabin_temp and hvac_power <= max_power:
        temp_needed = target_cabin_temp - cabin_temp
        eff_heat_rate = max(0.1, heater_delta - cooling_coeff * (target_cabin_temp - outside_temp))
        # 1.25x margin covers the cooling that happens before HVAC starts; cap to the
        # PDDL domain's 60 sim-minute max duration and to the remaining window.
        hvac_duration = min(time_remaining, 60.0, (temp_needed / eff_heat_rate) * 1.25)

        # Finish at departure; defer the start past charging only if the combined draw
        # would bust the budget (config keeps 3700+2000 <= 5750, so normally inactive).
        hvac_start = max(0.0, time_remaining - hvac_duration)
        if charge_duration > 0 and charger_power + hvac_power > max_power:
            hvac_start = max(hvac_start, charge_duration)

        plan.append({
            "action": "run-hvac",
            "start": round(hvac_start, 1),
            "duration": round(hvac_duration, 1),
            "power_w": hvac_power,
        })

    # --- Seat warmer (last 8 sim-minutes before departure) ---
    seat_start = max(0.0, time_remaining - 8)
    seat_end = seat_start + 7.0
    # Check the power budget across the seat-warming window: sum every load that
    # overlaps it (charging, and now HVAC which runs up to departure).
    draw_at_seat = 0.0
    if charge_duration > 0 and seat_start < charge_duration:
        draw_at_seat += charger_power
    for a in plan:
        if a["action"] == "run-hvac" and a["start"] < seat_end and seat_start < a["start"] + a["duration"]:
            draw_at_seat += hvac_power
    if seat_warmer_power + draw_at_seat <= max_power:
        plan.append({
            "action": "warm-seat",
            "start": round(seat_start, 1),
            "duration": 7.0,
            "power_w": seat_warmer_power,
        })

    # --- Lights (2 sim-minutes before departure) ---
    plan.append({
        "action": "set-lights-on",
        "start": max(0.0, time_remaining - 2),
        "duration": 1.0,
        "power_w": 0.0,
    })

    # --- Route loading (1 sim-minute before departure) ---
    if not route_loaded:
        plan.append({
            "action": "load-route",
            "start": max(0.0, time_remaining - 1),
            "duration": 1.0,
            "power_w": 0.0,
        })

    plan.sort(key=lambda a: a["start"])
    logger.info("Fallback planner produced %d actions", len(plan))
    return plan
