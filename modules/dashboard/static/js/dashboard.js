/**
 * dashboard.js — SocketIO listener; routes MQTT messages to panel updaters.
 * Smart EV Charging & Cabin Prep — Group 22
 */

'use strict';

// ============================================================
// State
// ============================================================

const state = {
  battSoc:         0,
  targetSoc:       80,
  cabinTemp:       20,
  targetCabinTemp: 22,
  outsideTemp:     5,
  occupancy:       false,
  minutesRemaining: 60,
  charging:        false,
  hvacOn:          false,
  seatWarmerOn:    false,
  lightsOn:        false,
  routeLoaded:     false,
  chargerAvailable: true,
  plan:            [],
  planTs:          0,
  lastPlanSource:  '',
  userArrivesToggle: false,
};

// ============================================================
// SocketIO connection
// ============================================================

const socket = io();
let connected = false;

socket.on('connect', () => {
  connected = true;
  setStatus(true);
});

socket.on('disconnect', () => {
  connected = false;
  setStatus(false);
});

socket.on('mqtt_message', (entry) => {
  routeMessage(entry.topic, entry.payload, entry.ts);
  appendLog(entry);
});

socket.on('log_history', (entries) => {
  entries.forEach(e => appendLog(e));
});

// ============================================================
// Message router
// ============================================================

function routeMessage(topic, payload, ts) {
  if (topic === 'state/current') {
    handleStateUpdate(payload);
  } else if (topic === 'planning/plan') {
    handlePlanUpdate(payload);
  } else if (topic.startsWith('actuators/plugwise/status')) {
    handlePlugwiseStatus(payload);
  } else if (topic.startsWith('actuators/') && topic.endsWith('/status')) {
    handleActuatorStatus(topic, payload);
  } else if (topic.startsWith('sensors/')) {
    handleSensorUpdate(topic, payload);
  }
}

// ============================================================
// State update (primary source of truth)
// ============================================================

function handleStateUpdate(payload) {
  if (!payload || typeof payload !== 'object') return;

  state.battSoc         = val(payload.battery_soc, state.battSoc);
  state.targetSoc       = val(payload.target_soc, state.targetSoc);
  state.cabinTemp       = val(payload.cabin_temp, state.cabinTemp);
  state.targetCabinTemp = val(payload.target_cabin_temp, state.targetCabinTemp);
  state.outsideTemp     = val(payload.outside_temp, state.outsideTemp);
  state.occupancy       = val(payload.occupancy, state.occupancy);
  state.minutesRemaining = val(payload.minutes_remaining, state.minutesRemaining);
  state.charging        = val(payload.charging, state.charging);
  state.hvacOn          = val(payload.hvac_on, state.hvacOn);
  state.seatWarmerOn    = val(payload.seat_warmer_on, state.seatWarmerOn);
  state.lightsOn        = val(payload.lights_on, state.lightsOn);
  state.routeLoaded     = val(payload.route_loaded, state.routeLoaded);
  state.chargerAvailable = val(payload.charger_available, state.chargerAvailable);

  renderLiveState();
  updateCockpit(state);
}

function handleSensorUpdate(topic, payload) {
  if (typeof payload !== 'object') return;
  const v = payload.value;
  if (topic.includes('battery_soc'))   { state.battSoc = v; renderLiveState(); updateCockpit(state); }
  // cabin_temp is deliberately NOT read from the raw sensor topic: the StateManager
  // applies the grove_dht-vs-simulator priority rule and publishes the authoritative
  // value on state/current. Taking the raw topic here would let a stale simulator
  // reading flash over a fresh real (grove_dht) reading.
  if (topic.includes('outside_temp'))  { state.outsideTemp = v; renderLiveState(); }
  if (topic.includes('occupancy'))     { state.occupancy = v; renderLiveState(); }
  if (topic.includes('departure_time')) {
    state.minutesRemaining = val(payload.minutes_remaining, state.minutesRemaining);
    renderLiveState();
  }
}

