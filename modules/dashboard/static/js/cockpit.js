/**
 * cockpit.js — EV Cockpit SVG synthetic widget animations.
 * Smart EV Charging & Cabin Prep — Group 22
 */

'use strict';

// ============================================================
// Public update function (called from dashboard.js)
// ============================================================

function updateCockpit(s) {
  updateBatteryFill(s.battSoc);
  updateChargingCable(s.charging);
  updateSeatGlow(s.seatWarmerOn);
  updateLedStrip(s.lightsOn);
  updateDashScreen(s.routeLoaded);
  updateHvacVents(s.hvacOn);
}

// ============================================================
// Battery fill bar (scales inside the car's battery floor rect)
// ============================================================

// Battery floor: x=82, width=136, y=172, height=156 (see SVG)
const BATT_MAX_WIDTH = 136;

function updateBatteryFill(soc) {
  const pct = Math.max(0, Math.min(100, soc)) / 100;
  const fill = document.getElementById('battery-fill-bar');
  const label = document.getElementById('battery-pct-svg');
  const arc   = document.getElementById('soc-arc');

  if (fill) {
    fill.setAttribute('width', String(Math.round(BATT_MAX_WIDTH * pct)));
    fill.setAttribute('fill', socToColor(soc));
  }
  if (label) label.textContent = `${Math.round(soc)}%`;
}

// ============================================================
// Charging cable glow
// ============================================================

function updateChargingCable(isCharging) {
  const cable = document.getElementById('charging-cable');
  if (!cable) return;

  if (isCharging) {
    cable.setAttribute('opacity', '1');
    cable.classList.add('charging-pulse');
  } else {
    cable.setAttribute('opacity', '0');
    cable.classList.remove('charging-pulse');
  }

  // Plugwise Circle 1 (charger plug SVG element)
  const p1 = document.getElementById('plugwise-c1');
  if (p1) {
    if (isCharging) {
      p1.setAttribute('opacity', '1');
      p1.setAttribute('fill', '#d29922');
    } else {
      p1.setAttribute('opacity', '0.3');
      p1.setAttribute('fill', '#444');
    }
  }
}

// ============================================================
// Seat warmer glow
// ============================================================

function updateSeatGlow(isOn) {
  const glow = document.getElementById('seat-glow');
  if (!glow) return;
  glow.setAttribute('opacity', isOn ? '0.75' : '0');
}

// ============================================================
// LED ambient strip
// ============================================================

function updateLedStrip(isOn) {
  ['led-strip-l', 'led-strip-r'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (isOn) {
      el.setAttribute('fill', 'rgba(63,185,80,0.6)');
      el.style.filter = 'drop-shadow(0 0 5px #3fb950)';
    } else {
      el.setAttribute('fill', 'transparent');
      el.style.filter = '';
    }
  });
}

// ============================================================
// Dashboard screen (route loaded indicator)
// ============================================================

function updateDashScreen(routeLoaded) {
  const screen = document.getElementById('dash-screen');
  const text   = document.getElementById('dash-text');
  if (!screen || !text) return;

  if (routeLoaded) {
    screen.setAttribute('fill', '#0b2a2b');
    screen.setAttribute('stroke', '#39d0d8');
    text.textContent = 'Route Ready';
    text.setAttribute('fill', '#39d0d8');
  } else {
    screen.setAttribute('fill', '#0d1117');
    screen.setAttribute('stroke', '#30363d');
    text.textContent = '—';
    text.setAttribute('fill', '#8b949e');
  }
}

// ============================================================
// HVAC vent animation
// ============================================================

function updateHvacVents(hvacOn) {
  const vents = document.getElementById('hvac-vents');
  if (!vents) return;
  vents.setAttribute('opacity', hvacOn ? '1' : '0.2');

  if (hvacOn) {
    vents.classList.add('active');
    startVentAnimation(vents);
  } else {
    vents.classList.remove('active');
    stopVentAnimation(vents);
  }
}

let ventAnimFrame = null;
let ventOffset = 0;

function startVentAnimation(vents) {
  if (ventAnimFrame) return;
  const rects = vents.querySelectorAll('.vent');

  function tick() {
    ventOffset = (ventOffset + 0.5) % 10;
    rects.forEach((r, i) => {
      const shift = (ventOffset + i * 3) % 10;
      r.setAttribute('x', String(95 + i * 35 + shift));
    });
    ventAnimFrame = requestAnimationFrame(tick);
  }
  ventAnimFrame = requestAnimationFrame(tick);
}

function stopVentAnimation(vents) {
  if (ventAnimFrame) {
    cancelAnimationFrame(ventAnimFrame);
    ventAnimFrame = null;
  }
  // Reset vent positions
  const rects = vents.querySelectorAll('.vent');
  const baseX = [95, 130, 165];
  rects.forEach((r, i) => r.setAttribute('x', String(baseX[i])));
}

// ============================================================
// Helper: SoC → color
// ============================================================

function socToColor(soc) {
  if (soc >= 70) return '#3fb950';
  if (soc >= 40) return '#d29922';
  return '#f85149';
}

// ============================================================
// Charging pulse CSS animation (injected once)
// ============================================================

(function injectChargingPulse() {
  const style = document.createElement('style');
  style.textContent = `
    @keyframes chargingPulse {
      0%, 100% { opacity: 1; }
      50%       { opacity: 0.5; }
    }
    .charging-pulse { animation: chargingPulse 1.2s ease-in-out infinite; }
  `;
  document.head.appendChild(style);
})();
