const $ = id => document.getElementById(id);
const AudioCtx = window.AudioContext || window.webkitAudioContext;
const state = {
  model: 'apx4500', online: false, joining: false, tuning: false, tx: false,
  held: new Set(), request: 0, epoch: 0, generation: 0, ws: null, context: null,
  stream: null, source: null, capture: null, playback: null, gain: null,
  started: 0, lastPong: 0, lastRx: 0, channels: [], config: null, timeout: null,
  wantOnline: false, reconnectTimer: null, reconnectAttempt: 0,
  txStarted: 0, txReceiver: 'main', lastLogged: null, rxLogTimer: null,
  toneTimer: null, monitor: false,
};
const airband = {
  online: false, joining: false, tuning: false, epoch: 0, ws: null,
  playback: null, gain: null, lastPong: 0, lastRx: 0,
  timeout: null, lastLogged: null, rxLogTimer: null, retryTimer: null,
  toneTimer: null, monitor: false,
};

// BEGIN F-10 PURE RADIO MIX
function radioMixLevels(mainPercent, airbandPercent) {
  const level = value => Math.max(0, Math.min(100, Number(value))) / 100;
  return {main: level(mainPercent), airband: level(airbandPercent)};
}

// Should this rx event be dropped because the radio it arrived on is keyed?
// The console-wide tx flag was used here once, which silently discarded every
// airband rx - and therefore every airband CAP Form 110 log entry - whenever
// the operator keyed the tactical net.
function rxIsSuppressed(tx, txReceiver, receiver) {
  return Boolean(tx) && txReceiver === receiver;
}

// A failure on the secondary receiver must not tear down the primary.
function failureScope(receiver) {
  return receiver === 'airband' ? 'airband' : 'console';
}

// Both radios pick from the same mission nets, so they can collide. Returns
// which radio must move and where, or null when the selection is already
// legal. The radio the operator just touched is the one that stays put.
function distinctNetResolution(mainId, airbandId, channelIds, changed) {
  if (!mainId || mainId !== airbandId) return null;
  const free = channelIds.find(id => id !== mainId) ?? channelIds[0] ?? '';
  return changed === 'main' ? {radio: 'airband', net: free}
                            : {radio: 'main', net: free};
}
// END F-10 PURE RADIO MIX

// BEGIN F-11 PURE SIDETONE PLAN
// The selected transmitter is latched when PTT starts. Tone selection is a
// per-radio decision: the tactical radio is P25; the airband radio is VHF-AM.
function transmitTonePlan(receiver, transition) {
  const airband = receiver === 'airband';
  if(transition === 'grant') return airband
    ? {tone:'am-click', speechDelayMs:15}
    : {tone:'p25-chirp', speechDelayMs:115};
  return airband
    ? {tone:'am-squelch-burst', speechDelayMs:0}
    : {tone:'p25-tail', speechDelayMs:0};
}
function transmitGrantSequence(receiver) {
  const plan = transmitTonePlan(receiver, 'grant');
  return [
    {action:'tone', tone:plan.tone, atMs:0},
    {action:'speech', atMs:plan.speechDelayMs},
  ];
}
// END F-11 PURE SIDETONE PLAN

// BEGIN F-12 PURE MONITOR POLICY
// This is a training threshold rather than a hardware calibration. MON bypasses
// it for one receiver only; it never changes the other radio's squelch state.
const SQUELCH_RMS_THRESHOLD = .012;
function monitorStatesAfterToggle(current, receiver) {
  return {
    main:receiver==='main'?!current.main:current.main,
    airband:receiver==='airband'?!current.airband:current.airband,
  };
}
function squelchPasses(monitorOpen, rms, threshold=SQUELCH_RMS_THRESHOLD) {
  return Boolean(monitorOpen)||Number(rms)>=threshold;
}
function controlHeadMonitorHit(model) {
  // The EFJ artwork labels this exact 94x50 key MON. The APX faceplate has no
  // MON-labelled control, so do not invent a hit region on an unrelated key.
  return model==='efj5300' ? ['Monitor / open squelch',489,32,94,50,'mon'] : null;
}
// END F-12 PURE MONITOR POLICY
const models = {
  apx4500: {className:'apx', title:'Motorola APX 4500 O2 control head', caption:'APX 4500 / O2 CONTROL HEAD',
    hits:[['Power / connect or disconnect',87,48,58,58,'power'],['Previous net',558,65,50,55,'prev'],
      ['Next net',558,127,50,55,'next'],['Home net',561,260,44,44,'home'],
      ['Choose mission net',199,244,76,52,'net'],['Next net',283,244,76,52,'next'],
      ['Adjust headset volume',367,244,76,52,'volume'],['Home net',451,244,76,52,'home'],
      ['Headset volume knob: arrow keys or wheel',783,193,110,110,'knob'],
      ...[controlHeadMonitorHit('apx4500')].filter(Boolean)]},
  efj5300: {className:'efj',title:'EFJohnson 5300 mobile/base control head',caption:'EFJOHNSON 5300 / MOBILE-BASE CONTROL HEAD',
    hits:[['Choose mission net',180,32,94,50,'net'],['Home net',592,32,94,50,'home'],
      controlHeadMonitorHit('efj5300'),
      ['Power / connect or disconnect',284,216,84,84,'power'],
      ['Next net: arrow keys or wheel',569,216,84,84,'channel']]},
};
function notice(message='') { $('notice').textContent=message; $('notice').hidden=!message; }

/* --------------------------------------------------------------------- F-9
   CAP Form 110 communications log.

   This lived only on /radio-legacy, so the console the MRO is actually meant
   to use could not produce the one document the role exists to produce. On a
   voice net the log records transmissions - who keyed, on which net, when -
   and the operator writes in what was passed, which is how a real Form 110 is
   kept. Nothing is sent to the console; the entries live in the page and are
   autosaved to sessionStorage (F2-4), so a reload, a back-swipe or iOS
   evicting the tab does not take a multi-hour log with it.  */

// BEGIN F2-4 PURE FORM 110 STORE
const COMMLOG_KEY = 'capvsar.form110.v1';
const LOG_LIMIT = 500;

function serializeCommLog(log, limit = LOG_LIMIT) {
  return JSON.stringify({v: 1, entries: log.slice(0, limit)});
}