function handleActuatorStatus(topic, payload) {
  if (typeof payload !== 'object') return;
  const s = payload.state;
  if (topic.includes('charging_plug')) {
    state.charging = s === 'on';
    state.chargerAvailable = s !== 'fault';
  } else if (topic.includes('cabin_heater')) {
    state.hvacOn = s === 'on';
  } else if (topic.includes('seat_warmer')) {
    state.seatWarmerOn = ['on', 'warming', 'warm'].includes(s);
  } else if (topic.includes('ambient_light')) {
    state.lightsOn = s === 'on';
  } else if (topic.includes('infotainment')) {
    state.routeLoaded = s === 'route_loaded';
  }
  renderBadges();
  updateCockpit(state);
}

function handlePlanUpdate(payload) {
  if (!payload || !Array.isArray(payload.actions)) return;
  state.plan = payload.actions;
  state.planTs = payload.ts || Date.now() / 1000;
  state.lastPlanSource = payload.source || 'unknown';
  updateGantt(state.plan, state.minutesRemaining, state.planTs, state.lastPlanSource);
  document.getElementById('plan-meta').textContent =
    `${state.plan.length} actions · ${state.lastPlanSource} · ${new Date(state.planTs * 1000).toLocaleTimeString()}`;
}

function handlePlugwiseStatus(payload) {
  if (!payload) return;
  const c1 = payload.circle_1 === 'on';
  const c2 = payload.circle_2 === 'on';
  document.getElementById('plugwise-c1-label').textContent = c1 ? 'ON' : 'OFF';
  document.getElementById('plugwise-c1-label').className = 'badge' + (c1 ? ' badge--on' : '');
  document.getElementById('plugwise-c2-label').textContent = c2 ? 'ON' : 'OFF';
  document.getElementById('plugwise-c2-label').className = 'badge' + (c2 ? ' badge--on' : '');
  // Update SVG plugwise plugs
  setClass(document.getElementById('plugwise-c1'), 'plugwise-plug--on', c1);
  setClass(document.getElementById('plugwise-c2'), 'plugwise-plug--on', c2);
}

// ============================================================
// Live State rendering
// ============================================================

function renderLiveState() {
  // SoC arc
  const arcLen = 251; // half-circle circumference for r=80
  const fill = Math.max(0, Math.min(1, state.battSoc / 100)) * arcLen;
  const arc = document.getElementById('soc-arc');
  if (arc) {
    arc.setAttribute('stroke-dasharray', `${fill} ${arcLen}`);
    arc.setAttribute('stroke', socColor(state.battSoc));
  }
  setText('soc-text', `${state.battSoc.toFixed(0)}%`);

  // Cabin temp bar (0°C = 0%, 40°C = 100%)
  const tempPct = Math.max(0, Math.min(100, (state.cabinTemp / 40) * 100));
  const tempBar = document.getElementById('cabin-temp-bar');
  if (tempBar) tempBar.style.setProperty('--temp-pct', `${tempPct}%`);
  setText('cabin-temp-text', `${state.cabinTemp.toFixed(1)}°C`);
  setText('cabin-temp-target', `Target: ${state.targetCabinTemp.toFixed(1)}°C`);

  // Outside temp
  setText('outside-temp-text', `${state.outsideTemp.toFixed(1)}°C`);

  // Occupancy
  const occDot = document.getElementById('occupancy-dot');
  if (occDot) {
    occDot.className = 'occupancy-dot ' + (state.occupancy ? 'occupancy-dot--on' : 'occupancy-dot--off');
  }
  setText('occupancy-text', state.occupancy ? 'Occupied' : 'Empty');

  // Countdown
  const mins = Math.max(0, state.minutesRemaining);
  const h = Math.floor(mins / 60);
  const m = Math.floor(mins % 60);
  const s = Math.floor((mins % 1) * 60);
  setText('countdown-text', h > 0 ? `${h}h ${m}m` : `${m}m ${s}s`);

  renderBadges();
}

