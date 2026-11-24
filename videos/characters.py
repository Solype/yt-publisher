"""Low-poly characters of the compiler series, and one staged frame of them (run inside Blender)."""
import argparse
import math
import os
import random
import subprocess
import sys
import time

SHOTS = ["mina", "stamp", "lumi", "scene"]

parser = argparse.ArgumentParser(
    prog="blender -b -P videos/characters.py --", description=__doc__,
    epilog="No environment variable. Needs Blender 5 and the Inter font.\n\n"
           "example:\n  blender -b -P videos/characters.py -- --out /tmp/characters --only scene",
    formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--out", default=".", help="output directory (default: current)")
parser.add_argument("--only", choices=SHOTS, help="render only this shot")
parser.add_argument("--engine", choices=["eevee", "cycles"], default="eevee", help="default: eevee")
parser.add_argument("--samples", type=int, default=48, help="default: 48")
if __name__ == "__main__":
    ARGS = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])

import bpy  # noqa: E402  (after --help, which must work without Blender)
from mathutils import Vector  # noqa: E402

GLOW, LIGHT = .68, .55  # overall brightness of the neons, and of the lamps
YELLOW, CYAN, RED, LILAC, WHITE = "ffc83d", "35d6e8", "ff4d4d", "a9b0e8", "f7f2e8"


def linear(rgb):
    out = []
    for i in (0, 2, 4):
        c = int(rgb[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1)


def mat(rgb, glow=0.0, alpha=1.0):
    name = f"{rgb}-{glow}-{alpha}"
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    n = m.node_tree.nodes["Principled BSDF"]
    n.inputs["Base Color"].default_value = linear(rgb)
    n.inputs["Roughness"].default_value = 0.8
    n.inputs["Alpha"].default_value = alpha
    if alpha < 1:
        m.surface_render_method = "BLENDED"
    if glow:
        n.inputs["Emission Color"].default_value = linear(rgb)
        n.inputs["Emission Strength"].default_value = glow * GLOW
    return m


def done(color, glow=0.0, scale=None, rot=None, alpha=1.0):
    o = bpy.context.object
    o.data.materials.append(mat(color, glow, alpha))
    if scale:
        o.scale = scale
    if rot:
        o.rotation_euler = [math.radians(a) for a in rot]
    return o


def ico(loc, r, color, scale=None, rot=None, sub=2, glow=0.0):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub, radius=r, location=loc)
    return done(color, glow, scale, rot)


def box(loc, size, color, rot=None, glow=0.0, alpha=1.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    return done(color, glow, size, rot, alpha)


def cone(loc, r1, r2, h, color, verts=8, rot=None, glow=0.0, alpha=1.0):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=h, location=loc)
    return done(color, glow, None, rot, alpha)


def ring(loc, r, thick, color, rot=None, glow=0.0, n=16):
    bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=thick, major_segments=n, minor_segments=6,
                                     location=loc)
    return done(color, glow, None, rot)


def limb(a, b, r1, r2, color, verts=6, glow=0.0):
    """A tapered segment from a to b."""
    a, b = Vector(a), Vector(b)
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=(b - a).length,
                                    location=(a + b) / 2)
    o = done(color, glow)
    o.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()
    return o


def page(w, h, cross=True):
    """A page of code facing -Y, centered on the origin."""
    box((0, 0, 0), (w, .02, h), "efe6d2")
    for i, (start, length) in enumerate([(0, .6), (.12, .7), (.12, .45), (0, .5)]):
        box((-w / 2 + w * (.1 + start + length * .4), -.016, h * (.3 - i * .19)), (w * length * .8, .01, h * .06),
            "444a6b")
    if cross:
        for a in (45, -45):
            box((0, -.03, 0), (w * .95, .012, h * .13), RED, (0, a, 0), glow=1.4).name = "cross"