// Anything unreadable restores as an empty log rather than throwing: this runs
// at page load, before the radio is usable. Entries are re-built field by
// field so nothing stored can introduce a shape the renderer does not expect.
function restoreCommLog(raw, limit = LOG_LIMIT) {
  let parsed;
  try { parsed = JSON.parse(raw); } catch (e) { return []; }
  const rows = parsed && parsed.v === 1 && Array.isArray(parsed.entries) ? parsed.entries : [];
  const text = (v, fallback) => (typeof v === 'string' ? v : fallback);
  return rows.filter(r => r && typeof r === 'object' && Number.isFinite(r.t)).slice(0, limit).map(r => ({
    id: text(r.id, `e${Math.round(r.t * 1000).toString(36)}`),
    t: r.t, from: text(r.from, ''), to: text(r.to, 'ALL'), traffic: text(r.traffic, ''),
    outgoing: r.outgoing === true, net: text(r.net, 'MISSION NET'),
    seconds: Number.isFinite(r.seconds) ? r.seconds : null,
  }));
}

function saveCommLog(storage, log) {
  try { storage.setItem(COMMLOG_KEY, serializeCommLog(log)); return true; }
  catch (e) { return false; }   // private window, quota, or storage blocked
}

function loadCommLog(storage) {
  try { return restoreCommLog(storage.getItem(COMMLOG_KEY)); }
  catch (e) { return []; }
}
// END F2-4 PURE FORM 110 STORE

// BEGIN F2-3 PURE FORM 110 VIEW
// The table used to be torn down and rebuilt on every transmission, which
// threw the MRO out of the traffic cell they were typing in whenever anyone on
// the net keyed. A new entry is now inserted as one row, and a full rebuild
// refuses to run while a traffic cell has focus. `doc` is the document (passed
// in so this can be exercised without a browser).
function form110Row(doc, entry, onEdit) {
  const when = new Date(entry.t * 1000);
  const row = doc.createElement('tr');
  row.className = entry.outgoing ? 'tx' : 'rx';
  const cells = [
    ['mono', when.toISOString().slice(0, 10)],
    ['mono dir', when.toISOString().slice(11, 19) + 'Z'],
    ['net', entry.net],
    ['', entry.from + (entry.seconds ? ` (${entry.seconds.toFixed(0)}s)` : '')],
    ['', entry.to],
  ];
  for (const [cls, text] of cells) {
    const td = doc.createElement('td');
    if (cls) td.className = cls;
    td.textContent = text;          // textContent, never innerHTML (F-6)
    row.appendChild(td);
  }
  const traffic = doc.createElement('td');
  traffic.className = 'traffic';
  traffic.contentEditable = 'true';
  traffic.spellcheck = false;
  traffic.textContent = entry.traffic;
  traffic.addEventListener('input', () => {
    entry.traffic = traffic.textContent.trim();
    if (onEdit) onEdit(entry);
  });
  row.appendChild(traffic);
  return row;
}

function form110Empty(doc) {
  const row = doc.createElement('tr');
  row.className = 'commlog-empty';
  const td = doc.createElement('td');
  td.colSpan = 6;
  td.textContent = 'No traffic logged yet.';
  row.appendChild(td);
  return row;
}

// Newest first, so a new entry goes on top. Returns the row it added.
function form110Insert(doc, body, entry, onEdit, limit = LOG_LIMIT) {
  const first = body.firstChild;
  if (first && first.className === 'commlog-empty') body.removeChild(first);
  const row = form110Row(doc, entry, onEdit);
  body.insertBefore(row, body.firstChild);
  while (body.children.length > limit) body.removeChild(body.lastChild);
  return row;
}

// Returns false (and touches nothing) when the operator is typing in a cell.
function form110Rebuild(doc, body, log, onEdit) {
  const active = doc.activeElement;
  if (active && active.className === 'traffic' && body.contains(active)) return false;
  body.textContent = '';
  if (!log.length) { body.appendChild(form110Empty(doc)); return true; }
  for (const entry of log) body.appendChild(form110Row(doc, entry, onEdit));
  return true;
}
// END F2-3 PURE FORM 110 VIEW

const commLog = loadCommLog(sessionStorageOrNull());

function sessionStorageOrNull() {
  try { return window.sessionStorage; } catch (e) { return null; }   // blocked storage throws on access
}
function persistCommLog() {
  const storage = sessionStorageOrNull();
  if (storage) saveCommLog(storage, commLog);
}

function logEntry({from, to = 'ALL', net, outgoing = false, seconds = null, traffic = ''}) {
  const entry = {
    id: `e${Date.now().toString(36)}${commLog.length}`,
    t: Date.now() / 1000, from, to, traffic, outgoing,
    net: net || channel()?.name || $('netSelect').value || 'MISSION NET',
    seconds,
  };
  commLog.unshift(entry);
  if (commLog.length > LOG_LIMIT) commLog.length = LOG_LIMIT;
  const body = $('commLogBody');
  if (body) form110Insert(document, body, entry, persistCommLog, LOG_LIMIT);
  persistCommLog();
  return entry;
}

function renderLog() {
  const body = $('commLogBody');
  if (body) form110Rebuild(document, body, commLog, persistCommLog);
}

function pad(value, width) {
  // The legacy export used padEnd alone, which does not truncate - one long
  // callsign pushed every column after it out of line for the rest of the
  // page. Truncate first, then pad.
  const text = String(value ?? '');
  return (text.length > width ? text.slice(0, width - 1) + '\u2026' : text).padEnd(width, ' ');
}

