// ==========================================================================
// CAP V-SAR MISSION RADIO OPERATOR (MRO) BASE STATION RADIO CONTROLLER
// ==========================================================================

const $ = id => document.getElementById(id);

// --------------------------------------------------------------------------
// WEB AUDIO SYNTHESIZER (Pure JS, zero external files)
// --------------------------------------------------------------------------
class RadioAudio {
  constructor() {
    this.ctx = null;
    this.noiseNode = null;
    this.noiseGain = null;
    this.enabled = true;
  }

  ensureContext() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.ctx = new AudioCtx();
    }
    if (this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
  }

  // Motorola P25 3-tone permit to speak chirp: 941 Hz, 1336 Hz, 1209 Hz
  playP25Chirp() {
    if (!this.enabled) return;
    this.ensureContext();
    const now = this.ctx.currentTime;
    const tones = [
      { freq: 941, dur: 0.035 },
      { freq: 1336, dur: 0.035 },
      { freq: 1209, dur: 0.045 }
    ];

    let t = now;
    tones.forEach(item => {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(item.freq, t);

      gain.gain.setValueAtTime(0.001, t);
      gain.gain.linearRampToValueAtTime(0.18, t + 0.005);
      gain.gain.exponentialRampToValueAtTime(0.001, t + item.dur);

      osc.connect(gain);
      gain.connect(this.ctx.destination);

      osc.start(t);
      osc.stop(t + item.dur);
      t += item.dur;
    });
  }

  // Motorola digital carrier squelch tail (120Hz click + noise cutoff)
  playP25Tail() {
    if (!this.enabled) return;
    this.ensureContext();
    const now = this.ctx.currentTime;

    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = 'sawtooth';
    osc.frequency.setValueAtTime(120, now);
    osc.frequency.exponentialRampToValueAtTime(40, now + 0.04);

    gain.gain.setValueAtTime(0.2, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.04);

    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start(now);
    osc.stop(now + 0.04);
  }

  // VHF-AM mechanical relay click
  playAmClick() {
    if (!this.enabled) return;
    this.ensureContext();
    const now = this.ctx.currentTime;

    const osc = this.ctx.createOscillator();
    const gain = this.ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(800, now);
    osc.frequency.exponentialRampToValueAtTime(200, now + 0.015);

    gain.gain.setValueAtTime(0.25, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.015);

    osc.connect(gain);
    gain.connect(this.ctx.destination);
    osc.start(now);
    osc.stop(now + 0.015);
  }

  // VHF-AM squelch burst (shhh-click)
  playAmSquelchBurst() {
    if (!this.enabled) return;
    this.ensureContext();
    const now = this.ctx.currentTime;

    // Generate white noise buffer
    const bufSize = this.ctx.sampleRate * 0.09;
    const buf = this.ctx.createBuffer(1, bufSize, this.ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < bufSize; i++) {
      data[i] = (Math.random() * 2 - 1);
    }

    const noise = this.ctx.createBufferSource();
    noise.buffer = buf;

    // Bandpass filter for communications audio (300Hz - 2800Hz)
    const filter = this.ctx.createBiquadFilter();
    filter.type = 'bandpass';
    filter.frequency.setValueAtTime(1400, now);
    filter.Q.setValueAtTime(1.5, now);

    const gain = this.ctx.createGain();
    gain.gain.setValueAtTime(0.22, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 0.09);

    noise.connect(filter);
    filter.connect(gain);
    gain.connect(this.ctx.destination);

    noise.start(now);
    noise.stop(now + 0.09);
  }

  // Text-To-Speech with simulated tactical radio voice
  speak(text, onEnd) {
    if (!('speechSynthesis' in window) || !$('chkTts').checked) {
      if (onEnd) onEnd();
      return;
    }
    const utter = new SpeechSynthesisUtterance(text);
    utter.rate = 1.05;
    utter.pitch = 0.95;
    utter.onend = () => { if (onEnd) onEnd(); };
    utter.onerror = () => { if (onEnd) onEnd(); };
    window.speechSynthesis.speak(utter);
  }
}

const audio = new RadioAudio();

// --------------------------------------------------------------------------
// RADIO SPECIFICATIONS & DATA
// --------------------------------------------------------------------------

