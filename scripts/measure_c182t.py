#!/usr/bin/env python3
"""Offline CAP 487 landmark metrology. Outputs contain measurements, not mesh data."""
from __future__ import annotations
import argparse
import html
import json
import math
from pathlib import Path

import convert_flightgear_c182 as converter
from fetch_flightgear_c182 import DEFAULT_DONOR, DONOR_ARCHIVE_SHA256, DONOR_COMMIT, validate_donor, sha256

MASTER = Path(__file__).with_name('c182t_dimension_master.json')
# Donor-native OBJ8 axes: right, up, aft. These selectors are NOT sourced FS.
SELECTORS = {
 'spinner_apex': ('chrome_spinner', 2, 'min', None),
 'rudder_trailing_edge': ('Rudder', 2, 'max', None),
 'fin_cap': ('Airframe', 1, 'max', None),
 'beacon_top': ('BeaconOff', 1, 'max', None),
 'strobe_left': ('Strobe', 0, 'min', None),
 'strobe_right': ('Strobe', 0, 'max', None),
 'wing_left': ('Airframe', 0, 'min', None),
 'wing_right': ('Airframe', 0, 'max', None),
 # Airframe contains fixed stabilizer; isolate the aft outboard region. This
 # window selects a named feature, not a published station or a hinge target.
 'tail_left': ('Airframe', 0, 'min', 'aft_outboard'),
 'tail_right': ('Airframe', 0, 'max', 'aft_outboard'),
}
WHEELS = {'main_left':'MainWheel.L', 'main_right':'MainWheel.R', 'nose':'FrontWheel'}


def units(value):
    if not math.isfinite(value):
        raise ValueError('Non-finite measurement')
    inches = abs(value) / .0254
    feet = math.floor(inches / 12)
    return {'m': value, 'ft': value / .3048, 'in': value / .0254,
            'feet_inches': f"{'-' if value < 0 else ''}{feet} ft {inches-feet*12:.3f} in"}


def vector(point):
    return {axis: units(v) for axis, v in zip(('right','up','aft'), point)}


def points(obj):
    indices = sorted({ref.vertex for surf in obj.surfaces for ref in surf.refs})
    if not indices or any(i < 0 or i >= len(obj.vertices) for i in indices):
        raise ValueError(f'Empty/invalid landmark object: {obj.name}')
    result = [converter.ac_to_xplane(obj.vertices[i]) for i in indices]
    if any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in result):
        raise ValueError(f'Non-finite geometry: {obj.name}')
    return result


def bounds(pts):
    if not pts: raise ValueError('Empty bounds selection')
    return [[min(p[i] for p in pts),max(p[i] for p in pts)] for i in range(3)]


def center(pts):
    return tuple((a+b)/2 for a,b in bounds(pts))


