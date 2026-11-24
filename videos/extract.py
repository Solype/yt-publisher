"""Animated extract: Mina, Stamp and Lumi at the customs booth, one PNG per frame (run inside Blender)."""
import argparse
import json
import math
import os
import sys
import time

parser = argparse.ArgumentParser(
    prog="blender -b -P videos/extract.py --", description=__doc__,
    epilog="No environment variable. Needs Blender 5, the Inter font, and the timeline.json of extract_mix.py.\n"
           "Frames already in --out are skipped, so an interrupted render goes on where it stopped.\n\n"
           "example:\n  blender -b -P videos/extract.py -- --timeline extract/timeline.json --out extract/frames",
    formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--timeline", required=True, help="timeline.json written by extract_mix.py")
parser.add_argument("--out", required=True, help="directory of the frames")
parser.add_argument("--at", type=float, nargs="+", metavar="SECONDS", help="render only the frames at these times")
parser.add_argument("--scale", type=int, default=67, help="percent of 1080x1920 (default: 67)")
parser.add_argument("--samples", type=int, default=16, help="EEVEE samples (default: 16)")
ARGS = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])

import bpy  # noqa: E402  (after --help, which must work without Blender)
from mathutils import Matrix, Vector  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import characters as c  # noqa: E402

with open(ARGS.timeline) as f:
    T = json.load(f)
L, FPS, BAM = T["lines"], T["fps"], T["bams"]
GREEN = "4de08a"


def ease(t, start, dur=.25):
    x = min(1.0, max(0.0, (t - start) / dur))
    return x * x * (3 - 2 * x)


def pop(t, start, end=1e9):
    """0, then a quick overshoot to 1, and back to 0 after end."""
    if t < start or t >= end:
        return 0.0
    x = min(1.0, (t - start) / .22)
    return 1 + 2.2 * (x - 1) ** 3 + 1.2 * (x - 1) ** 2


def named(prefix, root):
    return [o for o in root.children_recursive if o.name.startswith(prefix)]


def aim(o, a, b):
    """Stretches a limb from a to b, in the space of its parent."""
    if "length" not in o:
        o["length"] = o.dimensions.z or 1.0
    d = b - a
    o.location = (a + b) / 2
    o.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    o.scale.z = d.length / o["length"]


def group(build, parent, at=(0, 0, 0)):
    """Runs build() and hangs everything it creates on an empty placed at at, in the space of parent."""
    before = set(bpy.data.objects)
    build()
    made = set(bpy.data.objects) - before
    e = bpy.data.objects.new("group", None)
    bpy.context.scene.collection.objects.link(e)
    e.parent, e.location = parent, at
    for o in made:
        o.parent = e
        o.matrix_parent_inverse = Matrix.Translation(-Vector(at))
    return e


def show(e, k):
    e.scale = [max(k, .001)] * 3
    for o in e.children_recursive:
        o.hide_render = k < .02


# ------------------------------------------------------------------ the set

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
c.FONT.clear()
c.booth()
mina = c.place(c.mina, (-.92, -.2, 0), 48)
stamp = c.place(lambda: c.stamp((-.74, -.3, 1.72)), (.95, .35, .12), -22, .92)
page = c.place(lambda: c.page(.46, .56), (.3, -.32, 1.1), -10, 1.05, -42)
lumi = c.place(c.lumi, (0, -.1, 1.62), 8, .75)


def check_mark():
    c.box((-.085, -.03, -.06), (.2, .012, .07), GREEN, (0, 45, 0), glow=1.4)
    c.box((.06, -.03, .02), (.4, .012, .07), GREEN, (0, -52, 0), glow=1.4)


tick = group(check_mark, page)
cross = named("cross", page)
grip = bpy.data.objects.new("grip", None)
scene.collection.objects.link(grip)
HAND = Vector((-.74, -.3, 1.72))
grip.parent, grip.location = stamp, HAND
for o in named("stamp_head", stamp):
    o.parent = grip
    o.matrix_parent_inverse = Matrix.Translation(-HAND)
stamp_limb, = named("stamp_limb", stamp)
eyes = named("stamp_eye", stamp)
mouth, = named("mina_mouth", mina)
arms = {s: (named(f"mina_limb{s}", mina)[0], named(f"mina_hand{s}", mina)[0]) for s in (-1, 1)}

panel = bpy.data.objects.new("panel", None)
scene.collection.objects.link(panel)


def base():
    c.frame(0, 0, 2.72, 1.36, c.CYAN, fill="04061a")
    c.text("CALL  add", -1.22, .53, .13, c.LILAC, .8, "LEFT")
    c.box((0, 0, .41), (2.46, .005, .008), c.LILAC, glow=.4)
    c.frame(-.02, -.06, .58, .42, c.YELLOW, r=.08, fill=c.YELLOW, alpha=1)
    c.text("add", -.02, -.06, .22, "04061a", 0, y=-.02)
    c.text("ARGUMENTS", .86, .24, .12, c.WHITE, .9)


