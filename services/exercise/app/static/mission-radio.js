const $ = id => document.getElementById(id);
const AudioCtx = window.AudioContext || window.webkitAudioContext;
const state = {
  model: 'apx4500', online: false, joining: false, tuning: false, tx: false,
  held: new Set(), request: 0, epoch: 0, generation: 0, ws: null, context: null,
  stream: null, source: null, capture: null, playback: null, gain: null,
  started: 0, lastPong: 0, lastRx: 0, channels: [], config: null, timeout: null,
};
const models = {
  apx4500: {className:'apx', title:'Motorola APX 4500 O2 control head', caption:'APX 4500 / O2 CONTROL HEAD',
    hits:[['Power / connect or disconnect',87,48,58,58,'power'],['Previous net',558,65,50,55,'prev'],
      ['Next net',558,127,50,55,'next'],['Home net',561,260,44,44,'home'],
      ['Choose mission net',199,244,76,52,'net'],['Next net',283,244,76,52,'next'],
      ['Adjust headset volume',367,244,76,52,'volume'],['Home net',451,244,76,52,'home'],
      ['Headset volume knob: arrow keys or wheel',783,193,110,110,'knob']]},
  efj5300: {className:'efj',title:'EFJohnson 5300 mobile/base control head',caption:'EFJOHNSON 5300 / MOBILE-BASE CONTROL HEAD',
    hits:[['Choose mission net',180,32,94,50,'net'],['Home net',592,32,94,50,'home'],
      ['Power / connect or disconnect',284,216,84,84,'power'],
      ['Next net: arrow keys or wheel',569,216,84,84,'channel']]},
};
function notice(message='') { $('notice').textContent=message; $('notice').hidden=!message; }
function channel() { return state.channels.find(c=>c.id===$('netSelect').value); }
function send(data) {
  if (state.ws?.readyState===WebSocket.OPEN) { state.ws.send(JSON.stringify(data)); return true; }
  return false;
}
function render() {
  const ready=state.online && !state.tuning;
  $('ptt').disabled=!ready;
  $('ptt').setAttribute('aria-pressed',String(state.tx));
  $('pttLabel').textContent=state.tx?'TRANSMITTING':state.held.size?'KEYING MIC…':'HOLD TO TALK';
  $('pttHint').textContent=state.tx?'Release to listen':ready?'Hold here or hold the spacebar':state.tuning?'Changing mission net…':'Connect your headset to begin';
  $('join').disabled=state.joining;
  $('join').textContent=state.joining?'Connecting…':state.online?'Disconnect radio':'Join mission net ↗';
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
  $('screenNet').textContent=channel()?.label || 'PRIMARY';
  $('screenCall').textContent=$('callsign').value || 'MISSION BASE';
  if (!state.online) { $('speaker').textContent='Join the net to listen.'; $('instrument').classList.remove('receiving'); $('rxMeter').style.width='0%'; }
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
    button.setAttribute('aria-label',label); button.title=label;
    Object.assign(button.style,{left:`${x/9.6}%`,top:`${y/3.4}%`,width:`${w/9.6}%`,height:`${h/3.4}%`});
    button.addEventListener('click',()=>{
      if(action==='power') $('joinForm').requestSubmit();
      if(action==='prev') changeNet(-1);
      if(action==='next'||action==='channel') changeNet(1);
      if(action==='home') { $('netSelect').value='primary'; tune(); }
      if(action==='net') { $('netSelect').focus(); try{$('netSelect').showPicker();}catch{} }
      if(action==='volume'||action==='knob') $('volume').focus();
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
function tune() {
  releaseAll(); state.playback?.port.postMessage({clear:true}); state.lastRx=0;
  $('speaker').textContent='Listening for traffic.';
  if(state.online) { state.tuning=true; send({action:'tune',channel:$('netSelect').value}); }
  render();
}
function updateVolume() {
  const value=Number($('volume').value)/100;
  $('volumeValue').value=`${Math.round(value*100)}%`;
  if(state.gain) state.gain.gain.setTargetAtTime(value,state.context.currentTime,.02);
}
function silenceMic() {
  if(state.tx) $('speaker').textContent='Listening for traffic.';
  state.capture?.port.postMessage({active:false});
  state.stream?.getAudioTracks().forEach(track=>{track.enabled=false;});
  state.tx=false; clearTimeout(state.timeout); state.timeout=null;
}
function releaseAll(message='') {
  state.held.clear(); silenceMic();
  state.request=(state.request+1)%2147483647;
  send({action:'ptt',active:false,request:state.request});
  if(message) notice(message);
  render();
}
function press(source) {
  if(!state.online||state.tuning||state.held.has(source)) return;
  state.held.add(source);
  if(state.held.size===1) {
    notice(); state.request=(state.request+1)%2147483647;
    state.context.resume().catch(()=>releaseAll('Audio is paused. Tap Join to reconnect.'));
    send({action:'ptt',active:true,request:state.request});
  }
  render();
}
function release(source) {
  state.held.delete(source); if(!state.held.size) releaseAll();
}
async function audioContext() {
  if(state.context && state.context.state!=='closed') { await state.context.resume(); return; }
  if(!AudioCtx) throw new Error('This browser does not support headset audio. Use a current Safari, Chrome, Firefox or Edge.');
  try { state.context=new AudioCtx({sampleRate:48000,latencyHint:'interactive'}); }
  catch { state.context=new AudioCtx({latencyHint:'interactive'}); }
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
async function connect() {
  if(state.joining) return;
  if(!state.config?.configured) { notice('Mission voice has not been configured on this server.'); return; }
  if(!window.isSecureContext||!navigator.mediaDevices?.getUserMedia) { $('secureHelp').hidden=false; return; }
  if(!$('joinForm').reportValidity()) return;
  notice(); state.joining=true; const generation=++state.generation; render();
  try {
    await audioContext();
    // Load in the user-initiated audio context before connecting to the mission net.
    if(!state.capture) {
      await state.context.audioWorklet.addModule('/static/radio-worklet.js');
      state.capture=new AudioWorkletNode(state.context,'radio-capture');
      state.playback=new AudioWorkletNode(state.context,'radio-playback');
      state.capture.connect(state.context.destination); // Worklet always outputs silence.
      state.playback.connect(state.gain);
      state.capture.port.onmessage=({data})=>{
        if(!state.tx||!state.held.size||state.ws?.readyState!==WebSocket.OPEN) return;
        if(state.ws.bufferedAmount>1920*5) {releaseAll('Voice connection is delayed. Release PTT and try again.');return;}
        state.ws.send(data);
      };
    }
    const microphone=$('microphone').value;
    const stream=await navigator.mediaDevices.getUserMedia({audio:{deviceId:microphone?{exact:microphone}:undefined,channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false});
    if(generation!==state.generation) {stream.getTracks().forEach(t=>t.stop());return;}
    state.stream=stream; stream.getAudioTracks().forEach(track=>{
      track.enabled=false;
      track.addEventListener('ended',()=>{if(state.stream===stream){disconnect();notice('Microphone disconnected. Check your headset, then rejoin.');}});
      track.addEventListener('mute',()=>{if(state.tx)releaseAll('Microphone interrupted. Release PTT and check your headset.');});
    });
    state.source=state.context.createMediaStreamSource(stream); state.source.connect(state.capture);
    await devices();
    if(generation!==state.generation) return;
    const socket=new WebSocket(`${location.protocol==='https:'?'wss:':'ws:'}//${location.host}/api/radio/stream`);
    state.ws=socket; socket.binaryType='arraybuffer'; state.lastPong=Date.now();
    socket.addEventListener('open',()=>{
      if(generation!==state.generation){socket.close();return;}
      send({action:'join',callsign:$('callsign').value.trim(),accessCode:$('accessCode').value,channel:$('netSelect').value});
    });
    socket.addEventListener('message',event=>{if(state.ws===socket) receive(event.data);});
    socket.addEventListener('close',()=>{if(state.ws===socket){disconnect();notice('Radio disconnected. Rejoin when you are ready.');}});
    socket.addEventListener('error',()=>{if(state.ws===socket){disconnect();notice('Could not reach mission voice. Check your connection and retry.');}});
    state.timeout=setTimeout(()=>{if(state.joining&&state.ws===socket){disconnect();notice('The mission voice connection timed out. Try joining again.');}},15000);
  } catch(error) {
    if(generation!==state.generation) return;
    disconnect();
    notice(error.name==='NotAllowedError'?'Microphone permission is needed. Allow this site to use your headset, then join again.':error.name==='NotFoundError'?'No microphone was found. Pair or connect your headset, then retry.':error.name==='NotReadableError'?'The microphone is in use or unavailable. Check headset settings and try again.':error.message||'Headset setup failed. Please try again.');
  }
}
function disconnect() {
  ++state.generation; releaseAll();
  state.online=false; state.joining=false; state.tuning=false;
  const socket=state.ws; state.ws=null; socket?.close();
  state.stream?.getTracks().forEach(track=>track.stop()); state.stream=null;
  state.source?.disconnect(); state.source=null;
  state.capture?.disconnect(); state.playback?.disconnect();
  state.capture=null; state.playback=null;
  state.gain?.disconnect(); state.gain=null;
  if(state.context) { const old=state.context; state.context=null; old.close().catch(()=>{}); }
  render();
}
function receive(data) {
  if(data instanceof ArrayBuffer) {
    if(!state.online||state.tuning||state.tx||data.byteLength<10||data.byteLength%2) return;
    const header=new DataView(data), epoch=header.getUint32(0,true), speaker=header.getUint32(4,true);
    if(epoch!==state.epoch) return;
    const pcm=data.slice(8); state.playback.port.postMessage({speaker,pcm},[pcm]);
    let energy=0; for(let i=8;i<data.byteLength;i+=2){const sample=header.getInt16(i,true)/32768;energy+=sample*sample;}
    $('rxMeter').style.width=`${Math.min(100,Math.sqrt(energy/((data.byteLength-8)/2))*260)}%`;
    state.lastRx=Date.now(); $('instrument').classList.add('receiving');
    return;
  }
  let message; try{message=JSON.parse(data);}catch{disconnect();notice('Invalid response from the voice server.');return;}
  if(message.type==='tuned') {
    clearTimeout(state.timeout); state.timeout=null;
    silenceMic(); state.held.clear(); state.online=true;state.joining=false;state.tuning=false;state.epoch=message.epoch;
    $('netSelect').value=message.channel;state.playback.port.postMessage({clear:true});
    state.lastPong=Date.now();$('speaker').textContent='Listening for traffic.';notice();render();
  } else if(message.type==='ptt') {
    if(message.active) {
      if(!state.held.size||message.request!==state.request||!state.online||state.tuning){send({action:'ptt',active:false,request:state.request});return;}
      state.tx=true;state.started=Date.now();state.playback.port.postMessage({clear:true});
      state.stream?.getAudioTracks().forEach(track=>{track.enabled=true;});
      state.capture.port.postMessage({active:true});
      clearTimeout(state.timeout);state.timeout=setTimeout(()=>releaseAll('60-second transmit limit reached. Release PTT before speaking again.'),60000);
    } else if(message.request===state.request) {
      silenceMic();state.held.clear();if(message.reason)notice(message.reason);
    }
    render();
  } else if(message.type==='rx' && !state.tx) {
    $('speaker').textContent=`${message.speaker} transmitting`;
  } else if(message.type==='pong') state.lastPong=Date.now();
  else if(message.type==='error'){disconnect();notice(message.message||'Voice connection unavailable.');}
}

$('joinForm').addEventListener('submit',event=>{event.preventDefault();if(state.online)disconnect();else connect();});
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
window.addEventListener('pagehide',disconnect);
navigator.mediaDevices?.addEventListener('devicechange',()=>devices().catch(()=>{}));
setInterval(()=>{
  $('clock').textContent=new Date().toISOString().slice(11,19)+' Z';
  if(state.online) {
    if(Date.now()-state.lastPong>6000){disconnect();notice('Mission voice stopped responding. Rejoin to reconnect.');return;}
    send({action:'ping'});if(state.tx)send({action:'keepalive'});
    if(state.tx)$('pttHint').textContent=`${Math.floor((Date.now()-state.started)/1000)}s / 60s · release to listen`;
    if(Date.now()-state.lastRx>400){$('rxMeter').style.width='0%';$('instrument').classList.remove('receiving');$('speaker').textContent=state.tx?'Microphone open — transmitting.':'Listening for traffic.';}
  }
},500);

async function init() {
  setModel(new URLSearchParams(location.search).get('model')==='efj5300'?'efj5300':'apx4500');
  try {
    const response=await fetch('/api/radio/config');if(!response.ok)throw new Error('Could not load the mission radio configuration.');
    state.config=await response.json();state.channels=state.config.channels;
    $('netSelect').replaceChildren(...state.channels.map(c=>new Option(c.label,c.id)));
    $('accessRow').hidden=!state.config.accessCodeRequired;
    const secure=new URL(location.href);secure.protocol='https:';secure.port=String(state.config.securePort);$('secureLink').href=secure.href;
    if(!window.isSecureContext){$('secureHelp').hidden=false;}
    if(!state.config.configured)notice('Mission voice is not configured on this server yet.');
    await devices();render();
  }catch(error){notice(error.message||'Unable to initialize the radio.');}
}
init();
