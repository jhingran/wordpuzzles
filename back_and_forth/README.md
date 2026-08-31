# Back-and-Forth

A word-chain puzzle where the same string of letters, read left-to-right **and** right-to-left, both parse into valid English word sequences — with word boundaries at completely different positions.

```
Forward:   SUBTLE · BECAME · TATUM · SPA · TREE · BALE · TAN · APE · LITE · PIPS …
Backward:  … BALDNESS · BACKSIDE · MODE · GASPIPE · TILE · PANATELA · BEERTAP · SMU · TATE …
```

The constraint is strict: no cut position may be shared between the forward and backward chains anywhere in the string.

A worked example with solution is in [`examples/`](examples/).

---

## Quick start

```bash
# One puzzle, default settings (≈14 letters)
python back_and_forth.py

# Reproducible puzzle with a specific seed
python back_and_forth.py --seed 7 --length 15

# Save puzzle and answer PNGs (horizontal strip layout)
python back_and_forth.py --seed 7 --length 15 --png images/puzzle.png

# 5 distinct puzzles printed to stdout
python back_and_forth.py --count 5

# Force a word into the forward chain
python back_and_forth.py --include "TILE:forward; ROSE:backward"
# or either direction:
python back_and_forth.py --include "LLAMA; NOD"

# Two-step: generate clue draft, edit it, then render
python back_and_forth.py --length 100 --strategy join --draft-clues puzzle.txt
# ... edit puzzle.txt ...
python back_and_forth.py --render-clues puzzle.txt --png images/puzzle.png
```

---

## CLI flags

| Flag | Default | Description |
|------|---------|-------------|
| `--seed` | 42 | Random seed for reproducibility |
| `--length` | 14 | Target string length |
| `--len-tolerance` | 3 | ±tolerance on target length |
| `--min-score` | 90 | Minimum quality score for forward-chain words |
| `--min-score-bwd` | 80 | Minimum quality score for backward-chain words |
| `--min-words` | 3 | Minimum words in forward chain |
| `--max-words` | 5 | Maximum words in forward chain |
| `--min-word` | 3 | Minimum individual word length |
| `--max-word` | 8 | Maximum individual word length |
| `--tries` | 500,000 | Search attempts before giving up |
| `--time-limit` | 30.0 | Wall-clock budget in seconds |
| `--count` | 1 | Number of distinct puzzles to find |
| `--include` | — | Semicolon-separated words to force in (optionally `:forward` / `:backward`) |
| `--skip` | — | Semicolon-separated words to exclude |
| `--png` | — | Output path; also writes `stem_answer.png` |
| `--strategy` | auto | `random`, `extend`, or `join` (see below) |
| `--aid-to-solve` | off | Auto-find one 3-letter hidden word per row; shade cells and add a clue row |
| `--aid-words` | — | Semicolon-separated words to highlight (must read left to right in a grid row) |
| `--draft-clues` | — | Generate puzzle and AI clues, write an editable text file (no PNG) |
| `--render-clues` | — | Read edited clue file and render puzzle + answer PNGs (requires `--png`) |

---

## Two-step clue workflow

The clue setter can review and edit AI-generated clues before the final PNG is produced.

**Step 1 — draft:**
```bash
python back_and_forth.py --length 100 --strategy join \
  --aid-words "MOD;ASP;TAP;UTI;ALE;CAL;LET;APE" \
  --draft-clues hundred_clues.txt
```

This generates the puzzle, calls the AI for clues, and writes `hundred_clues.txt` — a plain-text file with one `WORD: clue` line per word, plus a machine-readable `## {JSON}` header and a human-readable answer grid. No PNG is produced yet.

**Step 2 — edit:** open `hundred_clues.txt` in any text editor and change any clue lines you like.

**Step 3 — render:**
```bash
python back_and_forth.py --render-clues hundred_clues.txt --png images/hundred.png
```

This reads your edited clues and writes `images/hundred.png` and `images/hundred_answer.png`. No search is run; the puzzle data comes entirely from the file.

---

## Strategies

### `random` (default for length ≤ 22)

Generates random forward chains and runs a DP backwards parser to find a compatible backward parse. Fast for short puzzles.

### `extend` (default for length > 22)

Builds a short seed puzzle, then repeatedly attempts to extend one end by prepending or appending extra words to both chains simultaneously. Good for medium lengths (20–50 letters).

### `join`

Generates a pool of short puzzles, then tries all O(n²) pairs via `join_original`. Each pair is tried in four orientations (flip each sub-puzzle or not). The join requires the backward parse to bridge the seam — producing one "bridge word" that straddles the junction. Good for building long puzzles (50–100+ letters).

```bash
python back_and_forth.py --strategy join --length 80 --png images/eighty.png
```

---

## Building long puzzles (100+ letters)

The recommended approach is to chain joins in Python directly:

```python
from back_and_forth import generate, generate_by_join, load_wordlist, join_original
from pathlib import Path

word_scores = load_wordlist(Path('../wordlist.dict'))
bwd_word_set = set(word_scores)

# Step 1: generate two short puzzles
p1 = generate(target_len=17, word_scores=word_scores, seed=0, ...)
p2 = generate(target_len=47, word_scores=word_scores, seed=1, ...)

# Step 2: join them → 64-letter puzzle
p64 = join_original(p1, p2, bwd_word_set, min_len=3, max_len=8)

# Step 3: join again with a fresh short puzzle → 80 letters, etc.
p3  = generate(target_len=16, ...)
p80 = join_original(p64, p3, bwd_word_set, min_len=3, max_len=8)
```

