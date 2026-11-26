"""Frames of an episode: Mina, Stamp and Lumi at the customs booth, one PNG per frame (run inside Blender)."""
import argparse
import json
import math
import os
import sys
import time

parser = argparse.ArgumentParser(
    prog="blender -b -P videos/scene.py --", description=__doc__,
    epilog="No environment variable. Needs Blender 5, the Inter font, and the timeline.json of mix.py.\n"
           "Frames already in --out are skipped, so an interrupted render goes on where it stopped.\n\n"
           "example:\n  blender -b -P videos/scene.py -- --timeline work/timeline.json --out work/frames",
    formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--timeline", required=True, help="timeline.json written by mix.py")
parser.add_argument("--out", required=True, help="directory of the frames")
parser.add_argument("--at", type=float, nargs="+", metavar="SECONDS", help="render only the frames at these times")
parser.add_argument("--scale", type=int, default=67, help="percent of 1080x1920 (default: 67)")
parser.add_argument("--step", type=int, default=1, help="render one frame out of this many (default: 1)")
parser.add_argument("--samples", type=int, default=16, help="EEVEE samples (default: 16)")
ARGS = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])

import bpy  # noqa: E402  (after --help, which must work without Blender)
from mathutils import Matrix, Vector  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import characters as c  # noqa: E402

with open(ARGS.timeline) as f:
    T = json.load(f)
FPS, BAM = T["fps"], T.get("bams", [])
CROSS = T.get("cross") or []  # on, off, on, off...
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
neck = bpy.data.objects.new("neck", None)
scene.collection.objects.link(neck)
neck.parent, neck.location = mina, (0, 0, 1.32)
for o in list(mina.children):
    if o is not neck and o.location.z > 1.33:
        o.parent = neck
        o.matrix_parent_inverse = Matrix.Translation((0, 0, -1.32))
lumi_arm, = named("lumi_arm1", lumi)
PAGE = page.location.copy()
arms = {s: (named(f"mina_limb{s}", mina)[0], named(f"mina_hand{s}", mina)[0]) for s in (-1, 1)}

def error(stage, good, bad, message):
    """The code of Mina with its wrong end in red, and why this stage of the compiler refuses it."""
    c.frame(0, 0, 2.72, 1.36, c.CYAN, fill="04061a")
    c.text(stage, -1.22, .53, .16, c.LILAC, .8, "LEFT")
    c.text("REFUSED", 1.22, .53, .13, c.RED, 1.2, "RIGHT")
    c.box((0, 0, .41), (2.46, .005, .008), c.LILAC, glow=.4)
    x, size = -1.1, .4 if bad else .3
    for part, color in ((good, c.WHITE), (bad, c.RED)):
        c.text(part, x, .06, size, color, 1.0, "LEFT")
        bpy.context.view_layer.update()
        start, x = x, x + bpy.context.object.dimensions.x + .03
    if not bad:  # something is missing: an empty slot
        start, x = start + .06, start + .3
        c.frame((start + x) / 2, .06, x - start, .38, c.RED, r=.04, thick=.014, dash=True)
    c.route((start, 0, -.2), (x, 0, -.2), c.RED, 1.6)
    c.text(message, -1.1, -.45, .24, c.YELLOW, 1.2, "LEFT")


COLORS = {"WORD": c.CYAN, "SYMBOL": c.YELLOW, "NUMBER": GREEN, "STRING": "ff8bd0", "VALUE": "ff9a4d", "CALL": "b18cff"}
START, ROOM, OUT, STUCK = (-1.08, .16), (0, .16), (1.08, .16), (.62, .16)


def tag(kind, left, z):
    """The label of a token: a small plate with its type, from left."""
    w = .1 + .075 * len(kind)
    c.box((left + w / 2, 0, z), (w, .03, .16), COLORS.get(kind, c.YELLOW), glow=.9)
    c.text(kind, left + w / 2, z, .11, "04061a", 0, y=-.03)


