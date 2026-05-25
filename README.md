# British Crossword Grid Generator

A Python tool for generating valid British-style crossword grids with rotational symmetry, configurable word-length distributions, and PNG output.

## Requirements

- Python 3.10+
- Pillow (`pip install Pillow`)

## Quick start

```bash
python3 grid_gen.py -n 15 --seed 42 -e 12 --numbers --improve --png grid.png
```

## How it works

### 1. Base pattern

For an odd-sized grid of size *n*, every cell at an even row **and** even column is blocked. For an 11×11 grid this places 25 isolated black squares at (2,2), (2,4), …, (10,10).

### 2. Extensions

The generator randomly grows the base squares by adding **connector** cells between adjacent base squares. Four shape types are used:

| Shape | Description |
|-------|-------------|
| `h_bar` | Horizontal connector — joins (r, c) to (r, c+2) |
| `v_bar` | Vertical connector — joins (r, c) to (r+2, c) |
| `l_shape` | Two connectors at 90° from a base cell |
| `plus` | All four connectors around a base cell |

Every extension is stamped with full rotational symmetry (90° or 180°) before being applied.

### 3. Validation

Each candidate extension is accepted only if:

- No word is exactly 2 letters long (runs of 1 are fine — unchecked cells are allowed in British style)
- All white cells remain connected
- No two consecutive letters in any word are both **unchecked** (i.e. only part of one word rather than crossed by a perpendicular word)

### 4. Improvement pass (`--improve`)

After generation, a greedy pass tries to remove orbits of black squares to reduce short words:

- At each step, every removable orbit is tried and the one that eliminates the most short words is applied
- Stops when no removal helps or when density would drop below `--min-density`
- The default target is words shorter than 5 letters; adjust with `--target-word`

## Options

```
-n / --size N          Grid size, must be odd (default: 11)
-s / --seed N          Random seed for reproducibility
-e / --extensions N    Extension groups to apply during generation (default: 6)
--sym 90|180           Rotational symmetry (default: 90°)
--min-word N           Minimum word length (default: 3)
--base                 Show the raw base grid before extensions
--numbers              Print word-start numbers in the grid
--count N              Generate N grids in one run (seeds: base, base+1, …)

--improve              Run the greedy improvement pass after generation
--target-word N        Improvement target: eliminate words shorter than N (default: 5)
--min-density F        Density floor for improvement pass, 0–1 (default: 0.35)

--png FILE             Save PNG output (use {seed} as placeholder with --count > 1)
--cell-px N            Cell size in pixels for PNG (default: 52)
```

## Typical recipes

**Single 15×15 grid with numbers, saved to PNG:**
```bash
python3 grid_gen.py -n 15 --seed 42 -e 12 --numbers --png grid.png
```

**Three varied grids, improved, at 36% density:**
```bash
python3 grid_gen.py -n 15 --count 3 --seed 400 -e 12 --numbers \
    --improve --min-density 0.35 --png grid_{seed}.png
```

**Denser grid (more 3-letter words, fewer removals):**
```bash
python3 grid_gen.py -n 15 --seed 42 -e 12 --numbers \
    --improve --min-density 0.37 --png grid.png
```

**More open grid (fewer short words):**
```bash
python3 grid_gen.py -n 15 --seed 42 -e 12 --numbers \
    --improve --min-density 0.33 --png grid.png
```

**180° symmetry instead of 90°:**
```bash
python3 grid_gen.py -n 15 --seed 42 -e 12 --sym 180 --numbers --png grid.png
```

## Typical output

For a 15×15 grid at 36% density after improvement:

- ~24 across + ~24 down clues
- Word lengths: mix of 3, 5, and 7 letters
- All words satisfy the British no-consecutive-unchecked rule

## Next steps

- Word-list filling: assign words from a dictionary to the grid slots
