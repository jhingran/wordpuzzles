# Cryptic Crossword — Claude Code Workflow

This directory contains tools for building British-style cryptic crosswords: a grid generator, a CSP word filler, and a clue-writing workflow designed for human + Claude collaboration.

---

## Quickstart for a new puzzle

```bash
# 1. Generate and fill a 15×15 grid interactively
python3 filler.py -n 15 --seed 401 -e 12 --improve --interactive --png filled.png

# 2. When happy with the fill, add it to puzzles_data.py (see format below)

# 3. Re-render any time
python3 puzzles_data.py my_puzzle_key
```

The interactive mode lets you ban unwanted words and re-solve until the fill is clean.

---

## Saving a puzzle (`puzzles_data.py`)

Add a new entry to the `PUZZLES` dict:

```python
"my_puzzle": {
    "size": 15,
    "grid": [
        "WORD....WORD",   # one string per row, '.' = black square
        ...
    ],
    "clues": {
        "1A":  "The clue text (7)",
        "1D":  "",          # empty string = not yet clued
        ...
    },
}
```

Re-render: `python3 puzzles_data.py my_puzzle`
Produces: `images/my_puzzle.png` (solution) and `images/my_puzzle_blank.png` (blank grid + clue panel).

---

## Cluing workflow

Cryptic cluing is a **dialogue**, not an automated step. Work one clue at a time:

1. State the word and its crossing letters for context
2. Propose a mechanism or ask Claude to suggest options
3. Verify the mechanism (see rules below)
4. Lock it — update `puzzles_data.py` immediately
5. Move to the next word

**The best clues come from the setter.** Claude's role is to verify, catch errors, generate fodder combinations, and hold the rules steady.

---

## Cryptic clue rules

### The basics
- Every clue = **DEFINITION** + **WORDPLAY** (in either order)
- Definition must be at the **start or end** — never in the middle
- Wordplay must account for **every letter** of the answer
- Never use the answer word (or its root) in the clue

### Mechanisms

| Type | How it works | Key rule |
|------|-------------|----------|
| **Anagram** [B1] | Letters of fodder rearranged | Fodder must be the **exact words** in the clue — **no synonyms** for anagram fodder |
| **Hidden word** [C1] | Answer concealed in consecutive letters | Indicator: "found in", "some", "part of" |
| **Reversal** [B3] | A word reversed | Across: "back", "returning"; Down: "up", "rising" |
| **Charade** [D1] | Components placed end-to-end | Components **can** use synonyms |
| **Container** [D2] | One word inside another | "harbours", "envelops", "surrounds", "holds" |
| **Double def** [F1] | Two separate definitions, no indicator | Both must genuinely clue the answer |
| **Cryptic def** [F3] | Single oblique definition | Use `?` at end |
| **Semi-&lit** [F6] | Whole clue = def + wordplay simultaneously | Use `?` at end |

### Style rules
- **No em dashes.** Use "of", "for", "in", "as" to connect wordplay to definition — e.g. "Fortune teller harbours past of voyager" not "Fortune teller harbours past — voyager"
- **No `?` unless F3 or F6.** Not just because a clue is oblique or clever
- **Anagram fodder = verbatim.** If the clue says "confused OGRE", the fodder is O,G,R,E — never a synonym of OGRE
- **Charade components can use synonyms.** CYAN for "blue-green", IDE for "fish" — both fine
- **Definition must match grammatically.** If the answer is a plural noun, the definition must also be plural

### Self-check before locking
1. Count letters: do fodder letters add up to the answer length?
2. Sort and compare: sorted(fodder) == sorted(answer)?
3. Is the definition at the start or end?
4. Does the surface reading make sense as an independent sentence?

---

## Reference files

| File | Purpose |
|------|---------|
| `rules.md` | Full mechanism taxonomy with examples |
| `clues_401v2.txt` | Worked example: all 32 clues with mechanism annotations |
| `clues_with_answers.txt` | Clue bank for style reference |
| `puzzles_data.py` | Canonical store for completed puzzles |

### Worked example (filled_401v2)
See `clues_401v2.txt` for a complete 15×15 British cryptic with annotations explaining every clue. Some highlights illustrating good technique:

- **Anagram + reversal hybrid:** "Panics when wives get confused next to backstreet (7)" — WIVES + TS (ST reversed) → SWIVETS
- **Container:** "Fortune teller harbours past of voyager (4,3)" — AGO inside SEER → SEAGOER  
- **Charade with reversal:** "Monks have hundred and one backbites (9)" — C + ENO (ONE back) + BITES → CENOBITES
- **Double def (contradictory):** "Hide or expose? (4,3)" → SEAL OFF
- **Double def as sentence:** "Curse makes one cry (3)" → SOB
- **Curtailment:** "Reduced price lettuce (3)" — COST − T → COS
