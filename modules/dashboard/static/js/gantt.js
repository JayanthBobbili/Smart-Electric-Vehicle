/**
 * gantt.js — Chart.js horizontal bar Gantt for plan timeline.
 * Smart EV Charging & Cabin Prep — Group 22
 */

'use strict';

// ============================================================
// Color map
// ============================================================

const ACTION_COLORS = {
  'charge-ev':     '#3fb950',
  'run-hvac':      '#58a6ff',
  'warm-seat':     '#ff8c00',
  'set-lights-on': '#f0e442',
  'load-route':    '#39d0d8',
  'default':       '#8b949e',
};

// ============================================================
// Action display names
// ============================================================

const ACTION_LABELS = {
  'charge-ev':     'Charging EV',
  'run-hvac':      'Heating Cabin',
  'warm-seat':     'Seat Warmer',
  'set-lights-on': 'Lights On',
  'load-route':    'Load Route',
};

// ============================================================
// Chart instance
// ============================================================

let ganttChart = null;
let replanLines = []; // [{x, label}]
let planStartTs = 0;  // unix timestamp when current plan was issued

function initGantt() {
  const ctx = document.getElementById('gantt-canvas');
  if (!ctx) return;

  ganttChart = new Chart(ctx, {
    type: 'bar',
    data: { labels: [], datasets: [] },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      scales: {
        x: {
          type: 'linear',
          min: 0,
          title: { display: true, text: 'Sim-minutes from plan start', color: '#8b949e' },
          ticks: { color: '#8b949e' },
          grid: { color: '#30363d' },
        },
        y: {
          ticks: { color: '#e6edf3', font: { size: 11 } },
          grid: { color: '#30363d' },
        },
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const d = ctx.raw;
              if (!d) return '';
              return `${d[0].toFixed(1)} → ${d[1].toFixed(1)} min (${(d[1]-d[0]).toFixed(1)} min)`;
            },
          },
        },
        annotation: buildAnnotationPlugin(),
      },
    },
  });
}

function buildAnnotationPlugin() {
  // Chart.js annotation plugin is not loaded here; we draw replan lines manually
  return {};
}

// ============================================================
// Update from new plan
// ============================================================

function updateGantt(actions, minutesRemaining, planTs, source) {
  if (!ganttChart) initGantt();
  if (!ganttChart || !Array.isArray(actions) || actions.length === 0) return;

  // Track replan events — push a line marker if this is a new plan
  if (planTs !== planStartTs && planStartTs > 0) {
    const elapsed = (planTs - planStartTs) / 60;
    replanLines.push({ x: elapsed, label: 'Replan' });
  }
  planStartTs = planTs || Date.now() / 1000;

  // Show all actions; the new domain uses combined actions so all have meaningful durations
  const displayActions = actions.filter(a => a.duration >= 1);

  const labels   = displayActions.map(a => ACTION_LABELS[a.action] || a.action);
  const colors   = displayActions.map(a => actionColor(a, minutesRemaining, planTs));
  const data     = displayActions.map(a => [a.start, a.start + a.duration]);

  ganttChart.data.labels = labels;
  ganttChart.data.datasets = [{
    data: data,
    backgroundColor: colors.map(c => hexToRgba(c, 0.7)),
    borderColor:     colors,
    borderWidth: 2,
    borderRadius: 4,
    barThickness: 18,
  }];

  ganttChart.options.scales.x.max = Math.ceil(minutesRemaining + 5);
  ganttChart.update();
}

// ============================================================
// Color by execution status
// ============================================================

function actionColor(action, minutesRemaining, planIssuedTs) {
  const baseName = action.action;
  const base = ACTION_COLORS[baseName] || ACTION_COLORS['default'];

  const nowTs = Date.now() / 1000;
  const elapsedSincePlan = nowTs - planIssuedTs;  // real seconds
  // Approximate elapsed sim-minutes (no time_scale here, but good enough for display)
  const elapsedSimMin = elapsedSincePlan;  // dashboard doesn't know time_scale; planner timestamps encode real start

  const actionEnd = action.start + action.duration;
  if (actionEnd <= elapsedSimMin) return '#30363d';  // completed — grey
  if (action.start <= elapsedSimMin) return '#3fb950'; // in progress — green
  return base;  // future — original color
}

// ============================================================
// Helpers
// ============================================================

function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}
