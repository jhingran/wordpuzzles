# Snakes & Ladders Word Puzzle

Inspired by Eric Berlin's *Jelly Roll* puzzle (ericberlin.com).

## How it works

Two vertical **LADDERS** are built from stacked words. **SNAKES** wind between the two ladders, consuming letters from both in an alternating braid:

```
1 letter from L1, then 2 from L2, 2 from L1, 2 from L2 … until both ladders are exhausted.
```

Each snake is a complete word (or phrase). Together the snakes use every letter of both ladders exactly once.

### Example (Eric Berlin)

```
Ladder 1: HITCH | SENATE | BOGUS
Ladder 2: ABATE | EMIR   | EARNEST

Snakes:
  HABITAT  ←  H(L1) + AB(L2) + IT(L1) + AT(L2)
  CHEESE   ←  CH(L1) + EE(L2) + SE(L1)
  MINARET  ←  MI(L2) + NA(L1) + RE(L2) + T(L1)
  EAR BONE ←  E(L1)  + AR(L2) + BO(L1) + NE(L2)
  GUSTS    ←  GU(L1) + ST(L2) + S(L1)
```

## Usage

```bash
# Check: given ladder words, find snakes automatically
python snakes_ladders.py check "HITCH SENATE BOGUS" "ABATE EMIR EARNEST"

# Generate: CSP backtracking finds a valid puzzle from scratch
python snakes_ladders.py generate --length 15 --seed 42 --min-score 60

# Verify: confirm a hand-crafted puzzle is mechanically correct
python snakes_ladders.py verify "HITCH SENATE BOGUS" "ABATE EMIR EARNEST" \
                                "HABITAT CHEESE MINARET EARBONE GUSTS"
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--length` | 15 | Ladder length in letters |
| `--min-word` / `--max-word` | 3 / 7 | Ladder word length range |
| `--min-snake` / `--max-snake` | 3 / 12 | Snake word length range |
| `--min-score` | 50 | Minimum wordlist quality score (higher = cleaner words) |
| `--time-limit` | 60 | Time budget in seconds for generator |
| `--seed` | 42 | Random seed |

## Algorithm

The generator uses **CSP backtracking**:
1. Randomly sample L1 word sequences.
2. For each L1, backtrack over L2 letter choices, pruning using *intersection of valid next letters*: at each braid position, only try letters that can legally extend both the current snake-word prefix AND the current L2-word prefix.
3. When a complete L2 is found that produces valid snakes, return the puzzle.

This is the same MRV + forward-checking strategy used in `cryptic/filler.py`, adapted to the braid structure.

## Wordlist

Shared from the parent directory (`../wordlist.dict`). Use `--min-score 60` or higher for better-quality puzzle words.