def extract(objects):
    """Reduce strictly parsed donor to a license-safe numeric landmark fixture."""
    converter.assert_all_objects_classified(objects)
    names = [o.name for o in objects]
    if len(names)!=len(set(names)): raise ValueError('Duplicate donor object name')
    by_name = {o.name:o for o in objects}
    required = {s[0] for s in SELECTORS.values()} | set(WHEELS.values()) | {'Blade1','Blade2','Blade3'}
    missing = required-set(names)
    if missing: raise ValueError('Required landmark objects missing: '+', '.join(sorted(missing)))
    landmarks = {}
    for key,(name,axis,extreme,region) in SELECTORS.items():
        pts = points(by_name[name])
        if region == 'aft_outboard':
            pts = [p for p in pts if 4 < p[2] < 6.3 and abs(p[0]) > 1.5 and .2 < p[1] < .7]
        if not pts: raise ValueError('Required landmark selector empty: '+key)
        value = (min if extreme=='min' else max)(p[axis] for p in pts)
        selected = [p for p in pts if abs(p[axis]-value)<1e-8]
        landmarks[key] = {'point_m':center(selected), 'object':name,
            'selector':f'{extreme} axis {axis}; region={region}; midpoint of tied extrema'}
    for key,name in WHEELS.items():
        pts=points(by_name[name]); c=center(pts)
        landmarks[key+'_axle']={'point_m':c, 'object':name,'selector':'midpoint of tire referenced-vertex bounds'}
        # Wheel centers from symmetric tire bounds; ground contact below center.
        landmarks[key+'_contact']={'point_m':(c[0],min(p[1] for p in pts),c[2]),
            'object':name,'selector':'tire lowest up ordinate at axle right/aft; nominal mesh contact'}
    rotation=converter.PROP_ROTATION
    axis=rotation.axis; hub=rotation.center
    radius=0.
    for name in ('Blade1','Blade2','Blade3'):
        for p in points(by_name[name]):
            d=[p[i]-hub[i] for i in range(3)]
            dot=sum(d[i]*axis[i] for i in range(3))
            radius=max(radius,math.sqrt(max(0.,sum(x*x for x in d)-dot*dot)))
    landmarks['prop_hub']={'point_m':hub,'object':'Models/c182t.xml / converter.PROP_ROTATION',
        'selector':'existing converter propeller rotation axis, not blade extrema'}
    # Mirror the converter's actual current selections; include light billboards
    # in all-rendered bounds, but never in structural bounds.
    rendered=[o for o in objects if (o.texture=='Default.png' and o.name not in
        (converter.PROP_NAMES|{'Blade1.001','Blade2.001','Blade3.001','Spinner','WinterKit'}))
        or o.name in converter.PROP_NAMES|converter.GLASS_NAMES|{converter.PROP_BLUR_NAME}
        or o.texture=='Lights.png']
    structural=[o for o in rendered if o.texture=='Default.png' and o.name!='Navlight']
    def group(objs):
        return {'objects':sorted(o.name for o in objs),'bounds_m':bounds([p for o in objs for p in points(o)])}
    return {'schema_version':1,'donor_archive_sha256':DONOR_ARCHIVE_SHA256,'donor_commit':DONOR_COMMIT,
        'landmarks':landmarks,'prop_axis':axis,'prop_radius_m':radius,
        'bounds':{'structural':group(structural),'all_rendered':group(rendered)},
        'known_unconverted':sorted(converter.KNOWN_UNCONVERTED)}


def pose_for(landmarks):
    left=landmarks['main_left_contact']['point_m']; right=landmarks['main_right_contact']['point_m']
    pivot=tuple((a+b)/2 for a,b in zip(left,right))
    nose=landmarks['nose_contact']['point_m']
    # Rotate about transverse main-wheel axis; keep wings level (no roll).
    theta=math.atan(-(nose[1]-pivot[1])/(nose[2]-pivot[2]))
    c,s=math.cos(theta),math.sin(theta)
    def pose(p):
        y,z=p[1]-pivot[1],p[2]-pivot[2]
        return (p[0],c*y+s*z,pivot[2]-s*y+c*z)
    return theta,pivot,pose


def check_symmetry(landmarks, tolerance_m=.01):
    for a,b in [('main_left_axle','main_right_axle'),('wing_left','wing_right'),
                ('strobe_left','strobe_right'),('tail_left','tail_right')]:
        l=landmarks[a]['point_m'];r=landmarks[b]['point_m']
        error=max(abs(l[0]+r[0]),abs(l[1]-r[1]),abs(l[2]-r[2]))
        if error > tolerance_m: raise ValueError(f'Left/right symmetry broken: {a}/{b}, {error:.6f} m')


