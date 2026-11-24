#!/usr/bin/env python3
"""Render the "how a compiler works" videos, based on Krc (https://github.com/Solype/Krc).

The machine code, sizes and addresses shown are the output of Krc v0.1.0 on the Korean
program of the last scene; code, tokens and messages are translated to English, the IR is simplified.
"""
import argparse
import hashlib
import math
import os
import subprocess
import sys
import wave

import cairo
import gi
import numpy as np

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

FPS = 30
RATE = 22050  # sample rate of the piper voice
LEAD, GAP, TAIL = 0.5, 0.35, 0.8  # silences: scene start, between beats, scene end
BG, SURF, LINE = "0f1719", "152125", "26373b"
FG, MUTED, TEAL, ORANGE = "e2ebe8", "95a7a8", "6cc2ad", "e48b60"
TEAL_BG, ORANGE_BG = "1b3530", "3a2319"
MONO = "Source Code Pro, Noto Sans Mono CJK KR"
SANS = "Inter, Noto Sans CJK KR"


def ease(t, start, dur=0.5):
    """0 before start, 1 after start + dur, smooth in between."""
    x = min(1.0, max(0.0, (t - start) / dur))
    return x * x * (3 - 2 * x)


def mix(a, b, k):
    return a + (b - a) * k


class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.surface = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
        self.cr = cairo.Context(self.surface)
        self.layout = PangoCairo.create_layout(self.cr)

    def color(self, rgb, alpha=1.0):
        self.cr.set_source_rgba(*(int(rgb[i:i + 2], 16) / 255 for i in (0, 2, 4)), alpha)

    def clear(self):
        self.color(BG)
        self.cr.paint()

    def measure(self, s, size, mono=False, bold=False):
        font = Pango.FontDescription()
        font.set_family(MONO if mono else SANS)
        font.set_absolute_size(size * Pango.SCALE)
        font.set_weight(Pango.Weight.SEMIBOLD if bold else Pango.Weight.NORMAL)
        self.layout.set_font_description(font)
        self.layout.set_text(s, -1)
        return self.layout.get_pixel_size()

    def text(self, x, y, s, size, color=FG, alpha=1.0, mono=False, bold=False, anchor=0.5):
        """y is the middle of the line; anchor 0 = left, 0.5 = center, 1 = right."""
        if alpha <= 0:
            return
        w, h = self.measure(s, size, mono, bold)
        self.color(color, alpha)
        self.cr.move_to(x - w * anchor, y - h / 2)
        PangoCairo.show_layout(self.cr, self.layout)

    def box(self, x, y, w, h, fill=SURF, stroke=LINE, alpha=1.0, r=16, lw=2):
        if alpha <= 0:
            return
        cr = self.cr
        cr.new_sub_path()
        for cx, cy, a in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0),
                          (x + r, y + h - r, 90), (x + r, y + r, 180)):
            cr.arc(cx, cy, r, math.radians(a), math.radians(a + 90))
        cr.close_path()
        if fill:
            self.color(fill, alpha)
            cr.fill_preserve()
        if stroke:
            self.color(stroke, alpha)
            cr.set_line_width(lw)
            cr.stroke_preserve()
        cr.new_path()

    def pill(self, x, y, s, size, fg=TEAL, bg=TEAL_BG, alpha=1.0, mono=True, pad=24):
        """Centered on (x, y); returns its width."""
        w = self.measure(s, size, mono)[0] + 2 * pad
        h = size * 1.9
        self.box(x - w / 2, y - h / 2, w, h, bg, fg, alpha)
        self.text(x, y, s, size, fg, alpha, mono)
        return w

    def arrow(self, x1, y1, x2, y2, k=1.0, color=MUTED, head=True):
        """A line drawn up to the fraction k."""
        if k <= 0:
            return
        cr = self.cr
        ex, ey = mix(x1, x2, k), mix(y1, y2, k)
        self.color(color)
        cr.set_line_width(4)
        cr.move_to(x1, y1)
        cr.line_to(ex, ey)
        cr.stroke()
        if head and k > 0.95:
            a = math.atan2(y2 - y1, x2 - x1)
            cr.move_to(ex, ey)
            for d in (2.6, -2.6):
                cr.line_to(ex + 20 * math.cos(a + d), ey + 20 * math.sin(a + d))
            cr.close_path()
            cr.fill()

    def code(self, x, y, lines, size=40, alpha=1.0, colors=None, step=1.55):
        for i, line in enumerate(lines):
            self.text(x, y + i * size * step, line, size, (colors or {}).get(i, FG), alpha, True, anchor=0)


