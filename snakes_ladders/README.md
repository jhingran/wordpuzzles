# Snakes & Ladders Word Puzzle

Inspired by Eric Berlin's *Jelly Roll* puzzle (ericberlin.com).

## How it works

Two vertical **LADDERS** are built from stacked words. **SNAKES** wind between the two ladders, consuming letters from both in an alternating braid:

```
one or more letters from L1, then one or more from L2, alternating … until both ladders are exhausted.
```

Each snake is a complete word. Together the snakes use every letter of both ladders exactly once.

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

A worked example with solution is in [`examples/`](examples/).

## Usage

```bash
# Generate: CSP backtracking finds a valid puzzle from scratch
python snakes_ladders.py generate --length 12 --seed 42

# Generate with themed words (e.g. for an anniversary)
python snakes_ladders.py generate --length 12 --seed 100 \
  --include "RENU: my wife; ARNIE: our son; JUNE: our wedding month; POPPY: her name for me"

# Generate and save puzzle images
python snakes_ladders.py generate --length 12 --seed 42 --png puzzle.png

# Check: given ladder words, find snakes automatically
python snakes_ladders.py check "HITCH SENATE BOGUS" "ABATE EMIR EARNEST"

# Verify: confirm a hand-crafted puzzle is mechanically correct
python snakes_ladders.py verify "HITCH SENATE BOGUS" "ABATE EMIR EARNEST" \
                                "HABITAT CHEESE MINARET EARBONE GUSTS"
```

## PNG output

Passing `--png FILE` to `generate` or `check` creates **two images** automatically:

| File | Contents |
|------|----------|
| `{stem}_solution.png` | Letters filled in; snake paths shown as smooth coloured curves |
| `{stem}_puzzle.png` | Blank cells for the solver; clue panel on the right |

Clues in the puzzle PNG are generated automatically via the Claude API (requires `ANTHROPIC_API_KEY`). User-supplied clues from `--include` are used as-is and skip the API.

## Themed puzzles (`--include`)

Use `--include` to embed personal words — names, dates, occasions — into the puzzle. At least 3 of the provided words are guaranteed to appear (as ladder words or snake words).

**Format:** semicolon-separated entries, each `WORD: clue text` or just `WORD` (Claude generates the clue).

```bash
python snakes_ladders.py generate --length 12 --seed 200 \
  --include "RENU: my wife; ARNIE: our son; JUNE: our wedding month; POPPY: her name for me" \
  --png anniversary.png
```

- Words with a supplied clue appear verbatim in the puzzle PNG — no API call needed for them.
- Words without a clue get a Claude-generated definition.
- If fewer than 3 theme words fit, the generator tries a different seed until they do.
- Try several `--seed` values to find a puzzle with both good theme coverage and clean snake words.

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--length N` | 15 | Ladder length in letters |
| `--min-word N` | 3 | Minimum ladder word length |
| `--max-word N` | 7 | Maximum ladder word length |
| `--min-snake N` | 3 | Minimum snake word length |
| `--max-snake N` | 10 | Maximum snake word length |
| `--max-short-snakes N` | 2 | Reject puzzles with more than N three-letter snakes |
| `--min-score N` | 50 | Minimum wordlist quality score (higher = cleaner words) |
| `--tries N` | 50 | Number of ladder-pair attempts |
| `--time-limit F` | 120 | Time budget in seconds |
| `--seed N` | 42 | Random seed |
| `--crossing` | off | Allow crossing snakes (default: non-crossing) |
| `--png FILE` | — | Save solution + puzzle PNGs |
| `--include WORDS` | — | Semicolon-separated themed words with optional clues |

## Algorithm

The generator uses **CSP backtracking**:

1. Randomly sample L1 word sequences (seeded with 1–2 theme words when `--include` is set).
2. For each L1, backtrack over L2 letter choices, pruning using *intersection of valid next letters*: at each braid position, only try letters that can legally extend both the current snake-word prefix AND the current L2-word prefix.
3. When a complete L2 is found that produces valid snakes, check quality:
   - No snake word repeats a ladder word.
   - At most `--max-short-snakes` snakes are three letters long.
   - At least 3 theme words appear (when `--include` is set).
4. The solver collects up to 40 snake candidates at each step and sorts longest-first, biasing toward 4–5 letter snakes rather than greedily taking the shortest match.

This is the same MRV + forward-checking strategy used in `cryptic/filler.py`, adapted to the braid structure.

## Setup

```bash
pip install Pillow
pip install anthropic          # only needed for clue generation
export ANTHROPIC_API_KEY=...   # only needed for clue generation
```

## Wordlist

Shared from the parent directory (`../wordlist.dict`). Use `--min-score 60` or higher for better-quality puzzle words.
