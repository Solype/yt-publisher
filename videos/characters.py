"""Low-poly character proposals for the compiler series, one PNG per character (run inside Blender)."""
import argparse
import math
import os
import sys

NAMES = ["mina", "otis", "pip", "stamp", "haechi", "fold"]

parser = argparse.ArgumentParser(
    prog="blender -b -P videos/characters.py --", description=__doc__,
    epilog="No environment variable. Needs Blender 5 (Cycles, on the CPU).\n\n"
           "example:\n  blender -b -P videos/characters.py -- --out /tmp/characters --only mina",
    formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--out", default=".", help="output directory (default: current)")
parser.add_argument("--only", choices=NAMES, help="render only this character")
parser.add_argument("--samples", type=int, default=48, help="Cycles samples (default: 48)")
ARGS = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])

import bpy  # noqa: E402  (after --help, which must work without Blender)
from mathutils import Vector  # noqa: E402

WARM, COLD = "ffb74a", "35d6e8"


def linear(rgb):
    out = []
    for i in (0, 2, 4):
        c = int(rgb[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1)


def mat(rgb, glow=0.0):
    name = f"{rgb}-{glow}"
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n = m.node_tree.nodes["Principled BSDF"]
    n.inputs["Base Color"].default_value = linear(rgb)
    n.inputs["Roughness"].default_value = 0.75
    if glow:
        n.inputs["Emission Color"].default_value = linear(rgb)
        n.inputs["Emission Strength"].default_value = glow
    return m


def done(color, glow=0.0, scale=None, rot=None):
    o = bpy.context.object
    o.data.materials.append(mat(color, glow))
    if scale:
        o.scale = scale
    if rot:
        o.rotation_euler = [math.radians(a) for a in rot]
    return o


def ico(loc, r, color, scale=None, rot=None, sub=2, glow=0.0):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub, radius=r, location=loc)
    return done(color, glow, scale, rot)


def box(loc, size, color, rot=None, glow=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    return done(color, glow, size, rot)


def cone(loc, r1, r2, h, color, verts=8, rot=None, scale=None, glow=0.0):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=h, location=loc)
    return done(color, glow, scale, rot)


def ring(loc, r, thick, color, rot=None, scale=None, glow=0.0, n=16):
    bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=thick, major_segments=n, minor_segments=6,
                                     location=loc)
    return done(color, glow, scale, rot)


def limb(a, b, r1, r2, color, verts=6, glow=0.0):
    """A tapered segment from a to b."""
    a, b = Vector(a), Vector(b)
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=(b - a).length,
                                    location=(a + b) / 2)
    o = done(color, glow)
    o.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()
    return o


def mesh(verts, faces, color):
    me = bpy.data.meshes.new("m")
    me.from_pydata(verts, [], faces)
    o = bpy.data.objects.new("m", me)
    bpy.context.collection.objects.link(o)
    me.materials.append(mat(color))
    return o


def eye(x, y, z, r, look=0.0, pupil="14121c"):
    ico((x, y, z), r, "f7f2e8", scale=(1, 0.45, 1.1))
    ico((x + look, y - r * 0.36, z), r * 0.58, pupil, scale=(1, 0.4, 1.1))
    ico((x + look - r * 0.2, y - r * 0.6, z + r * 0.28), r * 0.17, "ffffff", sub=1, glow=1.0)


