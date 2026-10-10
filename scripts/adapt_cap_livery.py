#!/usr/bin/env python3
"""Locally remap the downloaded Laminar C172 CAP paint onto the C182 prototype.

No generative painting and no changes to geometry or flight model. Requires
numpy, scipy and Pillow. Donor artwork and generated assets stay outside Git.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, map_coordinates, maximum_filter


def mesh(path):
    vertices, indices, faces = [], [], []
    name = path.stem
    for line in path.read_text().splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == 'VT':
            vertices.append(tuple(map(float, p[1:])))
        elif p[0] in ('IDX', 'IDX10'):
            indices.extend(map(int, p[1:]))
        elif p[0] == '#':
            name = ' '.join(p[1:])
        elif p[0] == 'TRIS':
            start, count = map(int, p[1:3])
            faces.extend((name, indices[i:i+3]) for i in range(start, start+count, 3))
    return np.array(vertices), faces


def raster(coords, width, height):
    """Yield covered pixel centers and their barycentric weights."""
    lo = np.maximum(np.floor(coords.min(0)).astype(int), 0)
    hi = np.minimum(np.ceil(coords.max(0)).astype(int), [width-1, height-1])
    if np.any(hi < lo):
        return None
    a, b, c = coords
    cross = lambda u, v: u[...,0]*v[...,1]-u[...,1]*v[...,0]
    det = cross(b-a, c-a)
    if abs(det) < 1e-7:
        return None
    yy, xx = np.mgrid[lo[1]:hi[1]+1, lo[0]:hi[0]+1]
    p = np.stack([xx+.5, yy+.5], -1)
    w1 = cross(p-a, c-a)/det
    w2 = cross(b-a, p-a)/det
    w0 = 1-w1-w2
    good = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
    return yy[good], xx[good], np.stack([w0[good], w1[good], w2[good]], -1)


def sample(image, uv):
    h, w = image.shape[:2]
    coords = np.array([(1-uv[:, 1])*h-.5, uv[:, 0]*w-.5])
    return np.stack([map_coordinates(image[:, :, c], coords, order=1, mode='nearest') for c in range(3)], -1)


def project(vertices, faces, image, axes, depth_axis, sign, bounds, density=400, wing_only=False, minimum_normal=.15):
    """Orthographic color projection, with a depth buffer for exterior surfaces."""
    low, high = np.array(bounds[0]), np.array(bounds[1])
    width, height = np.ceil((high-low)*density).astype(int)
    result = np.zeros((height, width, 3), np.uint8)
    depth = np.full((height, width), -np.inf, np.float32)
    for _, ids in faces:
        v = vertices[ids]
        if v[:, depth_axis+3].mean()*sign < minimum_normal:
            continue
        # Wing projections exclude the horizontal tail and wing struts.
        if wing_only and (v[:, 2].mean() > 3 or v[:, 1].mean() < .3):
            continue
        r = raster((v[:, axes]-low)*density, width, height)
        if r is None:
            continue
        yy, xx, weights = r
        z = weights@v[:, depth_axis]*sign
        closer = z > depth[yy, xx]
        yy, xx, weights, z = yy[closer], xx[closer], weights[closer], z[closer]
        result[yy, xx] = sample(image, weights@v[:, 6:8])
        depth[yy, xx] = z
    valid = np.isfinite(depth)
    if not valid.any():
        raise ValueError('Empty donor projection')
    nearest = distance_transform_edt(~valid, return_distances=False, return_indices=True)
    result[~valid] = result[tuple(nearest[:, ~valid])]
    return result, low, density


def projected_sample(projection, points):
    image, low, density = projection
    coords = ((points-low)*density-.5).T[::-1]
    return np.stack([map_coordinates(image[:, :, c], coords, order=1, mode='nearest') for c in range(3)], -1)


def adapt(args):
    args.output.mkdir(parents=True, exist_ok=True)
    fv, ff = mesh(args.c172/'objects/fuselage.obj')
    wv, wf = mesh(args.c172/'objects/wings.obj')
    gv, gf = mesh(args.c172/'objects/fuselage_gear.obj')
    fuselage = np.array(Image.open(args.source/'objects/fuselage.dds').convert('RGB'))
    wings = np.array(Image.open(args.source/'objects/wings.dds').convert('RGB'))
    side = {sign: project(fv, ff, fuselage, [2, 1], 0, sign, [[-1.5,-1], [7,2]]) for sign in [-1,1]}
    # Exclude emissive light/glass triangles between the main shell and controls.
    # Those project white lamp cutouts over the otherwise continuous wing paint.
    wf = wf[:15780//3] + wf[21438//3:]
    wing = {sign: project(wv, wf, wings, [0, 2], 1, sign, [[-5.6,.1], [5.6,2.5]], wing_only=True) for sign in [-1,1]}
    belly = project(fv, ff, fuselage, [0,2], 1, -1, [[-.7,-1.2],[.7,6.8]], density=500, minimum_normal=.95)
    Image.fromarray(belly[0]).save(args.output/'donor-belly.png')
    gear = {}
    for key, is_nose in [('nose',True),('main',False)]:
        selected = [(name,ids) for name,ids in gf if (abs(gv[ids,0].mean())<.2)==is_nose]
        gear[key] = project(gv, selected, fuselage, [2,1], 0, -1, [[-.8,-1.3],[2.1,-.5]], density=600)
    for sign, projection in side.items():
        Image.fromarray(projection[0][::-1]).save(args.output/f'donor-side-{sign}.png')
    for sign, projection in wing.items():
        Image.fromarray(projection[0][::-1]).save(args.output/f'donor-wing-{sign}.png')
    original = np.array(Image.open(args.base).convert('RGB'))
    result = original.copy()
    h, w = result.shape[:2]
    painted = np.zeros((h,w), bool)
    vertices, faces = mesh(args.aircraft/'objects/flightgear_c182t.obj')
    for name, ids in faces:
        v = vertices[ids]
        center = v[:, :3].mean(0)
        kind = None
        if name == 'Airframe' or name in ['Door.L','Door.R','BaggageDoor','Rudder','WindowFrame.L','WindowFrame.R']:
            kind = 'side'
            if abs(center[0]) > .67:
                kind = 'wing' if center[1] > .6 and center[2] < 2.5 else 'white'
            if center[1] > .65 and .4 < center[2] < 2.4 and abs(center[0]) < .67:
                kind = None  # C182 cabin roof; no donor paint/antenna projection.
            if center[2] > 4.5 and abs(center[0]) > .4 and center[1] < .6:
                kind = 'white'
            if kind == 'side' and v[:,4].mean() < -.85 and center[1] < .2:
                kind = 'belly'
        elif name.startswith(('Aileron','Flap.')):
            kind = 'wing'
        elif name.startswith('WheelFairing'):
            kind = 'gear'
        elif name.startswith('CowlFlap'):
            kind = 'belly'
        elif name.startswith(('Elevator','MainStrut')):
            kind = 'white'
        if kind is None:
            continue
        r = raster(v[:,6:8]*[w,-h]+[0,h], w, h)
        if r is None:
            continue
        yy, xx, weights = r
        p = weights@v[:,:3]
        if kind == 'side':
            sign = -1 if center[0] < 0 else 1
            source_z = np.interp(p[:,2], [-1.24,.64,1.58,4,6.8], [-1.07,.50,1.60,4,6.78])
            source_y = p[:,1] - .10 - .055*np.maximum(p[:,2]-1, 0)
            color = projected_sample(side[sign], np.c_[source_z, source_y])
            # The C182 owns the window openings. Do not paint C172 windows over them.
            window = (p[:,1] > .13) & (p[:,2] < 3) & (color.max(1)-color.min(1)<35) & (color.max(1)<100)
            color[window] = [240,241,238]
        elif kind == 'wing':
            sign = 1 if v[:,4].mean() >= 0 else -1
            source_z = np.interp(p[:,2], [.62,2.16], [.38,1.86])
            # The C172 has a leading-edge lamp recess absent from this C182 mesh.
            # Extend adjacent donor paint over it, retaining the C182's own lamps.
            lamp = (p[:,0] > -3.25) & (p[:,0] < -2.25) & (source_z < .70)
            source_z[lamp] = .70
            color = projected_sample(wing[sign], np.c_[p[:,0], source_z])
        elif kind == 'belly':
            source_z = np.interp(p[:,2], [-1.24,.64,1.58,4,6.8], [-1.07,.50,1.60,4,6.78])
            color = projected_sample(belly, np.c_[p[:,0]*.65,source_z])
        elif kind == 'gear':
            nose = name == 'WheelFairingNose'
            source_z = np.interp(p[:,2], [-.58,.25] if nose else [1.01,1.84], [-.635,.135] if nose else [.949,1.899])
            source_y = np.interp(p[:,1], [-1.1,-.76] if nose else [-.92,-.57], [-1.11,-.84] if nose else [-1.04,-.73])
            color = projected_sample(gear['nose' if nose else 'main'], np.c_[source_z,source_y])
        else:
            # Retain the C182's rivets and panel shading on unpainted white parts.
            color = original[yy,xx]
        result[yy,xx] = color
        painted[yy,xx] = True
    # Four-pixel bleed guards the atlas seams during mipmap filtering.
    nearest = distance_transform_edt(~painted, return_distances=False, return_indices=True)
    bleed = maximum_filter(painted, size=9) & ~painted
    result[bleed] = result[tuple(nearest[:,bleed])]
    destination = args.output/'objects/flightgear_c182t.png'
    destination.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(result).save(destination)
    inputs = [args.source/'objects/fuselage.dds', args.source/'objects/wings.dds',
              args.c172/'objects/fuselage.obj', args.c172/'objects/wings.obj',
              args.c172/'objects/fuselage_gear.obj',
              args.aircraft/'objects/flightgear_c182t.obj', args.base, Path(__file__)]
    archive = args.source.with_suffix('.zip')
    if archive.exists():
        inputs.append(archive)
    manifest = {'source_livery': str(args.source), 'source_registration':'N429CP',
                'source_note':'Reused the existing downloaded Civil Air Patrol.zip. Original author and download URL were not included in the archive.',
                'method':'Deterministic projection of C172 artwork through source and destination mesh coordinates',
                'aircraft_geometry_modified':False,'texture_size':[w,h],
                'arguments':{k:str(v) for k,v in vars(args).items()},
                'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
                'output_sha256':hashlib.sha256(destination.read_bytes()).hexdigest(),
                'painted_texels':int(painted.sum())}
    (args.output/'adaptation.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(destination)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ['source','c172','aircraft','base','output']:
        parser.add_argument('--'+option, type=Path, required=True)
    adapt(parser.parse_args())