def square(kind, x, z, w, h=.4):
    """A neon square around a token, its label on top."""
    for dx, dz, sx, sz in ((0, h / 2, w, .024), (0, -h / 2, w, .024), (-w / 2, 0, .024, h), (w / 2, 0, .024, h)):
        c.box((x + dx, 0, z + dz), (sx + .012, .02, sz), COLORS.get(kind, c.YELLOW), glow=1.6)
    tag(kind, x - w / 2, z + h / 2 + .09)


def width_of(word):
    return max(.36, .16 + .095 * len(word))


def plate(title, right=""):
    c.frame(0, 0, 2.72, 1.7, c.CYAN, fill="04061a")
    c.text(title, -1.22, .68, .16, c.LILAC, .8, "LEFT")
    c.text(right, 1.22, .68, .13, GREEN, 1.2, "RIGHT")


def tokens(stage, *_):
    """The pieces the lexer gives, side by side (see token_parts)."""
    plate(stage, "ACCEPTED")


def token_parts(args, board):
    """Each token, its place, and its place once they are put in another order."""
    words, kinds, order = args[1], args[2], args[3] if len(args) > 3 else range(len(args[1]))
    widths = [max(width_of(w), .14 + .075 * len(k)) for w, k in zip(words, kinds)]
    places = []
    for row in (range(len(words)), order):
        x, place = -(sum(widths) + .12 * (len(words) - 1)) / 2, {}
        for n in row:
            place[n] = x + widths[n] / 2
            x += widths[n] + .12
        places.append(place)

    def build(word, kind, w):
        square(kind, 0, -.12, w)
        c.text(word, 0, -.12, .22, c.WHITE, 1.2)

    return [(group(lambda: build(*token), board), places[0][n], places[1][n]) for n, token in enumerate(zip(words, kinds, widths))]


def shuffle(t, args, parts):
    """The tokens go to the other order, over or under each other."""
    k = ease(t, args[4], .7) if len(args) > 4 else 0
    for token, a, b in parts:
        token.location = (a + (b - a) * k, 0, .42 * math.sin(math.pi * k) * ((b < a) - (b > a)))


def recipe(kind, *_):
    """What something is made of, one row per way to make it (see recipe_parts)."""
    plate("")
    tag(kind, -1.22, .68)
    c.text("=", -1.22 + .2 + .075 * len(kind), .68, .2, c.WHITE, .8, "LEFT")


def recipe_parts(args, board):
    """The ingredients, empty squares, and when each one appears."""
    rows, times = args[1:]
    parts, times = [], iter(times)
    for n, kinds in enumerate(rows):
        h, z = (.5, -.15) if len(rows) == 1 else (.2, .23 - .44 * n)
        widths = [.2 + .085 * len(kind) for kind in kinds]
        x = -.8 if len(rows) > 1 else -(sum(widths) + .12 * (len(kinds) - 1)) / 2
        for i, (kind, w) in enumerate(zip(kinds, widths)):
            def build():
                square(kind, x + w / 2, z, w, h)
                if n and not i:
                    c.text("or", -1.15, z, .17, c.LILAC, .8, "LEFT")

            parts.append((group(build, board, (x + w / 2, 0, z)), next(times)))
            x += w + .12
    return parts


def nest(title, words, *_):
    """A sum, where each value holds the next one (see nest_parts)."""
    plate(title)
    for n, word in enumerate(words):
        c.text(word, -.94 + .44 * n, -.34, .3, COLORS["NUMBER" if word.isdigit() else "SYMBOL"], 1.0)


def nest_parts(args, board):
    """A square from each of these words to the last one, and when it appears."""
    parts = []
    for n, (first, at) in enumerate(args[2]):
        left, right = -1.13 + .44 * first, -.74 + .44 * (len(args[1]) - 1) + .08 * n
        low, high = -.56 - .08 * n, -.12 + .2 * n
        middle = ((left + right) / 2, (low + high) / 2)
        parts.append((group(lambda: square("VALUE", *middle, right - left, high - low), board, (middle[0], 0, middle[1])), at))
    return parts


def appear(t, args, parts):
    for part, at in parts:
        show(part, pop(t, at))