function exportLog() {
  if (!commLog.length) { notice('No traffic logged yet.'); return; }
  const station = ($('callsign').value || 'MISSION BASE').trim();
  const rows = commLog.slice().reverse();
  const opened = new Date(rows[0].t * 1000);
  const lines = [
    'CAP FORM 110 - COMMUNICATIONS LOG',
    'CIVIL AIR PATROL V-SAR EXERCISE TRAFFIC - NOT AN ACTUAL MISSION RECORD',
    `STATION: ${station}`,
    `OPENED:  ${opened.toISOString().slice(0, 10)} ${opened.toISOString().slice(11, 19)}Z`,
    `PRINTED: ${new Date().toISOString().slice(0, 19).replace('T', ' ')}Z`,
    ''.padEnd(104, '='),
    // The date column the legacy export never had: a sortie that runs through
    // 0000Z produced a log that appeared to go backwards in time.
    `${pad('DATE', 11)}| ${pad('TIME(Z)', 9)}| ${pad('NET', 16)}| ${pad('FROM', 22)}| ${pad('TO', 12)}| TRAFFIC`,
    ''.padEnd(104, '-'),
  ];
  for (const entry of rows) {
    const iso = new Date(entry.t * 1000).toISOString();
    const from = entry.from + (entry.seconds ? ` (${entry.seconds.toFixed(0)}s)` : '');
    lines.push(`${pad(iso.slice(0, 10), 11)}| ${pad(iso.slice(11, 19), 9)}| ` +
               `${pad(entry.net, 16)}| ${pad(from, 22)}| ${pad(entry.to, 12)}| ${entry.traffic || ''}`);
  }
  lines.push(''.padEnd(104, '='), `${rows.length} entries.`);

  const blob = new Blob([lines.join('\n') + '\n'], {type: 'text/plain'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `CAPF110_${station.replace(/[^A-Za-z0-9]+/g, '_')}_${new Date().toISOString().slice(0, 10)}.txt`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // The legacy export never revoked it, so every export leaked its blob for
  // the life of the page.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
function channel() { return state.channels.find(c=>c.id===$('netSelect').value); }
function airbandChannel() { return state.channels.find(c=>c.id===$('airbandNet')?.value); }
function activeReceiver() { return $('txAirband')?.checked ? 'airband' : 'main'; }
function sendRadio(receiver,data) {
  const socket=receiver==='airband'?airband.ws:state.ws;
  if(socket?.readyState===WebSocket.OPEN) { socket.send(JSON.stringify(data)); return true; }
  return false;
}
function send(data) {
  return sendRadio('main',data);
}
function render() {
  const chosen=activeReceiver(), chosenState=chosen==='airband'?airband:state;
  const ready=chosenState.online && !chosenState.tuning;
  $('ptt').disabled=!ready;
  $('ptt').setAttribute('aria-pressed',String(state.tx));
  $('pttLabel').textContent=state.tx?'TRANSMITTING':state.held.size?'KEYING MIC…':'HOLD TO TALK';
  $('pttHint').textContent=state.tx?'Release to listen':ready?'Hold here or hold the spacebar':state.tuning?'Changing mission net…':'Connect your headset to begin';
  $('join').disabled=state.joining;
  $('join').textContent=state.joining?'Connecting…':state.online?'Disconnect radio':state.wantOnline?'Cancel reconnect':'Join mission net ↗';
  $('join').classList.toggle('connected',state.online);
  $('callsign').disabled=state.joining || state.online;
  $('accessCode').disabled=state.joining || state.online;
  $('microphone').disabled=state.joining;
  for (const id of ['netSelect','previousNet','nextNet']) $(id).disabled=state.joining || state.tuning;
  $('instrument').classList.toggle('off',!state.online);
  $('instrument').classList.toggle('transmitting',state.tx);
  $('signalDot').classList.toggle('online',ready);
  $('signalDot').classList.toggle('tx',state.tx);
  $('connectionState').textContent=state.tx?'Transmitting':state.tuning?'Tuning radio…':state.online?'Listening on the net':state.joining?'Connecting to mission voice…':'Radio disconnected';
  $('screenState').textContent=state.tx?'TRANSMIT':state.tuning?'TUNING':state.online?'RECEIVE':'OFFLINE';
  if(state.monitor&&state.online&&!state.tx&&!state.tuning)$('screenState').textContent='MONITOR';
  $('screenNet').textContent=channel()?.label || 'PRIMARY';
  $('screenCall').textContent=$('callsign').value || 'MISSION BASE';
  if (!state.online) { $('speaker').textContent='Join the net to listen.'; $('instrument').classList.remove('receiving'); $('rxMeter').style.width='0%'; }
  if($('airbandState')) {
    $('airbandState').textContent=airband.tuning?'Tuning…':airband.online?'Listening':'Disconnected';
    $('airbandSpeaker').textContent=airband.online?($('airbandSpeaker').textContent||'Listening for traffic.'):'Join both radios to listen.';
    $('txMain').disabled=!state.online;
    $('txAirband').disabled=!airband.online;
  }
  const monitorButton=document.querySelector('#hitRegions .hit[data-action="mon"]');
  if(monitorButton){monitorButton.setAttribute('aria-pressed',String(state.monitor));monitorButton.title=state.monitor?'Monitor open — close squelch':'Monitor / open squelch';}
}
function setModel(model) {
  releaseAll(); state.model=model; const config=models[model];
  $('modelApx').setAttribute('aria-pressed',String(model==='apx4500'));
  $('modelEfj').setAttribute('aria-pressed',String(model==='efj5300'));
  $('instrument').classList.remove('apx','efj'); $('instrument').classList.add(config.className);
  $('instrument').dataset.model=model;
  $('faceplate').src=`/static/radio-art/${model}.svg`; $('faceplate').alt=config.title;
  $('modelCaption').textContent=config.caption; $('hitRegions').replaceChildren();
  for (const [label,x,y,w,h,action] of config.hits) {
    const button=document.createElement('button'); button.type='button'; button.className='hit';
    button.dataset.action=action;
    button.setAttribute('aria-label',label); button.title=label;
    Object.assign(button.style,{left:`${x/9.6}%`,top:`${y/3.4}%`,width:`${w/9.6}%`,height:`${h/3.4}%`});
    button.addEventListener('click',()=>{
      if(action==='power') $('joinForm').requestSubmit();
      if(action==='prev') changeNet(-1);
      if(action==='next'||action==='channel') changeNet(1);
      if(action==='home') { $('netSelect').value='primary'; tune(); }
      if(action==='net') { $('netSelect').focus(); try{$('netSelect').showPicker();}catch{} }
      if(action==='volume'||action==='knob') $('volume').focus();
      if(action==='mon') toggleMonitor('main');
    });
    if(action==='knob'||action==='channel') {
      button.addEventListener('wheel',e=>{e.preventDefault(); adjust(action,e.deltaY<0?1:-1);},{passive:false});
      button.addEventListener('keydown',e=>{if(['ArrowUp','ArrowRight','ArrowDown','ArrowLeft'].includes(e.key)){e.preventDefault();adjust(action,['ArrowUp','ArrowRight'].includes(e.key)?1:-1);}});
    }
    $('hitRegions').append(button);
  }
  render();
}
function adjust(action,delta) {
  if(action==='channel') changeNet(delta);
  else { $('volume').value=String(Math.max(0,Math.min(100,Number($('volume').value)+delta*5))); updateVolume(); }
}
function changeNet(delta) {
  if(state.joining||state.tuning||!state.channels.length) return;
  const i=state.channels.findIndex(c=>c.id===$('netSelect').value);
  $('netSelect').value=state.channels[(i+delta+state.channels.length)%state.channels.length].id; tune();
}
// X-9 said one Mumble client per operator, so a desk could not appear on the
// net as two people. F-10 deliberately spends two sessions per operator, and
// both radios choose from the SAME four mission nets - airband proper is
// PilotEdge's, in X-Plane, not a channel here. Nothing else stops an operator
// putting both radios on one net, which would re-create exactly the symptom
// X-9 closed: doubled audio, the desk listed twice, and the operator's own
// transmission routed back into their headset with the mic open. This is the
// guard that keeps them apart.
function enforceDistinctNets(changed) {
  if(!state.channels.length || !$('airbandNet')) return false;
  const main=$('netSelect'), air=$('airbandNet');
  const fix=distinctNetResolution(main.value,air.value,state.channels.map(c=>c.id),changed);
  if(fix){ (fix.radio==='airband'?air:main).value=fix.net; }
  // Make the collision unreachable in the UI as well as in state.
  for(const option of main.options) option.disabled = option.value===air.value;
  for(const option of air.options) option.disabled = option.value===main.value;
  return Boolean(fix);
}
function tune() {
  if(enforceDistinctNets('main')) { notice('Airband radio moved: the two radios cannot share a net.'); tuneAirband(); }
  releaseAll(); state.playback?.port.postMessage({clear:true}); state.lastRx=0;
  $('speaker').textContent='Listening for traffic.';
  if(state.online) { state.tuning=true; send({action:'tune',channel:$('netSelect').value}); }
  render();
}
function tuneAirband() {
  if(enforceDistinctNets('airband')) { notice('Tactical radio moved: the two radios cannot share a net.'); tune(); return; }
  airband.playback?.port.postMessage({clear:true});airband.lastRx=0;
  $('airbandSpeaker').textContent='Listening for traffic.';
  if(airband.online) {
    airband.tuning=true;
    sendRadio('airband',{action:'tune',channel:$('airbandNet').value});
  }
  render();
}
function updateVolume() {
  const levels=radioMixLevels($('volume').value,$('airbandVolume')?.value??55);
  $('volumeValue').value=`${Math.round(levels.main*100)}%`;
  if($('airbandVolumeValue')) $('airbandVolumeValue').value=`${Math.round(levels.airband*100)}%`;
  if(state.gain) state.gain.gain.setTargetAtTime(levels.main,state.context.currentTime,.02);
  if(airband.gain) airband.gain.gain.setTargetAtTime(levels.airband,state.context.currentTime,.02);
}
function toggleMonitor(receiver) {
  const radioState=receiver==='airband'?airband:state;
  if(!radioState.online)return;
  const next=monitorStatesAfterToggle({main:state.monitor,airband:airband.monitor},receiver);
  state.monitor=next.main;airband.monitor=next.airband;
  const speaker=$(receiver==='airband'?'airbandSpeaker':'speaker');
  speaker.textContent=radioState.monitor?'MON open — all signal levels audible.':'Squelch restored.';
  render();
}

// F-11 ports the legacy console's Web Audio tones. Each tone connects through
// the keyed radio's own gain, so radio selection and volume remain per-radio.
function toneDestination(receiver) {
  return (receiver==='airband'?airband.gain:state.gain)||state.context.destination;
}
function playP25Chirp(receiver='main') {
  const now=state.context.currentTime, destination=toneDestination(receiver);
  let at=now;
  for(const item of [{freq:941,dur:.035},{freq:1336,dur:.035},{freq:1209,dur:.045}]) {
    const oscillator=state.context.createOscillator(), gain=state.context.createGain();
    oscillator.type='sine';oscillator.frequency.setValueAtTime(item.freq,at);
    gain.gain.setValueAtTime(.001,at);gain.gain.linearRampToValueAtTime(.18,at+.005);
    gain.gain.exponentialRampToValueAtTime(.001,at+item.dur);
    oscillator.connect(gain);gain.connect(destination);oscillator.start(at);oscillator.stop(at+item.dur);
    oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();};
    at+=item.dur;
  }
}
function playP25Tail(receiver='main') {
  const now=state.context.currentTime, oscillator=state.context.createOscillator(), gain=state.context.createGain();
  oscillator.type='sawtooth';oscillator.frequency.setValueAtTime(120,now);
  oscillator.frequency.exponentialRampToValueAtTime(40,now+.04);
  gain.gain.setValueAtTime(.2,now);gain.gain.exponentialRampToValueAtTime(.001,now+.04);
  oscillator.connect(gain);gain.connect(toneDestination(receiver));oscillator.start(now);oscillator.stop(now+.04);
  oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();};
}
function playAmClick(receiver='airband') {
  const now=state.context.currentTime, oscillator=state.context.createOscillator(), gain=state.context.createGain();
  oscillator.type='triangle';oscillator.frequency.setValueAtTime(800,now);
  oscillator.frequency.exponentialRampToValueAtTime(200,now+.015);
  gain.gain.setValueAtTime(.25,now);gain.gain.exponentialRampToValueAtTime(.001,now+.015);
  oscillator.connect(gain);gain.connect(toneDestination(receiver));oscillator.start(now);oscillator.stop(now+.015);
  oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();};
}
function playAmSquelchBurst(receiver='airband') {
  const now=state.context.currentTime, length=Math.floor(state.context.sampleRate*.09);
  const buffer=state.context.createBuffer(1,length,state.context.sampleRate), samples=buffer.getChannelData(0);
  for(let i=0;i<length;i++) samples[i]=Math.random()*2-1;
  const noise=state.context.createBufferSource(), filter=state.context.createBiquadFilter(), gain=state.context.createGain();
  noise.buffer=buffer;filter.type='bandpass';filter.frequency.setValueAtTime(1400,now);filter.Q.setValueAtTime(1.5,now);
  gain.gain.setValueAtTime(.22,now);gain.gain.exponentialRampToValueAtTime(.001,now+.09);
  noise.connect(filter);filter.connect(gain);gain.connect(toneDestination(receiver));noise.start(now);noise.stop(now+.09);
  noise.onended=()=>{noise.disconnect();filter.disconnect();gain.disconnect();};
}
function playTransmitTone(receiver, transition) {
  const tone=transmitTonePlan(receiver,transition).tone;
  if(tone==='p25-chirp')playP25Chirp(receiver);
  if(tone==='p25-tail')playP25Tail(receiver);
  if(tone==='am-click')playAmClick(receiver);
  if(tone==='am-squelch-burst')playAmSquelchBurst(receiver);
}
function silenceMic() {
  if(state.tx) $('speaker').textContent='Listening for traffic.';
  for(const radioState of [state,airband]) {clearTimeout(radioState.toneTimer);radioState.toneTimer=null;}
  state.capture?.port.postMessage({active:false});
  state.stream?.getAudioTracks().forEach(track=>{track.enabled=false;});
  state.tx=false; clearTimeout(state.timeout); state.timeout=null;
}
function releaseAll(message='') {
  // F-9: log the transmission as it ends, so the duration is real. Anything
  // under half a second is a mis-key, not traffic.
  if(state.txStarted) {
    const seconds=(Date.now()-state.txStarted)/1000;
      state.txStarted=0;
    const txChannel=state.txReceiver==='airband'?airbandChannel():channel();
    if(seconds>=0.5) logEntry({from:($('callsign').value||'MISSION BASE').trim(),
                               to:'NET', net:txChannel?.name, outgoing:true, seconds});
  }
  const wasTransmitting=state.tx, receiver=state.txReceiver;
  state.held.clear(); silenceMic();
  if(wasTransmitting)playTransmitTone(receiver,'release');
  state.request=(state.request+1)%2147483647;
  sendRadio(state.txReceiver,{action:'ptt',active:false,request:state.request});
  if(message) notice(message);
  render();
}
function press(source) {
  const chosen=activeReceiver(),chosenState=chosen==='airband'?airband:state;
  if(!chosenState.online||chosenState.tuning||state.held.has(source)) return;
  state.held.add(source);
  if(state.held.size===1) {
    state.txReceiver=activeReceiver();
    state.txStarted=Date.now();
    notice(); state.request=(state.request+1)%2147483647;
    state.context.resume().catch(()=>connectionLost('Headset audio is paused.'));
    sendRadio(state.txReceiver,{action:'ptt',active:true,request:state.request});
  }
  render();
}
function release(source) {
  state.held.delete(source); if(!state.held.size) releaseAll();
}
function soundDisconnectAlarm() {
  if(!state.context) return;
  if(state.context.state==='suspended') {
    state.context.resume().then(soundDisconnectAlarm).catch(()=>{}); return;
  }
  if(state.context.state!=='running') return;
  const oscillator=state.context.createOscillator(), alarm=state.context.createGain();
  const now=state.context.currentTime; oscillator.frequency.value=880;
  alarm.gain.setValueAtTime(0,now);
  for(let i=0;i<3;i++) {
    alarm.gain.setValueAtTime(.16,now+i*.22);
    alarm.gain.setValueAtTime(0,now+i*.22+.11);
  }
  oscillator.connect(alarm);alarm.connect(state.gain||state.context.destination);
  oscillator.start(now);oscillator.stop(now+.66);
  oscillator.onended=()=>{oscillator.disconnect();alarm.disconnect();};
}
function cancelReconnect() {
  clearTimeout(state.reconnectTimer); state.reconnectTimer=null;
}
// FE-5: a server-sent error used to call disconnect(), which clears
// wantOnline, so the radio never came back. F-4's auto-rejoin therefore only
// covered a socket that died silently (a Wi-Fi blip, a console restart) - the
// commonest real failure, a Mumble container restart, arrives as an `error`
// frame and put every browser radio in the exercise permanently dark until
// each operator noticed and re-joined by hand.
//
// Only a few errors are worth giving up on: the ones that will fail again
// identically until a human changes something. Everything else - the voice
// server bouncing, a watchdog fault, congestion - is exactly what a retry is
// for. Matched on substrings because these strings are the server's own
// (radio.py), and are the operator-facing text as well.
const FATAL_ERRORS = ['access code', 'log in first', 'occupied',
                      'not configured', 'callsign of'];