def report(fixture, master):
    if fixture['donor_archive_sha256']!=DONOR_ARCHIVE_SHA256: raise ValueError('Fixture donor pin mismatch')
    lm=fixture['landmarks']
    expected=set(SELECTORS)|{k+s for k in WHEELS for s in ('_axle','_contact')}|{'prop_hub'}
    if set(lm)!=expected: raise ValueError('Required landmark set changed')
    check_symmetry(lm)
    theta,pivot,pose=pose_for(lm)
    posed={k:pose(v['point_m']) for k,v in lm.items()}
    axis=fixture['prop_axis']; norm=math.sqrt(sum(x*x for x in axis))
    if abs(norm-1)>1e-6: raise ValueError('Prop axis must be unit length')
    radius=fixture['prop_radius_m']
    if not math.isfinite(radius) or radius<=0: raise ValueError('Invalid prop radius')
    axis_up=math.cos(theta)*axis[1]+math.sin(theta)*axis[2]
    values={
        'overall_length':posed['rudder_trailing_edge'][2]-posed['spinner_apex'][2],
        'wing_span':posed['strobe_right'][0]-posed['strobe_left'][0],
        'overall_height':max(posed['beacon_top'][1],posed['fin_cap'][1]),
        'main_wheel_track':posed['main_right_axle'][0]-posed['main_left_axle'][0],
        'wheel_base':(posed['main_left_axle'][2]+posed['main_right_axle'][2])/2-posed['nose_axle'][2],
        'propeller_diameter':2*radius,
        'horizontal_tail_span':posed['tail_right'][0]-posed['tail_left'][0],
        'propeller_ground_clearance':posed['prop_hub'][1]-radius*math.sqrt(max(0.,1-axis_up**2)),
    }
    comparisons=[]
    for target in master['targets']:
        key=target['id']; item={'id':key,'source':target['source'],'page':target['page']}
        if key not in values:
            item.update(status='unmeasured',reason=target['applies_to'],measured=None)
            comparisons.append(item);continue
        measured=values[key];target_m=target['value_m']
        if key=='propeller_diameter':
            lo=target['limit_min_m'];hi=target['limit_max_in']*.0254
        else:
            tol=target.get('tolerance_proposed_in',0)*.0254 or target_m*target['tolerance_proposed_pct']/100
            lo,hi=target_m-tol,target_m+tol
        numeric='within_bounds' if lo<=measured<=hi else 'outside_bounds'
        reasons=[]
        if key in ('overall_length','overall_height','wheel_base','propeller_ground_clearance'):
            reasons.append('Wheel-contact ground pose; POH two-inch nose-strut extension unverified')
        if key=='wing_span' and 'Strobe' in fixture['known_unconverted']:
            reasons.append('Strobe is absent from emitted package; donor span only, package target unmeasured')
        if key=='overall_height' and 'BeaconOff' in fixture['known_unconverted']:
            reasons.append('BeaconOff is absent from emitted package; donor fin/beacon height only')
        item.update(measured=units(measured),target=units(target_m),error=units(measured-target_m),
                    error_pct=(measured-target_m)/target_m*100,bounds={'min':units(lo),'max':units(hi)},
                    numeric_result=numeric,status=('provisional' if reasons else ('pass' if numeric=='within_bounds' else 'fail')),
                    reasons=reasons, acceptance='certification_bound' if key=='propeller_diameter' else 'proposed_tolerance_not_ratified')
        comparisons.append(item)
    # No absolute donor-to-FS registration has been proven. All source stations
    # are shown as reference-only; loading arms and MAC are not mesh vertices.
    stations=[{**s,'target':units(s['fs_m']),'measured':None,'status':'unmeasured',
        'reason':'No validated donor firewall datum and named feature selector; reference station only'} for s in master['stations']['entries']]
    return {'aircraft':'CAP 487','schema_version':1,'donor_archive_sha256':fixture['donor_archive_sha256'],
        'ground_pose':{'pitch_deg':math.degrees(theta),'pivot_native':vector(pivot),
            'status':'provisional_contact_plane','nose_strut_extension':'unverified',
            'main_contact_residual_m':max(abs(posed[k+'_contact'][1]) for k in ('main_left','main_right'))},
        'landmarks':{k:{'native':vector(v['point_m']),'ground_pose':vector(posed[k]),
                          'object':v['object'],'selector':v['selector']} for k,v in lm.items()},
        'propeller':{'axis_native':axis,'radius':units(radius),'axis_up_ground_pose':axis_up},
        'bounds':{k:{'objects':v['objects'],'native':{a:{'min':units(b[0]),'max':units(b[1])}
            for a,b in zip(('right','up','aft'),v['bounds_m'])}} for k,v in fixture['bounds'].items()},
        'comparisons':comparisons,'stations':stations,
        'unknowns':[{**u,'status':'unmeasured','measured':None} for u in master['unknown']],
        'release_acceptance':False}


