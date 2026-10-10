#!/usr/bin/env python3
"""Headless Blender visual check of installed OBJ8 geometry and a livery.

Run with blender --background --python this_file -- AIRCRAFT TEXTURE OUTPUT [VIEW...].
Uses rest positions; this is a paint preview, not a simulator/animation test.
"""
import sys
from pathlib import Path
import bpy
from mathutils import Vector


def read_obj(path):
    vertices, indices, groups = [], [], []
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
            groups.extend((name, indices[i:i+3]) for i in range(start, start+count, 3))
    return vertices, groups


def load_mesh(path, texture, glass=False):
    verts, groups = read_obj(path)
    mesh = bpy.data.meshes.new(path.stem)
    mesh.from_pydata([(v[0], -v[2], v[1]) for v in verts], [], [g[1] for g in groups])
    mesh.update()
    uv = mesh.uv_layers.new()
    for poly in mesh.polygons:
        poly.use_smooth = True
        for loop_index in poly.loop_indices:
            uv.data[loop_index].uv = verts[mesh.loops[loop_index].vertex_index][6:8]
    obj = bpy.data.objects.new(path.stem, mesh)
    bpy.context.collection.objects.link(obj)
    mat = bpy.data.materials.new(path.stem)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Roughness'].default_value = .4
    if glass:
        bsdf.inputs['Base Color'].default_value = (.035, .08, .12, 1)
        bsdf.inputs['Metallic'].default_value = .4
        bsdf.inputs['Roughness'].default_value = .18
    else:
        tex = mat.node_tree.nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(str(texture))
        mat.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    obj.data.materials.append(mat)


def main():
    args = sys.argv[sys.argv.index('--')+1:]
    aircraft, texture, output = map(Path, args[:3])
    selected_views = set(args[3:])
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    load_mesh(aircraft/'objects/flightgear_c182t.obj', texture)
    for filename in ['flightgear_c182t_glass.obj', 'flightgear_c182t_propeller.obj']:
        obj = aircraft/'objects'/filename
        if obj.exists():
            tex = next((line.split(maxsplit=1)[1] for line in obj.read_text().splitlines() if line.startswith('TEXTURE ')), '')
            load_mesh(obj, aircraft/'objects'/tex, 'glass' in filename)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1500
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.world.color = (.55, .55, .55)
    scene.view_settings.view_transform = 'Standard'
    for name, location, energy, size in [('Key',(-6,3,10),1800,9),('Fill',(7,-4,8),1500,8),('Belly',(0,0,-7),700,8)]:
        bpy.ops.object.light_add(type='AREA', location=location)
        lamp = bpy.context.object
        lamp.name = name
        lamp.data.energy = energy
        lamp.data.shape = 'DISK'
        lamp.data.size = size
        lamp.rotation_euler = (Vector((0,-2,0))-lamp.location).to_track_quat('-Z','Y').to_euler()
    bpy.ops.object.camera_add()
    cam = bpy.context.object
    scene.camera = cam
    cam.data.type = 'ORTHO'
    views = [('port',(-13,-2.5,1.4),9),('starboard',(13,-2.5,1.4),9),
             ('overview',(-10,9,9),13),('top',(0,-2.7,17),15.5),
             ('underside',(-9,7,-7),13),('rear',(9,-13,5),13)]
    for name, location, scale in views:
        if selected_views and name not in selected_views:
            continue
        cam.location = location
        cam.rotation_euler = (Vector((0,-2.6,.35))-cam.location).to_track_quat('-Z','Y').to_euler()
        cam.data.ortho_scale = scale
        scene.render.filepath = str(output/(name+'.png'))
        bpy.ops.render.render(write_still=True)


if __name__ == '__main__':
    main()
