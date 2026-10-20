"""Regression coverage for the terrain-visible bright prop annulus (T40).

Synthetic geometry/textures only: never reads a donor or an X-Plane install.
"""
from pathlib import Path
import math
import sys

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_c182t_package as builder
import convert_flightgear_c182 as conv


@pytest.mark.parametrize('size', [128, 512])
def test_prop_blur_has_no_bright_rgb_at_transparent_or_tip_texels(tmp_path, size):
    texture = tmp_path / 'prop.png'
    conv.prop_disc_texture(texture, size)
    with Image.open(texture) as image:
        assert image.mode == 'RGBA'
        # A constant dark blade color, including zero-alpha texels, prevents
        # mipmap/filtering from bringing the former pale tip ring into view.
        assert image.convert('RGB').getextrema() == ((30, 30), (30, 30), (32, 32))


@pytest.mark.parametrize('size', [128, 512])
def test_prop_blur_is_faint_and_feathers_both_hub_and_outer_edge(tmp_path, size):
    texture = tmp_path / 'prop.png'
    conv.prop_disc_texture(texture, size)
    with Image.open(texture) as image:
        alpha = image.getchannel('A')
        assert alpha.getextrema() == (0, 15)
        c = size // 2
        assert alpha.getpixel((c, c)) == 0
        assert alpha.getpixel((size - 1, c)) == 0
        radial = [alpha.getpixel((x, c)) for x in range(c, size)]
        # The old annulus changed abruptly to 24% opacity at 86% radius.
        assert max(abs(a - b) for a, b in zip(radial, radial[1:])) <= (2 if size == 128 else 1)
        assert radial[-max(2, size // 64):] == [0] * max(2, size // 64)
        assert alpha.getpixel((c, size // 4)) > 0  # remains a visible blur
        assert alpha.getpixel((c, size // 4)) == alpha.getpixel((size // 4, c))


def test_disc_retains_measured_plane_radius_and_disc_mode_visibility(tmp_path, monkeypatch):
    monkeypatch.setattr(conv, 'PROP_ROTATION', conv.Rotation((0, 0, 0), (0, 0, 1), 0, 360, 0, 360, 'unused'))

    def triangle(name, points):
        # Inverse of the AC3D-to-OBJ8 coordinate conversion.
        return conv.ACObject(kind='poly', name=name,
            vertices=[(z, y, -x) for x, y, z in points],
            surfaces=[conv.ACSurface(0x10, 0, tuple(conv.ACRef(i, 0, 0) for i in range(3)))])

    blade = triangle('Blade1', [(0, 1, 0), (.2, .8, 0), (-.2, .8, 0)])
    donor_disc = triangle('FastProp', [(0, 0, -.1), (1, 0, -.1), (0, 1, -.1)])
    destination = tmp_path / 'disc.obj'
    report = conv.write_generated_prop_disc(destination, 'prop.png', [blade], [donor_disc])
    builder.use_default_alpha_blending_for_prop_disc(destination)
    text = destination.read_text()
    conv.validate_obj8(destination)
    assert report['radius_m'] == pytest.approx(1)
    assert report['hub_m'] == pytest.approx([0, 0, -.1])
    vertices = [tuple(map(float, line.split()[1:4])) for line in text.splitlines() if line.startswith('VT ')]
    assert len(vertices) == conv.PROP_DISC_SEGMENTS + 1
    assert all(z == pytest.approx(-.1) for x, y, z in vertices)
    assert all(math.hypot(x, y) == pytest.approx(1, abs=1e-6) for x, y, z in vertices[1:])
    assert 'ANIM_hide 0.000000 0.000000 sim/flightmodel2/engines/prop_is_disc[0]' in text
    assert 'BLEND_GLASS' not in text.splitlines()
    assert 'ATTR_no_cull' in text.splitlines()
    assert 'ATTR_no_depth' not in text.splitlines()