# ---------------------------------------------------------------- long video, 1920 x 1080

PROGRAM = ["int add(int a, int b) {", "    return a + b;", "}", "", "int main() {", "    return add(3, 4);", "}"]
KOREAN = ["정수를 반환하는 더하다(정수 가, 정수 나) {", "    (가 + 나)를 반환해요.", "}", "",
          "정수를 반환하는 main() {", "    3과 4를 더해서 반환해요.", "}"]
BYTES = ["48 55 48 8b ec 48 83 ec", "20 48 89 7d f8 48 89 75", "f0 48 8b 45 f8 48 03 45",
         "f0 48 89 45 e8 48 8b 45", "e8 48 8b e5 48 5d c3 48", "55 48 8b ec 48 83 ec 10"]
STAGES = ["Lexer", "Parser", "Semantics", "IR", "Codegen", "Encoding", "Linker"]


def header(g, stage):
    """Progress bar of the pipeline, with the current stage lit."""
    step = 250
    for i, name in enumerate(STAGES):
        x = g.w / 2 + (i - (len(STAGES) - 1) / 2) * step
        color = ORANGE if i == stage else TEAL if i < stage else MUTED
        if i:
            g.arrow(x - step + 90, 80, x - 90, 80, color=TEAL if i <= stage else LINE, head=False)
        g.text(x, 80, name, 32, color, bold=i == stage)


def s_hook(g, t, b):
    a = ease(t, b[0] - 0.3)
    g.box(130, 260, 720, 560, alpha=a)
    g.code(190, 350, PROGRAM, 40, a)
    k = ease(t, b[1])
    g.box(1070, 260, 720, 560, SURF, TEAL, k)
    g.code(1130, 350, BYTES, 40, k, {i: TEAL for i in range(len(BYTES))}, step=2)
    g.text(490, 890, "what you write", 36, MUTED, a)
    g.text(1430, 890, "what the processor reads", 36, MUTED, k)
    if t > b[2]:
        g.arrow(875, 540, 1050, 540, ease(t, b[2]), ORANGE)
        g.text(960, 475, "compiler", 36, ORANGE, ease(t, b[2]), bold=True)


def s_title(g, t, b):
    g.text(960, 480, "How a compiler works", 110, FG, ease(t, 0), bold=True)
    g.text(960, 610, "one small program, all the way down to bytes", 46, MUTED, ease(t, 0.4))


def s_program(g, t, b):
    k = ease(t, b[2])
    g.box(460, 230, 1000, 620)
    if k:
        g.box(490, 350 + 5 * 74 - 38, 940, 76, ORANGE_BG, ORANGE, k, 12)
    g.code(540, 350, PROGRAM, 48, 1, step=74 / 48)
    g.text(960, 930, "expected result: 7", 44, TEAL, ease(t, b[1]), True)


LEX = [("return", "keyword"), ("add", "name"), ("(", "punctuation"), ("3", "integer"), (",", "punctuation"),
       ("4", "integer"), (")", "punctuation"), (";", "punctuation")]