function isFatalError(message) {
  const m = (message||'').toLowerCase();
  return FATAL_ERRORS.some(f => m.includes(f));
}

function handleServerError(message) {
  const text = message || 'Voice connection unavailable.';
  if(isFatalError(text)) {
    disconnect();               // needs a human; stop trying
    notice(text);
    return;
  }
  // wantOnline stays set, so this takes the same path as a socket that died
  // on its own: release PTT, drop the connection, back off, retry.
  connectionLost(text);
}

function scheduleReconnect(message) {
  if(!state.wantOnline||state.reconnectTimer) return;
  const delay=Math.min(30000,1000*2**Math.min(state.reconnectAttempt,5));
  state.reconnectAttempt+=1;
  notice(`${message} Retrying in ${Math.ceil(delay/1000)} seconds.`);
  soundDisconnectAlarm();
  state.reconnectTimer=setTimeout(()=>{state.reconnectTimer=null;connect(true);},delay);
  render();
}
function airbandLost(message) {
  // The airband radio is a SECONDARY receiver. Tearing the console down when
  // it fails meant a refused airband join - which happens to operator nine,
  // because F-10 spends two of the server's sixteen sessions per desk - took
  // that operator's working tactical net with it, and cleared wantOnline so
  // nothing reconnected. Only this receiver stops.
  const socket=airband.ws;airband.ws=null;socket?.close();
  airband.online=false;airband.joining=false;airband.tuning=false;
  clearTimeout(airband.rxLogTimer);airband.rxLogTimer=null;airband.lastLogged=null;
  clearTimeout(airband.retryTimer);airband.retryTimer=null;
  if(state.tx&&state.txReceiver==='airband'){releaseAll();state.txReceiver='main';}
  $('airbandSpeaker').textContent='Airband radio offline.';
  if(message)notice(message);
  // Retry independently, so a transient hiccup on the secondary receiver
  // recovers without disturbing the primary.
  if(state.wantOnline&&state.online){
    const generation=state.generation;
    airband.retryTimer=setTimeout(()=>{airband.retryTimer=null;openAirbandSocket(generation);},5000);
  }
  render();
}
function connectionLost(message) {
  if(!state.wantOnline) return;
  ++state.generation; releaseAll();
  state.online=false;state.joining=false;state.tuning=false;
  const socket=state.ws;state.ws=null;socket?.close();
  const airSocket=airband.ws;airband.ws=null;airSocket?.close();
  airband.online=false;airband.joining=false;airband.tuning=false;
  state.stream?.getAudioTracks().forEach(track=>{track.enabled=false;});
  scheduleReconnect(message);
}
async function audioContext() {
  if(state.context && state.context.state!=='closed') { await state.context.resume(); return; }
  if(!AudioCtx) throw new Error('This browser does not support headset audio. Use a current Safari, Chrome, Firefox or Edge.');
  try { state.context=new AudioCtx({sampleRate:48000,latencyHint:'interactive'}); }
  catch { state.context=new AudioCtx({latencyHint:'interactive'}); }
  const context=state.context;
  state.context.addEventListener('statechange',()=>{
    if(state.context===context && context.state==='suspended' && state.wantOnline) {
      context.resume().catch(()=>connectionLost('Headset audio paused.'));
    }
  });
  await state.context.resume();
  state.gain=state.context.createGain(); updateVolume(); state.gain.connect(state.context.destination);
  if(typeof state.context.setSinkId==='function' && $('output').value) await state.context.setSinkId($('output').value);
}
async function devices() {
  if(!navigator.mediaDevices?.enumerateDevices) return;
  const items=await navigator.mediaDevices.enumerateDevices();
  for(const [id,kind] of [['microphone','audioinput'],['output','audiooutput']]) {
    const select=$(id), previous=select.value;
    select.replaceChildren(new Option(id==='microphone'?'System default / Bluetooth headset':'System audio output',''));
    items.filter(item=>item.kind===kind && item.deviceId && item.deviceId!=='default').forEach((item,i)=>select.add(new Option(item.label || `${kind==='audioinput'?'Microphone':'Output'} ${i+1}`,item.deviceId)));
    if([...select.options].some(o=>o.value===previous)) select.value=previous;
  }
  const routing=AudioCtx && typeof AudioCtx.prototype.setSinkId==='function';
  $('output').disabled=!routing;
  $('outputHelp').textContent=routing?'Select your headset here, or use the system default.':'This browser uses the device’s selected audio output. Choose your Bluetooth headset in system settings.';
}
function openAirbandSocket(generation) {
  if(generation!==state.generation||!state.wantOnline||airband.joining||airband.online)return;
  airband.joining=true;render();
  const socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/radio/stream`);
  airband.ws=socket;socket.binaryType='arraybuffer';airband.lastPong=Date.now();
  socket.addEventListener('open',()=>{
    if(generation!==state.generation){socket.close();return;}
    sendRadio('airband',{action:'join',callsign:$('callsign').value.trim(),
      accessCode:$('accessCode').value,channel:$('airbandNet').value,receiver:'airband'});
  });
  socket.addEventListener('message',event=>{if(airband.ws===socket)receive(event.data,'airband');});
  socket.addEventListener('close',()=>{if(airband.ws===socket)airbandLost('Airband radio disconnected.');});
  socket.addEventListener('error',()=>{if(airband.ws===socket)airbandLost('Could not reach the airband radio.');});
  airband.timeout=setTimeout(()=>{if(airband.joining&&airband.ws===socket)airbandLost('The airband connection timed out.');},15000);  // F2-2: this radio only
}
async function connect(automatic=false) {
  if(state.joining) return;
  if(!state.config?.configured) { notice('Mission voice has not been configured on this server.'); return; }
  if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia) { $('secureHelp').hidden=false; return; }
  if(!$('joinForm').reportValidity()) return;
  state.wantOnline=true;cancelReconnect();
  notice(automatic?'Reconnecting to mission voice…':'');
  state.joining=true; const generation=++state.generation; render();
  try {
    await audioContext();
    // Load in the user-initiated audio context before connecting to the mission net.
    if(!state.capture) {
      await state.context.audioWorklet.addModule('/static/radio-worklet.js');
      state.capture=new AudioWorkletNode(state.context,'radio-capture');
      state.playback=new AudioWorkletNode(state.context,'radio-playback');
      airband.playback=new AudioWorkletNode(state.context,'radio-playback');
      airband.gain=state.context.createGain();
      state.capture.connect(state.context.destination); // Worklet always outputs silence.
      state.playback.connect(state.gain);
      airband.playback.connect(airband.gain);airband.gain.connect(state.context.destination);
      updateVolume();
      state.capture.port.onmessage=({data})=>{
        const socket=state.txReceiver==='airband'?airband.ws:state.ws;
        if(!state.tx||!state.held.size||socket?.readyState!==WebSocket.OPEN) return;
        if(socket.bufferedAmount>1920*5) {releaseAll('Voice connection is delayed. Release PTT and try again.');return;}
        socket.send(data);
      };
    }
    const microphone=$('microphone').value;
    const stream=state.stream || await navigator.mediaDevices.getUserMedia({audio:{deviceId:microphone?{exact:microphone}:undefined,channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
    if(generation!==state.generation) {stream.getTracks().forEach(t=>t.stop());return;}
    if(!state.stream) {
      state.stream=stream; stream.getAudioTracks().forEach(track=>{
        track.enabled=false;
        track.addEventListener('ended',()=>{if(state.stream===stream){disconnect();notice('Microphone disconnected. Check your headset, then rejoin.');}});
        track.addEventListener('mute',()=>{if(state.tx)releaseAll('Microphone interrupted. Release PTT and check your headset.');});
      });
      state.source=state.context.createMediaStreamSource(stream); state.source.connect(state.capture);
    }
    await devices();
    if(generation!==state.generation) return;
    const socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/radio/stream`);
    state.ws=socket; socket.binaryType='arraybuffer'; state.lastPong=Date.now();
    socket.addEventListener('open',()=>{
      if(generation!==state.generation){socket.close();return;}
      send({action:'join',callsign:$('callsign').value.trim(),accessCode:$('accessCode').value,channel:$('netSelect').value,receiver:'main'});
    });
    socket.addEventListener('message',event=>{if(state.ws===socket) receive(event.data);});
    socket.addEventListener('close',()=>{if(state.ws===socket)connectionLost('Radio disconnected.');});
    socket.addEventListener('error',()=>{if(state.ws===socket)connectionLost('Could not reach mission voice.');});
    state.timeout=setTimeout(()=>{if(state.joining&&state.ws===socket)connectionLost('The mission voice connection timed out.');},15000);
  } catch(error) {
    if(generation!==state.generation) return;
    const message=error.name==='NotAllowedError'?'Microphone permission is needed. Allow this site to use your headset, then join again.':error.name==='NotFoundError'?'No microphone was found. Pair or connect your headset, then retry.':error.name==='NotReadableError'?'The microphone is in use or unavailable. Check headset settings and try again.':error.message||'Headset setup failed. Please try again.';
    if(['NotAllowedError','NotFoundError','NotReadableError'].includes(error.name)) {disconnect();notice(message);}
    else connectionLost(message);
  }
}
function disconnect() {
  state.wantOnline=false;state.reconnectAttempt=0;cancelReconnect();
  ++state.generation; releaseAll();
  state.online=false; state.joining=false; state.tuning=false;
  const socket=state.ws; state.ws=null; socket?.close();
  const airSocket=airband.ws;airband.ws=null;airSocket?.close();
  airband.online=false;airband.joining=false;airband.tuning=false;
  clearTimeout(airband.timeout);airband.timeout=null;
  clearTimeout(airband.retryTimer);airband.retryTimer=null;
  state.stream?.getTracks().forEach(track=>track.stop()); state.stream=null;
  state.source?.disconnect(); state.source=null;
  state.capture?.disconnect(); state.playback?.disconnect();airband.playback?.disconnect();
  state.capture=null; state.playback=null;
  state.gain?.disconnect();airband.gain?.disconnect();state.gain=null;airband.gain=null;airband.playback=null;
  if(state.context) { const old=state.context; state.context=null; old.close().catch(()=>{}); }
  render();
}
function receive(data,receiver='main') {
  const radioState=receiver==='airband'?airband:state;
  if(data instanceof ArrayBuffer) {
    if(!radioState.online||radioState.tuning||data.byteLength<10||data.byteLength%2) return;
    const header=new DataView(data), epoch=header.getUint32(0,true), speaker=header.getUint32(4,true);
    if(epoch!==radioState.epoch) return;
    let energy=0; for(let i=8;i<data.byteLength;i+=2){const sample=header.getInt16(i,true)/32768;energy+=sample*sample;}
    const rms=Math.sqrt(energy/((data.byteLength-8)/2));
    radioState.lastRx=Date.now();
    if(!squelchPasses(radioState.monitor,rms)) {
      if(receiver==='main'){$('rxMeter').style.width=`${Math.min(100,rms*260)}%`;$('instrument').classList.remove('receiving');}
      return;
    }
    const pcm=data.slice(8);radioState.playback.port.postMessage({speaker,pcm},[pcm]);
    if(receiver==='main') {
      $('rxMeter').style.width=`${Math.min(100,rms*260)}%`;
      $('instrument').classList.add('receiving');
    }
    return;
  }
  let message; try{message=JSON.parse(data);}catch{  // F2-11: the old handler cleared wantOnline, so FE-5 never retried
    const text='Invalid response from the voice server.';
    if(failureScope(receiver)==='airband')airbandLost(text);else connectionLost(text);
    return;
  }
  if(message.type==='tuned') {
    clearTimeout(radioState.timeout);radioState.timeout=null;
    radioState.online=true;radioState.joining=false;radioState.tuning=false;radioState.epoch=message.epoch;
    radioState.playback.port.postMessage({clear:true});radioState.lastPong=Date.now();
    if(receiver==='main') {
      cancelReconnect();state.reconnectAttempt=0;silenceMic();state.held.clear();
      $('netSelect').value=message.channel;$('speaker').textContent='Listening for traffic.';
      notice();openAirbandSocket(state.generation);
    } else {
      $('airbandNet').value=message.channel;$('airbandSpeaker').textContent='Listening for traffic.';
    }
    render();
  } else if(message.type==='ptt') {
    if(message.active) {
      if(!state.held.size||message.request!==state.request||receiver!==state.txReceiver||!radioState.online||radioState.tuning){sendRadio(receiver,{action:'ptt',active:false,request:state.request});return;}
      state.tx=true;state.started=Date.now();radioState.playback.port.postMessage({clear:true});
      const plan=transmitTonePlan(receiver,'grant');playTransmitTone(receiver,'grant');
      clearTimeout(radioState.toneTimer);
      radioState.toneTimer=setTimeout(()=>{
        radioState.toneTimer=null;
        if(!state.tx||!state.held.size||state.txReceiver!==receiver||message.request!==state.request)return;
        state.stream?.getAudioTracks().forEach(track=>{track.enabled=true;});
        state.capture.port.postMessage({active:true});
      },plan.speechDelayMs);
      clearTimeout(state.timeout);state.timeout=setTimeout(()=>releaseAll('60-second transmit limit reached. Release PTT before speaking again.'),60000);
    } else if(message.request===state.request) {
      const wasTransmitting=state.tx, owner=state.txReceiver;
      silenceMic();state.held.clear();if(wasTransmitting)playTransmitTone(owner,'release');
      if(message.reason)notice(message.reason);
    }
    render();
  } else if(message.type==='rx' && !rxIsSuppressed(state.tx,state.txReceiver,receiver)) {
    // The gate is per-RADIO. Using the console-wide tx flag here meant that
    // keying the tactical net silently discarded every airband rx event: the
    // audio still played, but the speaker label never updated and the
    // transmission was never written to the CAP Form 110 log.
    $(receiver==='airband'?'airbandSpeaker':'speaker').textContent=`${message.speaker} transmitting`;
    // F-9: one entry per station per transmission, not one per packet.
    const lastLogged=receiver==='airband'?airband.lastLogged:state.lastLogged;
    if(message.speaker && message.speaker!==lastLogged) {
      if(receiver==='airband')airband.lastLogged=message.speaker;
      else state.lastLogged=message.speaker;
      logEntry({from:message.speaker,to:($('callsign').value||'MISSION BASE').trim(),
                net:message.net||(receiver==='airband'?airbandChannel():channel())?.name});
    }
    const oldTimer=receiver==='airband'?airband.rxLogTimer:state.rxLogTimer;clearTimeout(oldTimer);
    const timer=setTimeout(()=>{if(receiver==='airband')airband.lastLogged=null;else state.lastLogged=null;},3000);
    if(receiver==='airband')airband.rxLogTimer=timer;else state.rxLogTimer=timer;
  } else if(message.type==='pong') radioState.lastPong=Date.now();
  else if(message.type==='error'){
    if(failureScope(receiver)!=='airband')handleServerError(message.message);  // FE-5: only errors a human must fix stop the radio
    else airbandLost(message.message||'Airband radio unavailable.');
  }
}

