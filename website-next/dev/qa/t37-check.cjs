// Run with NODE_PATH pointing at an installed Playwright module; uses system Chrome.
const {chromium}=require('playwright');
const fs=require('fs');
const path=require('path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..','..','site');   // T11: scripts moved to website-next/dev/qa
const shots=path.resolve(__dirname,'..','screenshots');
const base='http://127.0.0.1:8765/';
const report={checks:[],layouts:{},contrast:{},claims:'Unverified contact/source/guide destinations remain omitted; no ForeFlight feed, credentials, F-4 carrier, public GitHub status or test-count claims are presented.'};
function check(name,value){assert.ok(value,name);report.checks.push(name)}
function contrast(a,b){const lum=h=>{let c=h.match(/[a-f\d]{2}/gi).map(v=>parseInt(v,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722};const x=lum(a),y=lum(b);return +((Math.max(x,y)+.05)/(Math.min(x,y)+.05)).toFixed(2)}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
 try{
 for(const [name,width,height] of [['desktop',1440,900],['mobile',390,844]]){
  const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:1});
  const errors=[],external=[],badResponses=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!/\/assets\/video\/[^/]+\.(webm|mp4)$/.test((m.location()||{}).url||''))errors.push(m.text())});
  page.on('request',r=>{if(!r.url().startsWith(base))external.push(r.url())});page.on('response',r=>{if(r.status()>=400&&!/\/assets\/video\/[^/]+\.(webm|mp4)$/.test(r.url()))badResponses.push(r.url())});
  check(`${name}: HTTP 200`,(await page.goto(base,{waitUntil:'networkidle'})).status()===200);
  await page.evaluate(async()=>{document.querySelectorAll('img[loading=lazy]').forEach(i=>i.loading='eager');await document.fonts.ready;await Promise.all([...document.images].filter(i=>i.src).map(i=>i.decode()))});
  const scan=await page.evaluate(()=>{
   const headings=[...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(h=>+h.tagName[1]);
   return {width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,viewport:innerWidth,h1:document.querySelectorAll('h1').length,landmarks:['header','nav','main','footer'].every(s=>document.querySelector(s)),missingAlt:[...document.images].filter(i=>!i.hasAttribute('alt')).length,brokenImages:[...document.images].filter(i=>i.src&&!i.naturalWidth).length,headingSkips:headings.filter((h,i)=>i&&h>headings[i-1]+1),branches:[...document.querySelectorAll('details.branch')].map(d=>d.open),cards:document.querySelectorAll('.org-node,.ic-node').length,labels:[...document.querySelectorAll('.screen-chip')].map(s=>s.textContent),smallDisclosures:[...document.querySelectorAll('#org-chart summary')].filter(s=>s.checkVisibility()&&s.getBoundingClientRect().height<44).length,links:[...document.querySelectorAll('a[href]')].map(a=>a.getAttribute('href'))};
  });report.layouts[name]=scan;
  check(`${name}: no overflow`,scan.width===width);check(`${name}: one H1, landmarks, alt text, loaded images, ordered headings`,scan.h1===1&&scan.landmarks&&!scan.missingAlt&&!scan.brokenImages&&!scan.headingSkips.length);
  check(`${name}: eleven cards, plain labels, 44px disclosure targets`,scan.cards===11&&!scan.labels.some(t=>/\/(?:base|ready|radio|planner|setup|instructor|debrief)|SEAT|plugin/i.test(t))&&!scan.smallDisclosures);
  check(`${name}: branch defaults`,scan.branches.every(o=>o===(name==='desktop')));
  for(const link of scan.links){if(link.startsWith('#'))check(`${name}: fragment ${link}`,await page.locator(link).count()>0);else if(!link.includes(':')){const [file,fragment]=link.split('#');check(`${name}: local link ${link}`,fs.existsSync(path.join(root,file)));if(fragment)check(`${name}: target ${link}`,fs.readFileSync(path.join(root,file),'utf8').includes(`id="${fragment}"`))}}
  // Capture the normal landing state, with animations paused at a representative instant.
  await page.evaluate(()=>{document.body.classList.add('paused');document.querySelectorAll('.hero-map *').forEach(e=>e.getAnimations().forEach(a=>{a.currentTime=14000}))});
  await page.screenshot({path:path.join(shots,`home-${name}-full.png`),fullPage:true});
  report.layouts[name].sections=await page.evaluate(()=>Object.fromEntries([['hero','.hero'],['org','#org-chart'],['strip','#screens']].map(([part,selector])=>{const r=document.querySelector(selector).getBoundingClientRect();return [part,{x:r.x,y:r.y+scrollY,width:r.width,height:r.height}]})));
  // Resume explicitly before checking the actual Pause control.
  await page.evaluate(()=>document.body.classList.remove('paused'));
  const pause=page.locator('.pause-control');await pause.click();
  check(`${name}: Pause button stops all map animations`,/^Resume/.test(await pause.textContent())&&await page.evaluate(()=>[...document.querySelectorAll('.hero-map *')].flatMap(e=>e.getAnimations()).every(a=>a.playState==='paused')));
  await pause.click();check(`${name}: Resume button restarts map animations`,/^Pause/.test(await pause.textContent())&&await page.evaluate(()=>[...document.querySelectorAll('.hero-map *')].flatMap(e=>e.getAnimations()).every(a=>a.playState==='running')));
  if(name==='mobile'){
   const menu=page.getByRole('button',{name:'Menu',exact:true});await menu.click();check('mobile: menu opens with expanded state',await menu.getAttribute('aria-expanded')==='true');await page.keyboard.press('Escape');check('mobile: Escape closes menu and returns focus',await menu.getAttribute('aria-expanded')==='false'&&await menu.evaluate(e=>document.activeElement===e));
   const air=page.locator('.branch-air>.branch-heading');await air.focus();await page.keyboard.press('Enter');check('mobile: keyboard opens branch',await page.locator('.branch-air').evaluate(d=>d.open));
   const duty=page.locator('[data-seat="aobd"] summary');await duty.focus();await page.keyboard.press('Space');check('mobile: keyboard reveals duty',await page.locator('[data-seat="aobd"] details').evaluate(d=>d.open));check('mobile: focus ring visible',await duty.evaluate(e=>getComputedStyle(e).outlineStyle!=='none'));
   await page.addStyleTag({content:'.site-header,.skip-link{visibility:hidden}'});await page.locator('#org-chart').screenshot({path:path.join(shots,'t37-mobile-org-expanded.png')});await page.addStyleTag({content:'.site-header,.skip-link{visibility:visible}'});
  }
  const shot=page.locator('.shot-open').first();await shot.click();check(`${name}: lightbox opens`,await page.locator('dialog').evaluate(d=>d.open));await page.keyboard.press('Tab');check(`${name}: lightbox contains focus`,await page.locator('dialog').evaluate(d=>d.contains(document.activeElement)));await page.keyboard.press('Escape');check(`${name}: lightbox closes and returns focus`,await shot.evaluate(e=>document.activeElement===e)&&!await page.locator('dialog').evaluate(d=>d.open));
  check(`${name}: no console/page errors, failed responses, external requests`,!errors.length&&!badResponses.length&&!external.length);
  report.layouts[name].errors=errors;
  await page.close();
 }
 for(const width of [320,600,768,900,1024,1200]){
  const page=await browser.newPage({viewport:{width,height:900}});await page.goto(base);check(`${width}px: no page overflow`,await page.evaluate(()=>document.documentElement.scrollWidth===innerWidth));await page.close();
 }
 const still=await browser.newPage({viewport:{width:1440,height:900},reducedMotion:'reduce'});await still.goto(base);
 check('reduced motion: no map animations; both bearings fully drawn; glow visible',await still.evaluate(()=>[...document.querySelectorAll('.hero-map *')].every(e=>e.getAnimations().length===0)&&[...document.querySelectorAll('.bearings line')].every(e=>getComputedStyle(e).strokeDashoffset==='0px'&&getComputedStyle(e).strokeDasharray==='none')&&getComputedStyle(document.querySelector('.beacon-glow')).opacity==='1'));
 await still.locator('.hero').screenshot({path:path.join(shots,'t37-reduced-motion-hero.png')});await still.close();
 const offline=await browser.newPage({viewport:{width:390,height:844}});const fileErrors=[];offline.on('pageerror',e=>fileErrors.push(e.message));offline.on('console',m=>{if(m.type()==='error'&&!/\/assets\/video\/[^/]+\.(webm|mp4)$/.test((m.location()||{}).url||''))fileErrors.push(m.text())});await offline.goto('file://'+path.join(root,'index.html'));await offline.evaluate(async()=>{document.querySelectorAll('img[loading=lazy]').forEach(i=>i.loading='eager');await Promise.all([...document.images].filter(i=>i.src).map(i=>i.decode()))});
 check('file://: images, CSS, JS and zero overflow/errors',!fileErrors.length&&await offline.evaluate(()=>[...document.images].filter(i=>i.src).every(i=>i.naturalWidth>0)&&getComputedStyle(document.body).backgroundColor==='rgb(11, 18, 32)'&&document.querySelectorAll('details.branch[open]').length===0&&document.documentElement.scrollWidth===innerWidth));await offline.close();
 const nojs=await browser.newPage({viewport:{width:390,height:844},javaScriptEnabled:false});await nojs.goto(base);check('without JS: all branches initially open, native duties operable',await nojs.locator('details.branch[open]').count()===4);await nojs.locator('[data-seat="aobd"] summary').click();check('without JS: native duty opens',await nojs.locator('[data-seat="aobd"] details').evaluate(e=>e.open));await nojs.close();
 // Every linked page retains its shared header/footer, local resources, and disclaimers.
 for(const file of fs.readdirSync(root).filter(f=>f.endsWith('.html'))){const page=await browser.newPage();const r=await page.goto(base+file);check(`${file}: loads with disclaimer and trademark acknowledgement`,r.status()===200&&await page.locator('footer').innerText().then(t=>t.includes('not endorsed by Civil Air Patrol')&&t.includes('Product names are the property of their owners')));await page.close()}
 const sources=fs.readdirSync(root).filter(f=>f.endsWith('.html')).map(f=>fs.readFileSync(path.join(root,f),'utf8')).concat(['assets/css/style.css','assets/js/main.js','assets/brand/logo.svg'].map(f=>fs.readFileSync(path.join(root,f),'utf8'))).join('\n');
 check('forbidden strings: clean published source',!/(192\.168\.|ms01|SAR-|INSTR-|UDF-|@cap\.gov|\[VERIFY|TODO|TBD)/i.test(sources));
 check('external URLs: SVG namespace only',!(sources.replaceAll('http://www.w3.org/2000/svg','').match(/https?:\/\//)));
 check('no organization name substituted for CAP-VSAR logo',!/<(?:title|h1)[^>]*>\s*Civil Air Patrol|alt="Civil Air Patrol[^\"]*(?:logo|mark)/i.test(sources));
 for(const [name,a,b] of [['text/dark','#e6ecf2','#0b1220'],['muted/dark','#9aa7b5','#0b1220'],['cyan/dark','#27c7d9','#0b1220'],['orange/dark','#ff6a13','#0b1220'],['ink/paper','#15202b','#f3efe6'],['muted/paper','#4b5868','#f3efe6'],['green/paper','#356b2a','#f3efe6'],['ink/CTA','#15202b','#ff6a13'],['map label/halo','#f3efe6','#11202c'],['ELT label/halo','#ffd5b6','#11202c'],['screen label/card','#4b5868','#faf8f2']]){report.contrast[name]=contrast(a,b);check(`contrast ${name} >= 4.5:1`,report.contrast[name]>=4.5)}
 fs.writeFileSync(path.join(shots,'t37-qa.json'),JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({passed:report.checks.length,layouts:report.layouts,contrast:report.contrast},null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
