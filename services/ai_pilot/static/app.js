/**
 * AI Pilot Glassmorphic Web Deck Controller
 * Telemetry Polling, Canvas Attitude Indicator, Checklist Runner & Chat
 */

document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const elAirspeed = document.getElementById('val-airspeed');
  const elGs = document.getElementById('val-gs');
  const elAlt = document.getElementById('val-alt');
  const elAgl = document.getElementById('val-agl');
  const elVvi = document.getElementById('val-vvi');
  const elPitch = document.getElementById('val-pitch');
  const elRoll = document.getElementById('val-roll');
  const elHeading = document.getElementById('val-heading');
  const elHdgBug = document.getElementById('val-hdg-bug');
  const elAltBug = document.getElementById('val-alt-bug');
  const elRpm = document.getElementById('val-rpm');
  const elBarRpm = document.getElementById('bar-rpm');
  const elMp = document.getElementById('val-mp');
  const elBarMp = document.getElementById('bar-mp');
  const elFlaps = document.getElementById('val-flaps');
  const elBrakes = document.getElementById('val-brakes');
  const elPhaseBadge = document.getElementById('flight-phase-badge');
  const elDist = document.getElementById('dist-display');
  const elProgressFill = document.getElementById('flight-progress-fill');
  const elAircraftMarker = document.getElementById('aircraft-marker');
  const elEventsLog = document.getElementById('events-log');
  const elChecklistSelect = document.getElementById('checklist-select');
  const elChecklistBox = document.getElementById('checklist-box');
  const btnRunChecklist = document.getElementById('btn-run-checklist');
  const btnToggleAuto = document.getElementById('btn-toggle-auto');
  const elChatMessages = document.getElementById('chat-messages');
  const elChatForm = document.getElementById('chat-form');
  const elChatInput = document.getElementById('chat-input');

  // Canvas Attitude Indicator
  const canvas = document.getElementById('attitudeCanvas');
  const ctx = canvas.getContext('2d');

  let currentChecklists = {};
  let autonomousActive = false;

  // ---------------------------------------------------------------------------
  // Canvas Artificial Horizon Drawing
  // ---------------------------------------------------------------------------
  function drawAttitude(pitchDeg, rollDeg) {
    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;

    ctx.save();
    ctx.clearRect(0, 0, w, h);

    // Translate to center and rotate by roll angle
    ctx.translate(cx, cy);
    ctx.rotate((rollDeg * Math.PI) / 180);

    // Pitch pixels offset (approx 3 px per degree)
    const pitchOffset = pitchDeg * 3.0;

    // Sky
    ctx.fillStyle = '#0f4c81';
    ctx.fillRect(-w, -h - pitchOffset, w * 2, h + pitchOffset);

    // Ground
    ctx.fillStyle = '#5c4033';
    ctx.fillRect(-w, -pitchOffset, w * 2, h * 2);

    // Horizon Line
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(-w, -pitchOffset);
    ctx.lineTo(w, -pitchOffset);
    ctx.stroke();

    // Pitch ladder bars
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.7)';
    ctx.lineWidth = 1.5;
    ctx.fillStyle = '#ffffff';
    ctx.font = '9px monospace';
    ctx.textAlign = 'center';

    const pitches = [-20, -10, -5, 5, 10, 20];
    for (const p of pitches) {
      const y = -pitchOffset - (p * 3.0);
      const barW = Math.abs(p) % 10 === 0 ? 36 : 20;
      ctx.beginPath();
      ctx.moveTo(-barW / 2, y);
      ctx.lineTo(barW / 2, y);
      ctx.stroke();
      if (Math.abs(p) % 10 === 0) {
        ctx.fillText(Math.abs(p).toString(), -barW / 2 - 10, y + 3);
        ctx.fillText(Math.abs(p).toString(), barW / 2 + 10, y + 3);
      }
    }

    ctx.restore();

    // Aircraft fixed symbol (yellow wings & center dot)
    ctx.strokeStyle = '#ffcc00';
    ctx.lineWidth = 3;
    ctx.beginPath();
    // Left wing
    ctx.moveTo(cx - 50, cy);
    ctx.lineTo(cx - 20, cy);
    ctx.lineTo(cx - 20, cy + 8);
    // Right wing
    ctx.moveTo(cx + 50, cy);
    ctx.lineTo(cx + 20, cy);
    ctx.lineTo(cx + 20, cy + 8);
    // Center dot
    ctx.moveTo(cx - 3, cy);
    ctx.lineTo(cx + 3, cy);
    ctx.stroke();
  }

  // ---------------------------------------------------------------------------
  // Telemetry Polling (5 Hz)
  // ---------------------------------------------------------------------------
  async function fetchTelemetry() {
    try {
      const resp = await fetch('/api/telemetry');
      if (!resp.ok) return;
      const data = await resp.json();

      // Airspeeds & Altitudes
      elAirspeed.innerText = Math.round(data.flight_dynamics.kias);
      elGs.innerText = Math.round(data.flight_dynamics.groundspeed_kts);
      elAlt.innerText = Math.round(data.position.alt_msl_ft).toLocaleString();
      elAgl.innerText = Math.round(data.position.alt_agl_ft).toLocaleString();
      elVvi.innerText = Math.round(data.flight_dynamics.vvi_fpm);

      // Pitch & Roll
      const pitch = data.flight_dynamics.pitch_deg;
      const roll = data.flight_dynamics.roll_deg;
      elPitch.innerText = `${pitch.toFixed(1)}°`;
      elRoll.innerText = `${roll.toFixed(1)}°`;
      drawAttitude(pitch, roll);

      // Heading & Bugs
      elHeading.innerText = `${Math.round(data.position.heading_mag).toString().padStart(3, '0')}°`;
      elHdgBug.innerText = `${Math.round(data.autopilot.heading_bug).toString().padStart(3, '0')}°`;
      elAltBug.innerText = `${Math.round(data.autopilot.altitude_bug).toLocaleString()} FT`;

      // Engine Tach & MP
      const rpm = data.engine.rpm;
      elRpm.innerText = `${Math.round(rpm)} RPM`;
      elBarRpm.style.width = `${Math.min(100, (rpm / 2700) * 100)}%`;

      const mp = data.engine.mp_inhg;
      elMp.innerText = `${mp.toFixed(1)} IN HG`;
      elBarMp.style.width = `${Math.min(100, (mp / 30) * 100)}%`;

      // Flaps & Brakes
      const flaps = data.controls.flaps_ratio;
      if (flaps >= 0.9) elFlaps.innerText = '30° (FULL)';
      else if (flaps >= 0.5) elFlaps.innerText = '20° (APP)';
      else if (flaps >= 0.2) elFlaps.innerText = '10° (TAKEOFF)';
      else elFlaps.innerText = '0° (UP)';

      const brakes = data.controls.brakes_ratio;
      elBrakes.innerText = brakes > 0.5 ? 'PARK SET' : 'RELEASED';
      elBrakes.className = brakes > 0.5 ? 'eng-val text-amber' : 'eng-val text-green';

      // Phase & Distance
      elPhaseBadge.innerText = data.phase;
      const dist = data.navigation.distance_to_krnm_nm;
      elDist.innerText = `${dist.toFixed(1)} NM`;

      // Progress bar (total distance ~13.2 NM)
      const pct = Math.max(3, Math.min(100, ((13.2 - dist) / 13.2) * 100));
      elProgressFill.style.width = `${pct}%`;
      elAircraftMarker.style.left = `${pct}%`;

      // Autonomous badge
      autonomousActive = data.autonomous_active;
      btnToggleAuto.innerText = autonomousActive ? '🤖 AUTO-PILOT: ACTIVE' : '🤖 AUTO-PILOT: OFF';
      btnToggleAuto.style.background = autonomousActive ? 'linear-gradient(135deg, #00bb55, #007733)' : '';

      // Events Log
      if (data.recent_events && data.recent_events.length > 0) {
        elEventsLog.innerHTML = data.recent_events.map(ev => `<div class="log-line">${ev}</div>`).join('');
        elEventsLog.scrollTop = elEventsLog.scrollHeight;
      }
    } catch (e) {
      console.warn('Telemetry fetch error:', e);
    }
  }

  // ---------------------------------------------------------------------------
  // Checklists Management
  // ---------------------------------------------------------------------------
  async function fetchChecklists() {
    try {
      const resp = await fetch('/api/checklists');
      if (!resp.ok) return;
      const data = await resp.json();
      currentChecklists = {};
      for (const cl of data.checklists) {
        currentChecklists[cl.phase] = cl;
      }
      renderActiveChecklist();
    } catch (e) {
      console.warn('Checklists fetch error:', e);
    }
  }

  function renderActiveChecklist() {
    const selectedPhase = elChecklistSelect.value;
    const cl = currentChecklists[selectedPhase];
    if (!cl) {
      elChecklistBox.innerHTML = '<div class="log-line text-dim">No checklist selected.</div>';
      return;
    }

    elChecklistBox.innerHTML = cl.items.map(item => `
      <div class="checklist-item-row ${item.is_verified ? 'verified' : 'pending'}">
        <span class="chk-item">${item.challenge} ➔ <strong>${item.response}</strong></span>
        <span class="chk-status ${item.is_verified ? 'text-green' : 'text-amber'}">
          ${item.is_verified ? '✓ OK' : '○ PENDING'}
        </span>
      </div>
    `).join('');
  }

  elChecklistSelect.addEventListener('change', renderActiveChecklist);

  btnRunChecklist.addEventListener('click', async () => {
    const selectedPhase = elChecklistSelect.value;
    btnRunChecklist.disabled = true;
    btnRunChecklist.innerText = 'Running...';
    try {
      const resp = await fetch('/api/checklists/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ checklist: selectedPhase }),
      });
      await fetchChecklists();
      await fetchChat();
    } finally {
      btnRunChecklist.disabled = false;
      btnRunChecklist.innerText = '▶ Run Checklist';
    }
  });

  // ---------------------------------------------------------------------------
  // Chat / Dialogue System
  // ---------------------------------------------------------------------------
  async function fetchChat() {
    try {
      const resp = await fetch('/api/chat');
      if (!resp.ok) return;
      const data = await resp.json();
      if (data.messages) {
        renderChat(data.messages);
      }
    } catch (e) {
      console.warn('Chat fetch error:', e);
    }
  }

  function renderChat(messages) {
    elChatMessages.innerHTML = messages.map(m => `
      <div class="chat-msg ${m.sender}">
        <span class="sender-name">${m.sender === 'pilot' ? '👨‍✈️ PILOT' : '🤖 COPILOT'} [${m.timestamp}]:</span>
        <div class="msg-text">${m.text}</div>
      </div>
    `).join('');
    elChatMessages.scrollTop = elChatMessages.scrollHeight;
  }

  elChatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = elChatInput.value.trim();
    if (!text) return;
    elChatInput.value = '';

    // Append user message immediately
    const tempMsg = { sender: 'pilot', text, timestamp: new Date().toTimeString().split(' ')[0] };
    elChatMessages.innerHTML += `
      <div class="chat-msg pilot">
        <span class="sender-name">👨‍✈️ PILOT [${tempMsg.timestamp}]:</span>
        <div class="msg-text">${tempMsg.text}</div>
      </div>
    `;
    elChatMessages.scrollTop = elChatMessages.scrollHeight;

    try {
      const resp = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      });
      const data = await resp.json();
      if (data.messages) {
        renderChat(data.messages);
      }
      fetchTelemetry();
      fetchChecklists();
    } catch (err) {
      console.error('Chat error:', err);
    }
  });

  // ---------------------------------------------------------------------------
  // Quick Flight Command Buttons
  // ---------------------------------------------------------------------------
  async function sendPhaseCommand(phase) {
    await fetch('/api/phase', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phase }),
    });
    fetchTelemetry();
    fetchChat();
  }

  document.getElementById('cmd-spawn').addEventListener('click', async () => {
    await fetch('/api/spawn', { method: 'POST' });
    fetchTelemetry();
    fetchChat();
  });

  document.getElementById('cmd-start-engine').addEventListener('click', async () => {
    await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'start engine' }),
    });
    fetchTelemetry();
    fetchChat();
  });

  document.getElementById('cmd-takeoff').addEventListener('click', () => sendPhaseCommand('TAKEOFF_ROLL'));
  document.getElementById('cmd-climb').addEventListener('click', () => sendPhaseCommand('ENROUTE_CLIMB'));
  document.getElementById('cmd-descent').addEventListener('click', () => sendPhaseCommand('DESCENT'));
  document.getElementById('cmd-approach').addEventListener('click', () => sendPhaseCommand('APPROACH_INTERCEPT'));
  document.getElementById('cmd-land').addEventListener('click', () => sendPhaseCommand('FINAL_APPROACH'));
  document.getElementById('cmd-shutdown').addEventListener('click', () => sendPhaseCommand('ENGINE_SHUTDOWN'));

  btnToggleAuto.addEventListener('click', async () => {
    const endpoint = autonomousActive ? '/api/mission/stop' : '/api/mission/start';
    await fetch(endpoint, { method: 'POST' });
    fetchTelemetry();
    fetchChat();
  });

  // ---------------------------------------------------------------------------
  // Startup Loops
  // ---------------------------------------------------------------------------
  fetchTelemetry();
  fetchChecklists();
  fetchChat();

  // Polling intervals: Telemetry @ 200ms (5 Hz), Checklists & Chat @ 2s
  setInterval(fetchTelemetry, 200);
  setInterval(fetchChecklists, 2000);
  setInterval(fetchChat, 2000);
});

