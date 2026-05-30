# British Crossword Grid Generator & Filler

A Python tool for generating valid British-style crossword grids and filling them with words from a quality-scored word list.

## Requirements

- Python 3.10+
- Pillow (`pip install Pillow`)
- anthropic (`pip install anthropic`) — only for `clue_gen.py`

## Quick start

**Generate a grid:**
```bash
python3 grid_gen.py -n 15 --seed 42 -e 12 --improve --numbers --png grid.png
```

**Generate and fill a grid:**
```bash
python3 filler.py -n 15 --seed 400 -e 12 --improve --png filled.png
```

**Generate cryptic clues interactively (requires Claude API key):**
```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 clue_gen.py INTEGRAND EXQUISITE    # clue specific words
python3 clue_gen.py                        # prompts for words one at a time
```

---

## Grid generator (`grid_gen.py`)

### How it works

#### 1. Base pattern

For an odd-sized grid of size *n*, every cell at an even row **and** even column is blocked. For a 15×15 grid this places 49 isolated black squares at (2,2), (2,4), …, (14,14) — about 22% density.

#### 2. Extensions

The generator randomly grows the base squares by adding **connector** cells between adjacent base squares. Four shape types are used:

| Shape | Description |
|-------|-------------|
| `h_bar` | Horizontal connector — joins (r, c) to (r, c+2) |
| `v_bar` | Vertical connector — joins (r, c) to (r+2, c) |
| `l_shape` | Two connectors at 90° from a base cell |
| `plus` | All four connectors around a base cell |

Every extension is stamped with full rotational symmetry (90° or 180°) before being applied.

#### 3. Validation

Each candidate extension is accepted only if:

- No word is exactly 2 letters long (runs of 1 are fine — unchecked cells are allowed in British style)
- All white cells remain connected
- No two consecutive letters in any word are both **unchecked** (i.e. only part of one word rather than crossed by a perpendicular word)

#### 4. Improvement pass (`--improve`)

After generation, a greedy pass removes orbits of black squares to eliminate short words and bring density down to a proper British crossword level (~28–32%):

- At each step, every removable orbit is tried and the one that eliminates the most short words is applied
- Stops when the short-word count reaches `--max-short` (default 4) or no removal helps
- Will not drop density below `--min-density` (default 0.18)
- The default target is words shorter than 5 letters; adjust with `--target-word`

A typical 15×15 grid after improvement has ≤ 4 three-letter words, with most entries being 5, 7, or 9+ letters.

### Options

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
--min-density F        Density floor for improvement pass, 0–1 (default: 0.18)
--max-short N          Stop improving when short-word count ≤ N (default: 4)

--png FILE             Save PNG output (use {seed} as placeholder with --count > 1)
--cell-px N            Cell size in pixels for PNG (default: 52)
```

### Typical recipes

**Single 15×15 grid with numbers, saved to PNG:**
```bash
python3 grid_gen.py -n 15 --seed 42 -e 12 --improve --numbers --png grid.png
```

**Three varied grids:**
```bash
python3 grid_gen.py -n 15 --count 3 --seed 400 -e 12 --improve --numbers --png grid_{seed}.png
```

**Allow more short words (denser grid):**
```bash
python3 grid_gen.py -n 15 --seed 42 -e 12 --improve --max-short 8 --min-density 0.28 --numbers --png grid.png
```

**180° symmetry:**
```bash
python3 grid_gen.py -n 15 --seed 42 -e 12 --sym 180 --improve --numbers --png grid.png
```

### Typical output

For a 15×15 grid after improvement:

- ~32–36 slots (across + down)
- 28–32% black squares
- ≤ 4 three-letter words
- Word lengths: mix of 5, 7, 9 letters; occasionally 11+

---

## Word filler (`filler.py`)

Fills a generated grid using CSP (Constraint Satisfaction Problem) backtracking.

### Word list

Uses the [Collaborative Crossword Word List](https://github.com/Crossword-Nexus/collaborative-word-list) (~363k entries, `WORD;SCORE` format). It is downloaded automatically on first run to `wordlist.dict`.

Scores range from 100 (perfect) to below 50 (questionable). Only words scoring ≥ 50 are loaded by default.

### Filling strategy

1. **Variable ordering (MRV):** always fill the slot with the fewest remaining candidates first; break ties by most crossings (degree).
2. **Value ordering:** rank candidate words by `quality_score × crossing_letter_score × noise`, highest first.
   - *Quality score* — from the word list (50–100).
   - *Crossing-letter score* — how common each crossing letter is at its position in the corpus, weighted by how many words remain compatible (forward-looking flexibility).
   - *Noise* — a small random ±`noise` factor so different seeds produce varied fills.
3. **Forward checking:** after placing each word, immediately intersect every crossing slot's domain with the compatible set; backtrack if any domain empties.

### Word quality filters

Three layers of filtering ensure clean fill:

| Filter | What it removes |
|--------|----------------|
| Score threshold (`--min-score 50`) | Low-quality or obscure entries |
| Acronym filter | Vowelless abbreviations (MCS, WRT, …) — a short allowlist keeps GPS, ESPN, JFK, etc. |
| S-plural penalty | Words that are just another word + S or +ES (TASKS→TASK, GASES→GAS) are scored at 15% of their original value, so the solver strongly prefers non-trivial alternatives |

Words like NECESSITIES, LORRIES, IRONIES, SHRUBBERIES are **not** penalised because their stems (NECESSITIE, LORRIE, IRONIE, SHRUBBERIE) are not words.

### Options

```
-n / --size N          Grid size (default: 15)
-s / --seed N          Random seed — controls both the grid and fill diversity (default: 400)
-e / --extensions N    Extension groups (default: 12)
--sym 90|180           Rotational symmetry (default: 90°)
--improve              Run the grid improvement pass
--min-density F        Density floor for improvement (default: 0.18)
--max-short N          Stop improving at this many short words (default: 4)
--min-word N           Minimum word length (default: 3)