INPUT, PACK = .68, .56  # height of the input row on the plate (that of the title); scale of the stack
PITCH, LOW, CELL = .44, -.6 / .56, 1.2  # inside the stack: between two slots, height of the bottom slot, width of a slot
MIDDLE = -.15 / .56  # middle of the stack, inside it


def smaller(board, k=.82):
    """An empty in board that draws what hangs on it at k, to fit the labels of the tokens in the plate."""
    inner = group(lambda: None, board)
    inner.scale = [k] * 3
    return inner


def outline(kind, left, right, z, h):
    """A neon rectangle in the color of kind, without its label."""
    x, w = (left + right) / 2, right - left
    for dx, dz, sx, sz in ((0, h / 2, w, .024), (0, -h / 2, w, .024), (-w / 2, 0, .024, h), (w / 2, 0, .024, h)):
        c.box((x + dx, 0, z + dz), (sx + .012, .02, sz), COLORS.get(kind, c.YELLOW), glow=1.6)


def pile(title, *_):
    """The words still to read wait on the INPUT row; each one, shifted, falls into the STACK below, a narrow column
    open at the top, where it only says what it is (NUMBER...); a reduce replaces the items of the top by one (VALUE...);
    an arrow marks the top (see pile_parts)."""
    plate(title)
    c.text("INPUT", -.6, INPUT, .1, c.LILAC, .8, "LEFT")


def pile_parts(args, board):
    """Plays the shifts and reduces in order, to know each item of the stack: its slot, when it comes and when it is
    replaced; then draws the words of the input row, the items, the column, the arrow and the status."""
    words, kinds, shifts, reduces, (status, at) = args[1:6]
    done = group(lambda: c.text(status, 1.22, .68, .13, GREEN, 1.2, "RIGHT"), board, (1.1, 0, .68))
    events = sorted([(when, 0, i) for i, when in enumerate(shifts)] + [(r[3], 1, n) for n, r in enumerate(reduces)])
    stack, items, heights = [], [], []
    for when, reduce, i in events:
        if reduce:
            kind, first, _, _ = reduces[i]
            while stack and stack[-1]["first"] >= first:
                stack.pop()["end"] = when
            item = {"kind": kind, "first": first, "word": None}
        else:
            item = {"kind": kinds[i], "first": i, "word": i}
        item.update(start=when, end=1e9, slot=len(stack))
        stack.append(item)
        items.append(item)
        heights.append((when, len(stack) - 1))
    sizes = [.07 + .1 * len(w) for w in words]
    x, read = .5 - (sum(sizes) + .06 * (len(words) - 1)) / 2, []  # right of the title, where ACCEPTED comes once it is empty
    for word, s in zip(words, sizes):
        read.append((group(lambda: c.text(word, x + s / 2, INPUT, .2, c.WHITE, 1.2), board, (x + s / 2, 0, INPUT)), x + s / 2))
        x += s + .06
    pack = smaller(board, PACK)
    left, right, floor = MIDDLE - CELL / 2 - .12, MIDDLE + CELL / 2 + .12, LOW - .3
    roof = LOW + PITCH * max(h for _, h in heights) + .24

    def column():  # closed at the bottom, open at the top
        for a, b in (((left, floor), (right, floor)), ((left, floor), (left, roof)), ((right, floor), (right, roof))):
            c.limb((a[0], .01, a[1]), (b[0], .01, b[1]), .02, .02, c.LILAC, 6, 1.2)
        c.text("STACK", left - .14, (floor + roof) / 2, .22, c.LILAC, .8)
        bpy.context.object.rotation_euler = (math.pi / 2, -math.pi / 2, 0)  # along the wall, read upwards

    group(column, pack)

    def arrow():  # pointing left, at the item on the top
        c.limb((right + .5, 0, LOW), (right + .12, 0, LOW), .024, .024, c.YELLOW, 6, 1.4)
        for side in (-1, 1):
            c.limb((right + .12, 0, LOW), (right + .24, 0, LOW + .1 * side), .024, .024, c.YELLOW, 6, 1.4)
        c.text("TOP", right + .58, LOW, .22, c.YELLOW, 1.2, "LEFT")

    top = group(arrow, pack, (0, 0, LOW))
    for item in items:
        z, kind = LOW + PITCH * item["slot"], item["kind"]
        item["box"] = group(lambda: outline(kind, MIDDLE - CELL / 2, MIDDLE + CELL / 2, z, .36), pack, (MIDDLE, 0, z))
        said = f"{kind} {words[item['word']]}" if kind == "SYMBOL" else kind  # a symbol also says which one
        item["kind_of"] = group(lambda: c.text(said, MIDDLE, z, .2, COLORS.get(kind, c.YELLOW), 1.4), pack, (MIDDLE, 0, z))
        if item["word"] is not None:  # it falls from its word on the input row, and says it until it lands
            item["said"] = group(lambda: c.text(words[item["word"]], MIDDLE, z, .3, c.WHITE, 1.2), pack, (MIDDLE, 0, z))
            item["from"] = read[item["word"]][1] / PACK
    return {"read": read, "items": items, "top": top, "heights": heights, "status": (done, at)}