def sheet(loc, w, h, rot, stamp=None):
    """A page of code; stamp is the color of a big cross."""
    parts = [box(loc, (w, 0.012, h), "efe6d2", rot)]
    parts[0].rotation_euler = [math.radians(a) for a in rot]
    frame = parts[0].rotation_euler.to_matrix()
    for i, (start, length, c) in enumerate([(0, .6, "3a7ca5"), (.12, .7, "444054"), (.12, .5, "444054"),
                                            (0, .2, "444054"), (0, .5, "3a7ca5"), (.12, .6, "c8553d")]):
        local = Vector((-w / 2 + w * (.1 + start + length * .8 / 2), -0.012, h * (.36 - i * .14)))
        o = box(Vector(loc) + frame @ local, (w * length * .8, 0.008, h * .045), c)
        o.rotation_euler = parts[0].rotation_euler
    if stamp:
        for a in (45, -45):
            o = box(Vector(loc) + frame @ Vector((0, -0.024, 0)), (w * .8, 0.01, h * .1), stamp, glow=2.0)
            o.rotation_euler = (frame @ Vector((0, 0, 0))).to_track_quat("Z", "Y").to_euler()
            o.rotation_euler = [math.radians(rot[0]), math.radians(rot[1] + a), math.radians(rot[2])]


def mina():
    skin, hair, hoodie, jean = "e8a77c", "1d1a2b", "e0a526", "2c3a63"
    for s in (-1, 1):
        limb((.12 * s, 0, .72), (.13 * s, .02, .1), .12, .085, jean)
        box((.13 * s, -.06, .06), (.16, .3, .12), "f3efe6")
    cone((0, 0, .93), .36, .25, .62, hoodie)
    box((0, -.27, .8), (.34, .06, .18), "c48c16", (-8, 0, 0))
    ring((0, .04, 1.27), .17, .085, "c48c16", (12, 0, 0), n=9)
    for s in (-1, 1):
        limb((.05 * s, -.24, 1.2), (.06 * s, -.29, 1.02), .012, .012, "f3efe6", 5)
    limb((-.25, 0, 1.17), (-.42, .02, .9), .11, .095, hoodie)
    limb((-.42, .02, .9), (-.27, -.26, .84), .095, .08, hoodie)
    limb((.25, 0, 1.17), (.44, -.08, .95), .11, .095, hoodie)
    limb((.44, -.08, .95), (.36, -.34, 1.1), .095, .08, hoodie)
    ico((.35, -.38, 1.14), .075, skin, sub=1)
    cone((.33, -.46, 1.16), .085, .085, .17, "f7f2e8", 10)
    cone((.33, -.46, 1.246), .07, .07, .01, "3b2114", 10)
    cone((0, 0, 1.31), .09, .08, .14, skin)
    ico((0, .07, 1.64), .33, hair, (1.05, 1, 1.02))
    for s in (-1, 1):
        box((.275 * s, .0, 1.5), (.1, .26, .34), hair, (0, 6 * s, 0))
    ico((0, -.02, 1.55), .27, skin, (1, .98, 1.06))
    for i, x in enumerate((-.19, -.08, .04, .16)):
        box((x, -.235 + abs(x) * .25, 1.745), (.12, .09, .14), hair, (14, 0, -8 + 5 * i))
    for s in (-1, 1):
        eye(.11 * s, -.262, 1.555, .062, .012)
        ring((.11 * s, -.3, 1.555), .092, .012, COLD, (90, 0, 0), glow=1.5)
        box((.115 * s, -.275, 1.675), (.1, .03, .022), hair, (0, 10 * s, 0))
    box((0, -.31, 1.565), (.045, .015, .015), COLD, glow=1.5)
    cone((0, -.3, 1.49), .03, 0, .06, "d98f63", 4, (75, 0, 0))
    box((.025, -.262, 1.41), (.11, .02, .022), "8e2f35", (0, -9, 0))
    return 0, 1.0, WARM


