# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`clock-cli.py` is a single-file Python program: a terminal analog clock that also
reads the current time aloud in plain English (e.g. "Quarter past nine"). Its
purpose is to help people learn how to read time in English.

## Commands

```bash
python3 clock-cli.py          # live clock, centered; press q (or Ctrl-C) to quit
python3 clock-cli.py --once   # draw one frame and exit (useful for quick checks)
python3 clock-cli.py --set 9:15   # freeze a fixed time (HH:MM or HH:MM:SS)
python3 clock-cli.py --mono   # theme flags: --color (default) | --mono | --matrix
python3 -m py_compile clock-cli.py   # syntax check (there is no test suite)
```

`--once` piped to a non-tty auto-disables color, so `python3 clock-cli.py --once | cat`
gives plain-text output for diffing/inspection.

The only dependency is **Pillow** (`pip install pillow`). There is no build step,
linter config, or test suite — verification is by running `--once` and eyeballing.

## Rendering architecture (the non-obvious part)

The dial is drawn as a raster image with Pillow, then converted to **Braille
characters** for display. This is the core trick and touches several functions:

- **Braille sub-pixels.** Each terminal cell maps to a 2×4 grid of Braille dots
  (`BRAILLE_BASE`/`DOTMAP`), so the effective resolution is 2× horizontal and 4×
  vertical the character grid. The dial is drawn as pure line-art (strokes only,
  no filled regions) directly on the terminal background — there is intentionally
  no background-fill image.

- **`render_layers(D, now, theme)`** draws each dial element (rim, minor ticks,
  major ticks, numbers, hour/minute/second hands, hub) into its **own 1-bit
  `L`-mode image** so each can be colored independently. It returns a list of
  `(mask, rgb)` ordered **highest-priority first**. Priority resolves color when
  multiple elements overlap in one cell.

- **`compose(layers, D, Wc, Hc, use_color)`** walks every cell, samples the 8
  sub-pixels across all masks (first mask with a lit pixel wins that dot, and the
  lowest layer index seen sets the cell's foreground color), and emits one Braille
  glyph per cell with ANSI truecolor.

- **`fit_grid()`** sizes the square dial to the terminal. `D` is in Braille dots
  and must stay a multiple of 4; `Wc = D//2`, `Hc = D//4` are the cell dimensions.
  `_banner_reserve()` (currently 12 rows) reserves vertical space below the clock
  for the English reading + footer, so changing it changes how large the clock is.

Coordinate conventions used throughout: angles are degrees measured clockwise
from 12 o'clock; `pol(angle_deg, r)` converts to pixel coords. `R` is the outer
radius, `Rface` (`R*0.92`) is the numbered face radius that ticks/numbers/hands
are scaled against.

## English reading

`time_in_words(now)` (with `_num_word`) converts the time to speech, **ignoring
seconds** by analog convention. Rules baked in: multiples of 5 drop the word
"minutes" ("Five past two") while other minutes keep it ("Nine minutes past ten");
15/30/45 use quarter/half phrasing; the top half of the hour is "past" the current
hour, the bottom half is "to" the next hour.

## Terminal handling

`run_live()` uses cbreak mode + `select` to poll for `q` while sleeping to the next
whole second; it restores termios state and the cursor in a `finally`. `termios`/
`tty` are guarded by `HAVE_TTY` for non-Unix platforms. `frame()` fully repaints
(`HOME + CLEAR`) each tick — it does not do differential updates.

`--set HH:MM[:SS]` (`parse_set_time()`) freezes the dial at a fixed time instead of
`datetime.now()`. It works with `--once` (single frame) or live (`run_live(fixed=…)`
draws once, then just waits for `q` since the frozen time never advances).

## Themes and fonts

`THEMES` maps a theme name to a per-element color dict; add a new theme by adding
an entry and a corresponding `--<name>` flag in `main()`'s mutually-exclusive
group. `FONT_CANDIDATES` is tried in order for the bold numerals (macOS Arial Black
first, then a Linux DejaVu fallback, then Pillow's default) — extend this list for
other platforms.