def s_lexer(g, t, b):
    header(g, 0)
    src, cell, size = "return add(3, 4);", 84, 58
    g.text(960, 270, "characters", 38, MUTED, 1 - ease(t, b[1]))
    g.text(960, 270, "tokens", 38, TEAL, ease(t, b[1] + 0.6), True)
    k = ease(t, b[1] + 0.3, 1.2)
    # where each token ends up: its width, plus a fixed gap
    widths = [max(len(word) * 46 + 50, 100) for word, _ in LEX]
    gap = 50
    x = 960 - (sum(widths) + gap * (len(LEX) - 1)) / 2
    targets, pos = [], 0
    for (word, kind), w in zip(LEX, widths):
        pos = src.index(word, pos)
        g.box(x, 440, w, 130, TEAL_BG, TEAL, ease(t, b[1] + 1.1))
        for j in range(len(word)):
            targets.append((pos + j, x + w / 2 + (j - (len(word) - 1) / 2) * 46))
        pos += len(word)
        if kind != "punctuation":
            g.text(x + w / 2, 630, kind, 32, MUTED, ease(t, b[1] + 1.4))
        x += w + gap
    g.text(960, 720, "( , ) ;  punctuation", 32, MUTED, ease(t, b[1] + 1.4), True)
    end = dict(targets)
    for i, c in enumerate(src):
        cx = 960 + (i - (len(src) - 1) / 2) * cell
        shown = ease(t, b[0] + i * 0.07, 0.3)
        g.box(cx - 39, 465, 78, 80, SURF, LINE, shown * (1 - k), 10)
        if c == " ":
            g.text(cx, 505, "␣", 40, MUTED, shown * (1 - k), True)
        else:
            g.text(mix(cx, end[i], k), 505, c, size, FG, shown, True)
    g.text(960, 900, "spaces are gone", 40, ORANGE, ease(t, b[2]))


def node(g, x, y, s, alpha, hot=False):
    g.pill(x, y, s, 46, ORANGE if hot else TEAL, ORANGE_BG if hot else TEAL_BG, alpha, pad=36)


def s_parser(g, t, b):
    header(g, 1)
    fade = 1 - 0.65 * ease(t, b[1])
    widths = [g.measure(word, 40, True)[0] + 44 for word, _ in LEX]
    x = 960 - (sum(widths) + 30 * (len(LEX) - 1)) / 2
    for (word, _), w in zip(LEX, widths):
        g.pill(x + w / 2, 230, word, 40, MUTED, SURF, fade, pad=22)
        x += w + 30
    times = [b[1], b[2], b[3], b[3] + 0.9]
    spots = [(960, 400), (960, 580), (740, 780), (1180, 780)]
    for i, (p, q) in enumerate(((0, 1), (1, 2), (1, 3))):
        (x1, y1), (x2, y2) = spots[p], spots[q]
        g.arrow(x1, y1 + 48, x2, y2 - 48, ease(t, times[q] - 0.2), LINE, head=False)
    for (x, y), s, at in zip(spots, ["return", "call add", "3", "4"], times):
        node(g, x, y, s, ease(t, at), hot=s == "return")
    g.text(960, 960, "no comma, no parentheses: the shape carries the meaning", 40, ORANGE, ease(t, b[4]))


def s_semantics(g, t, b):
    header(g, 2)
    k = ease(t, b[4])  # the checklist leaves, the error comes
    g.pill(960, 210, "return add(3, 4);", 46, FG, SURF, ease(t, 0) * (1 - k))
    for i, s in enumerate(["add exists", "add takes two integers: 3 and 4", "main returns an integer"]):
        a = ease(t, b[i + 1]) * (1 - k)
        g.box(460, 300 + i * 170, 1000, 120, alpha=a)
        g.text(580, 360 + i * 170, s, 46, FG, a, anchor=0)
        g.text(520, 360 + i * 170, "✓", 52, TEAL, ease(t, b[i + 1] + 0.6) * (1 - k))
    g.box(260, 300, 1400, 420, SURF, ORANGE, k)
    g.code(320, 380, ["int main() {", "    return add(3);", "}"], 46, k)
    g.text(320, 640, "add.kr:6:5: no function 'add' takes the arguments (int)", 38, ORANGE, ease(t, b[4] + 0.6),
           True, anchor=0)
    g.text(960, 800, "line 6, column 5", 40, MUTED, ease(t, b[4] + 1.2))