def otis():
    skin, beard, vest, shirt = "c98a5e", "ece7dc", "2f6b4f", "efe6d2"
    for s in (-1, 1):
        limb((.15 * s, 0, .6), (.16 * s, 0, .1), .14, .11, "4a3b33")
        box((.16 * s, -.06, .06), (.19, .32, .12), "2a1d17")
    ico((0, 0, .98), .3, shirt, (1, .85, 1))
    cone((0, -.02, .88), .44, .33, .6, vest, 8, scale=(1, .9, 1))
    for z in (.74, .88, 1.02):
        ico((0, -.4 + (z - .74) * .22, z), .028, "e6b84c", sub=1, glow=.4)
    limb((-.3, 0, 1.12), (-.5, -.02, .85), .13, .11, shirt)
    limb((-.5, -.02, .85), (-.4, -.32, .95), .11, .09, shirt)
    limb((.3, 0, 1.12), (.52, -.05, .9), .13, .11, shirt)
    limb((.52, -.05, .9), (.46, -.36, 1.06), .11, .09, shirt)
    for s in (-1, 1):
        ico((.44 * s, -.38, 1.0 + .06 * (s > 0)), .085, skin, sub=1)
    g = (.46, -.45, 1.24)
    cone(g, .15, .15, .05, "e6b84c", 12, (90, 0, 0), glow=.5)
    for i in range(8):
        a = math.radians(45 * i)
        box((g[0] + .17 * math.cos(a), g[1], g[2] + .17 * math.sin(a)), (.07, .05, .06), "e6b84c",
            (0, -45 * i, 0), glow=.5)
    cone((g[0], g[1] - .03, g[2]), .05, .05, .03, "3a2a18", 8, (90, 0, 0))
    ico((0, 0, 1.44), .29, skin, (1, .95, 1))
    cone((0, -.14, 1.24), .05, .27, .42, beard, 7, scale=(1, .62, 1))
    for s in (-1, 1):
        cone((.1 * s, -.29, 1.385), .06, .01, .2, beard, 5, (0, 100 * s, 0))
        ico((.27 * s, .02, 1.44), .09, beard, (.6, 1, 1.2), sub=1)
        box((.12 * s, -.275, 1.585), (.14, .05, .045), beard, (0, -10 * s, 0))
    ico((0, -.32, 1.45), .065, "b97550", (1, .9, 1.1), sub=1)
    eye(-.115, -.262, 1.515, .05)
    eye(.115, -.262, 1.515, .05)
    cone((.115, -.33, 1.515), .085, .07, .12, "e6b84c", 10, (90, 0, 0), glow=.3)
    cone((.115, -.394, 1.515), .06, .06, .01, COLD, 10, (90, 0, 0), glow=2.0)
    ico((0, .02, 1.68), .31, "6b4a3a", (1.05, 1.1, .45))
    box((0, -.28, 1.645), (.36, .2, .04), "57392c", (-12, 0, 0))
    return 0, 1.0, WARM


def pip():
    fur, dark, light = "7c8094", "20202c", "d9d6d0"
    for s in (-1, 1):
        limb((.14 * s, 0, .42), (.17 * s, -.02, .1), .13, .1, fur)
        ico((.17 * s, -.08, .07), .11, dark, (1, 1.4, .7), sub=1)
    ico((0, 0, .68), .34, fur, (1, .9, 1.15))
    ico((0, -.13, .66), .25, light, (.95, .85, 1.1))
    for i in range(7):
        a = i / 6
        ico((.3 + .42 * math.sin(a * 1.7), .22 + .06 * a, .42 + .62 * a), .17 - .012 * i,
            dark if i % 2 else fur, (1, 1, .85), sub=1)
    box((0, .33, .84), (.5, .26, .5), "1f8a86")
    box((0, .31, 1.07), (.44, .22, .1), "2bb3ad")
    for x, r in ((-.14, -9), (.02, 5), (.14, 14)):
        box((x, .33, 1.2), (.2, .02, .26), "efe6d2", (0, r, 0))
    for s in (-1, 1):
        limb((.17 * s, -.2, .98), (.2 * s, -.29, .6), .035, .035, "1f8a86", 4)
    limb((-.28, -.05, .86), (-.42, -.2, .68), .1, .085, fur)
    limb((-.42, -.2, .68), (-.24, -.44, .7), .085, .07, dark)
    limb((.28, -.05, .86), (.42, -.2, .68), .1, .085, fur)
    limb((.42, -.2, .68), (.24, -.44, .7), .085, .07, dark)
    sheet((0, -.47, .66), .44, .46, (-14, 0, 0))
    ico((0, -.03, 1.25), .33, fur, (1.12, .95, .95))
    for s in (-1, 1):
        cone((.25 * s, .02, 1.54), .12, .02, .2, fur, 5, (0, 18 * s, 0))
        cone((.245 * s, -.035, 1.52), .07, .01, .13, dark, 5, (0, 18 * s, 0))
        ico((.17 * s, -.24, 1.27), .145, dark, (1.15, .55, .8), (0, 22 * s, 0))
        eye(.14 * s, -.318, 1.275, .062, -.01 * s)
        box((.15 * s, -.29, 1.4), (.15, .05, .035), light, (0, 12 * s, 0))
        cone((.3 * s, -.18, 1.13), .1, .01, .18, light, 5, (70, 0, 50 * s))
    cone((0, -.36, 1.14), .14, .06, .2, light, 7, (90, 0, 0))
    ico((0, -.47, 1.165), .05, dark, (1.2, .8, .9), sub=1)
    box((.02, -.4, 1.06), (.12, .02, .02), dark, (0, -10, 0))
    return 0, 1.15, WARM