`join_original` returns `(fwd_words, bwd_words_reversed, s, fwd_cuts, bwd_cuts)` in the same format as `generate`. Each join introduces one **bridge word** — a backward-chain word that spans the seam between the two sub-puzzles.

---

## PNG output

### Horizontal strip (`draw_puzzle_png`)

Used by the CLI (`--png`). Cells are laid out left-to-right in a single row. Practical up to ~30 letters before it gets unwieldy.

### Spiral grid (`draw_puzzle_png_spiral`)

For longer puzzles. Letters are placed in a clockwise spiral starting at the top-left corner. The spiral "groove" — a continuous dark line — traces the boundary between adjacent rings, spiralling inward.

**Grid sizing** is automatic via `_best_grid(N)`: finds the most square-like factoring of N.

| N | Grid |
|---|------|
| 100 | 10×10 |
| 96 | 8×12 |
| 80 | 8×10 |
| 72 | 8×9 |
| 64 | 8×8 |
| 47 (prime) | 1×47 strip |

For prime-length puzzles the grid degenerates to a strip; prefer composite target lengths.

```python
from back_and_forth import draw_puzzle_png_spiral

draw_puzzle_png_spiral(
    fwd_words, bwd_words, s, fwd_cuts, bwd_cuts, clues,
    'images/puzzle_spiral.png', solved=False,
)
draw_puzzle_png_spiral(
    fwd_words, bwd_words, s, fwd_cuts, bwd_cuts, clues,
    'images/puzzle_spiral_answer.png', solved=True,
)
```

---

## Clue generation

Clues are generated automatically when `--png` is used and `ANTHROPIC_API_KEY` is set in the environment (or a `.env` file in the project root).

The prompt instructs Claude to use the **most common everyday meaning** of each word. To call it directly:

```python
from back_and_forth import generate_clues

clues = generate_clues(fwd_words, bwd_words)
# Returns dict[word -> clue_string]
```

Without an API key the PNG is still generated; clue slots are left blank.

---

## Aid to solve

Two modes:

**Auto (`--aid-to-solve`):** the generator finds the highest-scoring 3-letter word per grid row (reading left or right) that isn't in the puzzle chains. Good for a first pass.

**Manual (`--aid-words`):** the cluemaster picks the exact words. They must read left→right somewhere in a grid row. The cells are shaded light blue and the aid clues appear as a third row labelled "Aid to solve (left → right):".

```bash
# Auto-find one word per row
python back_and_forth.py --length 100 --strategy join --aid-to-solve --png images/puzzle.png

# Cluemaster-chosen words
python back_and_forth.py --length 100 --strategy join \
  --aid-words "MOD;ASP;TAP;UTI;ALE;CAL;LET;APE" --png images/puzzle.png
```

To call it programmatically:

```python
from back_and_forth import find_aid_words, generate_clues, draw_puzzle_png_spiral

aid_words = find_aid_words(s, word_scores, fwd_words, bwd_words)
# aid_words: list of (word, row, col_start, 'fwd'|'bwd') or None, one per grid row

aid_word_strs = [item[0] for item in aid_words if item]
aid_clue_dict = generate_clues(aid_word_strs, [])
aid_clues = [aid_clue_dict.get(item[0], '—') if item else '—' for item in aid_words]

draw_puzzle_png_spiral(
    fwd_words, bwd_words, s, fwd_cuts, bwd_cuts, clues,
    'images/puzzle_spiral.png', solved=False,
    aid_words=aid_words, aid_clues=aid_clues,
)
```

The spiral layout (used automatically for puzzles longer than 30 letters) displays three clue rows:
- **↻ Clockwise:** clues in reading order from top-left
- **↺ Anticlockwise:** clues in reading order from center
- **Aid to solve:** one clue per grid row, top to bottom

---

## Rendering saved puzzles

Finished puzzles are stored in `puzzles_data.py` so they can be re-rendered without re-running the search. PNGs are gitignored, so run this once after cloning to produce them:

```python
from back_and_forth import draw_puzzle_png_spiral
from puzzles_data import PUZZLES

p = PUZZLES['hundred']
draw_puzzle_png_spiral(
    p['fwd_words'], p['bwd_words'], p['s'],
    p['fwd_cuts'],  p['bwd_cuts'],  p['clues'],
    'images/hundred_spiral.png',        solved=False,
    aid_words=p['aid_words'], aid_clues=p['aid_clues'],
)
draw_puzzle_png_spiral(
    p['fwd_words'], p['bwd_words'], p['s'],
    p['fwd_cuts'],  p['bwd_cuts'],  p['clues'],
    'images/hundred_spiral_answer.png', solved=True,
    aid_words=p['aid_words'], aid_clues=p['aid_clues'],
)
```

---

## Files

| File | Description |
|------|-------------|
| `back_and_forth.py` | Main generator, solver, and PNG renderer |
| `puzzles_data.py` | Saved puzzle data (strings, cuts, clues, aid words) for finished puzzles |
| `back_and_forth_inside_out.py` | Variant: inside-out construction strategy |
| `images/hundred_spiral.png` | 100-letter puzzle (tracked in git) |
| `images/hundred_spiral_answer.png` | 100-letter answer key (tracked in git) |
| `images/` | All other output PNGs are gitignored — regenerate from `puzzles_data.py` |

---

## Requirements

- Python 3.10+
- `Pillow` — `pip install Pillow`
- `anthropic` — `pip install anthropic` (optional, for clue generation)
- `ANTHROPIC_API_KEY` in environment or `.env`
