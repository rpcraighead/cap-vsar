"""Generate scalable base-radio faceplates from CAP ICUT control references.

Live text and functional hit regions are overlaid by mission-radio.html/js.
Coordinates use a shared 960x340 instrument surface. No frequencies are baked in.
"""
from pathlib import Path
import math

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'services/exercise/app/static/radio-art'
DEFS = '''<defs>
 <linearGradient id="case" x2="0" y2="1"><stop stop-color="#454748"/><stop offset=".5" stop-color="#303334"/><stop offset="1" stop-color="#232628"/></linearGradient>
 <linearGradient id="rubber" x2=".4" y2="1"><stop stop-color="#353a3b"/><stop offset=".4" stop-color="#202425"/><stop offset="1" stop-color="#101314"/></linearGradient>
 <radialGradient id="knob" cx=".35" cy=".25" r=".8"><stop stop-color="#3b4141"/><stop offset=".8" stop-color="#202526"/><stop offset="1" stop-color="#101516"/></radialGradient>
 <linearGradient id="steel" x2=".8" y2="1"><stop stop-color="#707676"/><stop offset=".48" stop-color="#323839"/><stop offset="1" stop-color="#131818"/></linearGradient>
 <linearGradient id="lcd" x2="0" y2="1"><stop stop-color="#c5cd98"/><stop offset="1" stop-color="#a3b46d"/></linearGradient>
 <pattern id="grain" width="3" height="3" patternUnits="userSpaceOnUse"><path d="M0 0h1v1H0z" fill="#fff" opacity=".035"/><path d="M2 2h1v1H2z" fill="#000" opacity=".08"/></pattern>
</defs>'''


def knob(cx,cy,r):
 pts=[]
 for i in range(240):
  a=i*math.tau/240;rr=r*(.968+.032*math.cos(12*a));pts.append(f'{cx+rr*math.cos(a):.2f},{cy+rr*math.sin(a):.2f}')
 return f'<circle cx="{cx}" cy="{cy+2}" r="{r+3}" fill="#111617"/><polygon points="{" ".join(pts)}" fill="url(#steel)" stroke="#141819" stroke-width="2"/><circle cx="{cx}" cy="{cy}" r="{r*.79}" fill="url(#knob)" stroke="#363c3d" stroke-width="1.2"/>'


def screw(x,y):
 return f'<circle cx="{x}" cy="{y}" r="16" fill="#1a1e1f"/><circle cx="{x}" cy="{y}" r="10" fill="url(#steel)"/><path d="M{x-5} {y-5}l10 10m0-10l-10 10" stroke="#0e1213" stroke-width="3"/>'


def key(x,y,w,h,label='',color='#262c2e'):
 return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="#111617" stroke="#505655"/><rect x="{x+3}" y="{y+3}" width="{w-6}" height="{h-6}" rx="7" fill="{color}"/><path d="M{x+10} {y+5}h{w-20}" stroke="#69706c" opacity=".4"/>'+text(x+w/2,y+h/2+5,label,15,'#28312b' if color=='#bcc3ba' else '#cbd0ca')


def text(x,y,label,size=15,color='#cbd0ca'):
 return f'<text x="{x}" y="{y}" text-anchor="middle" font-family="Arial,sans-serif" font-size="{size}" fill="{color}">{label}</text>'