// Motorola APX 6500 Zones & Channels
const APX_ZONES = [
  {
    name: 'ZONE 1 (TACTICAL)',
    channels: [
      { name: 'TAC 1',    freq: '148.1500 MHz', tone: 'N110.9', direct: true,  power: 'H' },
      { name: 'TAC 2',    freq: '148.1250 MHz', tone: 'N110.9', direct: true,  power: 'H' },
      { name: 'CC 1',     freq: '150.2250 MHz', tone: 'P25 $293', direct: false, power: 'H' },
      { name: 'CC 2',     freq: '149.2750 MHz', tone: 'P25 $293', direct: false, power: 'H' },
      { name: 'AIR 1',    freq: '150.5375 MHz', tone: 'N110.9', direct: true,  power: 'H' },
      { name: 'AIR 2',    freq: '149.5375 MHz', tone: 'N110.9', direct: true,  power: 'H' },
      { name: 'SAR 1',    freq: '149.9250 MHz', tone: 'N110.9', direct: true,  power: 'H' },
      { name: 'GUARD',    freq: '148.1500 MHz', tone: 'DIRECT', direct: true,  power: 'H' }
    ]
  },
  {
    name: 'ZONE 2 (GROUND & LOG)',
    channels: [
      { name: 'GROUND 1', freq: '148.1500 MHz', tone: 'SIMPLEX', direct: true, power: 'H' },
      { name: 'GROUND 2', freq: '148.1250 MHz', tone: 'SIMPLEX', direct: true, power: 'H' },
      { name: 'BASE DISP',freq: '150.2250 MHz', tone: 'P25 $293', direct: false, power: 'H' },
      { name: 'LOGISTICS',freq: '149.2750 MHz', tone: 'N110.9', direct: true,  power: 'H' },
      { name: 'AIR EVAC', freq: '150.5375 MHz', tone: 'N110.9', direct: true,  power: 'H' },
      { name: 'SAR 2',    freq: '149.9000 MHz', tone: 'N110.9', direct: true,  power: 'H' }
    ]
  },
  {
    name: 'ZONE 3 (INTEROP)',
    channels: [
      { name: 'VFIRE 21', freq: '154.2800 MHz', tone: 'N156.7', direct: true,  power: 'H' },
      { name: 'VTAC 11',  freq: '151.1375 MHz', tone: 'N156.7', direct: true,  power: 'H' },
      { name: 'CALCORD',  freq: '156.0750 MHz', tone: 'N156.7', direct: true,  power: 'H' },
      { name: 'NATL GRD', freq: '149.2500 MHz', tone: 'P25 $293', direct: false, power: 'H' }
    ]
  }
];

// Icom IC-A120 Aeronautical Memory Presets
const ICOM_PRESETS = [
  { ch: 'CH 01', freq: 123.100, alias: 'SAR PRI' },
  { ch: 'CH 02', freq: 122.900, alias: 'SAR SEC' },
  { ch: 'CH 03', freq: 121.500, alias: 'ELT GUARD' },
  { ch: 'CH 04', freq: 122.775, alias: 'AIR-AIR' },
  { ch: 'CH 05', freq: 123.050, alias: 'UNICOM' },
  { ch: 'CH 06', freq: 126.200, alias: 'MIL SAR' },
  { ch: 'CH 07', freq: 119.200, alias: 'TOWER' },
  { ch: 'CH 08', freq: 120.500, alias: 'APPROACH' }
];

// --------------------------------------------------------------------------
// COMPONENT STATE
// --------------------------------------------------------------------------

let displayMode = 'apx'; // 'apx', 'icom', 'dual'
let activeRadio = 'apx'; // which radio is active for PTT transmission
let transmitting = false;
let pttLocked = false;
let rxActiveTimer = null;

const apx = {
  power: true,
  vol: 8,       // 0..10 (0 = OFF)
  zoneIdx: 0,
  chanIdx: 0,
  scan: false,
  mon: false,
  dim: false,
  volAngle: 45,
  chanAngle: 0
};

const icom = {
  power: true,
  vol: 7,       // 0..10
  sql: 5,       // 0..10
  mode: 'CH',   // 'CH' (Memory) or 'VFO' (Direct frequency)
  memIdx: 0,
  vfoFreq: 123.100,
  step1Mhz: false,
  pri: false,   // Priority watch 121.500 Guard
  scan: false,
  anl: true,
  volAngle: 30,
  sqlAngle: 0,
  dialAngle: 0
};

const commLog = [];