IR = ["fn add(v0, v1) -> int", "    v2 = v0 + v1", "    return v2", "", "fn main() -> int",
      "    v0 = call add(3, 4)", "    return v0"]


def s_ir(g, t, b):
    header(g, 3)
    g.box(110, 240, 760, 600)
    g.code(160, 330, PROGRAM, 42, 0.75)
    g.arrow(890, 540, 1010, 540, ease(t, b[0] + 0.8), ORANGE)
    g.box(1030, 240, 780, 600, SURF, TEAL, ease(t, b[0] + 1))
    for i, line in enumerate(IR):
        hot = ease(t, b[1]) > 0.5 and i in (1, 5)
        g.text(1080, 330 + i * 42 * 1.55, line, 42, ORANGE if hot else FG, ease(t, b[0] + 1.2 + i * 0.3), True,
               anchor=0)
    g.text(960, 930, "one operation per line", 42, ORANGE, ease(t, b[1]))
    g.text(960, 990, "not tied to any processor", 36, MUTED, ease(t, b[2]))


def s_codegen(g, t, b):
    header(g, 4)
    g.pill(585, 240, "v2 = v0 + v1", 50, alpha=ease(t, b[0]))
    g.arrow(585, 300, 585, 385, ease(t, b[0] + 0.8), ORANGE)
    asm = [("mov rax, [rbp-8]", "load"), ("add rax, [rbp-16]", "add"), ("mov [rbp-24], rax", "store")]
    at = [b[2], b[3], b[4]]
    for i, (line, what) in enumerate(asm):
        hot = at[i] <= t < (at + [1e9])[i + 1]
        y = 460 + i * 130
        g.box(170, y - 52, 830, 104, ORANGE_BG if hot else SURF, ORANGE if hot else LINE,
              ease(t, b[0] + 1 + i * 0.3))
        g.text(210, y, line, 46, FG, ease(t, b[0] + 1 + i * 0.3), True, anchor=0)
        g.text(960, y, what, 36, ORANGE if hot else MUTED, ease(t, at[i]), anchor=1)
    s = ease(t, b[1])
    g.text(1430, 340, "stack", 38, MUTED, s)
    slots = [("v0", "[rbp-8]", "3"), ("v1", "[rbp-16]", "4"), ("v2", "[rbp-24]", "7" if t > at[2] + 0.4 else "")]
    for i, (name, where, value) in enumerate(slots):
        y = 420 + i * 110
        g.box(1180, y - 48, 500, 96, SURF, TEAL, s, 8)
        g.text(1210, y, name, 42, TEAL, s, True, anchor=0)
        g.text(1300, y, where, 34, MUTED, s, True, anchor=0)
        g.text(1640, y, value, 48, FG, s, True, True, anchor=1)
    rax = "" if t < at[0] + 0.4 else "3" if t < at[1] + 0.4 else "7"
    g.box(1180, 790, 500, 110, TEAL_BG, TEAL, s, 8)
    g.text(1210, 845, "rax", 42, TEAL, s, True, anchor=0)
    g.text(1640, 845, rax, 54, FG, s, True, True, anchor=1)
    g.text(1430, 940, "register", 34, MUTED, s)


ENCODED = [("48", "64-bit operation"), ("03", "add to a register"), ("45", "rax, [rbp + offset]"),
           ("f0", "offset: -16")]