def draw(model):
 s=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 340" role="img">',f'<title>{model} reference-inspired training faceplate</title>',DEFS]
 s+=['<rect x="6" y="9" width="948" height="324" rx="30" fill="#101416"/>','<rect x="10" y="7" width="940" height="320" rx="28" fill="url(#case)" stroke="#626866" stroke-width="1.5"/>','<rect x="12" y="9" width="936" height="316" rx="26" fill="url(#grain)"/>']
 for x,y in [(43,42),(917,42),(43,292),(917,292)]:s.append(screw(x,y))
 if model=='Motorola APX 4500':
  s+=['<rect x="186" y="24" width="358" height="286" rx="20" fill="#1a1e20" stroke="#505554" stroke-width="2"/>',text(365,52,'MOTOROLA',20),'<rect x="203" y="65" width="324" height="158" rx="3" fill="#d1d5cf" stroke="#0a0e0e" stroke-width="5"/>']
  for i in range(4):s.append(key(199+i*84,244,76,52));s.append(f'<rect x="{219+i*84}" y="267" width="36" height="7" rx="3" fill="#9caeb9"/>')
  s.append('<circle cx="116" cy="77" r="29" fill="#111617" stroke="#555d5a" stroke-width="2"/><circle cx="116" cy="77" r="22" fill="url(#rubber)"/><path d="M116 62v14m-10-10a16 16 0 1 0 20 0" stroke="#52b7a0" fill="none" stroke-width="4" stroke-linecap="round"/>')
  for i in range(3):s.append(f'<rect x="96" y="{128+i*19}" width="40" height="10" rx="5" fill="#677171" stroke="#222a2b"/>')
  s.append('<circle cx="116" cy="242" r="43" fill="url(#steel)"/><circle cx="116" cy="242" r="32" fill="#181d1e" stroke="#565d5b" stroke-width="3"/>')
  for i in range(8):
   a=i*math.tau/8;s.append(f'<circle cx="{116+20*math.cos(a):.2f}" cy="{242+20*math.sin(a):.2f}" r="3.8" fill="#090e0f"/>')
  for y,label in [(65,'▲'),(127,'▼')]:s.append(key(558,y,50,55,label))
  for y,label in [(224,'☼'),(282,'⌂')]:s.append(f'<circle cx="583" cy="{y}" r="22" fill="url(#rubber)" stroke="#565d59"/>'+text(583,y+7,label,25))
  for y in [91,160,229]:s.append(f'<rect x="643" y="{y}" width="152" height="32" rx="16" fill="#151a1b" stroke="#525957" stroke-width="2"/><rect x="651" y="{y+6}" width="136" height="20" rx="10" fill="url(#rubber)"/>')
  s.append('<circle cx="836" cy="75" r="27" fill="#171d1e" stroke="#59605d"/><circle cx="836" cy="75" r="20" fill="#d36729"/>')
  s.append(knob(838,244,51));s.append(text(720,299,'APX 4500 · O2',13,'#8e9994'))
 else:
  s.append('<rect x="166" y="22" width="546" height="292" rx="9" fill="#222728" stroke="#535957"/>')
  for i,label in enumerate(['ZONE','SCAN','SQL','MON','HOME']):s.append(key(180+i*103,32,94,50,label,'#bcc3ba'))
  s.append('<rect x="177" y="104" width="524" height="98" rx="5" fill="url(#lcd)" stroke="#111716" stroke-width="7"/>')
  s.append('<circle cx="85" cy="62" r="6" fill="#435d4b"/>');s.append(key(41,109,88,45,'EMER','#993829'))
  s.append('<circle cx="82" cy="246" r="39" fill="url(#steel)"/><circle cx="82" cy="246" r="29" fill="#121718" stroke="#606966" stroke-width="2"/>')
  for i in range(6):
   a=i*math.tau/6;s.append(f'<circle cx="{82+18*math.cos(a):.2f}" cy="{246+18*math.sin(a):.2f}" r="4" fill="#090d0d"/>')
  s.append(knob(326,258,41));s.append(knob(611,258,41))
  s += [text(224,271,'ON/OFF',15),text(515,271,'SELECT',15)]
  for i in range(12):s.append(f'<rect x="744" y="{70+i*16}" width="141" height="7" rx="3" fill="#111617"/><path d="M750 {78+i*16}h130" stroke="#4c5351" opacity=".6"/>')
  s.append(text(812,299,'EFJOHNSON 5300',14,'#c6cec6'))
 s.append('</svg>');return '\n'.join(s)


if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True)
 for slug,name in [('apx4500','Motorola APX 4500'),('efj5300','EFJohnson 5300')]:
  (OUT/(slug+'.svg')).write_text(draw(name));print(OUT/(slug+'.svg'))