$('logExport')?.addEventListener('click',exportLog);
$('logClear')?.addEventListener('click',()=>{
  if(!commLog.length||confirm('Clear the communications log? Export it first if you need the record.')) {
    commLog.length=0; persistCommLog(); renderLog();
  }
});
$('logAdd')?.addEventListener('click',()=>{
  // A Form 110 records traffic the operator heard on the radio too, not only
  // what passed through this console.
  const entry=logEntry({from:($('callsign').value||'MISSION BASE').trim(), to:'NET'});
  const row=$('commLogBody').querySelector('tr');
  row?.querySelector('.traffic')?.focus();
  return entry;
});
renderLog();

$('joinForm').addEventListener('submit',event=>{event.preventDefault();if(state.wantOnline)disconnect();else connect();});
$('modelApx').addEventListener('click',()=>setModel('apx4500'));
$('modelEfj').addEventListener('click',()=>setModel('efj5300'));
$('callsign').addEventListener('input',render);
$('previousNet').addEventListener('click',()=>changeNet(-1));$('nextNet').addEventListener('click',()=>changeNet(1));
$('netSelect').addEventListener('change',tune);$('volume').addEventListener('input',updateVolume);
$('microphone').addEventListener('change',async()=>{if(state.online){disconnect();await connect();}});
$('output').addEventListener('change',async()=>{try{if(state.context?.setSinkId)await state.context.setSinkId($('output').value);}catch{notice('Could not select that output. Choose the headset in your device’s audio settings.');}});
$('soundTest').addEventListener('click',async()=>{
  try {
    await audioContext();await devices();
    const oscillator=state.context.createOscillator(), gain=state.context.createGain(), now=state.context.currentTime;
    oscillator.frequency.value=660;gain.gain.setValueAtTime(0,now);gain.gain.linearRampToValueAtTime(.08,now+.02);gain.gain.linearRampToValueAtTime(0,now+.3);
    oscillator.connect(gain);gain.connect(state.gain);oscillator.start();oscillator.stop(now+.31);
    oscillator.onended=()=>{oscillator.disconnect();gain.disconnect();};
  }catch(error){notice(error.message||'Unable to play the headset test.');}
});
$('ptt').addEventListener('pointerdown',event=>{
  if(event.button!==0||!event.isPrimary)return;event.preventDefault();$('ptt').setPointerCapture(event.pointerId);press(`pointer-${event.pointerId}`);
});
for(const type of ['pointerup','pointercancel','lostpointercapture']) $('ptt').addEventListener(type,event=>{event.preventDefault();release(`pointer-${event.pointerId}`);});
$('ptt').addEventListener('contextmenu',event=>event.preventDefault());
window.addEventListener('keydown',event=>{
  if(event.code!=='Space'||event.altKey||event.ctrlKey||event.metaKey)return;
  const editing=event.target.closest?.('input,textarea,select,[contenteditable]:not([contenteditable="false"]),a,button:not(#ptt)');
  if(editing)return;event.preventDefault();if(!event.repeat)press('keyboard');
});
window.addEventListener('keyup',event=>{if(event.code==='Space'&&state.held.has('keyboard')){event.preventDefault();release('keyboard');}});
window.addEventListener('blur',()=>releaseAll());
document.addEventListener('visibilitychange',()=>{if(document.hidden)releaseAll();});
// Release PTT, but do not disconnect(): that clears wantOnline, so a page the
// browser restores from its back/forward cache (iOS Safari backgrounding) would
// come back dark with no retry. The watchdog notices the dead sockets instead.
window.addEventListener('pagehide',()=>releaseAll());
navigator.mediaDevices?.addEventListener('devicechange',()=>devices().catch(()=>{}));
setInterval(()=>{
  $('clock').textContent=new Date().toISOString().slice(11,19)+' Z';
  if(state.online) {
    if(Date.now()-state.lastPong>6000){connectionLost('Mission voice stopped responding.');return;}
    if(airband.online&&Date.now()-airband.lastPong>6000)airbandLost('Airband radio stopped responding.');  // F2-2: this radio only
    send({action:'ping'});if(airband.online)sendRadio('airband',{action:'ping'});
    if(state.tx)sendRadio(state.txReceiver,{action:'keepalive'});
    if(state.tx)$('pttHint').textContent=`${Math.floor((Date.now()-state.started)/1000)}s / 60s · release to listen`;
    if(Date.now()-state.lastRx>400){$('rxMeter').style.width='0%';$('instrument').classList.remove('receiving');$('speaker').textContent=state.tx?'Microphone open — transmitting.':'Listening for traffic.';}
    if(airband.online&&Date.now()-airband.lastRx>400)$('airbandSpeaker').textContent='Listening for traffic.';
  }
},500);

