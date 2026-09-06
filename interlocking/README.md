# Interlocking Squares

A diamond-shaped word puzzle where adjacent rows share corner letters that form 4-letter square words.

## How it works

The grid has six rows with widths **3 · 5 · 7 · 7 · 5 · 3**. Where adjacent rows overlap, their four shared corner letters form a 4-letter word that can be read clockwise or anticlockwise starting from any corner. A full puzzle has **18** such square words, grouped into three colour regions (green / blue / red) for clueing.

```
         A  B  C
       D  E  F  G  H
     I  J  K  L  M  N  O
     P  Q  R  S  T  U  V
       W  X  Y  Z  .
         .  .  .
```

Shared corners between rows A–B and B–C: letters B·C·G·F form a square word (e.g. CAGE, EGAC, GACE, ACEG — whichever is a real word).

A worked example with solution is in [`examples/`](examples/).

## Features

- **CSP solver** — backtracking with forward-checking and quality scoring
- **Acrostic** (`--acrostic WORD`) — constrains the first letter of each row to spell a hidden word, highlighted in crimson on the solution PNG
- **Theme words** (`--include "word; word"`) — the solver prioritises grids containing your words as row words or square words
- **PNG output** — solution and puzzle images with colour-coded clue panels, generated via Claude (requires `ANTHROPIC_API_KEY`)
- **Selective row clueing** (`--rows B D`) — choose which rows get across clues; others are left blank

## Quick start

```bash
# Basic puzzle
python3 interlocking.py --seed 850 --png out.png

# Puzzle with 6-letter acrostic, rows B and D clued
python3 interlocking.py --seed 3100 --min-score 60 \
    --acrostic ENIGMA --rows B D \
    --title '"Puzzling" Interlocking Squares' \
    --png images/isq_enigma.png

# Include theme words (e.g. a name as a square word)
python3 interlocking.py --seed 1 \
    --include "happy; love; home" --min-included 1 \
    --acrostic HEARTS --rows B D --png out.png
```

## Options

```
--seed N            Random seed
--min-score N       Minimum word quality (default 70; try 60 for more variety)
--tries N           Search attempts (default 200)
--time-limit F      Seconds per search budget (default 60)
--acrostic WORD     Constrain first letters of all rows to spell WORD (up to 6 letters)
--rows A B …        Which rows to clue explicitly (e.g. B D); others left blank
--include "w;w;w"   Theme words to try to include (as row words or square words)
--min-included N    Require at least N theme words in the solution (default 1)
--col N             Pre-fill column N in the puzzle PNG
--title TEXT        Override default puzzle title in both PNGs
--png FILE          Save solution + puzzle PNGs (adds _solution / _puzzle suffix)
```

## PNG output

Passing `--png FILE` creates two images:

| File | Contents |
|------|----------|
| `{stem}_solution.png` | All letters filled in; acrostic letters highlighted in crimson |
| `{stem}_puzzle.png` | Blank grid with clue panel; acrostic hint shown in crimson |

Clues are generated automatically via the Claude API. Set `ANTHROPIC_API_KEY` before running.

## Wordlist

Shared from the parent directory (`../wordlist.dict`). Use `--min-score 60` or higher for cleaner words. Theme words not in the wordlist (e.g. proper names) are injected automatically when `--include` is set.