def s_encoding(g, t, b):
    header(g, 5)
    g.pill(960, 290, "add rax, [rbp-16]", 58, FG, SURF, ease(t, b[0]), pad=40)
    g.arrow(960, 360, 960, 450, ease(t, b[0] + 0.8), ORANGE)
    for i, (byte, what) in enumerate(ENCODED):
        x = 960 + (i - 1.5) * 400
        hot = b[i + 1] <= t < (b + [1e9])[i + 2]
        a = ease(t, b[0] + 1.4 + i * 0.15)
        g.box(x - 130, 490, 260, 200, ORANGE_BG if hot else TEAL_BG, ORANGE if hot else TEAL, a)
        g.text(x, 590, byte, 110, ORANGE if hot else TEAL, a, True, True)
        g.text(x, 760, what, 36, FG, ease(t, b[i + 1]))


def s_linker(g, t, b):
    header(g, 6)
    g.text(480, 210, "add.o", 42, TEAL, ease(t, b[0]), True)
    rows = [("ELF header", "64 bytes"), (".text", "97 bytes of code"), (".symtab", "add, main"),
            (".rela.text", "1 hole to fill")]
    for i, (name, what) in enumerate(rows):
        hot = t > b[1] and i == 3
        a = ease(t, b[0] + 0.5 + i * 0.35)
        g.box(140, 260 + i * 140, 680, 120, ORANGE_BG if hot else SURF, ORANGE if hot else LINE, a, 8)
        g.text(180, 320 + i * 140, name, 40, FG, a, True, anchor=0)
        g.text(780, 320 + i * 140, what, 34, ORANGE if hot else MUTED, a, anchor=1)
    g.text(1370, 320, "call add", 46, FG, ease(t, b[1]), True)
    done = ease(t, b[2] + 0.8)
    for i, (old, new) in enumerate(zip("e8 00 00 00 00".split(), "e8 ad ff ff ff".split())):
        x = 1370 + (i - 2) * 160
        c, bg = (TEAL, TEAL_BG) if i == 0 or done > 0.5 else (ORANGE, ORANGE_BG)
        g.box(x - 70, 400, 140, 130, bg, c, ease(t, b[1]))
        g.text(x, 465, old, 64, c, ease(t, b[1]) * (1 - done if i else 1), True, True)
        if i:
            g.text(x, 465, new, 64, c, done, True, True)
    g.text(1370, 600, "address of add: unknown", 38, ORANGE, ease(t, b[1]) * (1 - done))
    g.text(1370, 600, "address of add: 83 bytes back", 38, TEAL, done)
    g.arrow(1370, 660, 1370, 750, ease(t, b[2] + 1.2), ORANGE)
    g.pill(1370, 820, "a.out", 54, alpha=ease(t, b[2] + 1.6), pad=40)


def s_run(g, t, b):
    g.box(360, 270, 1200, 500, "0a1012", LINE)
    lines = [("$ ./compiler -x add.kr", 0, FG), ("ELF written: add.o", 0.4, MUTED), ("$ ./a.out", 0.8, FG),
             ("$ echo $?", 1.2, FG)]
    for i, (s, at, c) in enumerate(lines):
        g.text(420, 345 + i * 78, s, 46, c, ease(t, b[0] + at, 0.2), True, anchor=0)
    g.text(420, 345 + 4 * 78 + 20, "7", 72, TEAL, ease(t, b[1], 0.2), True, True, anchor=0)


def s_reveal(g, t, b):
    g.text(960, 130, "Krc", 84, TEAL, ease(t, b[0]), bold=True)
    k = ease(t, b[1])
    g.box(90, 260, 700, 520, alpha=1)
    g.code(130, 340, PROGRAM, 38, 1)
    g.arrow(805, 520, 865, 520, k, ORANGE)
    g.box(880, 260, 950, 520, SURF, TEAL, k)
    g.code(920, 340, KOREAN, 38, k)
    g.text(960, 850, "extra step: split the particles, un-conjugate the verbs", 40, ORANGE, ease(t, b[2]))
    g.text(960, 920, "same tree, same bytes", 44, TEAL, ease(t, b[3]), bold=True)
    g.text(960, 1010, "Code, tokens and messages translated from Korean, IR simplified. Machine code and addresses: real Krc v0.1.0 output.",
           28, MUTED, k)