function renderBadges() {
  setBadge('badge-charging', state.charging,     state.chargerAvailable ? null : 'fault');
  setBadge('badge-hvac',     state.hvacOn);
  setBadge('badge-seat',     state.seatWarmerOn);
  setBadge('badge-lights',   state.lightsOn);
  setBadge('badge-route',    state.routeLoaded);

  if (!state.chargerAvailable) {
    const b = document.getElementById('badge-charging');
    if (b) { b.className = 'badge badge--fault'; b.textContent = '⚡ FAULT'; }
  }
}

// ============================================================
// Trigger buttons
// ============================================================

async function triggerCalendarShift() {
  await fetch('/api/trigger/calendar_shift', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ shift_sim_minutes: -30 }),
  });
}

async function triggerChargerFault() {
  await fetch('/api/trigger/charger_fault', { method: 'POST' });
}

async function triggerUserArrives() {
  state.userArrivesToggle = !state.userArrivesToggle;
  await fetch('/api/trigger/user_arrives', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ occupied: state.userArrivesToggle }),
  });
}

async function triggerReplan() {
  await fetch('/api/trigger/replan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason: 'manual' }),
  });
}

// ============================================================
// Event Log
// ============================================================

const MAX_LOG_ENTRIES = 80;
let logCount = 0;

function appendLog(entry) {
  const scroll = document.getElementById('log-scroll');
  if (!scroll) return;

  // Remove placeholder
  const placeholder = scroll.querySelector('.log-placeholder');
  if (placeholder) placeholder.remove();

  // Cap log entries
  while (scroll.children.length >= MAX_LOG_ENTRIES) {
    scroll.removeChild(scroll.lastChild);
  }

  const cat = topicCategory(entry.topic);
  const div = document.createElement('div');
  div.className = `log-entry log-entry--${cat}`;

  const ts = new Date(entry.ts * 1000).toLocaleTimeString();
  const bodyStr = typeof entry.payload === 'object'
    ? JSON.stringify(entry.payload, null, 0)
    : String(entry.payload);

  div.innerHTML = `
    <span class="log-ts">${ts}</span>
    <span class="log-topic">${entry.topic}</span>
    <span class="log-body">${truncate(bodyStr, 120)}</span>
  `;
  scroll.insertBefore(div, scroll.firstChild);
  logCount++;
}

function clearLog() {
  const scroll = document.getElementById('log-scroll');
  if (scroll) scroll.innerHTML = '<div class="log-placeholder">Log cleared.</div>';
}

// ============================================================
// Helpers
// ============================================================

function val(v, fallback) { return v !== undefined && v !== null ? v : fallback; }

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function setBadge(id, active, modifier) {
  const el = document.getElementById(id);
  if (!el) return;
  if (modifier === 'fault') { el.className = 'badge badge--fault'; return; }
  el.className = 'badge' + (active ? ' badge--on' : '');
}

function setClass(el, cls, on) {
  if (!el) return;
  on ? el.classList.add(cls) : el.classList.remove(cls);
}

function setStatus(ok) {
  const dot   = document.getElementById('broker-status');
  const label = document.getElementById('broker-label');
  if (dot)   dot.className   = 'status-dot ' + (ok ? 'status-dot--connected' : 'status-dot--disconnected');
  if (label) label.textContent = ok ? 'Connected' : 'Disconnected';
}

function socColor(soc) {
  if (soc >= 70) return '#3fb950'; // green
  if (soc >= 40) return '#d29922'; // orange
  return '#f85149';                // red
}

function topicCategory(topic) {
  if (topic.startsWith('sensors/'))   return 'sensor';
  if (topic.startsWith('state/'))     return 'state';
  if (topic.startsWith('planning/'))  return 'plan';
  if (topic.startsWith('events/'))    return 'event';
  if (topic.startsWith('actuators/')) return 'actuator';
  return 'state';
}

function truncate(str, max) {
  return str.length > max ? str.slice(0, max) + '…' : str;
}