def mina(left=(-.46, -.02, .72), right=(.46, -.02, .72)):
    skin, hair, hoodie = "eab08a", "231f36", "f0b02c"
    for s in (-1, 1):
        limb((.13 * s, 0, .7), (.13 * s, 0, .1), .12, .09, "2f3f70")
        box((.13 * s, -.06, .06), (.18, .3, .12), WHITE)
    cone((0, 0, .95), .38, .24, .62, hoodie, 7)
    for s, hand in ((-1, left), (1, right)):
        limb((.25 * s, 0, 1.16), hand, .11, .08, hoodie).name = f"mina_limb{s}"
        ico(hand, .085, skin, sub=1).name = f"mina_hand{s}"
    ico((0, .08, 1.63), .34, hair, (1.06, 1, 1))
    for s in (-1, 1):
        ico((.27 * s, .04, 1.47), .19, hair, (.5, .9, 1.25))
    ico((0, -.03, 1.54), .28, skin, (1, .98, 1.05))
    ico((0, -.17, 1.74), .22, hair, (1.2, .6, .5))
    for s in (-1, 1):
        ico((.115 * s, -.3, 1.55), .04, "14121c", (1, .5, 1.3), sub=1)
        ring((.115 * s, -.31, 1.55), .1, .014, CYAN, (90, 0, 0), glow=1.2, n=10)
    box((0, -.315, 1.56), (.05, .02, .02), CYAN, glow=1.2)
    box((0, -.285, 1.385), (.1, .03, .05), "8e2f35").name = "mina_mouth"


def stamp(hand=(.82, -.3, 1.2)):
    cream, navy = "efe4c8", "25335f"
    box((0, 0, .2), (.66, .46, .4), navy)
    box((0, 0, .78), (.86, .56, .76), cream)
    box((0, -.29, .74), (.5, .03, .06), "14121c")
    box((0, 0, 1.46), (.72, .54, .56), cream)
    box((0, -.275, 1.46), (.58, .02, .38), "0b1020")
    for s in (-1, 1):
        box((.14 * s, -.29, 1.44), (.11, .012, .16), CYAN, glow=1.3).name = f"stamp_eye{s}"
        box((.14 * s, -.295, 1.57), (.2, .014, .04), CYAN, (0, -16 * s, 0), glow=1.3)
    cone((0, 0, 1.8), .46, .52, .16, navy, 8)
    box((0, -.42, 1.735), (.56, .3, .04), "14121c", (-10, 0, 0))
    cone((0, -.5, 1.81), .085, .085, .04, YELLOW, 6, (90, 0, 0), glow=1.0)
    side = math.copysign(1, hand[0])
    limb((-.43 * side, 0, .98), (-.66 * side, -.1, .72), .08, .07, navy)
    limb((.43 * side, 0, 1.0), hand, .08, .07, navy).name = "stamp_limb"
    x, y, z = hand
    for part in (cone((x, y, z - .02), .07, .11, .28, "9a6236", 8), ico((x, y, z + .15), .14, "9a6236", sub=1),
                 cone((x, y, z - .22), .24, .17, .14, "9a6236", 8),
                 cone((x, y, z - .31), .25, .25, .06, RED, 8, glow=1.2)):
        part.name = "stamp_head"


def lumi():
    wood = "3a2430"
    cone((0, 0, 1.42), .2, .12, .07, wood, 8)
    ring((0, 0, 1.53), .07, .016, YELLOW, (90, 0, 0), glow=.6, n=8)
    cone((0, 0, 1.28), .34, .26, .22, "e0483e", 8, glow=.25)
    cone((0, 0, 1.02), .36, .34, .3, "ffd27a", 8, glow=.45)
    cone((0, 0, .77), .26, .36, .2, "1f8a86", 8, glow=.3)
    cone((0, 0, .64), .12, .2, .07, wood, 8)
    limb((0, 0, .6), (0, 0, .46), .02, .02, YELLOW, 5)
    cone((0, 0, .38), .07, .03, .18, "e0483e", 6)
    for s in (-1, 1):
        ico((.12 * s, -.335, 1.05), .042, "14121c", (1, .5, 1.35), sub=1)
        limb((.34 * s, 0, 1.1), (.52 * s, -.04, 1.22), .035, .05, "e0483e", 5).name = f"lumi_arm{s}"
    for x, z in ((-.05, .975), (0, .955), (.05, .975)):
        box((x, -.345, z), (.055, .02, .022), "14121c", (0, 22 if x < 0 else -22 if x > 0 else 0, 0))


def place(build, loc, yaw=0.0, scale=1.0, rot_x=0.0):
    """Runs build() and moves everything it creates."""
    before = set(bpy.data.objects)
    build()
    pivot = bpy.data.objects.new("pivot", None)
    bpy.context.scene.collection.objects.link(pivot)
    for o in set(bpy.data.objects) - before - {pivot}:
        o.parent = pivot
    pivot.location, pivot.scale = loc, [scale] * 3
    pivot.rotation_euler = (math.radians(rot_x), 0, math.radians(yaw))
    return pivot