def s_outro(g, t, b):
    g.text(960, 440, "github.com/Solype/Krc", 84, TEAL, ease(t, 0), True, True)
    g.text(960, 570, "a Korean programming language, its compiler in Rust", 44, MUTED, ease(t, 0.4))


# (draw function, narration beats); a beat is its caption, or (caption, spoken) when they differ
LONG = [
    (s_hook, ["Your processor cannot read this.", "It can only read this.",
              "A compiler turns one into the other."]),
    (s_title, ["Let's follow one program, all the way down."]),
    (s_program, ["add takes two integers and returns their sum. main calls it with 3 and 4.",
                 "So we expect 7.", "Let's follow this line."]),
    (s_lexer, ["Step one: the lexer. To a compiler, your file is just a row of characters.",
               "The lexer groups them into tokens: words, numbers, punctuation.",
               "And the spaces disappear."]),
    (s_parser, ["Step two: the parser. It checks the tokens against the grammar of the language, and builds a tree.",
                "Return", "the result of a call to add,", "with two arguments: 3, and 4.",
                "The commas and parentheses have done their job: the shape of the tree now carries the meaning."]),
    (s_semantics, ["Step three: semantic analysis. The grammar is fine, but does it make sense?",
                   "Does add exist?", "Does it take two integers?", "Does main return what it promised?",
                   "Forget an argument, and the compiler stops, and points at the exact place."]),
    (s_ir, ["Step four: the intermediate representation. The program becomes a list of tiny steps.",
            "One operation per line, on numbered variables.",
            "It is close to assembly, but not tied to any processor yet."]),
    (s_codegen, ["Step five: code generation. Each step becomes real processor instructions.",
                 "Every variable gets a slot on the stack.", "Load the first value.", "Add the second.",
                 "Store the result."]),
    (s_encoding, ["Step six: encoding. Every instruction becomes bytes. This addition takes four.",
                  ("48: work on 64 bits.", "Four eight: work on sixty-four bits."),
                  ("03: add.", "Zero three: add."),
                  ("45: which register, and which memory.", "Four five: which register, and which memory."),
                  ("F0: minus 16.", "F zero: minus sixteen.")]),
    (s_linker, ["Those bytes go into an object file, in the ELF format that Linux uses.",
                "But there is a hole. In the call, the address of add is still zero.",
                "The linker fills it in, and adds the code that starts the program."]),
    (s_run, ["And now, it runs.", "Seven."]),
    (s_reveal, [("One last thing. The compiler in this video is called Krc.",
                 "One last thing. The compiler in this video is called K R C."),
                "And this is the program it really read.",
                "The language is Korean, so Krc has one extra step: it splits off the particles, "
                "and un-conjugates the verbs.",
                "After that, the compiler does not care which language you speak."]),
    (s_outro, ["It is open source. The link is in the description."]),
]
# the only caption with Krc besides the one above
LONG[-2][1][2] = (LONG[-2][1][2], LONG[-2][1][2].replace("Krc", "K R C"))

# ---------------------------------------------------------------- short, 1080 x 1920