--wordlist FILE        Path to word list (default: wordlist.dict)
--min-score N          Minimum word quality score to load (default: 50)
--download             Force re-download of word list
--allow-s-plurals      Disable the S-plural score penalty

--time-limit F         Backtracking time limit in seconds (default: 60)
--noise F              Score randomisation ±fraction for fill diversity (default: 0.15)
--interactive          After solving, enter a feedback loop to ban words and re-solve

--png FILE             Save filled grid as PNG
--cell-px N            Cell size in pixels (default: 64)
```

### Interactive mode

Run with `--interactive` to refine the fill in a terminal loop:

```bash
python3 filler.py -n 15 --seed 401 -e 12 --improve --interactive --png filled.png
```

After each solve the program prints a numbered word list with quality scores:

```
ACROSS
   1. NETASSETS  (90)
   9. STEWARD    (90)
  14. SQUALIDNESS (90)
  ...
DOWN
   2. THEPIPS    (90)
  13. SASSAFRAS  (90)
  ...

Ban words (comma-separated, blank to finish):
```

Type any words you want removed (comma-separated) and press Enter — the solver re-runs with those words permanently excluded and the PNG is updated. The ban list accumulates across rounds. Press Enter on a blank line to stop.

```
Ban words (comma-separated, blank to finish): TEDDANSON, PASSOFFAS
# → re-solves without those two words

Ban words (comma-separated, blank to finish): BOOHISS
# → re-solves without all three banned words

Ban words (comma-separated, blank to finish):
# → blank line exits
```

Banning a word that crossing slots depend on causes the solver to backtrack into those slots too, so each round can produce a substantially different fill.

### Post-solve local optimizer

After every solve (interactive or not) the filler runs a fast greedy pass: for each slot it looks for a higher-scoring word that satisfies the exact same crossing letters, and swaps if one exists. This upgrades 1–3 words per fill at negligible cost and is always on.

### Typical recipes

**Fill a grid and save PNG:**
```bash
python3 filler.py -n 15 --seed 400 -e 12 --improve --png filled.png
```

**Compare fills across seeds (same grid structure):**
```bash
python3 filler.py -n 15 --seed 400 -e 12 --improve --png filled_400.png
python3 filler.py -n 15 --seed 401 -e 12 --improve --png filled_401.png
python3 filler.py -n 15 --seed 402 -e 12 --improve --png filled_402.png
```

**More varied fills (higher noise):**
```bash
python3 filler.py -n 15 --seed 400 -e 12 --improve --noise 0.30 --png filled.png
```

**Deterministic fill (no noise):**
```bash
python3 filler.py -n 15 --seed 400 -e 12 --improve --noise 0 --png filled.png
```

### Typical output

For a 15×15 grid (seed 400, 12 extensions, improved):

```
Size 15×15  black=69/225 (30%)  across=18  down=18
Word-length distribution: len3:4  len5:12  len7:16  len9:4
Slots: 36 total
SOLVED — 0.04s, 36 nodes explored
```

The solver almost never needs to backtrack thanks to MRV + forward checking — most grids solve in under 0.1 seconds with one node visited per slot.

---

## Cryptic clue generator (`clue_gen.py`)

Once you have a filled grid, use `clue_gen.py` to generate and refine cryptic clues interactively with Claude.

### Setup

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...   # your key from console.anthropic.com
```

### Usage

```bash
# Clue specific words (e.g. from your filled grid)
python3 clue_gen.py INTEGRAND EXQUISITE ENAMELING

# Or enter words interactively
python3 clue_gen.py
```

### How the loop works

1. Claude generates 3 candidate clues using different techniques (anagram, charade, hidden word, etc.)
2. You give feedback in plain English — Claude refines based on your notes
3. Repeat until you're happy
4. `save <clue text>` to append the approved clue to `claude_created_clues.txt`
5. `next` to move to the next word, `quit` to exit

### Example session

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Word: INTEGRAND  (9 letters)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Claude: [generates 3 clues...]

You: I like the anagram one but the surface is too obvious
Claude: [refines...]

You: love it — save Maths expression recalculates new gradient (9)
  → Saved to claude_created_clues.txt

You: next
```

The clue bank in `clues_with_answers.txt` is automatically loaded as examples so Claude learns your style. Approved clues accumulate in `claude_created_clues.txt`.