def assert_accepted(result, accepted):
    by_id={c['id']:c for c in result['comparisons']}
    for name in accepted:
        if name not in by_id or by_id[name]['status']!='pass':
            raise ValueError('Accepted dimension regression: '+name)


def write_overlays(result, directory):
    """Vector metrology diagrams: landmarks/bounds only, no donor mesh or textures."""
    for view,axes in [('side',('aft','up')),('front',('right','up')),('top',('aft','right'))]:
        parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1500" height="1750" viewBox="0 0 1500 1750">',
               '<rect width="1500" height="1750" fill="#111827"/>',
               '<g fill="#e5e7eb" font-family="monospace" font-size="14">',
               f'<text x="30" y="30">CAP 487 | {view.upper()} | measured landmarks (cyan), bounds listed below | amber=target, cyan=measured | units in JSON</text>',
               '<text x="30" y="55">Ground pose provisional; no mesh correction. Source FS stations are reference-only, not aligned to donor.</text>']
        # Equal horizontal/vertical metric scale within each orthographic panel.
        coords = [lm['ground_pose'] for lm in result['landmarks'].values()]
        xmin = min(p[axes[0]]['m'] for p in coords)
        xmax = max(p[axes[0]]['m'] for p in coords)
        ymin = min(p[axes[1]]['m'] for p in coords)
        ymax = max(p[axes[1]]['m'] for p in coords)
        scale = min(700 / (xmax-xmin), 250 / (ymax-ymin))
        def project(p):
            return (60 + scale*(p[axes[0]]['m']-xmin),
                    340 - scale*(p[axes[1]]['m']-ymin))
        # Native bounds are listed separately from ground-posed landmarks.
        for j,(group,b) in enumerate(result['bounds'].items()):
            text=f"{group} NATIVE bounds: "+"; ".join(f"{a} {b['native'][a]['min']['m']:.3f}..{b['native'][a]['max']['m']:.3f} m" for a in ('right','up','aft'))
            parts.append(f'<text x="30" y="{410+j*23}">{html.escape(text)}</text>')
        label_positions=[]
        for index,(name,lm) in enumerate(result['landmarks'].items()):
            x,y=project(lm['ground_pose'])
            lx,ly=x+9,y-6
            while any(abs(lx-a)<18 and abs(ly-b)<13 for a,b in label_positions):
                ly+=14
            label_positions.append((lx,ly))
            parts.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="3" fill="#67e8f9"/><line x1="{x:.3f}" y1="{y:.3f}" x2="{lx:.3f}" y2="{ly:.3f}" stroke="#4b5563"/><text x="{lx:.3f}" y="{ly:.3f}" font-size="10">{index+1}</text>')
        for index,name in enumerate(result['landmarks']):
            parts.append(f'<text x="850" y="{85+index*17}" font-size="12">{index+1}: {html.escape(name)}</text>')
        # Dimension bars overlay target (amber) and measured (cyan) on a common
        # local zero. They compare separations only, never invent absolute FS.
        relevant={'side':['overall_length','wheel_base','propeller_ground_clearance'],
                  'front':['wing_span','main_wheel_track','overall_height','propeller_diameter'],
                  'top':['horizontal_tail_span','overall_length','wing_span']}[view]
        for j,key in enumerate(relevant):
            c=next(c for c in result['comparisons'] if c['id']==key)
            y=465+j*20
            parts.append(f'<text x="30" y="{y+4}" font-size="11">{key}</text>')
            for dy,value,color in [(-3,c['target']['m'],'#fbbf24'),(3,c['measured']['m'],'#67e8f9')]:
                parts.append(f'<line x1="270" y1="{y+dy}" x2="{270+value*65:.3f}" y2="{y+dy}" stroke="{color}" stroke-width="3"/>')
        parts.append('<text x="30" y="570">TARGET COMPARISONS: donor measurements; missing emitted lights prevent package acceptance</text>')
        for i,c in enumerate(result['comparisons']):
            if c['measured'] is None: line=f"{c['id']}: UNMEASURED - {c['reason']}"
            else:
                line=(f"{c['id']}: {c['status'].upper()} | target {c['target']['m']:.4f} m | measured {c['measured']['m']:.4f} m "
                      f"({c['measured']['feet_inches']}) | error {c['error']['m']:+.4f} m | bounds {c['bounds']['min']['m']:.4f}..{c['bounds']['max']['m']:.4f} m")
            parts.append(f'<text x="30" y="{600+i*24}">{html.escape(line)}</text>')
        parts.append('<text x="30" y="875">SOURCE STATION LADDER (FS inches aft of firewall); all measured FS = UNMEASURED</text>')
        for i,s in enumerate(result['stations']):
            line=f"FS {s['fs_in']:7.2f} in / {s['fs_m']:.4f} m: {s['feature']}"
            parts.append(f'<text x="30" y="{903+i*21}">{html.escape(line)}</text>')
        parts.append('<text x="30" y="1245">FS REFERENCE RULER: inches aft of firewall; donor alignment UNKNOWN</text>')
        parts.append('<line x1="60" y1="1320" x2="1400" y2="1320" stroke="#fbbf24"/>')
        for i,s in enumerate(result['stations']):
            x=170+s['fs_in']*6.5
            parts.append(f'<line x1="{x:.2f}" y1="1310" x2="{x:.2f}" y2="1330" stroke="#fbbf24"/><text x="{x:.2f}" y="{1350+(i%3)*15}" font-size="10">{s["fs_in"]}</text>')
        parts.append('<text x="30" y="1440">UNKNOWN TARGETS: fail closed, no substitute coordinates</text>')
        for i,u in enumerate(result['unknowns']):
            parts.append(f'<text x="30" y="{1465+i*24}">{html.escape(u["item"])}: UNMEASURED</text>')
        parts.append('</g></svg>')
        (directory/f'{view}.svg').write_text('\n'.join(parts)+'\n')


def load_donor(path):
    validate_donor(path)
    root=converter.AC3DParser((path/'Models/c182s.ac').read_text(errors='strict')).parse()
    return [o for o in converter.flatten(root) if o.kind=='poly' and o.surfaces]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--donor',type=Path,default=DEFAULT_DONOR)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--fixture',type=Path,help='Replay derived numeric fixture without any donor access')
    parser.add_argument('--write-fixture',type=Path)
    args=parser.parse_args()
    fixture=json.loads(args.fixture.read_text()) if args.fixture else extract(load_donor(args.donor))
    result=report(fixture,json.loads(MASTER.read_text()))
    result['master_sha256']=sha256(MASTER)
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'report.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    write_overlays(result,args.output)
    if args.write_fixture:
        args.write_fixture.parent.mkdir(parents=True,exist_ok=True)
        args.write_fixture.write_text(json.dumps(fixture,indent=2,sort_keys=True,allow_nan=False)+'\n')
    for c in result['comparisons']:
        print(c['id'],c['status'],c.get('numeric_result',''), c['measured']['feet_inches'] if c['measured'] else '')

if __name__=='__main__':main()