FONT = []


def text(s, x, z, size, color, glow=1.0, align="CENTER", bold=.012, y=0.0):
    if not FONT:
        path = subprocess.run(["fc-match", "-f", "%{file}", "Inter:bold"], capture_output=True, text=True).stdout
        FONT.append(bpy.data.fonts.load(path))
    bpy.ops.object.text_add(location=(x, y, z), rotation=(math.pi / 2, 0, 0))
    o = bpy.context.object
    o.data.body, o.data.size, o.data.font = s, size, FONT[0]
    o.data.align_x, o.data.align_y, o.data.offset = align, "CENTER", bold * size
    o.data.materials.append(mat(color, glow))


def frame(x, z, w, h, color, r=.1, thick=.018, glow=1.6, fill=None, alpha=.82, dash=False, y=0.0):
    """A neon rounded rectangle facing -Y."""
    if fill:
        box((x, y + (.005 if alpha == 1 else .02), z), (w - r * .4, .01, h - r * .4), fill, alpha=alpha, glow=.9 if alpha == 1 else 0)
    pts = []
    for cx, cz, a0 in ((x + w / 2 - r, z + h / 2 - r, 0), (x - w / 2 + r, z + h / 2 - r, 90),
                       (x - w / 2 + r, z - h / 2 + r, 180), (x + w / 2 - r, z - h / 2 + r, 270)):
        for k in range(5):
            a = math.radians(a0 + 22.5 * k)
            pts.append((cx + r * math.cos(a), y, cz + r * math.sin(a)))
    for a, b in zip(pts, pts[1:] + pts[:1]):
        if dash and (Vector(b) - Vector(a)).length > .1:
            route(a, b, color, glow, thick)
        else:
            limb(a, b, thick, thick, color, glow=glow)


def route(a, b, color, glow=1.0, thick=.012):
    """A dashed line."""
    a, b = Vector(a), Vector(b)
    n = max(2, round((b - a).length / .07))
    for i in range(n):
        limb(a.lerp(b, (i + .2) / n), a.lerp(b, (i + .75) / n), thick, thick, color, 5, glow)


def panel():
    """Why Stamp refuses add(3): one argument out of two."""
    frame(0, 0, 2.72, 1.36, CYAN, fill="04061a")
    text("CALL  add(3)", -1.22, .53, .13, LILAC, .8, "LEFT")
    text("REFUSED", 1.22, .53, .13, RED, 1.2, "RIGHT")
    box((0, 0, .41), (2.46, .005, .008), LILAC, glow=.4)
    # two inputs on the left, the function on their right
    frame(-.98, .14, .3, .3, CYAN, r=.06, fill=CYAN, alpha=1)
    text("3", -.98, .14, .22, "04061a", 0, y=-.02)
    frame(-.98, -.26, .3, .3, RED, r=.06, thick=.012, dash=True)
    text("?", -.98, -.26, .22, RED, 1.4)
    route((-.8, 0, .14), (-.35, 0, 0), CYAN)
    route((-.8, 0, -.26), (-.35, 0, -.12), RED)
    frame(-.02, -.06, .58, .42, YELLOW, r=.08, fill=YELLOW, alpha=1)
    text("add", -.02, -.06, .22, "04061a", 0, y=-.02)
    text("ARGUMENTS", .86, .24, .12, WHITE, .9)
    text("1/2", .86, -.08, .52, YELLOW, 1.5)
    box((-.82, 0, -.55), (.6, .02, .09), CYAN, glow=1.2)
    frame(-.16, -.55, .6, .09, RED, r=.02, thick=.008)
    text("needs two integers, got one", 1.22, -.55, .1, WHITE, .8, "RIGHT", .006)


def light(loc, energy, color, size, target=(0, 0, 1)):
    bpy.ops.object.light_add(type="AREA", location=loc)
    o = bpy.context.object
    o.data.energy, o.data.color, o.data.size = energy * LIGHT, linear(color)[:3], size
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def portrait(build, accent, yaw):
    place(build, (0, 0, 0), yaw)
    cone((0, 0, -.05), 1.15, 1.1, .1, "171833", 12)
    ring((0, 0, .01), 1.1, .015, accent, glow=1.6, n=12)
    box((0, 2.6, 1.5), (12, .05, 8), "0c0e2b")
    box((0, 0, -.12), (12, 8, .04), "0a0b20")
    light((-2.2, -2.6, 2.8), 150, "ffd2a0", 1.2)
    light((2.4, 1.2, 2.2), 240, "4a6cff", 1.0)
    light((1.6, -2.6, .8), 35, "7f8cff", 2.0)
    return (0, -5.2, 1.35), (0, 0, .95), 62, (720, 900)