def shift(t, args, parts):
    """A shifted word leaves the input row and falls into the stack, where it turns into its kind; a reduce swaps the
    items of the top for one; the arrow follows the top."""
    for item in parts["items"]:
        z, start, end = LOW + PITCH * item["slot"], item["start"], item["end"]
        if item["word"] is None:
            show(item["box"], pop(t, start, end))
            show(item["kind_of"], pop(t, start, end))
            continue
        show(parts["read"][item["word"]][0], float(t < start))
        k = ease(t, start, .35)
        landed = start + .35
        place = (item["from"] + (MIDDLE - item["from"]) * k, 0, z + (INPUT / PACK - z) * (1 - k))
        for e in (item["box"], item["said"], item["kind_of"]):
            e.location = place
        show(item["box"], float(start <= t < end))
        show(item["said"], float(start <= t < landed))
        show(item["kind_of"], pop(t, landed, end))
    h = 0.0
    for when, slot in parts["heights"]:
        h += (slot - h) * ease(t, when + .1, .3)
    parts["top"].location.z = LOW + PITCH * h
    show(parts["top"], pop(t, parts["heights"][0][0]))
    appear(t, args, [parts["status"]])



def tree(title, *_):
    """The squares of the pile, unfolded: each one under the recipe that holds it (see tree_parts)."""
    plate(title)


def tree_parts(args, board):
    """Each node [kind, word, x, z, parent], its line to its parent, when it appears, and the scale (default .82)."""
    nodes, times = args[1:3]
    board = smaller(board, args[3] if len(args) > 3 else .82)
    widths = [max(.3, .12 + .08 * len(word), .14 + .075 * len(kind)) for kind, word, *_ in nodes]
    parts = []
    for (kind, word, x, z, up), w, at in zip(nodes, widths, times):
        def build():
            square(kind, x, z, w, .26)
            c.text(word, x, z, .17, c.WHITE, 1.2)
            if up >= 0:  # behind the label of the node
                c.limb((nodes[up][2], .02, nodes[up][3] - .13), (x, .02, z + .13), .008, .008, c.LILAC, 6, 1.0)

        parts.append((group(build, board, (x, 0, z)), at))
    return parts


def slices(title, *_):
    """A text that is cut into words, each one then framed by its type (see frame_words)."""
    plate(title)


def words_of(args, board):
    """For each word: its place in the text, its place once cut, and the groups of the word, its square and the knife."""
    words, kinds = args[1:3]
    parts, x = [], 0
    for n, (word, kind) in enumerate(zip(words, kinds)):
        column = (n - (len(words) - 1) / 2) * .88
        w = group(lambda: c.text(word, 0, 0, .28, c.WHITE, 1.2), board)
        bpy.context.view_layer.update()
        width = w.children[0].dimensions.x
        box = group(lambda: square(kind, column, -.05, max(width + .22, .14 + .075 * len(kind)), .46), board, (column, 0, -.05))
        knife = group(lambda: c.route((0, 0, -.24), (0, 0, .24), c.RED, 1.8, .016), board) if n else None
        parts.append({"start": x + width / 2, "left": x - .06, "column": column, "word": w, "box": box, "knife": knife})
        x += width + .12
    for part in parts:
        part["start"] -= (x - .12) / 2
        part["left"] -= (x - .12) / 2
    return parts


