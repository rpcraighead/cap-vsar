#!/usr/bin/env python3
"""Generate original, font-free CAP-VSAR artwork; render with system librsvg.

Run: python3 website-next/brand/build_brand.py
All outputs stay beside this script. No network or font dependencies.
"""
from pathlib import Path
from html import escape
import ctypes as C
import ctypes.util
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
TAGLINE = 'Run the whole search before anyone leaves the ground.'
DISCLAIMER = 'Unofficial training tool. Not affiliated with or endorsed by Civil Air Patrol.'
PALETTES = {
    'dark': dict(bg='#111C28', ink='#F4F1E8', cyan='#72D4DB', green='#9CB99F', orange='#FF8A42'),
    'light': dict(bg='#F4F1E8', ink='#111C28', cyan='#176573', green='#42694F', orange='#A9410C'),
    'white': dict(bg=None, ink='#FFFFFF', cyan='#FFFFFF', green='#FFFFFF', orange='#FFFFFF'),
    'black': dict(bg=None, ink='#000000', cyan='#000000', green='#000000', orange='#000000'),
}
DIRECTIONS = {
    'a-bearing': ('A', 'Bearing', 'A fix, not just a signal.', 'Two DF bearings cross at the orange beacon. Range rings give the mark its operations-room character.'),
    'b-wing-pulse': ('B', 'Wing + Pulse', 'Flight meets signal.', 'An original asymmetric folded wing sits above two signal arcs and a beacon. No feathers, star, propeller, or shield.'),
    'c-chart-tile': ('C', 'Chart tile', 'Plan the search.', 'A compact chart grid carries an expanding-square search trace around an orange beacon.'),
}

# Original geometric placard lettering. Filled outlines; no text/font elements.
GLYPHS = {
    'C': 'M48 0H12L0 12V60L12 72H48V60H18L12 54V18L18 12H48Z',
    'A': 'M0 72L16 0H32L48 72H35L31 52H17L13 72ZM20 40H28L24 19Z',
    'P': 'M0 72V0H35L48 13V31L35 44H12V72ZM12 12V32H30L36 26V18L30 12Z',
    '-': 'M0 30H24V42H0Z',
    'V': 'M0 0H13L24 53L35 0H48L32 72H16Z',
    'S': 'M48 0H12L0 12V31L11 42H31L36 47V54L30 60H0V72H36L48 60V41L37 30H17L12 25V18L18 12H48Z',
    'R': 'M0 72V0H35L48 13V31L36 43L50 72H36L23 44H12V72ZM12 12V32H30L36 26V18L30 12Z',
}

# Original monoline lowercase lettering for the exact sentence-case tagline.
SMALL = {
    'R': (5,'M0 7V0H3.5Q5 0 5 1.8Q5 3.5 3.5 3.5H0M3 3.5L5 7'),
    'u': (4,'M0 3V5.5Q0 7 1.5 7Q4 7 4 5V3M4 5V7'),
    'n': (4,'M0 7V3M0 5Q0 3 2 3Q4 3 4 5V7'),
    't': (3,'M1 1V5.8Q1 7 2.3 7H3M0 3H3'),
    'h': (4,'M0 7V0M0 5Q0 3 2 3Q4 3 4 5V7'),
    'e': (4,'M0 5H4Q4 3 2 3Q0 3 0 5Q0 7 2 7Q3 7 4 6.4'),
    'w': (6,'M0 3L1.2 7L3 3.5L4.8 7L6 3'),
    'o': (4,'M4 5Q4 3 2 3Q0 3 0 5Q0 7 2 7Q4 7 4 5Z'),
    'l': (1.5,'M0 0V6Q0 7 1.5 7'),
    's': (4,'M4 3.4Q3 3 2 3Q0 3 0 4Q0 5 2 5Q4 5 4 6Q4 7 2 7Q1 7 0 6.6'),
    'a': (4,'M4 5Q4 3 2 3Q0 3 0 5Q0 7 2 7Q4 7 4 5M4 3V7'),
    'r': (3,'M0 7V3M0 5Q0 3 3 3'),
    'c': (4,'M4 3.5Q3 3 2 3Q0 3 0 5Q0 7 2 7Q3 7 4 6.5'),
    'b': (4,'M0 0V7M0 5Q0 3 2 3Q4 3 4 5Q4 7 2 7Q0 7 0 5'),
    'f': (3,'M1 7V1.5Q1 0 3 0M0 3H3'),
    'y': (4,'M0 3L2 7M4 3L1.5 8.5Q1 9 0 9'),
    'v': (4,'M0 3L2 7L4 3'),
    'g': (4,'M4 5Q4 3 2 3Q0 3 0 5Q0 7 2 7Q4 7 4 5M4 3V7Q4 9 2 9H.5'),
    'd': (4,'M4 0V7M4 5Q4 3 2 3Q0 3 0 5Q0 7 2 7Q4 7 4 5'),
    '.': (1,'M.5 6.8V7'),
}