def stamp():
    cream, steel, navy, red = "e9dfc7", "6f7f93", "24335c", "e0483e"
    for s in (-1, 1):
        cone((.2 * s, 0, .24), .1, .1, .36, steel, 8)
        box((.2 * s, -.05, .06), (.26, .38, .12), navy)
    box((0, 0, .75), (.82, .5, .68), cream)
    box((0, -.26, .9), (.62, .03, .16), navy)
    for i in range(5):
        box((-.22 + i * .11, -.28, .9), (.07, .02, .07), [COLD, COLD, COLD, WARM, red][i], glow=2.5)
    box((0, -.26, .62), (.5, .03, .05), "14121c")
    sheet((.02, -.31, .52), .3, .24, (-10, 0, 0))
    cone((0, 0, 1.13), .13, .13, .1, steel, 8)
    box((0, 0, 1.4), (.62, .46, .44), cream)
    box((0, -.235, 1.4), (.5, .02, .3), "0b1020")
    for s in (-1, 1):
        box((.12 * s, -.25, 1.42), (.09, .01, .13), COLD, glow=4.0)
        box((.12 * s, -.255, 1.53), (.15, .012, .03), COLD, (0, -14 * s, 0), glow=4.0)
        cone((.34 * s, 0, 1.4), .08, .08, .06, steel, 8, (0, 90, 0))
    box((0, -.25, 1.29), (.16, .01, .022), COLD, glow=4.0)
    cone((0, 0, 1.66), .34, .34, .1, navy, 10)
    cone((0, 0, 1.77), .36, .42, .13, navy, 10)
    box((0, -.36, 1.63), (.46, .22, .035), "14121c", (-14, 0, 0))
    cone((0, -.4, 1.75), .075, .075, .03, WARM, 6, (90, 0, 0), glow=2.0)
    limb((-.42, 0, .98), (-.64, -.06, .78), .07, .07, steel, 8)
    limb((-.64, -.06, .78), (-.56, -.4, .98), .07, .06, steel, 8)
    sheet((-.54, -.45, 1.12), .34, .42, (-6, 0, 12), red)
    limb((.42, 0, .98), (.68, -.04, 1.08), .07, .07, steel, 8)
    limb((.68, -.04, 1.08), (.72, -.22, 1.34), .07, .06, steel, 8)
    cone((.72, -.24, 1.5), .06, .1, .22, "8a5a34", 8)
    ico((.72, -.24, 1.64), .11, "8a5a34", sub=1)
    cone((.72, -.24, 1.36), .17, .13, .12, "8a5a34", 8)
    cone((.72, -.24, 1.285), .18, .18, .04, red, 8, glow=1.2)
    return 0, 1.0, COLD


