#!/usr/bin/env python3
"""
clock-cli.py — learn to read the time in English, on a terminal analog clock.

Renders an analog wall clock with Pillow, then paints it in the terminal using
Braille characters: each character cell packs a 2x4 grid of dots, so the dial
(rim, numbers, tick marks, hands) is drawn at 2x4 the cell resolution as crisp
line-art. Below it, the time is read out in plain English to help learners.

Usage:
    python3 clock-cli.py               # live clock, centered; press q to quit
    python3 clock-cli.py --once        # draw a single frame and exit
    python3 clock-cli.py --mono        # --color (default) | --mono | --matrix

Requires: Pillow  (pip install pillow)
"""

import argparse
import math
import select
import shutil
import sys
import time
from datetime import datetime

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    sys.exit("This clock needs Pillow. Install it with:  pip install pillow")

try:
    import termios
    import tty
    HAVE_TTY = True
except ImportError:  # non-unix
    HAVE_TTY = False

# ---- ANSI helpers ----------------------------------------------------------

ESC = "\x1b"
HIDE_CURSOR = f"{ESC}[?25l"
SHOW_CURSOR = f"{ESC}[?25h"
CLEAR = f"{ESC}[2J"
HOME = f"{ESC}[H"
RESET = f"{ESC}[0m"

# ---- color themes ----------------------------------------------------------
# Everything is line-art drawn as dots on the terminal's own background (no fill
# image), so colors are chosen to stay visible on a dark terminal. Each element
# gets its own color; a theme maps element -> RGB.

THEMES = {
    "vivid": {
        "rim":     (90, 150, 235),   # blue rim
        "minor":   (110, 120, 140),  # slate minute ticks
        "major":   (240, 200, 90),   # amber 5-minute ticks
        "numbers": (240, 240, 245),  # white numerals
        "hour":    (95, 205, 160),   # teal hour hand
        "minute":  (120, 190, 255),  # light-blue minute hand
        "second":  (235, 70, 70),    # red second hand
        "hub":     (245, 210, 90),   # yellow hub
    },
    "mono": {
        "rim": (232, 232, 232), "minor": (150, 150, 150),
        "major": (232, 232, 232), "numbers": (245, 245, 245),
        "hour": (232, 232, 232), "minute": (232, 232, 232),
        "second": (224, 48, 48), "hub": (232, 232, 232),
    },
    "matrix": {
        "rim": (0, 200, 90), "minor": (0, 110, 60), "major": (120, 255, 140),
        "numbers": (180, 255, 190), "hour": (0, 220, 100), "minute": (90, 255, 150),
        "second": (220, 255, 120), "hub": (200, 255, 200),
    },
}