// --------------------------------------------------------------------------
// DISPLAY UPDATES & RENDERING
// --------------------------------------------------------------------------

function renderApx() {
  const disp = $('apxDisplay');
  if (!apx.power || apx.vol === 0) {
    disp.classList.add('off');
    $('apxVolDisplay').textContent = 'OFF';
    $('apxLedTx').classList.remove('active');
    $('apxLedRx').classList.remove('active');
    $('apxLedScan').classList.remove('active');
    return;
  }

  disp.classList.remove('off');
  $('apxVolDisplay').textContent = `VOL ${apx.vol}`;

  const currentZone = APX_ZONES[apx.zoneIdx];
  const currentChan = currentZone.channels[apx.chanIdx];

  $('apxZoneLabel').textContent = `Z${apx.zoneIdx + 1}`;
  $('apxChanName').textContent = currentChan.name;
  $('apxChanFreq').textContent = currentChan.freq;
  $('apxChanTone').textContent = currentChan.tone;
  $('apxChanIndexDisplay').textContent = `CH ${String(apx.chanIdx + 1).padStart(2, '0')}`;

  $('apxFlagDir').classList.toggle('active', currentChan.direct);
  $('apxFlagScan').classList.toggle('active', apx.scan);
  $('apxLedScan').classList.toggle('active', apx.scan);

  // Update knob rotations
  $('apxVolKnob').style.transform = `rotate(${apx.volAngle}deg)`;
  $('apxChanKnob').style.transform = `rotate(${apx.chanAngle}deg)`;
}

function renderIcom() {
  const disp = $('icomDisplay');
  const pwrLed = $('icomPwrLed');

  if (!icom.power) {
    disp.classList.add('off');
    pwrLed.classList.remove('active');
    $('icomFlagTx').classList.remove('active');
    $('icomFlagRx').classList.remove('active');
    return;
  }

  disp.classList.remove('off');
  pwrLed.classList.add('active');

  let freqStr = '', memStr = '', aliasStr = '';
  if (icom.mode === 'CH') {
    const preset = ICOM_PRESETS[icom.memIdx];
    freqStr = preset.freq.toFixed(3);
    memStr = preset.ch;
    aliasStr = preset.alias;
  } else {
    freqStr = icom.vfoFreq.toFixed(3);
    memStr = 'VFO';
    aliasStr = 'DIRECT';
  }

  $('icomFreqMain').textContent = freqStr;
  $('icomMemCh').textContent = memStr;
  $('icomAlias').textContent = aliasStr;

  $('icomFlagPri').classList.toggle('active', icom.pri);
  $('icomFlagScan').classList.toggle('active', icom.scan);
  $('icomFlagAnl').classList.toggle('active', icom.anl);
  $('icomFlagStep').classList.toggle('active', icom.step1Mhz);

  // Update knob rotations
  $('icomVolKnob').style.transform = `rotate(${icom.volAngle}deg)`;
  $('icomSqlKnob').style.transform = `rotate(${icom.sqlAngle}deg)`;
  $('icomDialKnob').style.transform = `rotate(${icom.dialAngle}deg)`;
}

function updateActiveRadioLabel() {
  if (displayMode === 'apx') {
    activeRadio = 'apx';
    $('activeRadioLabel').textContent = 'MOTOROLA APX 6500 (VHF-FM TACTICAL)';
  } else if (displayMode === 'icom') {
    activeRadio = 'icom';
    $('activeRadioLabel').textContent = 'ICOM IC-A120 (VHF-AM AVIATION)';
  } else {
    // Dual mode: show whichever is active
    if (activeRadio === 'apx') {
      $('activeRadioLabel').textContent = 'ACTIVE: MOTOROLA APX 6500 (CLICK ICOM TO SWAP)';
    } else {
      $('activeRadioLabel').textContent = 'ACTIVE: ICOM IC-A120 (CLICK APX TO SWAP)';
    }
  }
}

// --------------------------------------------------------------------------
// TRANSMISSION & PTT CONTROLLER
// --------------------------------------------------------------------------