def haechi():
    stone, mane, pale, gold = "4f9a94", "1f5c66", "cfe3d6", "e6b84c"
    ico((0, .22, .55), .46, stone, (.95, 1.1, 1.05))
    ico((0, -.05, .78), .36, stone, (1, .85, 1.1))
    ico((0, -.17, .76), .27, pale, (.95, .7, 1.15))
    for s in (-1, 1):
        ico((.38 * s, .18, .3), .27, stone, (.75, 1.1, 1.05))
        ico((.42 * s, -.16, .1), .15, stone, (1, 1.3, .7), sub=1)
        limb((.23 * s, -.14, .8), (.22 * s, -.3, .12), .15, .11, stone, 7)
        ico((.22 * s, -.36, .1), .15, pale, (1, 1.25, .7), sub=1)
        for t in (-.07, 0, .07):
            cone((.22 * s + t, -.53, .07), .025, 0, .07, "f7f2e8", 4, (90, 0, 0))
    for i, (x, z, r) in enumerate(((.5, .5, .15), (.6, .72, .15), (.56, .95, .13), (.44, 1.1, .1))):
        ico((x, .5, z), r, mane if i % 2 == 0 else gold, sub=1)
    for i in range(11):
        a = math.radians(-35 + 25 * i)
        ico((.43 * math.cos(a), .06, 1.32 + .42 * math.sin(a)), .15, mane, sub=1)
    ico((0, -.06, 1.32), .38, stone, (1.08, .95, .95))
    box((0, -.36, 1.2), (.44, .24, .2), stone)
    ico((0, -.48, 1.29), .1, mane, (1.4, .8, .8), sub=1)
    box((0, -.47, 1.1), (.46, .06, .07), "5a1f2a")
    for x in (-.17, -.085, 0, .085, .17):
        big = abs(x) > .1
        cone((x, -.49, 1.11), .04, 0, .12 if big else .06, "f7f2e8", 4, (180, 0, 0))
    for s in (-1, 1):
        eye(.17 * s, -.375, 1.41, .1, -.02 * s)
        box((.18 * s, -.36, 1.55), (.24, .1, .06), mane, (0, -16 * s, 0))
        cone((.33 * s, -.02, 1.62), .1, .02, .2, stone, 5, (0, 35 * s, 0))
        ico((.21 * s, -.43, 1.17), .08, pale, (1, .8, .8), sub=1)
    cone((0, -.2, 1.75), .085, 0, .32, "f1e3bf", 6, (12, 0, 0))
    ring((0, -.1, .97), .3, .035, "c8382f", (14, 0, 0), n=12)
    ico((0, -.45, .86), .12, gold, glow=.7)
    box((0, -.55, .83), (.12, .04, .02), "2a1d17")
    return -14, 1.05, COLD


def fold():
    paper, shade, ink = "f1ead8", "cfc6ae", "3a7ca5"
    z = .15
    f, b, left, r, t, d = ((0, -.36, 1.08 + z), (0, .38, 1.0 + z), (-.2, 0, 1.0 + z), (.2, 0, 1.0 + z),
                           (0, .02, 1.2 + z), (0, 0, .72 + z))
    mesh([f, b, left, r, t, d], [(0, 4, 2), (0, 3, 4), (1, 2, 4), (1, 4, 3)], paper)
    mesh([f, b, left, r, t, d], [(0, 2, 5), (0, 5, 3), (1, 5, 2), (1, 3, 5)], shade)
    for s in (-1, 1):
        rf, rb = Vector((.12 * s, -.22, 1.1 + z)), Vector((.12 * s, .28, 1.06 + z))
        mid, tip = Vector((.55 * s, -.2, 1.36 + z)), Vector((.98 * s, .2, 1.72 + z))
        back = Vector((.6 * s, .34, 1.3 + z))
        mesh([rf, rb, mid, tip, back], [(0, 2, 1), (1, 2, 4)], paper)
        mesh([rf, rb, mid, tip, back], [(2, 3, 4)], shade)
        for i, k in enumerate((.25, .45, .65, .85)):
            p = rf.lerp(mid, k) + Vector((0, -.012, -.012))
            q = rb.lerp(back, k) + Vector((0, 0, -.012))
            e = p.lerp(q, .55 if i % 2 else .8)
            up = Vector((0, -.006, .03))
            limb(p.lerp(q, .12) + up, e + up, .013, .013, ["c8553d", ink, "444054", ink][i], 4)
    limb((0, -.28, 1.05 + z), (0, -.52, 1.58 + z), .11, .06, paper, 4)
    cone((0, -.66, 1.6 + z), .1, .0, .34, paper, 4, (100, 0, 0))
    cone((0, -.8, 1.575 + z), .04, 0, .12, "e0883e", 4, (100, 0, 0))
    for s in (-1, 1):
        ico((.058 * s, -.6, 1.64 + z), .036, "14121c", (.5, 1, 1), sub=1)
        ico((.07 * s, -.615, 1.655 + z), .012, "ffffff", sub=1, glow=2.0)
    limb((0, .3, 1.02 + z), (0, .86, 1.5 + z), .12, .01, shade, 4)
    for i in range(9):
        a = i / 8
        box((.5 * math.sin(a * 4.4) * (1 - a * .3), .45 - a * .9, .78 - a * .66), (.1, .1, .1),
            [COLD, TEAL, WARM][i % 3], (20 * i, 35 * i, 10 * i), glow=2.2)
    return 42, 1.1, COLD


