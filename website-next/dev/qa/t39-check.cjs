// T39 quality gates for the detail pages. Run with NODE_PATH pointing at an installed Playwright module and
// a local http.server on 127.0.0.1:8765 serving website-next/site; uses system Google Chrome.
const {chromium}=require('playwright');
const fs=require('fs');
const path=require('path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..','..','site');   // T11: scripts moved to website-next/dev/qa
const shots=path.resolve(__dirname,'..','screenshots');
const base='http://127.0.0.1:8765/';
const pages=['comms','df','foreflight','caltopo','ai-pilot','airplane','how-its-built'];
const report={checks:[],failures:[],layouts:{},contrast:{},fileUrl:{}};
function check(name,value){if(value){report.checks.push(name)}else{report.failures.push(name);console.error('FAIL',name)}}
function contrast(a,b){const lum=h=>{let c=h.match(/[a-f\d]{2}/gi).map(v=>parseInt(v,16)/255).map(x=>x<=.04045?x/12.92:((x+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722};const x=lum(a),y=lum(b);return +((Math.max(x,y)+.05)/(Math.min(x,y)+.05)).toFixed(2)}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
 try{
 for(const [name,width,height] of [['desktop',1440,900],['mobile',390,844]]){
  for(const slug of pages){
   const page=await browser.newPage({viewport:{width,height},deviceScaleFactor:1});
   const errors=[],external=[],badResponses=[];
   page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error'&&!/\/assets\/video\/[^/]+\.(webm|mp4)$/.test((m.location()||{}).url||''))errors.push(m.text())});
   page.on('request',r=>{if(!r.url().startsWith(base))external.push(r.url())});page.on('response',r=>{if(r.status()>=400&&!/\/assets\/video\/[^/]+\.(webm|mp4)$/.test(r.url()))badResponses.push(r.url())});
   const tag=`${slug} ${name}`;
   check(`${tag}: HTTP 200`,(await page.goto(base+slug+'.html',{waitUntil:'networkidle'})).status()===200);
   await page.evaluate(async()=>{document.querySelectorAll('img[loading=lazy]').forEach(i=>i.loading='eager');await document.fonts.ready;await Promise.all([...document.images].filter(i=>i.src).map(i=>i.decode().catch(()=>{})))});
   await page.waitForTimeout(150);
   const scan=await page.evaluate(()=>{
    const headings=[...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(h=>+h.tagName[1]);
    const scrolls=e=>{for(let a=e.parentElement;a;a=a.parentElement){const o=getComputedStyle(a).overflowX;if(o==='auto'||o==='scroll')return true}return false};const wide=[...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();return r.right>innerWidth+1&&getComputedStyle(e).position!=='fixed'&&!scrolls(e)}).map(e=>e.tagName+'.'+e.className).slice(0,5);
    return {width:document.documentElement.scrollWidth,height:document.documentElement.scrollHeight,h1:document.querySelectorAll('h1').length,landmarks:['header','nav','main','footer'].every(s=>document.querySelector(s)),missingAlt:[...document.images].filter(i=>!i.hasAttribute('alt')).length,brokenImages:[...document.images].filter(i=>i.src&&!i.naturalWidth).map(i=>i.src),headingSkips:headings.filter((h,i)=>i&&h>headings[i-1]+1),current:[...document.querySelectorAll('a[aria-current=page]')].map(a=>a.getAttribute('href')),svgs:[...document.querySelectorAll('svg[role=img]')].map(s=>!!s.getAttribute('aria-labelledby')&&!!s.querySelector('title')&&!!s.querySelector('desc')),links:[...document.querySelectorAll('a[href]')].map(a=>a.getAttribute('href')),wide,smallTargets:[...document.querySelectorAll('a.button,button')].filter(b=>b.checkVisibility()&&b.getBoundingClientRect().height<44).map(b=>b.textContent.trim()).slice(0,5),nextLink:!!document.querySelector('nav.page-next a.button-primary'),animated:[...document.querySelectorAll('main *')].filter(e=>!e.closest('.reel,.clip')&&e.getAnimations&&e.getAnimations().length).length};
   });
   report.layouts[tag]=scan;
   check(`${tag}: no overflow ${scan.width}/${width} ${JSON.stringify(scan.wide)}`,scan.width===width&&!scan.wide.length);
   check(`${tag}: one H1, landmarks, alt text, loaded images, ordered headings`,scan.h1===1&&scan.landmarks&&!scan.missingAlt&&!scan.brokenImages.length&&!scan.headingSkips.length);
   check(`${tag}: nav marks ${slug}.html current twice`,scan.current.length===2&&scan.current.every(h=>h===slug+'.html'));
   check(`${tag}: every diagram has title and desc`,scan.svgs.every(Boolean));
   check(`${tag}: next-page link present`,scan.nextLink);
   check(`${tag}: 44px buttons ${JSON.stringify(scan.smallTargets)}`,!scan.smallTargets.length);
   check(`${tag}: no animations in main`,scan.animated===0);
   check(`${tag}: no console or page errors ${JSON.stringify(errors)}`,!errors.length);
   check(`${tag}: no external requests ${JSON.stringify(external)}`,!external.length);
   check(`${tag}: no failed responses ${JSON.stringify(badResponses)}`,!badResponses.length);
   for(const link of scan.links){if(link.startsWith('#'))check(`${tag}: fragment ${link}`,await page.locator(link).count()>0);else if(!link.includes(':')){const [file,fragment]=link.split('#');check(`${tag}: local link ${link}`,fs.existsSync(path.join(root,file)));if(fragment)check(`${tag}: target ${link}`,fs.readFileSync(path.join(root,file),'utf8').includes(`id="${fragment}"`))}}
   await page.screenshot({path:path.join(shots,`${slug}-${name}-full.png`),fullPage:true});
   // lightbox on the first figure, where there is one
   const opener=page.locator('[data-lightbox]').first();
   if(await opener.count()){await opener.scrollIntoViewIfNeeded();await opener.click();const dialog=page.locator('dialog.lightbox');check(`${tag}: lightbox opens`,await dialog.evaluate(d=>d.open));await page.keyboard.press('Escape');check(`${tag}: Escape closes lightbox and returns focus`,!(await dialog.evaluate(d=>d.open))&&await opener.evaluate(e=>document.activeElement===e))}
   if(name==='mobile'){const menu=page.getByRole('button',{name:'Menu',exact:true});await menu.click();check(`${tag}: menu opens`,await menu.getAttribute('aria-expanded')==='true');await page.keyboard.press('Escape');check(`${tag}: Escape closes menu`,await menu.getAttribute('aria-expanded')==='false')}
   // keyboard focus ring on the first nav link
   await page.keyboard.press('Tab');await page.keyboard.press('Tab');
   check(`${tag}: visible focus ring`,await page.evaluate(()=>{const e=document.activeElement;return e&&getComputedStyle(e).outlineStyle!=='none'}));
   await page.close();
  }
 }
 // the alias redirects
 {const page=await browser.newPage();const r=await page.goto(base+'coms.html',{waitUntil:'networkidle'});await page.waitForURL(/comms\.html$/,{timeout:5000}).catch(()=>{});check('coms.html redirects to comms.html',page.url().endsWith('comms.html'));await page.close()}
 // file:// loads with local assets
 for(const slug of ['comms','ai-pilot']){const page=await browser.newPage({viewport:{width:1440,height:900}});const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.goto('file://'+path.join(root,slug+'.html'),{waitUntil:'load'});await page.evaluate(async()=>{document.querySelectorAll('img[loading=lazy]').forEach(i=>i.loading='eager');await Promise.all([...document.images].filter(i=>i.src).map(i=>i.decode().catch(()=>{})))});const s=await page.evaluate(()=>({css:getComputedStyle(document.body).backgroundColor,broken:[...document.images].filter(i=>i.src&&!i.naturalWidth).length,width:document.documentElement.scrollWidth}));report.fileUrl[slug]=s;check(`file:// ${slug}: stylesheet, images and width`,s.css==='rgb(11, 18, 32)'&&!s.broken&&s.width===1440&&!errors.length);await page.close()}
 // reduced motion: nothing in main animates, and the pages render
 {const ctx=await browser.newContext({viewport:{width:1440,height:900},reducedMotion:'reduce'});const page=await ctx.newPage();await page.goto(base+'df.html',{waitUntil:'networkidle'});check('reduced motion: df renders without animations',await page.evaluate(()=>[...document.querySelectorAll('main *')].every(e=>!e.getAnimations||!e.getAnimations().length)));await ctx.close()}
 // contrast of the new colour pairs, from the shipped tokens
 const pairs={'text/dark':['#E6ECF2','#0B1220'],'muted/dark':['#9AA7B5','#0B1220'],'muted/card':['#9AA7B5','#111A2B'],'cyan/dark':['#27C7D9','#0B1220'],'cyan-soft/dark':['#7FE0EA','#0B1220'],'orange-soft/dark':['#FF8A47','#0B1220'],'green/dark':['#7FBF4D','#0B1220'],'ink/paper':['#15202B','#F3EFE6'],'ink-muted/paper':['#4B5868','#F3EFE6'],'green-deep/paper':['#356B2A','#F3EFE6'],'chip cyan on paper':['#146A76','#F3EFE6'],'chip orange on paper':['#9A3D05','#F3EFE6'],'diagram note #9aa7b5 on #0b1220':['#9AA7B5','#0B1220'],'card ink on #faf8f2':['#15202B','#FAF8F2'],'ink on orange CTA':['#15202B','#FF6A13']};
 for(const [k,[a,b]] of Object.entries(pairs)){report.contrast[k]=contrast(a,b);check(`contrast ${k} ${report.contrast[k]}:1`,report.contrast[k]>=4.5)}
 }finally{await browser.close()}
 fs.writeFileSync(path.join(shots,'t39-qa.json'),JSON.stringify(report,null,1));
 console.log(`${report.checks.length} checks passed, ${report.failures.length} failed`);
 if(report.failures.length)process.exit(1);
})().catch(e=>{console.error(e);process.exit(1)});