function startTransmit() {
  if (transmitting) return;
  audio.ensureContext();

  // Check radio power
  if (activeRadio === 'apx' && (!apx.power || apx.vol === 0)) {
    console.warn('Cannot transmit: APX 6500 is powered off.');
    return;
  }
  if (activeRadio === 'icom' && !icom.power) {
    console.warn('Cannot transmit: IC-A120 is powered off.');
    return;
  }

  transmitting = true;

  // Visual cues
  $('micPttLever').parentElement.classList.add('transmitting');
  $('masterPttBtn').classList.add('transmitting');
  $('pttBtnText').textContent = 'TRANSMITTING...';

  if (activeRadio === 'apx') {
    $('apxLedTx').classList.add('active');
    audio.playP25Chirp();
  } else {
    $('icomFlagTx').classList.add('active');
    audio.playAmClick();
  }
}

function stopTransmit() {
  if (!transmitting) return;
  transmitting = false;

  // Visual cues
  $('micPttLever').parentElement.classList.remove('transmitting');
  $('masterPttBtn').classList.remove('transmitting');
  $('pttBtnText').textContent = 'TRANSMIT (PTT)';

  if (activeRadio === 'apx') {
    $('apxLedTx').classList.remove('active');
    audio.playP25Tail();
  } else {
    $('icomFlagTx').classList.remove('active');
    audio.playAmSquelchBurst();
  }

  // If there is message text in the input, dispatch it
  const bodyText = $('msgBody').value.trim();
  if (bodyText) {
    sendCommsMessage(bodyText);
    $('msgBody').value = '';
  }
}

async function sendCommsMessage(text) {
  const recipient = $('msgRecipient').value.trim() || 'ALL';
  let senderTag = '';
  let channelTag = '';

  if (activeRadio === 'apx') {
    const curChan = APX_ZONES[apx.zoneIdx].channels[apx.chanIdx];
    senderTag = `BASE (APX6500 [${curChan.name}])`;
    channelTag = `FM: ${curChan.name} (${curChan.freq.split(' ')[0]})`;
  } else {
    let freqVal = (icom.mode === 'CH') ? ICOM_PRESETS[icom.memIdx].freq : icom.vfoFreq;
    senderTag = `BASE (IC-A120 [${freqVal.toFixed(3)}])`;
    channelTag = `AM: ${freqVal.toFixed(3)} MHz`;
  }

  // Dispatch to backend API
  try {
    const res = await fetch('/api/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sender: senderTag, recipient, body: text })
    });
    if (!res.ok) console.warn('Message send failed:', res.status);
  } catch (err) {
    console.error('Error dispatching message:', err);
  }

  // Log locally into CAP Form 110 immediately
  addForm110Entry({
    t: Date.now() / 1000,
    channel: channelTag,
    sender: senderTag,
    recipient,
    body: text,
    outgoing: true
  });
}

// --------------------------------------------------------------------------
// CAP FORM 110 COMMUNICATIONS LOG
// --------------------------------------------------------------------------

function addForm110Entry(item) {
  commLog.unshift(item);
  const tbody = $('logBody');
  const d = new Date(item.t * 1000);
  const timeZ = d.toUTCString().slice(17, 22);

  const row = document.createElement('tr');
  row.className = item.outgoing ? 'outgoing' : 'incoming';

  row.innerHTML = `
    <td><b>${timeZ}Z</b></td>
    <td>${item.channel || 'MISSION NET'}</td>
    <td><b>${escapeHtml(item.sender)}</b></td>
    <td>${escapeHtml(item.recipient)}</td>
    <td>${escapeHtml(item.body)}</td>
  `;

  tbody.insertBefore(row, tbody.firstChild);

  // Keep max 100 rows
  while (tbody.children.length > 100) {
    tbody.removeChild(tbody.lastChild);
  }
}

