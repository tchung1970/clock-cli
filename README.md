# clock-cli

A crisp terminal analog clock that also reads the time aloud in plain English —
**learn how to read time in English** while you watch the clock tick.

The dial is rendered with Pillow and painted using **Braille characters**, so
each character cell packs a 2×4 grid of dots and the rim, numbers, tick marks,
and hands come out as sharp line-art. Below the clock, the current time is
spelled out ("Quarter past nine", "Twenty-five minutes to one", …).

## Install

Requires Python 3 and [Pillow](https://python-pillow.org/):

```bash
pip install pillow
git clone https://github.com/tchung1970/clock-cli.git
cd clock-cli
python3 clock-cli.py
```

Optionally symlink it onto your `PATH`:

```bash
ln -s "$PWD/clock-cli.py" ~/bin/clock-cli
clock-cli
```

## Usage

```
clock-cli                 # live clock, centered; press q to quit
clock-cli --once          # draw a single frame and exit
clock-cli --color         # full-color dial (default)
clock-cli --mono          # monochrome dial
clock-cli --matrix        # green matrix dial
```

Press `q` (or Ctrl-C) to quit. The clock auto-fits your terminal size.

## How the English reading works

Seconds are ignored, as you would when reading an analog face:

| Time  | Reading                     |
|-------|-----------------------------|
| 10:00 | Ten o'clock                 |
| 10:09 | Nine minutes past ten       |
| 09:15 | Quarter past nine           |
| 06:30 | Half past six               |
| 04:45 | Quarter to five             |
| 11:55 | Five to twelve              |

Multiples of five drop the word "minutes" ("Five past two"); other minutes keep
it ("Nine minutes past ten").

## License

This project is open source and available under the [MIT License](LICENSE).