def frame_words(t, args, parts):
    """The knives fall between the words, the words move apart, and a square appears around each one."""
    cut, shown = args[3:]
    for part, at in zip(parts, shown):
        apart = ease(t, cut + .12, .3)
        part["word"].location = (part["start"] + (part["column"] - part["start"]) * apart, -.07, -.05)
        show(part["box"], pop(t, at))
        if part["knife"]:
            part["knife"].location = (part["left"], -.1, -.05 + .5 * (1 - ease(t, cut - .12, .12)))
            show(part["knife"], float(cut - .12 <= t < cut + .3))


def pitch(chars):
    return min(.2, 2.24 / len(chars))


def maze(title, enter, loop, leave, chars, *_):
    """A state machine: the door of the first character, a room where the others turn around, and the way out."""
    plate(title)
    c.frame(*START, .34, .34, c.LILAC, r=.16)
    c.text("IN", *START, .12, c.LILAC, .9)
    c.frame(*ROOM, .6, .4, c.CYAN, r=.1)
    c.ring((0, 0, .48), .15, .014, c.CYAN, (90, 0, 0), glow=1.6)
    c.cone((.15, 0, .46), .05, 0, .1, c.CYAN, 6, (180, 0, 0), glow=1.6)
    c.text(loop, .24, .52, .16, c.WHITE, 1.0, "LEFT")
    c.frame(*OUT, .34, .34, GREEN, r=.16)
    c.text("OUT", *OUT, .12, GREEN, .9)
    for x, color, label in ((-.61, c.YELLOW, enter), (.61, GREEN, leave)):
        c.route((x - .27, 0, .16), (x + .2, 0, .16), color, 1.4)
        c.cone((x + .23, 0, .16), .05, 0, .1, color, 6, (0, 90, 0), glow=1.4)
        c.text(label, x, .3, .18, color, 1.0)
    for i, char in enumerate(chars):
        c.text(char, -1.12 + pitch(chars) * i, -.55, .22, c.WHITE, 1.0)


def growing(color, board):
    """The four sides of a box that walk() stretches: top, bottom, left, right."""
    sides = []

    def build():
        for size in ((1, .02, .026), (1, .02, .026), (.026, .02, .36), (.026, .02, .36)):
            c.box((0, 0, 0), size, color, glow=1.8)
            sides.append(bpy.context.object)

    return group(build, board), sides


def maze_parts(args, board):
    chars, times, result, kind = args[4:]
    left = -1.12 - pitch(chars) / 2
    return {"ball": group(lambda: c.ico((0, 0, 0), .11, c.YELLOW, glow=1.2), board),
            "letters": [group(lambda: c.text(char, 0, 0, .15, "04061a", 0, y=-.13), board) for char in chars[:len(times)]],
            "boxes": [growing(color, board) for color in (c.YELLOW, COLORS[kind] if result else c.RED)],
            "end": group(lambda: tag(kind, left, -.28), board, (left, 0, -.28)) if result else
            group(lambda: c.text("NO DOOR!", .82, -.2, .19, c.RED, 1.3), board, (.82, 0, -.2))}


