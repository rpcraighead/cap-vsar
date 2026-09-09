"""Run only against a disposable Mumble test server: this sends synthetic audio.

Requires Playwright and Chrome. Start a separate exercise process configured for
that test server, then pass its localhost URL as the sole command-line argument.
Never point this at the live mission service. See docs/mission-base-radio/README.md.
"""
import asyncio, math, struct, wave, sys, tempfile
from urllib.parse import urlsplit
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
if len(sys.argv) != 2 or urlsplit(sys.argv[1]).hostname not in ('localhost', '127.0.0.1'):
 raise SystemExit('Pass the localhost URL of an isolated radio test instance.')
URL=sys.argv[1].rstrip('/')+'/radio'
(ROOT/'output/mission-base-radio').mkdir(parents=True, exist_ok=True)
with wave.open(str(Path(tempfile.gettempdir())/'cap-radio-tone.wav'),'wb') as f:
 f.setnchannels(1);f.setsampwidth(2);f.setframerate(48000)
 f.writeframes(b''.join(struct.pack('<h',int(10000*math.sin(2*math.pi*620*i/48000))) for i in range(48000*3)))

async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True,args=['--no-sandbox','--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream',f'--use-file-for-fake-audio-capture={Path(tempfile.gettempdir())/"cap-radio-tone.wav"}','--autoplay-policy=no-user-gesture-required'])
  contexts=[];pages=[];errors=[]
  for name in ['BASE TEST','AIRCREW TEST']:
   context=await browser.new_context(viewport={'width':1440,'height':1100},permissions=['microphone'])
   await context.add_init_script('''window.__nodes={}; const Original=window.AudioWorkletNode; window.AudioWorkletNode=class extends Original {constructor(ctx,name,...args){super(ctx,name,...args);window.__nodes[name]=this;}};''')
   page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(URL);await page.locator('#callsign').fill(name)
   await page.locator('#join').click()
   try:await page.wait_for_function('document.getElementById("connectionState").textContent === "Listening on the net"',timeout=15000)
   except:
    print('JOIN FAILED:',await page.locator('#notice').inner_text());raise
   contexts.append(context);pages.append(page)
  a,b=pages
  await a.screenshot(path=str(ROOT/'output/mission-base-radio/desktop-apx4500.png'),full_page=True)
  await a.locator('#instrument').screenshot(path=str(ROOT/'output/mission-base-radio/apx4500-instrument.png'))
  await b.evaluate('''window.__analyser=__nodes['radio-playback'].context.createAnalyser();__nodes['radio-playback'].connect(__analyser);window.__peak=0;window.__audioPoll=setInterval(()=>{const b=new Float32Array(__analyser.fftSize);__analyser.getFloatTimeDomainData(b);window.__peak=Math.max(window.__peak,...b.map(Math.abs));},20);''')
  await a.bring_to_front();await a.locator('h1').click();await a.keyboard.down('Space')
  await a.wait_for_function('document.getElementById("ptt").getAttribute("aria-pressed")==="true"')
  await b.wait_for_function('window.__peak > .01',timeout=10000)
  print('Browser-to-browser Mumble audio peak:',await b.evaluate('window.__peak'))
  await a.keyboard.up('Space');await a.wait_for_function('document.getElementById("ptt").getAttribute("aria-pressed")==="false"')
  print('Spacebar PTT release passed')
  await a.keyboard.down('Space');await a.wait_for_function('document.getElementById("ptt").getAttribute("aria-pressed")==="true"')
  await a.evaluate('window.dispatchEvent(new Event("blur"))');assert await a.locator('#ptt').get_attribute('aria-pressed')=='false';await a.keyboard.up('Space')
  print('Blur unkeys microphone')
  await a.locator('#volume').focus();await a.keyboard.down('Space');assert await a.locator('#ptt').get_attribute('aria-pressed')=='false';await a.keyboard.up('Space')
  print('Spacebar ignored inside controls')
  await a.locator('#netSelect').select_option('alternate');await a.wait_for_function('document.getElementById("connectionState").textContent === "Listening on the net"')
  await b.wait_for_timeout(400);await b.evaluate('window.__peak=0')
  await a.locator('h1').click();await a.keyboard.down('Space');await a.wait_for_function('document.getElementById("ptt").getAttribute("aria-pressed")==="true"');await b.wait_for_timeout(750)
  assert await b.evaluate('window.__peak')<.001, 'Audio leaked between mission nets'
  await a.keyboard.up('Space');print('Different-net audio isolation passed')
  await a.locator('#modelEfj').click();await a.screenshot(path=str(ROOT/'output/mission-base-radio/desktop-efj5300.png'),full_page=True)
  await a.locator('#instrument').screenshot(path=str(ROOT/'output/mission-base-radio/efj5300-instrument.png'))
  await a.set_viewport_size({'width':768,'height':1024});await a.screenshot(path=str(ROOT/'output/mission-base-radio/tablet-efj5300.png'),full_page=True)
  assert await a.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
  await a.locator('#modelApx').click()
  await a.set_viewport_size({'width':390,'height':844});await a.screenshot(path=str(ROOT/'output/mission-base-radio/phone-apx4500.png'),full_page=True)
  assert await a.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
  print('Tablet and phone fit passed')
  # Capture a held pointer, then cancel it as a touch interruption would.
  await a.set_viewport_size({'width':768,'height':1024});await a.locator('#ptt').scroll_into_view_if_needed()
  box=await a.locator('#ptt').bounding_box();await a.mouse.move(box['x']+40,box['y']+30);await a.mouse.down()
  await a.wait_for_function('document.getElementById("ptt").getAttribute("aria-pressed")==="true"')
  await a.locator('#ptt').dispatch_event('pointercancel',{'pointerId':1,'isPrimary':True});await a.mouse.up()
  assert await a.locator('#ptt').get_attribute('aria-pressed')=='false'
  print('Pointer cancellation unkeys microphone')
  for page in pages:await page.locator('#join').click()
  print('Browser errors:',errors);assert not errors
  await browser.close()
if __name__ == '__main__':
 asyncio.run(main())