def s_short(g, t, b):
    cx = 500  # left of center: the buttons of Shorts cover the right edge
    g.text(cx, 150, "a + b", 110, FG, ease(t, 0), True, True)
    g.cr.save()
    g.cr.translate(cx * 0.12, 75)  # the title of a Short covers its bottom: keep everything above y = 1500
    g.cr.scale(0.88, 0.88)

    def row(i, y, label):
        a = ease(t, b[i])
        g.arrow(cx, y - 150, cx, y - 105, a)
        g.text(70, y - 128, label, 34, ORANGE if b[i] <= t < (b + [1e9])[i + 1] else MUTED, a, anchor=0)
        return a

    a = row(1, 470, "tokens")
    for i, s in enumerate("a+b"):
        g.box(cx - 70 + (i - 1) * 190, 420, 140, 110, TEAL_BG, TEAL, a)
        g.text(cx + (i - 1) * 190, 475, s, 60, TEAL, a, True)
    a = row(2, 720, "tree")
    for x in (-130, 130):
        g.arrow(cx, 690, cx + x, 800, a, LINE, head=False)
    for x, y, s in ((0, 690, "+"), (-130, 810, "a"), (130, 810, "b")):
        g.box(cx + x - 55, y - 45, 110, 90, TEAL_BG, TEAL, a)
        g.text(cx + x, y, s, 52, TEAL, a, True)
    a = row(3, 1030, "intermediate code")
    g.pill(cx, 1025, "v2 = v0 + v1", 54, alpha=a)
    a = row(4, 1250, "instructions")
    for i, s in enumerate(["mov rax, [rbp-8]", "add rax, [rbp-16]", "mov [rbp-24], rax"]):
        g.text(cx, 1230 + i * 62, s, 46, ORANGE if i == 1 and t > b[5] else FG, a, True)
    a = row(5, 1530, "bytes")
    for i, (byte, _) in enumerate(ENCODED):
        g.box(cx - 75 + (i - 1.5) * 180, 1475, 150, 110, ORANGE_BG, ORANGE, ease(t, b[5] + 1.6 + i * 0.45))
        g.text(cx + (i - 1.5) * 180, 1530, byte, 64, ORANGE, ease(t, b[5] + 1.6 + i * 0.45), True, True)
    g.cr.restore()


SHORT = [(s_short, [("What does a + b become, inside your computer?", "What does A plus B become, inside your computer?"),
                    "First, the compiler cuts it into tokens.",
                    ("Then it builds a tree: a plus, with a and b below.",
                     "Then it builds a tree: a plus, with A and B below."),
                    "The tree becomes one simple step.",
                    "That step becomes three instructions: load, add, store.",
                    ("And the add becomes four bytes: 48, 03, 45, F0.",
                     "And the add becomes four bytes: four eight, zero three, four five, F zero."),
                    "That is all your processor ever sees."])]

VIDEOS = {"long": (LONG, 1920, 1080, False), "short": (SHORT, 1080, 1920, True)}


# ---------------------------------------------------------------- voice, timeline, render