# Braille: 2 cols x 4 rows of dots per cell; these are the bit values.
BRAILLE_BASE = 0x2800
DOTMAP = ((0x01, 0x08), (0x02, 0x10), (0x04, 0x20), (0x40, 0x80))  # [row][col]

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def load_font(size):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_layers(D, now, theme):
    """Return an ordered list of (mask, RGB) layers, highest priority first.

    Everything is line-art: the rim, tick marks, numbers, and hands are drawn
    as strokes (no filled face/bezel) into separate masks so each can be a
    different color. Sampled per Braille dot in compose().
    """
    c = D / 2.0
    R = D / 2.0 - 1
    Rface = R * 0.92

    def blank():
        img = Image.new("L", (D, D), 0)
        return img, ImageDraw.Draw(img)

    rim, d_rim = blank()
    minor, d_minor = blank()
    major, d_major = blank()
    nums, d_nums = blank()
    hourL, d_hour = blank()
    minL, d_min = blank()
    secL, d_sec = blank()
    hubL, d_hub = blank()

    def pol(angle_deg, r):
        a = math.radians(angle_deg - 90)
        return c + math.cos(a) * r, c + math.sin(a) * r

    # --- rim (two concentric circles => a bezel ring) ---
    d_rim.ellipse([c - R, c - R, c + R, c + R], outline=255, width=max(1, int(R * 0.03)))
    d_rim.ellipse([c - Rface, c - Rface, c + Rface, c + Rface],
                  outline=255, width=max(1, int(R * 0.015)))

    # --- tick marks ---
    for m in range(60):
        deg = m * 6
        if m % 5 == 0:
            x0, y0 = pol(deg, Rface * 0.97)
            x1, y1 = pol(deg, Rface * 0.84)
            d_major.line([x0, y0, x1, y1], fill=255, width=max(2, int(R * 0.05)))
        else:
            x0, y0 = pol(deg, Rface * 0.96)
            x1, y1 = pol(deg, Rface * 0.90)
            d_minor.line([x0, y0, x1, y1], fill=255, width=max(1, int(R * 0.012)))

    # --- hour numbers (bold font) ---
    font = load_font(max(8, int(Rface * 0.25)))
    for n in range(1, 13):
        tx, ty = pol(n * 30, Rface * 0.72)
        s = str(n)
        bb = d_nums.textbbox((0, 0), s, font=font)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        d_nums.text((tx - w / 2 - bb[0], ty - h / 2 - bb[1]), s, font=font, fill=255)

    # --- hands (tapered) ---
    def hand(dd, angle_deg, length, half_w, tail):
        a = math.radians(angle_deg - 90)
        dx, dy = math.cos(a), math.sin(a)
        px, py = -dy, dx
        shoulder = length * 0.32
        tip = (c + dx * length, c + dy * length)
        shR = (c + dx * shoulder + px * half_w, c + dy * shoulder + py * half_w)
        shL = (c + dx * shoulder - px * half_w, c + dy * shoulder - py * half_w)
        tp = (c - dx * tail, c - dy * tail)
        dd.polygon([tp, shR, tip, shL], fill=255)

    hour = now.hour % 12 + now.minute / 60.0
    minute = now.minute + now.second / 60.0
    second = now.second

    hand(d_hour, hour * 30, Rface * 0.52, R * 0.045, R * 0.07)
    hand(d_min, minute * 6, Rface * 0.80, R * 0.032, R * 0.08)

    # second hand: thin pointer + counterweight tail
    sa = second * 6
    sx, sy = pol(sa, Rface * 0.90)
    tx, ty = pol(sa + 180, Rface * 0.22)
    d_sec.line([tx, ty, sx, sy], fill=255, width=max(2, int(R * 0.016)))
    cwx, cwy = pol(sa + 180, Rface * 0.22)
    d_sec.ellipse([cwx - R * 0.03, cwy - R * 0.03, cwx + R * 0.03, cwy + R * 0.03],
                  fill=255)

    # center hub
    d_hub.ellipse([c - R * 0.06, c - R * 0.06, c + R * 0.06, c + R * 0.06], fill=255)

    # priority: topmost drawn last on screen -> listed first here
    return [
        (secL, theme["second"]),
        (hubL, theme["hub"]),
        (minL, theme["minute"]),
        (hourL, theme["hour"]),
        (nums, theme["numbers"]),
        (major, theme["major"]),
        (minor, theme["minor"]),
        (rim, theme["rim"]),
    ]


def compose(layers, D, Wc, Hc, use_color):
    """Turn ordered colored layers into centered rows of Braille text."""
    pix = [(img.load(), col) for img, col in layers]

    def rgb_fg(rgb):
        return f"{ESC}[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m"

    lines = []
    for cy in range(Hc):
        parts = []
        cur_fg = None
        for cx in range(Wc):
            mask = 0
            best = None  # index of highest-priority layer present in this cell
            for ry in range(4):
                yy = cy * 4 + ry
                if yy >= D:
                    continue
                for rx in range(2):
                    xx = cx * 2 + rx
                    if xx >= D:
                        continue
                    for li, (px, _) in enumerate(pix):
                        if px[xx, yy] > 127:
                            mask |= DOTMAP[ry][rx]
                            if best is None or li < best:
                                best = li
                            break

            if mask == 0:
                parts.append(" ")
                continue

            if use_color:
                fg = pix[best][1]
                if fg != cur_fg:
                    parts.append(rgb_fg(fg))
                    cur_fg = fg
            parts.append(chr(BRAILLE_BASE + mask))
        if use_color:
            parts.append(RESET)
        lines.append("".join(parts))
    return lines


_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
         "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
         "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty"]


def _num_word(n):
    if n < 20:
        return _ONES[n]
    t, o = divmod(n, 10)
    return _TENS[t] + ("-" + _ONES[o] if o else "")


