# Back-and-Forth

A word-chain puzzle where the same string of letters, read left-to-right **and** right-to-left, both parse into valid English word sequences — with word boundaries at completely different positions.

```
Forward:   SUBTLE · BECAME · TATUM · SPA · TREE · BALE · TAN · APE · LITE · PIPS …
Backward:  … BALDNESS · BACKSIDE · MODE · GASPIPE · TILE · PANATELA · BEERTAP · SMU · TATE …
```

The constraint is strict: no cut position may be shared between the forward and backward chains anywhere in the string.

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

## Files

| File | Description |
|------|-------------|
| `back_and_forth.py` | Main generator, solver, and PNG renderer |
| `back_and_forth_inside_out.py` | Variant: inside-out construction strategy |
| `images/` | Output PNGs |

---

## Requirements

- Python 3.10+
- `Pillow` — `pip install Pillow`
- `anthropic` — `pip install anthropic` (optional, for clue generation)
- `ANTHROPIC_API_KEY` in environment or `.env`