def speak(text, voice, cache):
    """The voice saying text, as int16 samples (cached: synthesis is slow)."""
    path = os.path.join(cache, hashlib.sha256((voice + text).encode()).hexdigest()[:16] + ".wav")
    if not os.path.exists(path):
        subprocess.run(["piper", "-m", voice, "-f", path + ".tmp"], input=text.encode(), check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.rename(path + ".tmp", path)
    with wave.open(path) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (RATE, 1, 2), "unexpected voice format"
        return np.frombuffer(w.readframes(w.getnframes()), np.int16)


def build_timeline(scenes, voice, cache):
    """[(draw, start, end, beat starts)] and [(start, end, caption)], in seconds, and the audio samples."""
    timeline, cues, audio, now = [], [], [], 0.0

    def add(samples):
        nonlocal now
        audio.append(samples)
        now += len(samples) / RATE

    def silence(seconds):
        add(np.zeros(int(seconds * RATE), np.int16))

    for draw, beats in scenes:
        start, at = now, []
        silence(LEAD)
        for i, beat in enumerate(beats):
            caption, spoken = beat if isinstance(beat, tuple) else (beat, beat)
            if i:
                silence(GAP)
            at.append(now - start)
            begin = now
            add(speak(spoken, voice, cache))
            cues.append((begin, now, caption))
        silence(TAIL)
        timeline.append((draw, start, now, at))
    assert all(a[1] <= b[0] for a, b in zip(cues, cues[1:])), "captions overlap"
    return timeline, cues, np.concatenate(audio)


def draw_frame(g, t, timeline, cues, captions):
    g.clear()
    draw, start, end, at = next((s for s in timeline if s[1] <= t < s[2]), timeline[-1])
    alpha = min(ease(t, start, 0.3), 1 - ease(t, end - 0.3, 0.3))
    if len(timeline) == 1:
        alpha = 1
    g.cr.push_group()
    draw(g, t - start, at)
    g.cr.pop_group_to_source()
    g.cr.paint_with_alpha(alpha)
    if captions:
        for begin, stop, caption in cues:
            if begin <= t < stop + GAP / 2:
                lines, line = [], ""
                for word in caption.split():
                    if line and g.measure(line + " " + word, 46, bold=True)[0] > 840:
                        lines.append(line)
                        line = word
                    else:
                        line = (line + " " + word).strip()
                for i, s in enumerate(lines + [line]):
                    g.text(500, 255 + i * 58, s, 46, FG, bold=True)


def stamp(t):
    ms = round(t * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"


def main():
    p = argparse.ArgumentParser(
        description="Render the 'how a compiler works' videos (MP4, plus SRT subtitles).",
        epilog="needs: ffmpeg, piper, pycairo, PyGObject (Pango), numpy. No environment variable.\n\n"
               "example:\n  python3 videos/compiler_video.py long --out ~/Videos/yt-publisher",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("video", choices=VIDEOS, help="long: 1920x1080, every stage; short: 1080x1920, what a + b becomes")
    p.add_argument("--out", default=".", help="output directory (default: current)")
    p.add_argument("--voice", default=os.path.expanduser("~/.local/share/piper/en_US-ljspeech-high.onnx"),
                   help="piper voice, 22050 Hz (default: %(default)s)")
    p.add_argument("--cache", default=os.path.expanduser("~/.cache/yt-publisher"),
                   help="directory of the synthesized sentences (default: %(default)s)")
    p.add_argument("--stills", metavar="DIR", help="only write one PNG per beat into DIR, to check the layout")
    a = p.parse_args()

    scenes, w, h, captions = VIDEOS[a.video]
    os.makedirs(a.cache, exist_ok=True)
    timeline, cues, audio = build_timeline(scenes, a.voice, a.cache)
    g = Canvas(w, h)
    if a.stills:
        os.makedirs(a.stills, exist_ok=True)
        for i, (_, stop, _) in enumerate(cues):
            draw_frame(g, stop + 0.1, timeline, cues, captions)
            g.surface.write_to_png(os.path.join(a.stills, f"{a.video}-{i:02}.png"))
        return 0

    os.makedirs(a.out, exist_ok=True)
    base = os.path.join(a.out, f"compiler-{a.video}")
    with open(base + ".srt", "w") as f:
        for i, (begin, stop, caption) in enumerate(cues, 1):
            f.write(f"{i}\n{stamp(begin)} --> {stamp(stop)}\n{caption}\n\n")
    voice_wav = os.path.join(a.cache, f"{a.video}.wav")
    with wave.open(voice_wav, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(audio.tobytes())
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr0", "-s", f"{w}x{h}", "-r", str(FPS),
         "-i", "-", "-i", voice_wav, "-af", "loudnorm=I=-14:TP=-1.5", "-ar", "48000", "-c:v", "libx264",
         "-threads", "4", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", base + ".mp4"], stdin=subprocess.PIPE)
    for n in range(int(len(audio) / RATE * FPS)):
        draw_frame(g, n / FPS, timeline, cues, captions)
        g.surface.flush()
        ffmpeg.stdin.write(g.surface.get_data())
    ffmpeg.stdin.close()
    if ffmpeg.wait():
        sys.exit("ffmpeg failed")
    print(f"{base}.mp4 ({len(audio) / RATE:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