def booth():
    """The customs booth: walls, counter and lamps, without the characters."""
    rng = random.Random(4)  # the same lit pigeonholes at each render
    box((0, 2.4, 2.5), (9, .1, 9), "0a0c28")
    box((0, 0, -.05), (9, 9, .1), "14163a")
    for i in range(9):
        for j in range(11):
            lit = rng.random() if j < 8 else 0  # dark behind the panel and the subtitle
            color, glow = ("ffd27a", .5) if lit > .9 else ("8fa6ff", .28) if lit > .84 else ("141a4a", 0.0)
            box((-2.0 + i * .5, 2.3, .35 + j * .5), (.34, .06, .34), color, glow=glow)
    box((.85, -.28, .42), (1.5, .5, .84), "4a2f52")
    box((.85, -.3, .87), (1.62, .6, .07), "7b4d63")
    frame(.85, .42, 1.1, .42, RED, r=.06, thick=.012, glow=1.2, y=-.55)
    text("CUSTOMS", .85, .42, .2, WHITE, 1.0, y=-.56)
    light((-2.4, -3.2, 3.2), 190, "ffd2a0", 1.2)
    light((2.6, 1.4, 2.6), 260, "4a6cff", 1.0)
    light((1.4, -3.2, 1.2), 45, "7f8cff", 2.0)


def staged():
    booth()
    place(lambda: mina((-.5, -.15, .82), (.3, -.62, 1.06)), (-.92, -.2, 0), 48)
    place(lambda: stamp((-.74, -.3, 1.72)), (.95, .35, .12), -22, .92)
    place(lambda: page(.46, .56), (.32, -.45, 1.17), -12, 1, -18)
    place(lumi, (0, -.1, 1.62), 8, .75)
    place(panel, (0, -.1, 3.55), 0, 1.02, 0)
    text("It wants two. You gave one.", 0, 4.5, .19, WHITE, 1.2, bold=0, y=-.1)
    return (0, -9, 2.15), (0, 0, 2.05), 56, (1080, 1920)


def bloom(scene):
    tree = bpy.data.node_groups.new("bloom", "CompositorNodeTree")
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    layers, glare, out = (tree.nodes.new(t) for t in ("CompositorNodeRLayers", "CompositorNodeGlare",
                                                      "NodeGroupOutput"))
    glare.inputs["Type"].default_value = "Bloom"
    glare.inputs["Threshold"].default_value = .6
    glare.inputs["Strength"].default_value = .28
    glare.inputs["Size"].default_value = .45
    tree.links.new(layers.outputs["Image"], glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], out.inputs[0])
    scene.compositing_node_group = tree


def render(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    FONT.clear()
    scene = bpy.context.scene
    pos, target, lens, size = {
        "mina": lambda: portrait(mina, YELLOW, 16), "stamp": lambda: portrait(stamp, RED, 16),
        "lumi": lambda: portrait(lumi, CYAN, 12), "scene": staged}[name]()
    scene.world = bpy.data.worlds.new("w")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs[0].default_value = linear("0b0d26")
    scene.world.node_tree.nodes["Background"].inputs[1].default_value = .4
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    cam.location, cam.data.lens, scene.camera = pos, lens, cam
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()
    if ARGS.engine == "eevee":
        scene.render.engine = "BLENDER_EEVEE"
        scene.eevee.taa_render_samples = ARGS.samples
    else:
        scene.render.engine = "CYCLES"
        scene.cycles.samples, scene.cycles.use_denoising = ARGS.samples, True
    scene.render.threads_mode, scene.render.threads = "FIXED", 6  # other sessions share the machine
    scene.render.resolution_x, scene.render.resolution_y = size
    scene.view_settings.view_transform = "Standard"
    bloom(scene)
    scene.render.filepath = os.path.join(os.path.abspath(ARGS.out), name + ".png")
    start = time.time()
    bpy.ops.render.render(write_still=True)
    print(f"{name}: {time.time() - start:.1f} s", flush=True)


if __name__ == "__main__":
    os.makedirs(ARGS.out, exist_ok=True)
    for shot in [ARGS.only] if ARGS.only else SHOTS:
        render(shot)
