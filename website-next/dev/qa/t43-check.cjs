// T43: reel and clip behaviour. Serve website-next/site on 127.0.0.1:8765 first; NODE_PATH to Playwright.
const {chromium}=require('playwright');const fs=require('fs');const path=require('path');
const root=path.resolve(__dirname,'..','..','site');const shots=path.resolve(__dirname,'..','screenshots');const base='http://127.0.0.1:8765/';
const report={checks:[],failures:[],weights:{}};
function check(name,ok){(ok?report.checks:report.failures).push(name);if(!ok)console.error('FAIL',name)}
async function load(ctx,url,errors,bytes){const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!/\/assets\/video\/[^/]+\.(webm|mp4)$/.test((m.location()||{}).url||''))errors.push(m.text())});
 page.on('response',async r=>{try{const u=r.url();if(!u.startsWith(base))return;const h=r.headers();const len=+h['content-length']||0;bytes[u]=(bytes[u]||0)+len}catch(e){}});
 await page.goto(base+url,{waitUntil:'networkidle'});await page.waitForFunction(()=>[...document.querySelectorAll('.reel,.clip')].every(f=>f.dataset.ready==='true'||f.hidden),null,{timeout:15000}).catch(()=>{});await page.waitForTimeout(800);return page}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox','--autoplay-policy=no-user-gesture-required']});
 try{
  // Home: the hero reel, its first slide the map, clips only where files exist; autoplay, timer, pause, off-screen.
  for(const [name,width,height] of [['desktop',1440,900],['mobile',390,844]]){
   const errors=[],bytes={};const ctx=await browser.newContext({viewport:{width,height}});const page=await load(ctx,'index.html',errors,bytes);
   const s=await page.evaluate(()=>{const fig=document.querySelector('.hero-reel');const slides=[...fig.querySelectorAll('.reel-slide')];const active=fig.querySelector('.reel-slide.is-active');
    return {ready:fig.dataset.ready,slides:slides.length,states:slides.map(x=>x.dataset.state),firstIsMap:!!slides[0].querySelector('svg.hero-map'),activeIndex:slides.indexOf(active),controls:getComputedStyle(fig.querySelector('.reel-controls')).display,dots:fig.querySelectorAll('.reel-dot').length,playing:slides.filter(x=>x.querySelector('video')&&!x.querySelector('video').paused).length,missing:[...document.querySelectorAll('img')].filter(i=>i.src&&i.complete&&!i.naturalWidth&&!(i.classList.contains('slide-poster')&&i.closest('[data-state=video]'))).length}});
   check(`${name}: hero reel initialised, map first, ${s.slides} slides (${s.states.join(',')}), active ${s.activeIndex}, missing ${s.missing}`,s.ready==='true'&&s.firstIsMap&&s.slides>=1&&s.activeIndex>=0&&!s.missing);
   if(s.slides>1){await page.locator('.hero-reel .reel-dot').nth(1).click();await page.waitForTimeout(1500);await page.locator('.hero').screenshot({path:path.join(shots,`t43-hero-slide2-${name}.png`)});await page.locator('.hero-reel .reel-dot').nth(0).click();await page.waitForTimeout(300)}
   check(`${name}: controls ${s.slides>1?'shown':'hidden'} and ${s.dots} dots match`,(s.slides>1?s.controls!=='none':s.controls==='none')&&s.dots===(s.slides>1?s.slides:0));
   check(`${name}: at most one video playing`,s.playing<=1);
   if(s.slides>1){
    await page.locator('.hero-reel .reel-next').click();await page.waitForTimeout(1200);
    const a=await page.evaluate(()=>{const fig=document.querySelector('.hero-reel');const slides=[...fig.querySelectorAll('.reel-slide')];const active=fig.querySelector('.reel-slide.is-active');const v=active.querySelector('video');return {i:slides.indexOf(active),playing:v?!v.paused:null,state:active.dataset.state,live:fig.querySelector('.reel-live').textContent.length>0,dot:fig.querySelectorAll('.reel-dot[aria-current=true]').length}});
    check(`${name}: Next advances to slide 2, announces, marks the dot`,a.i===1&&a.live&&a.dot===1);
    if(a.state==='video')check(`${name}: active video slide plays`,a.playing===true);
    await page.locator('.pause-control').click();await page.waitForTimeout(400);
    check(`${name}: hero Pause control pauses the reel video`,await page.evaluate(()=>[...document.querySelectorAll('.hero-reel video')].every(v=>v.paused)));
    await page.locator('.pause-control').click();await page.waitForTimeout(600);
    if(a.state==='video')check(`${name}: Resume restarts it`,await page.evaluate(()=>{const v=document.querySelector('.hero-reel .reel-slide.is-active video');return v&&!v.paused}));
    await page.evaluate(()=>window.scrollTo(0,document.body.scrollHeight));await page.waitForTimeout(700);
    check(`${name}: off-screen reel pauses`,await page.evaluate(()=>[...document.querySelectorAll('.hero-reel video')].every(v=>v.paused)));
    await page.evaluate(()=>window.scrollTo(0,0));await page.waitForTimeout(900);
    if(a.state==='video')check(`${name}: back on screen it plays again`,await page.evaluate(()=>{const v=document.querySelector('.hero-reel .reel-slide.is-active video');return v&&!v.paused}));
    await page.evaluate(()=>{document.querySelector('.hero-reel .reel-dots').focus();document.querySelector('.hero-reel .reel-dot').focus()});await page.keyboard.press('ArrowRight');await page.waitForTimeout(300);
    check(`${name}: arrow keys move between slides`,await page.evaluate(()=>{const fig=document.querySelector('.hero-reel');return [...fig.querySelectorAll('.reel-slide')].indexOf(fig.querySelector('.is-active'))===2%fig.querySelectorAll('.reel-slide').length}));
   }
   check(`${name}: no console or page errors ${JSON.stringify(errors)}`,!errors.length);
   const total=Object.values(bytes).reduce((a,b)=>a+b,0);report.weights[`home ${name}`]={bytes:total,resources:Object.keys(bytes).length};
   await ctx.close();
  }
  // Reduced motion: posters only, nothing plays, nothing auto-advances.
  {const errors=[],bytes={};const ctx=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});const page=await load(ctx,'index.html',errors,bytes);await page.waitForTimeout(2500);
   const r=await page.evaluate(()=>{const fig=document.querySelector('.hero-reel');const slides=[...fig.querySelectorAll('.reel-slide')];return {playing:slides.filter(x=>x.querySelector('video')&&!x.querySelector('video').paused).length,active:slides.indexOf(fig.querySelector('.is-active')),videoStates:slides.map(x=>x.dataset.state).filter(x=>x==='video').length}});
   check(`reduced motion: no video plays, no video state, map stays`,r.playing===0&&r.videoStates===0&&r.active===0);
   const d=await load(ctx,'df.html',errors,bytes);check('reduced motion: clips on DF show posters, none play',await d.evaluate(()=>[...document.querySelectorAll('.clip')].every(c=>c.hidden||(c.dataset.state!=='video'&&(!c.querySelector('video')||c.querySelector('video').paused)))));
   check(`reduced motion: no errors ${JSON.stringify(errors)}`,!errors.length);await ctx.close()}
  // DF: clip figures: existing clips play when scrolled into view, pending ones hidden, pause button works.
  {const errors=[],bytes={};const ctx=await browser.newContext({viewport:{width:1440,height:900}});const page=await load(ctx,'df.html',errors,bytes);
   const c=await page.evaluate(()=>[...document.querySelectorAll('.clip')].map(x=>({id:x.dataset.clip,state:x.dataset.state,hidden:x.hidden,note:!!x.querySelector('.clip-note'),button:x.querySelector('.clip-pause')?.hidden})));
   check(`df: clips resolved ${JSON.stringify(c)}`,c.every(x=>x.hidden||['video','poster'].includes(x.state)));
   check('df: poster-only clips carry the Still badge and hide their button',c.filter(x=>x.state==='poster').every(x=>x.note&&x.button===true));
   const vid=c.find(x=>x.state==='video');
   if(vid){const fig=page.locator(`.clip[data-clip="${vid.id}"]`);await fig.scrollIntoViewIfNeeded();await page.waitForTimeout(900);
    check(`df: ${vid.id} plays in view`,await fig.evaluate(f=>!f.querySelector('video').paused));
    await fig.locator('.clip-pause').click();await page.waitForTimeout(300);check(`df: ${vid.id} Pause clip pauses it`,await fig.evaluate(f=>f.querySelector('video').paused&&f.querySelector('.clip-pause').textContent==='Play clip'));
    await fig.locator('.clip-pause').click();await page.waitForTimeout(500);check(`df: ${vid.id} Play clip resumes`,await fig.evaluate(f=>!f.querySelector('video').paused));
    await page.evaluate(()=>window.scrollTo(0,0));await page.waitForTimeout(700);check(`df: ${vid.id} pauses off-screen`,await fig.evaluate(f=>f.querySelector('video').paused))}
   check(`df: no errors ${JSON.stringify(errors)}`,!errors.length);
   const total=Object.values(bytes).reduce((a,b)=>a+b,0);report.weights['df desktop']={bytes:total,resources:Object.keys(bytes).length};
   await ctx.close()}
  // Pages with only pending clips: figures hidden, nothing broken.
  for(const slug of ['ai-pilot','airplane','how-its-built','comms']){const errors=[],bytes={};const ctx=await browser.newContext({viewport:{width:1440,height:900}});const page=await load(ctx,slug+'.html',errors,bytes);
   const c=await page.evaluate(()=>[...document.querySelectorAll('.clip')].map(x=>({id:x.dataset.clip,state:x.dataset.state,hidden:x.hidden})));
   check(`${slug}: clips ${JSON.stringify(c)}`,c.every(x=>x.hidden||['video','poster'].includes(x.state))&&!errors.length);await ctx.close()}
 }finally{await browser.close()}
 fs.writeFileSync(path.join(shots,'t43-qa.json'),JSON.stringify(report,null,1));
 console.log(`${report.checks.length} checks passed, ${report.failures.length} failed`,JSON.stringify(report.weights));
 if(report.failures.length)process.exit(1);
})().catch(e=>{console.error(e);process.exit(1)});
