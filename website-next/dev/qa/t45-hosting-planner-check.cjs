// T45: checks for hosting.html and flight-planner.html.
// Serve website-next/site first:  python3 -m http.server 8791 --bind 127.0.0.1 --directory website-next/site
// Run with Playwright on NODE_PATH and system Chrome:  NODE_PATH=/tmp/t36-render/node_modules node website-next/dev/qa/t45-hosting-planner-check.cjs
const {chromium}=require('playwright');const fs=require('fs');const path=require('path');
const shots=path.resolve(__dirname,'..','screenshots');const base=process.env.QA_BASE||'http://127.0.0.1:8791/';
const pages=['hosting.html','flight-planner.html'];
const report={checks:[],failures:[]};
function check(name,ok){(ok?report.checks:report.failures).push(name);if(!ok)console.error('FAIL',name)}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/google-chrome',args:['--no-sandbox']});
 try{
  for(const slug of pages){
   for(const [label,width,height] of [['mobile',375,812],['tablet',768,1024],['narrow-desktop',905,800],['mid',1000,800],['desktop',1280,900]]){
    const errors=[];const failedReq=[];
    const ctx=await browser.newContext({viewport:{width,height}});const page=await ctx.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    page.on('console',m=>{if(m.type()==='error')errors.push(m.text())});
    page.on('requestfailed',r=>failedReq.push(r.url()));
    page.on('response',r=>{if(r.status()>=400)failedReq.push(r.status()+' '+r.url())});
    await page.goto(base+slug,{waitUntil:'networkidle'});
    // bring every lazy image into view and wait for it, then return to the top
    await page.evaluate(async()=>{for(const i of document.querySelectorAll('img[loading=lazy]')){i.scrollIntoView({block:'center'});for(let k=0;k<75&&!i.complete;k++)await new Promise(r=>setTimeout(r,40))}window.scrollTo(0,0)});await page.waitForTimeout(400);
    const tag=`${slug} @${width}`;
    check(`${tag}: no console errors or failed requests ${JSON.stringify(errors.concat(failedReq))}`,!errors.length&&!failedReq.length);
    const m=await page.evaluate(()=>{
      const de=document.documentElement;
      const hs=[...document.querySelectorAll('h1,h2,h3')].map(h=>+h.tagName[1]);
      let order=true;for(let i=1;i<hs.length;i++)if(hs[i]-hs[i-1]>1)order=false;
      const imgs=[...document.querySelectorAll('img')].filter(i=>i.currentSrc||i.src);
      const broken=imgs.filter(i=>i.complete&&!i.naturalWidth).map(i=>i.src);
      const lazyPending=imgs.filter(i=>!i.complete).length;
      const svgs=[...document.querySelectorAll('svg[role=img]')].map(s=>({vis:s.getBoundingClientRect().width>0&&getComputedStyle(s).display!=='none',w:Math.round(s.getBoundingClientRect().width),t:!!s.querySelector('title'),d:!!s.querySelector('desc'),lab:s.getAttribute('aria-labelledby')}));
      const nav=document.querySelector('.primary-nav');
      const navRect=nav?nav.getBoundingClientRect():null;
      const header=document.querySelector('.site-header');
      const links=[...document.querySelectorAll('.primary-nav a')];
      const navOverflow=getComputedStyle(nav).display!=='none'&&getComputedStyle(nav).position!=='fixed'?(links[links.length-1].getBoundingClientRect().right>window.innerWidth||nav.scrollWidth>nav.clientWidth+1):false;
      const wrapped=getComputedStyle(nav).display!=='none'&&getComputedStyle(nav).position!=='fixed'?(Math.max(...links.map(a=>a.getBoundingClientRect().top))-Math.min(...links.map(a=>a.getBoundingClientRect().top)))>4:false;
      return {sw:de.scrollWidth,iw:window.innerWidth,h1:document.querySelectorAll('h1').length,hs,order,broken,lazyPending,svgs,navOverflow,wrapped,mainLabel:!!document.querySelector('main#main'),skip:!!document.querySelector('.skip-link'),title:document.title,desc:!!document.querySelector('meta[name=description]'),headerH:header.getBoundingClientRect().height};
    });
    check(`${tag}: no horizontal page overflow (${m.sw} <= ${m.iw})`,m.sw<=m.iw);
    check(`${tag}: one H1, heading levels in order`,m.h1===1&&m.order);
    check(`${tag}: all images loaded (${m.broken.length} broken, ${m.lazyPending} still pending)`,!m.broken.length&&!m.lazyPending);
    check(`${tag}: skip link, main landmark, title "${m.title}", description`,m.skip&&m.mainLabel&&m.desc&&/—\s*CAP-VSAR$/.test(m.title));
    check(`${tag}: every svg role=img has title, desc and labelledby`,m.svgs.every(s=>s.t&&s.d&&s.lab));
    if(width>=901)check(`${tag}: header nav fits on one line, no overflow (overflow ${m.navOverflow}, wrapped ${m.wrapped}, header ${m.headerH}px)`,!m.navOverflow&&!m.wrapped);
    if(slug==='hosting.html'){
     const visible=m.svgs.filter(s=>s.vis);
     check(`${tag}: exactly one architecture diagram visible (${JSON.stringify(m.svgs)})`,visible.length===1);
     if(width<=1000)check(`${tag}: narrow diagram used, full width without sideways scroll`,await page.evaluate(()=>{const f=document.querySelector('.diagram.arch');const s=f.querySelector('svg.arch-narrow');return getComputedStyle(s).display==='block'&&f.scrollWidth<=f.clientWidth+1}));
     else check(`${tag}: wide diagram used`,await page.evaluate(()=>getComputedStyle(document.querySelector('svg.arch-wide')).display==='block'));
     if(width===375){
      // effective text size in the diagram at phone width
      const px=await page.evaluate(()=>{const s=document.querySelector('svg.arch-narrow');const r=s.getBoundingClientRect();const scale=r.width/s.viewBox.baseVal.width;const t=[...s.querySelectorAll('text')].map(x=>parseFloat(getComputedStyle(x).fontSize)*scale);return {scale:+scale.toFixed(2),min:+Math.min(...t).toFixed(1)}});
      check(`${tag}: smallest diagram text renders at >= 11.5 px (${JSON.stringify(px)})`,px.min>=11.5);
     }
    }
    if(label==='desktop'||label==='mobile'){
     await page.screenshot({path:path.join(shots,`t45-${slug.replace('.html','')}-${label}-full.png`),fullPage:true});
     if(slug==='hosting.html'){const f=page.locator('.diagram.arch');await f.scrollIntoViewIfNeeded();await page.addStyleTag({content:'.site-header,.skip-link{visibility:hidden}'});await f.screenshot({path:path.join(shots,`t45-hosting-diagram-${label}.png`)})}
    }
    // local links and fragments resolve
    if(label==='desktop'){
     const hrefs=await page.evaluate(()=>[...document.querySelectorAll('a[href],img[src],link[href],script[src],[data-lightbox]')].map(e=>e.getAttribute('href')||e.getAttribute('src')||e.getAttribute('data-lightbox')).filter(h=>h&&!/^(https?:|mailto:|tel:|#)/.test(h)));
     const bad=[];for(const h of new Set(hrefs)){const [file,frag]=h.split('#');const u=new URL(file||slug,base+slug).href;const r=await ctx.request.get(u);if(r.status()!==200){bad.push(h+' '+r.status());continue}
       if(frag){const html=await r.text();if(!new RegExp(`id=["']${frag}["']`).test(html))bad.push(h+' (no such id)')}}
     check(`${slug}: all ${new Set(hrefs).size} local links, images and fragments resolve ${JSON.stringify(bad)}`,!bad.length);
     const fragsHere=await page.evaluate(()=>[...document.querySelectorAll('a[href^="#"]')].map(a=>a.getAttribute('href').slice(1)).filter(id=>id&&!document.getElementById(id)));
     check(`${slug}: in-page anchors resolve ${JSON.stringify(fragsHere)}`,!fragsHere.length);
     // privacy sweep of the visible text and source
     const html=await page.content();
     const leaks=[/\b192\.168\.\d+\.\d+/,/\b10\.0\.0\.\d+/,/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/,/\bms01\b/i,/\/home\/\w+/,/ron-MS/i,/rpc-cyberflight/i,/N499CP/i,/@(gmail|cap\.gov)/i,/\b([0-9a-f]{2}:){5}[0-9a-f]{2}\b/i].filter(r=>r.test(html)).map(String);
     check(`${slug}: privacy sweep finds no address, hostname, path, tail number or email ${JSON.stringify(leaks)}`,!leaks.length);
    }
    await ctx.close();
   }
  }
 }finally{await browser.close()}
 fs.writeFileSync(path.join(shots,'t45-qa.json'),JSON.stringify(report,null,1));
 console.log(`${report.checks.length} checks passed, ${report.failures.length} failed`);
 if(report.failures.length)process.exit(1);
})().catch(e=>{console.error(e);process.exit(1)});