def wordmark(x=204, y=53.5, scale=1.18, ink='#FFFFFF'):
    parts, offset = [], 0
    for letter in 'CAP-VSAR':
        parts.append(f'<path transform="translate({offset} 0)" d="{GLYPHS[letter]}"/>')
        offset += (24 if letter == '-' else 48) + 9
    return f'<g transform="translate({x} {y}) scale({scale})" fill="{ink}" fill-rule="evenodd">'+''.join(parts)+'</g>'

def tagline(ink):
    parts, x = [], 0
    for letter in TAGLINE:
        if letter == ' ':
            x += 3.8
            continue
        width, path = SMALL[letter]
        parts.append(f'<path transform="translate({x:g} 0)" d="{path}"/>')
        x += width + 1.7
    scale = min(2.1, 498 / x)
    return f'<g transform="translate(204 151) scale({scale:g})" fill="none" stroke="{ink}" stroke-width=".65" stroke-linecap="round" stroke-linejoin="round">'+''.join(parts)+'</g>'

def mark(direction, p):
    cyan, green, orange = p['cyan'], p['green'], p['orange']
    mono = p['bg'] is None
    if direction == 'a-bearing':
        # The line intersection is exactly (64,64).
        return f'''<g fill="none" stroke-linecap="round">
          <circle cx="64" cy="64" r="48" stroke="{cyan}" stroke-width="3.5"/>
          <circle cx="64" cy="64" r="27" stroke="{green}" stroke-width="2.5"/>
          <path d="M30 100L98 28" stroke="{cyan}" stroke-width="4.5"/>
          <path d="M20 40L108 88" stroke="{green}" stroke-width="4.5"/>
          </g><circle cx="64" cy="64" r="10" fill="{p['bg'] or 'none'}"/>
          <circle cx="64" cy="64" r="7" fill="{orange}"/>'''
    if direction == 'b-wing-pulse':
        return f'''<path d="M14 37L112 15L80 55L61 45L39 59Z" fill="{cyan}"/>
          <g fill="none" stroke-linecap="round" stroke-width="5.5">
          <path d="M38 85Q64 59 90 85" stroke="{green}"/>
          <path d="M48 95Q64 79 80 95" stroke="{cyan}"/>
          </g><circle cx="64" cy="108" r="6" fill="{orange}"/>'''
    grid = '' if mono else f'<path d="M48 19V109M80 19V109M19 48H109M19 80H109" fill="none" stroke="{green}" stroke-width="1.8" opacity=".48"/>'
    return f'''<rect x="16" y="16" width="96" height="96" rx="16" fill="none" stroke="{cyan}" stroke-width="3.5"/>
      {grid}
      <path d="M64 64H80V80H48V48H96V96H32V32" fill="none" stroke="{cyan}" stroke-width="4.5" stroke-linejoin="round" stroke-linecap="round"/>
      <circle cx="64" cy="64" r="7" fill="{orange}"/>'''

def svg(direction, variant, kind):
    p = PALETTES[variant]
    name = DIRECTIONS[direction][1]
    w, h = (128,128) if kind == 'icon' else (728,208 if kind == 'lockup' else 192)
    background = '' if p['bg'] is None else f'<rect width="{w}" height="{h}" rx="{24 if kind == "icon" else 0}" fill="{p["bg"]}"/>'
    artwork = mark(direction, p)
    if kind != 'icon':
        artwork = '<g transform="translate(24 24) scale(1.125)">'+artwork+'</g>'
        artwork += wordmark(y=43 if kind == 'lockup' else 53.5, ink=p['ink'])
        if kind == 'lockup':
            artwork += tagline(p['ink'])
    title = f'CAP-VSAR / {name} / {variant} / {kind}'
    description = f'{TAGLINE} {DISCLAIMER}'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-labelledby="title desc">