def walk(t, args, parts):
    """The ball goes in with the first character, around with the next ones, out (or stuck) with the last; a box grows
    over what it has read."""
    chars, times, result = args[4:7]
    k = sum(at <= t for at in times)
    x = ease(t, times[k - 1], .25) if k else 0
    places = [START] + [ROOM] * (len(times) - 1) + [OUT if result else STUCK]
    (ax, az), (bx, bz) = places[max(0, k - 1)], places[k]
    up = math.sin(math.pi * x) if k and places[k - 1] == places[k] else 0
    parts["ball"].location = (ax + (bx - ax) * x + .16 * math.sin(2 * math.pi * x) * up, -.1, az + (bz - az) * x + .44 * up)
    for n, letter in enumerate(parts["letters"]):
        letter.location = parts["ball"].location
        show(letter, float(n == k - 1))
    last = len(result) or len(times) - 1  # the characters that stay in the box
    before, now = min(max(0, k - 1), last), min(k, last)
    left = -1.12 - pitch(chars) / 2
    width = max(.01, pitch(chars) * (before + (now - before) * x))
    ended = t >= times[-1] + .15
    for (box, (top, bottom, start, end)), on in zip(parts["boxes"], (k and not ended, ended)):
        for side, z in ((top, -.37), (bottom, -.73)):
            side.location, side.scale.x = (left + width / 2, -.02, z), width
        start.location, end.location = (left, -.02, -.55), (left + width, -.02, -.55)
        show(box, float(on))
    show(parts["end"], pop(t, times[-1] + .15))


KINDS = {"error": (error, None, None), "maze": (maze, maze_parts, walk), "tokens": (tokens, token_parts, shuffle),
         "slice": (slices, words_of, frame_words), "recipe": (recipe, recipe_parts, appear), "nest": (nest, nest_parts, appear),
         "pile": (pile, pile_parts, shift), "tree": (tree, tree_parts, appear)}
BOARDS = []
for start, end, kind, *args in T.get("boards", []):
    draw, parts_of, _ = KINDS[kind]
    board = group(lambda: draw(*args), None)
    parts = parts_of and parts_of(args, board)
    BOARDS.append((start, end, kind, args, board, parts))

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

CAMS = {"WIDE": ((0, -9, 2.15), (0, 0, 2.05)), "MINA": ((-.1, -3.5, 1.72), (-.82, -.25, 1.42)),
        "STAMP": ((.25, -3.5, 1.75), (.82, .3, 1.42)), "PANEL": ((.1, -9.1, 2.75), (0, 0, 2.6)),
        "DESK": ((-.35, -3.3, 1.95), (.5, -.1, 1.3)), "LUMI": ((.1, -3.9, 2.3), (0, -.1, 2.42))}
POSE = {name: {-1: Vector(a), 1: Vector(b)} for name, a, b in (
    ("REST", (-.46, -.02, .72), (.46, -.02, .72)), ("OFFER", (-.5, -.15, .82), (.3, -.62, 1.06)),
    ("SHRUG", (-.66, -.3, 1.08), (.66, -.3, 1.08)), ("POINT", (-.5, -.2, .8), (.3, -.66, 1.34)))}
LOOK = {"STAMP": (0, 0, 0, 48), "LUMI": (-16, 0, 8, 12), "CAMERA": (0, 0, -34, 48)}  # degrees: head on body, body
LUMI_LOOK = {"CAMERA": (8,), "MINA": (-30,), "STAMP": (50,)}
SHOTS, POSES, LOOKS = T["shots"], T["poses"], T.get("looks") or [[0, "STAMP"]]


def level(who, t):
    v = T["level"][who]
    return v[min(len(v) - 1, max(0, int(t * FPS)))]


def turn(cues, table, t):
    """Where the last cue leads, eased from the one before it."""
    k = max(n for n, v in enumerate(cues) if v[0] <= t)
    a, b, x = table[cues[max(0, k - 1)][1]], table[cues[k][1]], ease(t, cues[k][0], .3)
    return [math.radians(p + (q - p) * x) for p, q in zip(a, b)]