function installAirbandPanel() {
  const panel=document.createElement('section');panel.id='airbandPanel';
  panel.setAttribute('aria-label','Second radio receiver');
  Object.assign(panel.style,{margin:'1rem 0',padding:'1rem',border:'1px solid #53605d',borderRadius:'8px',background:'#111817'});
  panel.innerHTML=`<p class="eyebrow">RADIO 02 / AIRBAND</p>
    <div class="radio-controls">
      <div class="net-control"><label for="airbandNet">AERONAUTICAL SAR NET</label><select id="airbandNet"></select></div>
      <div class="volume-control"><label for="airbandVolume">AIRBAND VOLUME <output id="airbandVolumeValue">55%</output></label><input id="airbandVolume" type="range" min="0" max="100" value="55"></div>
    </div>
    <div class="receiver-status"><div><span class="signal-dot"></span><strong id="airbandState">Disconnected</strong><span id="airbandSpeaker" style="display:block;color:#a0ada2;font-size:12px;margin:6px 0 0 17px">Join both radios to listen.</span></div></div>
    <fieldset style="display:flex;gap:1.5rem;align-items:center;margin-top:.8rem;border:1px solid #39423d;border-radius:4px;padding:.8rem"><legend>PTT TRANSMITTER</legend><label style="display:flex;align-items:center;gap:.45rem;margin:0"><input id="txMain" style="appearance:auto;width:auto;height:auto;padding:0" type="radio" name="txRadio" value="main" checked> Tactical radio</label><label style="display:flex;align-items:center;gap:.45rem;margin:0"><input id="txAirband" style="appearance:auto;width:auto;height:auto;padding:0" type="radio" name="txRadio" value="airband"> Airband radio</label></fieldset>`;
  document.querySelector('.station .radio-controls').insertAdjacentElement('afterend',panel);
  $('airbandVolume').addEventListener('input',updateVolume);
  $('airbandNet').addEventListener('change',tuneAirband);
  $('txMain').addEventListener('change',render);$('txAirband').addEventListener('change',render);
  document.querySelector('.ptt-help span').textContent='Both nets stay audible.';
}

async function init() {
  installAirbandPanel();
  setModel(new URLSearchParams(location.search).get('model')==='efj5300'?'efj5300':'apx4500');
  try {
    const response=await fetch('/api/radio/config');if(!response.ok)throw new Error('Could not load the mission radio configuration.');
    state.config=await response.json();state.channels=state.config.channels;
    $('netSelect').replaceChildren(...state.channels.map(c=>new Option(c.label,c.id)));
    $('airbandNet').replaceChildren(...state.channels.map(c=>new Option(c.label,c.id)));
    $('airbandNet').value=state.channels.some(c=>c.id==='alternate')?'alternate':state.channels[1]?.id||state.channels[0]?.id||'';
    enforceDistinctNets('main');
    $('accessRow').hidden=!state.config.accessCodeRequired;
    const secure=new URL(location.href);secure.protocol='https:';secure.port=String(state.config.securePort);$('secureLink').href=secure.href;
    if(!window.isSecureContext){$('secureHelp').hidden=false;}
    if(!state.config.configured)notice('Mission voice is not configured on this server yet.');
    await devices();render();
  }catch(error){notice(error.message||'Unable to initialize the radio.');}
}
init();