<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>
{background}{artwork}
</svg>'''

class Renderer:
    """The librsvg + Cairo pipeline used by rsvg-convert, via its C API."""
    def __init__(self):
        self.rsvg = C.CDLL(ctypes.util.find_library('rsvg-2'))
        self.cairo = C.CDLL(ctypes.util.find_library('cairo'))
        self.obj = C.CDLL(ctypes.util.find_library('gobject-2.0'))
        self.rsvg.rsvg_handle_new_from_file.argtypes = [C.c_char_p,C.POINTER(C.c_void_p)]
        self.rsvg.rsvg_handle_new_from_file.restype = C.c_void_p
        self.rsvg.rsvg_handle_render_document.argtypes = [C.c_void_p,C.c_void_p,C.c_void_p,C.POINTER(C.c_void_p)]
        self.rsvg.rsvg_handle_render_document.restype = C.c_int
        self.cairo.cairo_image_surface_create.argtypes = [C.c_int,C.c_int,C.c_int]
        self.cairo.cairo_image_surface_create.restype = C.c_void_p
        self.cairo.cairo_create.argtypes = [C.c_void_p]
        self.cairo.cairo_create.restype = C.c_void_p
        self.cairo.cairo_surface_write_to_png.argtypes = [C.c_void_p,C.c_char_p]
        self.cairo.cairo_surface_write_to_png.restype = C.c_int
        self.cairo.cairo_destroy.argtypes = [C.c_void_p]
        self.cairo.cairo_surface_destroy.argtypes = [C.c_void_p]
        self.obj.g_object_unref.argtypes = [C.c_void_p]

    def render(self, source, target, width, height):
        class Rect(C.Structure):
            _fields_ = [(k,C.c_double) for k in ('x','y','width','height')]
        error = C.c_void_p()
        handle = self.rsvg.rsvg_handle_new_from_file(str(source).encode(), C.byref(error))
        if not handle:
            raise RuntimeError(f'Could not load {source}')
        surface = self.cairo.cairo_image_surface_create(0,width,height)
        context = self.cairo.cairo_create(surface)
        viewport = Rect(0,0,width,height)
        ok = self.rsvg.rsvg_handle_render_document(handle,context,C.byref(viewport),C.byref(error))
        status = self.cairo.cairo_surface_write_to_png(surface,str(target).encode()) if ok else -1
        self.cairo.cairo_destroy(context)
        self.cairo.cairo_surface_destroy(surface)
        self.obj.g_object_unref(handle)
        if status:
            raise RuntimeError(f'Rendering failed for {source}: {status}')

def inline(source, prefix):
    # Unique accessible IDs throughout the standalone preview.
    return source.replace('id="title"',f'id="{prefix}-title"').replace('id="desc"',f'id="{prefix}-desc"').replace('aria-labelledby="title desc"',f'aria-labelledby="{prefix}-title {prefix}-desc"')

def preview():
    cards = []
    for direction,(letter,name,headline,description) in DIRECTIONS.items():
        panels = []
        for variant in ('dark','light'):
            lockup = inline(svg(direction,variant,'logo'),f'{direction}-{variant}-logo')
            icon32 = inline(svg(direction,variant,'icon'),f'{direction}-{variant}-32')
            icon96 = inline(svg(direction,variant,'icon'),f'{direction}-{variant}-96')
            panels.append(f'<div class="panel {variant}"><span class="swatch-label">{variant} / full color</span><div class="lockup">{lockup}</div><div class="sizes"><div class="size32">{icon32}</div><div class="size96">{icon96}</div><span>Actual 32 px<br>+ 96 px</span></div></div>')
        monos = ''.join(f'<div class="mono {v}">{inline(svg(direction,v,"logo"),direction+v)}</div>' for v in ('white','black'))
        cards.append(f'<article><div class="card-heading"><span class="letter">{letter}</span><div><h2>{name}</h2><p>{headline}</p></div></div><p class="description">{description}</p>{"".join(panels)}<div class="mono-pair">{monos}</div><div class="asset-note">SVG + PNG · four color treatments · three icon sizes</div></article>')
    hero_rows = []
    for direction,(_,name,_,_) in DIRECTIONS.items():
        heroes = ''.join('<div class="native-lockup">'+inline(svg(direction,v,'lockup'),f'{direction}-{v}-hero')+'</div>' for v in ('dark','light'))
        hero_rows.append(f'<h3>{escape(name)}</h3><div class="native-scroll">{heroes}</div>')
    hero_review = '<details class="hero-review"><summary>Inspect full-size tagline lockups</summary><p>Native 728 px artwork on dark and light. Scroll horizontally on smaller screens.</p>'+''.join(hero_rows)+'</details>'
    html = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CAP-VSAR — three logo directions</title><style>
:root{color-scheme:dark;--night:#111c28;--paper:#f4f1e8;--cyan:#72d4db;--green:#9cb99f;--orange:#ff8a42}*{box-sizing:border-box}body{margin:0;background:#0b141e;color:var(--paper);font-family:Arial,Helvetica,sans-serif;line-height:1.5}main{max-width:1680px;margin:auto;padding:60px 40px 32px}header{border-top:3px solid var(--orange);padding-top:26px;display:flex;justify-content:space-between;gap:40px;align-items:end;margin-bottom:38px}.eyebrow,.swatch-label,.asset-note,.letter,.meta{font-family:ui-monospace,monospace}.eyebrow{color:var(--cyan);font-size:12px;letter-spacing:.15em}h1{font-size:clamp(28px,3.2vw,48px);line-height:1.1;letter-spacing:-.04em;margin:15px 0 14px}header p{margin:0;color:#b9c7cf;max-width:620px}header aside{max-width:300px;color:var(--green);font-size:13px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}article{min-width:0;border:1px solid #30404e;border-radius:14px;overflow:hidden;background:#16232f}.card-heading{display:flex;gap:15px;align-items:center;padding:24px 24px 0}.letter{display:grid;place-items:center;border:1px solid #48616f;width:40px;height:40px;border-radius:50%;color:var(--cyan);flex-shrink:0}h2{font-size:24px;margin:0;letter-spacing:-.03em}.card-heading p{margin:0;color:var(--green);font-size:13px}.description{font-size:14px;color:#c0ccd3;min-height:92px;padding:0 24px;margin:18px 0 0}.panel{padding:18px 20px 22px}.panel.dark{background:var(--night)}.panel.light{background:var(--paper);color:#111c28}.swatch-label{text-transform:uppercase;font-size:10px;letter-spacing:.12em;opacity:.7}.lockup{padding:22px 0 24px}.lockup svg{width:100%;height:auto;display:block}.sizes{display:flex;align-items:center;gap:24px;min-height:96px}.sizes svg{display:block;width:100%;height:100%}.size32{width:32px;height:32px;flex:none}.size96{width:96px;height:96px;flex:none}.sizes span{font-family:ui-monospace,monospace;font-size:10px;opacity:.65}.mono-pair{display:grid;grid-template-columns:1fr 1fr}.mono{padding:12px}.mono.white{background:#111c28}.mono.black{background:#fff}.mono svg{display:block;width:100%;height:auto}.asset-note{font-size:9px;letter-spacing:.03em;color:#b0c0ca;padding:13px 18px}.recommendation{border-left:3px solid var(--orange);padding:6px 24px;margin:36px 0 30px;max-width:950px}.recommendation strong{color:var(--orange)}.recommendation p{margin:5px 0;color:#c1ced6;font-size:14px}footer{border-top:1px solid #30404e;padding-top:20px;color:#9eafb9;font-size:12px}.meta{font-size:10px;letter-spacing:.08em;color:var(--green);margin-bottom:8px}@media(max-width:1050px){main{padding:32px 20px}.grid{gap:14px}.card-heading{padding:18px 16px 0}.description{padding:0 16px;min-height:118px}.panel{padding:16px 12px}.sizes{gap:12px}.sizes span{font-size:9px}h2{font-size:21px}}@media(max-width:760px){header{display:block}header aside{max-width:100%;margin-top:20px}.grid{grid-template-columns:1fr}.description{min-height:0;margin-bottom:22px}.panel{padding:20px 24px}.lockup{max-width:640px}.sizes{gap:28px}.sizes span{font-size:11px}}@media print{body{background:#fff}main{padding:12px}header aside{color:#42694f}.grid{gap:12px}article{break-inside:avoid}.recommendation,footer{color:#111c28}}
</style></head><body><main><header><div><div class="eyebrow">CAP-VSAR / IDENTITY STUDY / 01</div><h1>One mission. Three directions.</h1><p>Virtual search-and-rescue training, from first bearing to a confident fix. Original marks for an ops room at night.</p></div><aside>Each direction includes a path-drawn wordmark, the full mission tagline, light and dark palettes, and white / black artwork.</aside></header><section class="grid" aria-label="Compare three logo directions">'''+''.join(cards)+'''</section><div class="recommendation"><div class="meta">RECOMMENDED / A</div><strong>Bearing — a signal becomes a position.</strong><p>The crossing bearings and orange fix communicate the core training task immediately. The open circular silhouette stays legible at favicon size and extends naturally into range rings, DF overlays, and maps.</p></div><footer><div class="meta">ORIGINAL ARTWORK · FONT-FREE SVG · LOCAL, STANDALONE PREVIEW</div>'''+DISCLAIMER+'''<br>All three are proposals for an unofficial simulator. No official insignia or third-party product marks are included.</footer></main></body></html>'''
    html = html.replace('Virtual search-and-rescue training, from first bearing to a confident fix. Original marks for an ops room at night.', TAGLINE+' Three original marks for an ops room at night.')
    html = html.replace('<div class="recommendation">',hero_review+'<div class="recommendation">')
    html = html.replace('@media(max-width:1050px)', '.hero-review{margin-top:28px;border:1px solid #30404e;border-radius:12px;padding:18px 20px}.hero-review summary{cursor:pointer;color:var(--cyan)}.hero-review p{color:#b9c7cf;font-size:13px}.hero-review h3{font-size:16px;margin:26px 0 10px}.native-scroll{display:flex;gap:16px;overflow-x:auto;padding-bottom:12px}.native-lockup{width:728px;flex:none}.native-lockup svg{display:block;width:728px;height:208px}@media(max-width:1050px)')
    (ROOT/'preview.html').write_text('\n'.join(line.rstrip() for line in html.splitlines())+'\n')