function escapeHtml(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function exportCommLog() {
  if (!commLog.length) {
    alert('No communications logged yet.');
    return;
  }
  let text = "CAP FORM 110 - COMMUNICATIONS LOG\n";
  text += "CIVIL AIR PATROL V-SAR SIMULATION\n";
  text += "========================================================================================\n";
  text += "TIME (Z) | NET / FREQ       | FROM                   | TO           | TRAFFIC\n";
  text += "----------------------------------------------------------------------------------------\n";
  commLog.slice().reverse().forEach(item => {
    const timeZ = new Date(item.t * 1000).toUTCString().slice(17, 22) + "Z";
    const net = (item.channel || "MISSION NET").padEnd(16, " ");
    const from = (item.sender || "").padEnd(22, " ");
    const to = (item.recipient || "").padEnd(12, " ");
    text += `${timeZ} | ${net} | ${from} | ${to} | ${item.body}\n`;
  });
  text += "========================================================================================\n";

  const blob = new Blob([text], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `CAPF110_COMM_LOG_${new Date().toISOString().slice(0, 10)}.txt`;
  a.click();
}

// --------------------------------------------------------------------------
// INCOMING RADIO TRAFFIC & WEBSOCKET LISTENER
// --------------------------------------------------------------------------

function connectWebSocket() {
  const wsUrl = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`;
  const ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    $('status').textContent = 'live';
    $('status').className = 'status online';
  };

  ws.onclose = () => {
    $('status').textContent = 'reconnecting';
    $('status').className = 'status offline';
    setTimeout(connectWebSocket, 2500);
  };

  ws.onmessage = e => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === 'message') {
        handleIncomingRadioTraffic(msg);
      }
    } catch (err) {
      console.warn('WS message parse error:', err);
    }
  };
}

function handleIncomingRadioTraffic(msg) {
  // Determine if it was an outgoing message sent by this console
  if (msg.sender && msg.sender.startsWith('BASE (APX') || msg.sender.startsWith('BASE (IC-A')) {
    return; // Already logged locally
  }

  // Trigger radio receive effects
  if (activeRadio === 'apx' && apx.power && apx.vol > 0) {
    $('apxLedRx').classList.add('active');
    audio.playP25Chirp();
  } else if (activeRadio === 'icom' && icom.power) {
    $('icomFlagRx').classList.add('active');
    audio.playAmSquelchBurst();
  }

  // Log in Form 110 table
  addForm110Entry({
    t: msg.t || (Date.now() / 1000),
    channel: (activeRadio === 'apx' ? 'CAP VHF-FM TAC' : 'CAP VHF-AM SAR'),
    sender: msg.sender || 'UNKNOWN',
    recipient: msg.recipient || 'BASE',
    body: msg.body,
    outgoing: false
  });

  // Read message over speaker via TTS if enabled
  audio.speak(`${msg.sender} says: ${msg.body}`, () => {
    $('apxLedRx').classList.remove('active');
    $('icomFlagRx').classList.remove('active');
    if (activeRadio === 'apx') audio.playP25Tail();
    else audio.playAmSquelchBurst();
  });

  // Auto clear RX LED after 3s if TTS not active
  clearTimeout(rxActiveTimer);
  rxActiveTimer = setTimeout(() => {
    $('apxLedRx').classList.remove('active');
    $('icomFlagRx').classList.remove('active');
  }, 3000);
}

// --------------------------------------------------------------------------
// EVENT LISTENERS & OPERATING CONTROLS
// --------------------------------------------------------------------------

function setupControls() {
  // Radio Mode Selector Tabs (Header)
  document.querySelectorAll('.radio-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.radio-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      displayMode = tab.dataset.mode;
      document.body.setAttribute('data-mode', displayMode);
      updateActiveRadioLabel();
    });
  });

  // Dual mode focus swap on chassis click
  $('apxChassis').addEventListener('click', () => {
    if (displayMode === 'dual') {
      activeRadio = 'apx';
      updateActiveRadioLabel();
    }
  });
  $('icomChassis').addEventListener('click', () => {
    if (displayMode === 'dual') {
      activeRadio = 'icom';
      updateActiveRadioLabel();
    }
  });

  // --- MOTOROLA APX 6500 CONTROLS ---
  $('apxVolUp').addEventListener('click', () => {
    audio.ensureContext();
    if (apx.vol < 10) apx.vol++;
    apx.volAngle = (apx.vol - 5) * 20;
    apx.power = true;
    renderApx();
  });

  $('apxVolDown').addEventListener('click', () => {
    audio.ensureContext();
    if (apx.vol > 0) apx.vol--;
    if (apx.vol === 0) apx.power = false;
    apx.volAngle = (apx.vol - 5) * 20;
    renderApx();
  });

  $('apxChanUp').addEventListener('click', () => {
    audio.ensureContext();
    const zone = APX_ZONES[apx.zoneIdx];
    apx.chanIdx = (apx.chanIdx + 1) % zone.channels.length;
    apx.chanAngle = (apx.chanAngle + 22.5) % 360;
    renderApx();
  });

  $('apxChanDown').addEventListener('click', () => {
    audio.ensureContext();
    const zone = APX_ZONES[apx.zoneIdx];
    apx.chanIdx = (apx.chanIdx - 1 + zone.channels.length) % zone.channels.length;
    apx.chanAngle = (apx.chanAngle - 22.5 + 360) % 360;
    renderApx();
  });

  $('apxBtnHome').addEventListener('click', () => {
    audio.ensureContext();
    apx.zoneIdx = 0;
    apx.chanIdx = 2; // CC 1 (Default Command & Control)
    renderApx();
  });

  $('apxBtnZoneUp').addEventListener('click', () => {
    audio.ensureContext();
    apx.zoneIdx = (apx.zoneIdx + 1) % APX_ZONES.length;
    apx.chanIdx = 0;
    renderApx();
  });

  $('apxBtnZoneDown').addEventListener('click', () => {
    audio.ensureContext();
    apx.zoneIdx = (apx.zoneIdx - 1 + APX_ZONES.length) % APX_ZONES.length;
    apx.chanIdx = 0;
    renderApx();
  });

  $('apxBtnScan').addEventListener('click', () => {
    audio.ensureContext();
    apx.scan = !apx.scan;
    renderApx();
  });

  $('apxBtnMon').addEventListener('click', () => {
    audio.ensureContext();
    apx.mon = !apx.mon;
    if (apx.mon) {
      audio.playAmSquelchBurst();
      $('apxLedRx').classList.add('active');
    } else {
      $('apxLedRx').classList.remove('active');
    }
  });

  $('apxBtnDim').addEventListener('click', () => {
    apx.dim = !apx.dim;
    $('apxDisplay').style.filter = apx.dim ? 'brightness(0.6)' : 'brightness(1)';
  });

  // --- ICOM IC-A120 CONTROLS ---
  $('icomPwrBtn').addEventListener('click', () => {
    audio.ensureContext();
    icom.power = !icom.power;
    renderIcom();
  });

  $('icomVolUp').addEventListener('click', () => {
    audio.ensureContext();
    if (icom.vol < 10) icom.vol++;
    icom.volAngle = (icom.vol - 5) * 20;
    renderIcom();
  });
  $('icomVolDown').addEventListener('click', () => {
    audio.ensureContext();
    if (icom.vol > 0) icom.vol--;
    icom.volAngle = (icom.vol - 5) * 20;
    renderIcom();
  });

  $('icomSqlUp').addEventListener('click', () => {
    audio.ensureContext();
    if (icom.sql < 10) icom.sql++;
    icom.sqlAngle = (icom.sql - 5) * 20;
    renderIcom();
  });
  $('icomSqlDown').addEventListener('click', () => {
    audio.ensureContext();
    if (icom.sql > 0) icom.sql--;
    icom.sqlAngle = (icom.sql - 5) * 20;
    renderIcom();
  });

  $('icomDialUp').addEventListener('click', () => {
    audio.ensureContext();
    if (icom.mode === 'CH') {
      icom.memIdx = (icom.memIdx + 1) % ICOM_PRESETS.length;
    } else {
      const step = icom.step1Mhz ? 1.0 : 0.025;
      icom.vfoFreq = Math.min(136.975, Math.round((icom.vfoFreq + step) * 1000) / 1000);
    }
    icom.dialAngle = (icom.dialAngle + 15) % 360;
    renderIcom();
  });

  $('icomDialDown').addEventListener('click', () => {
    audio.ensureContext();
    if (icom.mode === 'CH') {
      icom.memIdx = (icom.memIdx - 1 + ICOM_PRESETS.length) % ICOM_PRESETS.length;
    } else {
      const step = icom.step1Mhz ? 1.0 : 0.025;
      icom.vfoFreq = Math.max(118.000, Math.round((icom.vfoFreq - step) * 1000) / 1000);
    }
    icom.dialAngle = (icom.dialAngle - 15 + 360) % 360;
    renderIcom();
  });

  $('icomDialStepBtn').addEventListener('click', () => {
    icom.step1Mhz = !icom.step1Mhz;
    $('icomDialStepBtn').textContent = icom.step1Mhz ? 'STEP: 1.0MHz' : 'STEP: 25kHz';
    renderIcom();
  });

  $('icomBtnChWx').addEventListener('click', () => {
    audio.ensureContext();
    icom.mode = (icom.mode === 'CH') ? 'VFO' : 'CH';
    renderIcom();
  });

  $('icomBtnScan').addEventListener('click', () => {
    audio.ensureContext();
    icom.scan = !icom.scan;
    renderIcom();
  });

  $('icomBtnPri').addEventListener('click', () => {
    audio.ensureContext();
    icom.pri = !icom.pri;
    renderIcom();
  });

  $('icomBtnAnl').addEventListener('click', () => {
    icom.anl = !icom.anl;
    renderIcom();
  });

  // --- PTT MECHANISM (TOUCH, MOUSE, KEYBOARD) ---
  const pttTriggerElements = [$('masterPttBtn'), $('micPttLever')];

  pttTriggerElements.forEach(el => {
    // Mouse down / Touch start
    el.addEventListener('mousedown', e => {
      if (e.button !== 0) return;
      if ($('modeLatch').checked) {
        if (transmitting) stopTransmit();
        else startTransmit();
      } else {
        startTransmit();
      }
    });

    el.addEventListener('touchstart', e => {
      e.preventDefault();
      if ($('modeLatch').checked) {
        if (transmitting) stopTransmit();
        else startTransmit();
      } else {
        startTransmit();
      }
    }, { passive: false });
  });

  // Release on mouseup / touchend if momentary
  window.addEventListener('mouseup', () => {
    if (!$('modeLatch').checked && transmitting) {
      stopTransmit();
    }
  });

  window.addEventListener('touchend', () => {
    if (!$('modeLatch').checked && transmitting) {
      stopTransmit();
    }
  });

  // Keyboard Spacebar PTT shortcut (when not in text input)
  window.addEventListener('keydown', e => {
    if (e.code === 'Space' && document.activeElement.tagName !== 'INPUT') {
      e.preventDefault();
      if (!$('modeLatch').checked && !transmitting) {
        startTransmit();
      }
    }
  });

  window.addEventListener('keyup', e => {
    if (e.code === 'Space' && document.activeElement.tagName !== 'INPUT') {
      e.preventDefault();
      if (!$('modeLatch').checked && transmitting) {
        stopTransmit();
      }
    }
  });

  // Canned Tactical Message Buttons
  document.querySelectorAll('.canned-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const msg = btn.dataset.msg;
      $('msgBody').value = msg;
      // Trigger short transmit cycle
      startTransmit();
      setTimeout(() => {
        stopTransmit();
      }, 400);
    });
  });

  // Direct Transmit Button
  $('btnSend').addEventListener('click', () => {
    const text = $('msgBody').value.trim();
    if (!text) return;
    startTransmit();
    setTimeout(() => {
      stopTransmit();
    }, 400);
  });

  $('msgBody').addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      $('btnSend').click();
    }
  });

  // Form 110 Actions
  $('btnExportLog').addEventListener('click', exportCommLog);
  $('btnClearLog').addEventListener('click', () => {
    if (confirm('Clear the Form 110 display? (Does not delete server sortie messages)')) {
      $('logBody').innerHTML = '';
      commLog.length = 0;
    }
  });

  // Audio SFX checkbox
  $('chkAudioSfx').addEventListener('change', e => {
    audio.enabled = e.target.checked;
  });
}

// --------------------------------------------------------------------------
// INITIALIZATION
// --------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  const urlParams = new URLSearchParams(window.location.search);
  const qMode = urlParams.get('mode');
  if (qMode && ['apx', 'icom', 'dual'].includes(qMode)) {
    displayMode = qMode;
    document.querySelectorAll('.radio-tab').forEach(t => {
      t.classList.toggle('active', t.dataset.mode === displayMode);
    });
  }
  document.body.setAttribute('data-mode', displayMode);
  setupControls();
  renderApx();
  renderIcom();
  updateActiveRadioLabel();
  connectWebSocket();

  // Zulu Clock
  setInterval(() => {
    $('clock').textContent = new Date().toUTCString().slice(17, 25) + 'Z';
  }, 1000);

  // Pre-load recent messages from server
  fetch('/api/messages')
    .then(r => r.json())
    .then(msgs => {
      msgs.forEach(m => {
        addForm110Entry({
          t: m.t,
          channel: 'MISSION NET',
          sender: m.sender,
          recipient: m.recipient,
          body: m.body,
          outgoing: (m.sender && (m.sender.startsWith('BASE') || m.sender.startsWith('MISSION BASE')))
        });
      });
    })
    .catch(err => console.warn('Could not fetch existing messages:', err));
});