def hole(z):
    c.frame(-.98, z, .3, .3, c.RED, r=.06, thick=.012, dash=True)
    c.text("?", -.98, z, .22, c.RED, 1.4)


def token(z, value):
    c.frame(-.98, z, .3, .3, c.CYAN, r=.06, fill=c.CYAN, alpha=1)
    c.text(value, -.98, z, .22, "04061a", 0, y=-.02)


def wire(z, color):
    c.route((-.8, 0, z), (-.35, 0, 0 if z > 0 else -.12), color)


P = {"base": group(base, panel)}
for n, (z, value) in enumerate(((.14, "3"), (-.26, "4"))):
    P[f"hole{n}"] = group(lambda: hole(z), panel, (-.98, 0, z))
    P[f"token{n}"] = group(lambda: token(z, value), panel, (-.98, 0, z))
    P[f"red{n}"] = group(lambda: wire(z, c.RED), panel)
    P[f"wire{n}"] = group(lambda: wire(z, c.CYAN), panel)
    x = -.82 + .66 * n
    P[f"empty{n}"] = group(lambda: c.frame(x, -.55, .6, .09, c.RED, r=.02, thick=.008), panel)
    P[f"bar{n}"] = group(lambda: c.box((x, 0, -.55), (.6, .02, .09), c.CYAN, glow=1.2), panel, (x, 0, -.55))
for n in range(3):
    P[f"count{n}"] = group(lambda: c.text(f"{n}/2", .86, -.08, .52, c.YELLOW if n < 2 else GREEN, 1.5), panel,
                           (.86, 0, -.08))
P["refused"] = group(lambda: c.text("REFUSED", 1.22, .53, .13, c.RED, 1.2, "RIGHT"), panel, (.9, 0, .53))
P["accepted"] = group(lambda: c.text("ACCEPTED", 1.22, .53, .13, GREEN, 1.2, "RIGHT"), panel, (.9, 0, .53))

scene.world = bpy.data.worlds.new("w")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs[0].default_value = c.linear("0b0d26")
scene.world.node_tree.nodes["Background"].inputs[1].default_value = .4
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
scene.collection.objects.link(cam)
scene.camera, cam.data.lens = cam, 56
scene.render.engine = "BLENDER_EEVEE"
scene.eevee.taa_render_samples = ARGS.samples
scene.render.threads_mode, scene.render.threads = "FIXED", 6  # other sessions share the machine
scene.render.resolution_x, scene.render.resolution_y = 1080, 1920
scene.render.resolution_percentage = ARGS.scale
scene.view_settings.view_transform = "Standard"
c.bloom(scene)

# ------------------------------------------------------------------ the shots

WIDE = (0, -9, 2.15), (0, 0, 2.05)
MINA = (-.1, -3.5, 1.72), (-.82, -.25, 1.42)
STAMP = (.25, -3.5, 1.75), (.82, .3, 1.42)
PANEL = (.1, -9.1, 2.75), (0, 0, 2.6)
DESK = (-.35, -3.3, 1.95), (.5, -.1, 1.3)
got_one = L[4]["start"] + .55 * (L[4]["end"] - L[4]["start"])  # "You gave one"
got_two = L[5]["start"] + .62 * (L[5]["end"] - L[5]["start"])  # "How about now?"
SHOTS = [(0, WIDE), (BAM[0] - .12, DESK), (L[1]["start"] - .08, MINA), (L[2]["start"] - .06, STAMP),
         (L[3]["start"] - .06, MINA), (L[4]["start"] - .1, WIDE), (got_one - .1, PANEL), (L[5]["start"] - .06, MINA),
         (got_two - .15, PANEL), (BAM[1] - .3, DESK), (L[6]["start"] + .75, WIDE)]
REST = {-1: Vector((-.46, -.02, .72)), 1: Vector((.46, -.02, .72))}
OFFER = {-1: Vector((-.5, -.15, .82)), 1: Vector((.3, -.62, 1.06))}
SHRUG = {-1: Vector((-.66, -.3, 1.08)), 1: Vector((.66, -.3, 1.08))}
POINT = {-1: Vector((-.5, -.2, .8)), 1: Vector((.3, -.66, 1.34))}
# (from when, pose)
POSES = [(0, OFFER), (BAM[0] + .1, REST), (L[1]["start"] + .05, SHRUG), (L[2]["start"] + .2, REST),
         (L[3]["start"], POINT), (L[4]["start"] + .2, REST), (L[5]["start"], SHRUG), (got_two - .3, OFFER),
         (L[6]["start"] + .4, REST)]


def level(who, t):
    v = T["level"][who]
    return v[min(len(v) - 1, max(0, int(t * FPS)))]