def time_in_words(now):
    """Read the clock aloud in English, ignoring seconds (analog convention)."""
    h = now.hour % 12 or 12
    nxt = h % 12 + 1
    hw, nw = _num_word(h), _num_word(nxt)
    m = now.minute

    if m == 0:
        return f"{_num_word(h).capitalize()} o'clock"
    if m == 15:
        return f"Quarter past {hw}"
    if m == 30:
        return f"Half past {hw}"
    if m == 45:
        return f"Quarter to {nw}"
    if m < 30:
        unit = "" if m % 5 == 0 else (" minute" if m == 1 else " minutes")
        return f"{_num_word(m).capitalize()}{unit} past {hw}"
    to = 60 - m
    unit = "" if to % 5 == 0 else (" minute" if to == 1 else " minutes")
    return f"{_num_word(to).capitalize()}{unit} to {nw}"


def _banner_reserve():
    """Rows to keep clear below the clock for the reading + labels."""
    return 12


def fit_grid():
    """Return (D dots, Wc cells wide, Hc cells tall) for the terminal.
    Clock is square, and leaves room for the reading."""
    cols, rows = shutil.get_terminal_size((80, 24))
    D = min(cols * 2, (rows - _banner_reserve()) * 4)
    D = max(24, D - (D % 4))            # multiple of 4
    return D, D // 2, D // 4


def _center(line_pairs, cols):
    """line_pairs: list of (visible_width, text). Return left-padded lines."""
    return [(" " * max(0, (cols - w) // 2)) + t for w, t in line_pairs]


def frame(D, Wc, Hc, now, use_color, theme):
    """Build the full centered screen: small clock, big English reading."""
    cols, rows = shutil.get_terminal_size((80, 24))
    layers = render_layers(D, now, theme)
    clock = compose(layers, D, Wc, Hc, use_color)

    accent = theme["numbers"]
    fg = f"{ESC}[1;38;2;{accent[0]};{accent[1]};{accent[2]}m" if use_color else ""
    end = RESET if use_color else ""

    # plain (bold) English reading of the time
    phrase = time_in_words(now)
    footer = "q to quit"

    lines = []
    lines += _center([(Wc, ln) for ln in clock], cols)
    lines.append("")
    lines += _center([(len(phrase), fg + phrase + end)], cols)
    lines.append("")
    lines += _center([(len(footer), footer)], cols)

    top = max(0, (rows - len(lines)) // 2)
    return ("\n" * top) + "\n".join(lines)


def run_live(D, Wc, Hc, use_color, theme):
    interactive = sys.stdin.isatty() and HAVE_TTY
    old = termios.tcgetattr(sys.stdin) if interactive else None
    if interactive:
        tty.setcbreak(sys.stdin.fileno())

    def quit_pressed(timeout):
        if not interactive:
            time.sleep(max(0, timeout))
            return False
        end = time.monotonic() + timeout
        while True:
            remaining = end - time.monotonic()
            if remaining <= 0:
                return False
            r, _, _ = select.select([sys.stdin], [], [], remaining)
            if r and sys.stdin.read(1) in ("q", "Q"):
                return True

    try:
        sys.stdout.write(HIDE_CURSOR + CLEAR)
        while True:
            now = datetime.now()
            sys.stdout.write(HOME + CLEAR + frame(D, Wc, Hc, now, use_color, theme))
            sys.stdout.flush()
            if quit_pressed(1 - datetime.now().microsecond / 1_000_000):
                break
    except KeyboardInterrupt:
        pass
    finally:
        if interactive and old is not None:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old)
        sys.stdout.write(SHOW_CURSOR + RESET + "\n")
        sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(
        description="Learn to read the time in English — a terminal analog clock.")
    ap.add_argument("--once", action="store_true", help="draw one frame and exit")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--color", action="store_const", const="vivid", dest="theme",
                   help="full-color dial (default)")
    g.add_argument("--mono", action="store_const", const="mono", dest="theme",
                   help="monochrome dial")
    g.add_argument("--matrix", action="store_const", const="matrix", dest="theme",
                   help="green matrix dial")
    ap.set_defaults(theme="vivid")
    args = ap.parse_args()

    use_color = sys.stdout.isatty()
    theme = THEMES[args.theme]
    D, Wc, Hc = fit_grid()

    if args.once:
        print(frame(D, Wc, Hc, datetime.now(), use_color, theme))
        return

    run_live(D, Wc, Hc, use_color, theme)


if __name__ == "__main__":
    main()