def set_frame(t):
    # camera: a slow push inside each shot, and a shake after each blow
    i = max(k for k, s in enumerate(SHOTS) if s[0] <= t)
    start, (pos, target) = SHOTS[i][0], CAMS[SHOTS[i][1]]
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
    *neck.rotation_euler, body = turn(LOOKS, LOOK, t)
    mina.rotation_euler = (math.radians(-3 * talk), math.radians(2 * math.sin(3 * t) * talk), body)
    x = 1 - ease(t, T["mina_in"], 1.1) if "mina_in" in T else 0  # walks in from the left
    away = -2.2 * x
    mina.location.x = -.92 + away
    if 0 < x < 1:
        mina.location.z += .06 * abs(math.sin(9 * t))
    mouth.scale = (.1 + .02 * talk, .03, .02 + .08 * talk)
    k = max(n for n, p in enumerate(POSES) if p[0] <= t)
    x = ease(t, POSES[k][0], .2) if k else 1
    for s, (arm, hand) in arms.items():
        here = POSE[POSES[max(0, k - 1)][1]][s].lerp(POSE[POSES[k][1]][s], x) + Vector((0, 0, .03 * talk))
        hand.location = here
        aim(arm, Vector((.25 * s, 0, 1.16)), here)

    # Stamp: the arm goes up, waits, strikes the page, goes back up
    bpy.context.view_layer.update()
    strike = stamp.matrix_world.inverted() @ Vector((.28, -.42, 1.5))
    hit = 0.0
    for b in BAM:
        hit = max(hit, ease(t, b - .09, .09) * (1 - ease(t, b + .16, .4)))
    lift = max((ease(t, b - .5, .35) * (1 - ease(t, b - .09, .05)) for b in BAM), default=0)
    hand = (HAND + Vector((0, 0, .1 * lift))).lerp(strike, hit)
    grip.location, grip.rotation_euler = hand, (math.radians(-16 * hit), 0, 0)
    side = math.copysign(1, HAND.x)
    aim(stamp_limb, Vector((.43 * side, 0, 1.0)), hand)
    talk = level("stamp", t)
    stamp.location.z = .12 + .015 * talk - .03 * hit
    blink = .12 if (t % 3.1) > 2.98 or any(0 <= t - b < .16 for b in T.get("blinks", [])) else 1
    for o in eyes:
        o.scale.z = .16 * blink * (1 - .35 * talk)

    # the page: crossed or ticked by the blows
    crossed = any(on <= t < off for on, off in zip(CROSS[::2], CROSS[1::2]))
    ticked = t >= T.get("tick", 1e9) and not crossed
    if T.get("page_in"):  # slides from Mina to the counter
        x = ease(t, T["page_in"], .5)
        page.location = Vector((-.42 + away, -.75, 1.0)).lerp(PAGE, x) + Vector((0, 0, .25 * math.sin(math.pi * x)))
    for o in cross:
        o.hide_render = not crossed
    show(tick, 1.0 if ticked else 0.0)
    page.scale = [1.05 * (1 - .12 * hit)] * 3

    # Lumi: floats, grows a little when it talks
    talk = level("lumi", t)
    x = t - T.get("lumi_in", -9)
    drop = 3.2 * math.exp(-4.5 * x) * math.cos(5 * x) if x > 0 else 9
    lumi.location.z = 1.62 + .05 * math.sin(1.9 * t) + .04 * talk + drop
    x = ease(t, T.get("lumi_point", 1e9), .25)
    aim(lumi_arm, Vector((.34, 0, 1.1)), Vector((.52, -.04, 1.22)).lerp(Vector((.82, -.25, .98)), x))
    lumi.scale = [.75 * (1 + .08 * talk)] * 3
    lumi.rotation_euler.z = turn(T.get("lumi_looks") or [[0, "CAMERA"]], LUMI_LOOK, t)[0] + math.radians(8 * math.sin(.9 * t))
    for o in lumi.children_recursive:  # its feet would hang at the top of the close-ups
        o.hide_render = SHOTS[i][1] in ("DESK", "STAMP", "MINA") or t < T.get("lumi_in", -1)
    for start, end, kind, args, board, parts in BOARDS:
        k = pop(t, start, end)
        # out of Stamp or of Lumi, in front of them
        board.location = Vector((0, -.9, 2.3) if kind not in ("error", "tokens") else (.8, -1, 1.5)).lerp(
            Vector((0, -.5, 3.63 + .015 * math.sin(1.4 * t))), min(1, k))
        show(board, 1.02 * k)
        if parts and k > .02:
            KINDS[kind][2](t, args, parts)


os.makedirs(ARGS.out, exist_ok=True)
frames = [round(t * FPS) for t in ARGS.at] if ARGS.at else range(0, int(T["duration"] * FPS), ARGS.step)
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