TEAL = "6cc2ad"
BUILD = dict(zip(NAMES, (mina, otis, pip, stamp, haechi, fold)))


def light(loc, energy, color, size):
    bpy.ops.object.light_add(type="AREA", location=loc)
    o = bpy.context.object
    o.data.energy, o.data.color, o.data.size = energy, linear(color)[:3], size
    o.rotation_euler = (Vector((0, 0, 1)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def render(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    yaw, zoom, accent = BUILD[name]()
    pivot = bpy.data.objects.new("pivot", None)
    scene.collection.objects.link(pivot)
    for o in list(scene.collection.all_objects):
        if o is not pivot:
            o.parent = pivot
    pivot.rotation_euler[2] = math.radians(yaw + 16)
    pivot.scale = [zoom] * 3

    cone((0, 0, -.05), 1.25, 1.2, .1, "171833", 12)
    ring((0, 0, .01), 1.2, .015, accent, glow=3.0, n=12)
    for x, z, w, h in ((-1.5, 1.9, .22, .32), (-1.15, 1.9, .22, .32), (-1.5, 1.45, .22, .32), (1.2, 2.1, .22, .32),
                       (1.55, 2.1, .22, .32), (1.55, 1.2, .22, .32), (-1.15, .7, .22, .32)):
        box((x * 1.25, 2.4, z), (w, .02, h), "f2c14e", glow=1.1)
    box((0, 2.6, 1.5), (12, .05, 8), "0c0e2b")
    box((0, 0, -.12), (12, 8, .04), "0a0b20")
    light((-2.2, -2.6, 2.8), 170, "ffd2a0", 1.2)
    light((2.4, 1.2, 2.2), 260, "4a6cff", 1.0)
    light((1.6, -2.6, .8), 35, "7f8cff", 2.0)
    scene.world = bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = linear("0b0d26")
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = .6

    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    cam.location = (0, -5.2, 1.35)
    cam.rotation_euler = (Vector((0, 0, .98)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = 62
    scene.camera = cam
    scene.render.engine = "CYCLES"
    scene.cycles.samples = ARGS.samples
    scene.cycles.use_denoising = True
    scene.render.threads_mode, scene.render.threads = "FIXED", 6  # other sessions share the machine
    scene.render.resolution_x, scene.render.resolution_y = 720, 900
    scene.view_settings.view_transform = "Standard"
    scene.render.filepath = os.path.join(os.path.abspath(ARGS.out), name + ".png")
    bpy.ops.render.render(write_still=True)


os.makedirs(ARGS.out, exist_ok=True)
for who in [ARGS.only] if ARGS.only else NAMES:
    render(who)