def set_frame(t):
    # camera: a slow push inside each shot, and a shake after each blow
    i = max(k for k, s in enumerate(SHOTS) if s[0] <= t)
    start, (pos, target) = SHOTS[i]
    pos, target = Vector(pos), Vector(target)
    pos = pos.lerp(target, min(.06, .03 * (t - start)))
    for b in BAM:
        if 0 <= t - b < .35:
            k = .05 * math.exp(-11 * (t - b))
            pos += Vector((k * math.sin(90 * t), 0, k * math.cos(75 * t)))
    cam.location = pos
    cam.rotation_euler = (target - pos).to_track_quat("-Z", "Y").to_euler()

    # Mina: breath, small jumps when she talks, mouth on the sound, arms from pose to pose
    talk = level("mina", t)
    mina.location.z = .012 * math.sin(2.2 * t) + .035 * talk
    mina.rotation_euler = (math.radians(-3 * talk), math.radians(2 * math.sin(3 * t) * talk), math.radians(48))
    mouth.scale = (.1 + .02 * talk, .03, .02 + .08 * talk)
    k = max(n for n, p in enumerate(POSES) if p[0] <= t)
    x = ease(t, POSES[k][0], .2) if k else 1
    for s, (arm, hand) in arms.items():
        here = POSES[max(0, k - 1)][1][s].lerp(POSES[k][1][s], x) + Vector((0, 0, .03 * talk))
        hand.location = here
        aim(arm, Vector((.25 * s, 0, 1.16)), here)

    # Stamp: the arm goes up, waits, strikes the page, goes back up
    bpy.context.view_layer.update()
    strike = stamp.matrix_world.inverted() @ Vector((.28, -.42, 1.5))
    hit = 0.0
    for b in BAM:
        hit = max(hit, ease(t, b - .09, .09) * (1 - ease(t, b + .16, .4)))
    lift = max(ease(t, b - .5, .35) * (1 - ease(t, b - .09, .05)) for b in BAM)
    hand = (HAND + Vector((0, 0, .1 * lift))).lerp(strike, hit)
    grip.location, grip.rotation_euler = hand, (math.radians(-16 * hit), 0, 0)
    side = math.copysign(1, HAND.x)
    aim(stamp_limb, Vector((.43 * side, 0, 1.0)), hand)
    talk = level("stamp", t)
    stamp.location.z = .12 + .015 * talk - .03 * hit
    blink = .12 if (t % 3.1) > 2.98 else 1
    for o in eyes:
        o.scale.z = .16 * blink * (1 - .35 * talk)

    # the page: crossed by the first blow, ticked by the second one
    crossed, ticked = BAM[0] <= t < got_two - .2, t >= BAM[1]
    for o in cross:
        o.hide_render = not crossed
    show(tick, 1.0 if ticked else 0.0)
    page.scale = [1.05 * (1 - .12 * hit)] * 3

    # Lumi: floats, grows a little when it talks; the panel comes out of it
    talk = level("lumi", t)
    lumi.location.z = 1.62 + .05 * math.sin(1.9 * t) + .04 * talk
    lumi.scale = [.75 * (1 + .08 * talk)] * 3
    lumi.rotation_euler.z = math.radians(8 + 8 * math.sin(.9 * t))
    for o in lumi.children_recursive:  # its feet would hang at the top of the close-ups
        o.hide_render = SHOTS[i][1] in (DESK, STAMP, MINA)
    k = pop(t, L[4]["start"] - .05)
    panel.location = Vector((0, -.1, 2.5)).lerp(Vector((0, -.1, 3.55 + .015 * math.sin(1.4 * t))), min(1, k))
    panel.scale = [max(.001, 1.02 * k)] * 3
    two = t >= got_two
    one = t >= got_one
    on = {"base": 1, "hole0": not one, "token0": pop(t, got_one), "red0": not one, "wire0": one,
          "hole1": not two, "token1": pop(t, got_two), "red1": not two, "wire1": two,
          "empty0": not one, "bar0": pop(t, got_one), "empty1": not two, "bar1": pop(t, got_two),
          "count0": not one, "count1": pop(t, got_one, got_two), "count2": pop(t, got_two),
          "refused": t < BAM[1], "accepted": pop(t, BAM[1])}
    for name, v in on.items():
        show(P[name], float(v) if k > .02 else 0.0)


os.makedirs(ARGS.out, exist_ok=True)
frames = [round(t * FPS) for t in ARGS.at] if ARGS.at else range(int(T["duration"] * FPS))
begin, count = time.time(), 0
for n in frames:
    path = os.path.join(os.path.abspath(ARGS.out), f"{n:04}.png")
    if os.path.exists(path) and not ARGS.at:
        continue
    set_frame(n / FPS)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    count += 1
    if count % 24 == 0 or ARGS.at:
        print(f"frame {n}: {(time.time() - begin) / count:.1f} s per frame", flush=True)
print(f"{count} frames in {time.time() - begin:.0f} s", flush=True)