def contact_sheets():
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18)
    small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',12)
    sheet = Image.new('RGB',(1600,1210),'#09121c')
    draw = ImageDraw.Draw(sheet)
    draw.text((28,18),'CAP-VSAR / all directions, color treatments, and actual-size icons',fill='#f4f1e8',font=font)
    for col,(direction,(_,name,_,_)) in enumerate(DIRECTIONS.items()):
        x=20+col*530
        draw.text((x,66),name,fill='#ff8a42',font=font)
        for row,variant in enumerate(PALETTES):
            y=108+row*270
            bg = PALETTES[variant]['bg'] or ('#111C28' if variant=='white' else '#FFFFFF')
            panel = Image.new('RGBA',(510,250),bg)
            lock = Image.open(ROOT/direction/'png'/f'lockup-{variant}.png').convert('RGBA')
            lock.thumbnail((490,145),Image.Resampling.LANCZOS)
            panel.alpha_composite(lock,((510-lock.width)//2,12))
            for size,xx in [(32,20),(180,96),(512,285)]:
                icon = Image.open(ROOT/direction/'png'/f'icon-{variant}-{size}.png').convert('RGBA')
                if size > 32:
                    icon.thumbnail((90,90),Image.Resampling.LANCZOS)
                panel.alpha_composite(icon,(xx,148))
            sheet.paste(panel.convert('RGB'),(x,y))
            draw.text((x+375,y+183),variant,fill=PALETTES[variant]['ink'],font=small)
    sheet.save(ROOT/'qa-contact-sheet.png')
    hero = Image.new('RGB',(1504,980),'#09121c')
    d=ImageDraw.Draw(hero)
    for row,(direction,(_,name,_,_)) in enumerate(DIRECTIONS.items()):
        y=20+row*320
        d.text((24,y),name+' / native hero-size lockups',fill='#ff8a42',font=font)
        for col,variant in enumerate(('dark','light')):
            img=Image.open(ROOT/direction/'png'/f'lockup-{variant}.png').convert('RGB')
            hero.paste(img,(16+col*744,y+38))
    hero.save(ROOT/'qa-hero-lockups.png')

def main():
    renderer = Renderer()
    manifest=[]
    for direction in DIRECTIONS:
        folder=ROOT/direction
        (folder/'png').mkdir(parents=True,exist_ok=True)
        for variant in PALETTES:
            for kind in ('logo','icon','lockup'):
                source=folder/f'{kind}-{variant}.svg'
                source.write_text(svg(direction,variant,kind))
                tree=ET.fromstring(source.read_text())
                assert not any(e.tag.endswith('text') or e.tag.endswith('image') for e in tree.iter())
                sizes=[(n,n) for n in (32,180,512)] if kind=='icon' else [(728,208 if kind=='lockup' else 192)]
                for width,height in sizes:
                    target=folder/'png'/f'{kind}-{variant}{"-"+str(width) if kind=="icon" else ""}.png'
                    renderer.render(source,target,width,height)
                    manifest.append(dict(source=str(source.relative_to(ROOT)),png=str(target.relative_to(ROOT)),width=width,height=height))
    preview()
    contact_sheets()
    (ROOT/'export-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Generated 36 SVGs, {len(manifest)} PNG exports, standalone preview and two QA sheets.')

if __name__=='__main__':
    main()
