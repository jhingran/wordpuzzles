#!/usr/bin/env python3
"""
Crossword grid filler — CSP backtracking.

Strategy
--------
1. Load word list, build (length, pos, letter) → set[word] index.
2. Extract slots from the generated grid; map crossing constraints.
3. Initialise each slot's domain to all words of the right length.
4. Backtracking search:
     • Variable selection : MRV (fewest remaining candidates); degree as tiebreak.
     • Value ordering     : words scored by crossing-letter frequency in corpus
                            × word-quality score — highest first.
     • Forward checking   : after placing a word, intersect every crossing slot's
                            domain with the compatible set for the new fixed letter;
                            backtrack immediately if any domain goes empty.
5. No word may be reused across slots.
"""

import argparse
import random
import sys
import time
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

WORDLIST_URL = (
    "https://raw.githubusercontent.com/Crossword-Nexus/"
    "collaborative-word-list/main/xwordlist.dict"
)
DEFAULT_WORDLIST = Path(__file__).parent / "wordlist.dict"

Cell = tuple[int, int]

# ── Acronym / abbreviation filtering ─────────────────────────────────────
# Y counts as a vowel (CRY, FLY, GYM are fine).  Any word with *no* vowel
# from AEIOUY is treated as a bare abbreviation and excluded — unless it
# appears in this explicit allowlist of well-known, crossword-acceptable ones.
_VOWELS = frozenset("AEIOUY")

_ABBREV_OK = frozenset({
    # Sports & media
    "NFL", "NHL", "NBA", "CBS", "NBC", "CNN", "MTV", "TNT", "TLC", "BBC",
    "PBS", "NPR", "MGM", "SNL", "TBS", "ESPN",
    # Common abbreviations everyone knows
    "BTW", "TBH", "FYI", "RSVP", "BLT", "BBQ", "MVP", "VIP",
    "CPR", "GPS", "LCD", "DVD", "DVR", "USB",
    # Historical / cultural initials
    "JFK", "MLK", "LBJ", "FDR", "JFK",
    # Interjections (legitimate crossword fill)
    "HMM", "BRR", "GRR", "PST", "SHH",
    # Widely recognised orgs
    "LGBT", "LGBTQ", "NAACP",
})


# ── Slot ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Slot:
    direction: str          # 'A' or 'D'
    start: Cell
    cells: tuple[Cell, ...]

    @property
    def length(self) -> int:
        return len(self.cells)

    def __repr__(self) -> str:
        r, c = self.start
        return f"{self.direction}{r},{c}({self.length})"


# ── Word list loading ─────────────────────────────────────────────────────

def download_wordlist(path: Path) -> None:
    print(f"Downloading word list → {path} ...", end=" ", flush=True)
    urllib.request.urlretrieve(WORDLIST_URL, path)
    print(f"{path.stat().st_size // 1024:,} KB")


def _is_acronym(word: str) -> bool:
    """True if word looks like a bare abbreviation (no vowels incl. Y)."""
    return not any(c in _VOWELS for c in word) and word not in _ABBREV_OK


def _is_trivial_s_plural(word: str, word_scores: dict[str, int]) -> bool:
    """True if word is another word with S (or ES) simply appended.

    Catches: TASKS→TASK, ROSES→ROSE, GASES→GAS, FOXES→FOX.
    Passes:  LORRIES (LORRIE not a word), STORIES (STORIE not a word),
             NECESSITIES (NECESSITIE not a word), SINUS (SINU not a word).
    """
    if len(word) < 4:
        return False
    # Simple +S: TASKS → TASK, ROSES → ROSE
    if word.endswith("S") and word[:-1] in word_scores:
        return True
    # +ES added to consonant-ending stem: GASES → GAS, FOXES → FOX
    if len(word) >= 5 and word.endswith("ES") and word[:-2] in word_scores:
        return True
    return False


def load_wordlist(
    path: Path,
    min_score: int = 50,
    min_len: int = 3,
    max_len: int = 21,
    filter_acronyms: bool = True,
    penalize_s_plurals: bool = True,
    s_plural_factor: float = 0.15,
) -> tuple[
    dict[str, int],           # word → quality score
    dict[tuple, frozenset],   # (length, pos, letter) → frozenset[word]
    dict[tuple, dict],        # (length, pos) → {letter: frequency}
    dict[int, frozenset],     # length → frozenset[word]
]:
    if not path.exists():
        download_wordlist(path)

    word_scores: dict[str, int] = {}
    n_acronym = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or ";" not in line:
                continue
            raw, score_str = line.rsplit(";", 1)
            word = raw.upper().strip()
            if not word.isalpha():
                continue
            try:
                score = int(score_str.strip())
            except ValueError:
                continue
            if score < min_score or not (min_len <= len(word) <= max_len):
                continue
            if filter_acronyms and _is_acronym(word):
                n_acronym += 1
                continue
            word_scores[word] = max(word_scores.get(word, 0), score)
    if n_acronym:
        print(f"  (filtered {n_acronym:,} vowelless abbreviations)")

    # Penalise trivial S-plurals (word = stem + S, stem also in wordlist).
    # Reduce their score to s_plural_factor of original so the solver
    # strongly prefers non-trivial alternatives but can still fall back.
    if penalize_s_plurals:
        n_plural = sum(1 for w in word_scores if _is_trivial_s_plural(w, word_scores))
        for w in list(word_scores):
            if _is_trivial_s_plural(w, word_scores):
                word_scores[w] = max(1, round(word_scores[w] * s_plural_factor))
        if n_plural:
            print(f"  (penalized {n_plural:,} trivial S-plurals to {s_plural_factor:.0%} score)")

    # Position index and letter-frequency table
    pos_sets: dict[tuple, set] = defaultdict(set)
    letter_count: dict[tuple, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    length_sets: dict[int, set] = defaultdict(set)

    for word in word_scores:
        n = len(word)
        length_sets[n].add(word)
        for pos, letter in enumerate(word):
            pos_sets[(n, pos, letter)].add(word)
            letter_count[(n, pos)][letter] += 1

    pos_index = {k: frozenset(v) for k, v in pos_sets.items()}
    length_index = {k: frozenset(v) for k, v in length_sets.items()}

    letter_freq: dict[tuple, dict[str, float]] = {}
    for key, counts in letter_count.items():
        total = sum(counts.values())
        letter_freq[key] = {l: c / total for l, c in counts.items()}

    print(
        f"Loaded {len(word_scores):,} words (score≥{min_score}, "
        f"len {min_len}–{max_len}) | {len(pos_index):,} index entries"
    )
    return word_scores, pos_index, letter_freq, length_index


# ── Grid → slots & crossings ──────────────────────────────────────────────

def extract_slots(blocked: set[Cell], n: int, min_len: int = 3) -> list[Slot]:
    slots: list[Slot] = []
    for r in range(1, n + 1):
        run: list[Cell] = []
        for c in range(1, n + 2):
            if c <= n and (r, c) not in blocked:
                run.append((r, c))
            else:
                if len(run) >= min_len:
                    slots.append(Slot("A", run[0], tuple(run)))
                run = []
    for c in range(1, n + 1):
        run = []
        for r in range(1, n + 2):
            if r <= n and (r, c) not in blocked:
                run.append((r, c))
            else:
                if len(run) >= min_len:
                    slots.append(Slot("D", run[0], tuple(run)))
                run = []
    return slots


def build_crossings(slots: list[Slot]) -> dict[Slot, list[tuple[Slot, int, int]]]:
    """Return slot → [(cross_slot, my_pos, their_pos)]."""
    cell_map: dict[Cell, list[tuple[Slot, int]]] = defaultdict(list)
    for slot in slots:
        for pos, cell in enumerate(slot.cells):
            cell_map[cell].append((slot, pos))

    crossings: dict[Slot, list[tuple[Slot, int, int]]] = {s: [] for s in slots}
    for cell, occupants in cell_map.items():
        if len(occupants) == 2:
            (s1, p1), (s2, p2) = occupants
            crossings[s1].append((s2, p1, p2))
            crossings[s2].append((s1, p2, p1))
    return crossings


# ── Scoring ───────────────────────────────────────────────────────────────

def crossing_score(
    word: str,
    crossings_for_slot: list[tuple[Slot, int, int]],
    pos_index: dict[tuple, frozenset],
    letter_freq: dict[tuple, dict],
) -> float:
    """Score a word by how 'common' its crossing letters are.

    For each crossing, we combine:
      • letter frequency at that position in the corpus   (corpus-wide quality)
      • size of the compatible set in the vocabulary      (flexibility)
    Both are cheap O(1) lookups.
    """
    total = 0.0
    for cross_slot, my_pos, their_pos in crossings_for_slot:
        letter = word[my_pos]
        freq = letter_freq.get((cross_slot.length, their_pos), {}).get(letter, 1e-4)
        compat = len(pos_index.get((cross_slot.length, their_pos, letter), frozenset()))
        total += freq * (compat ** 0.4)   # dampened count
    return total if crossings_for_slot else 1.0


# ── Backtracking solver ───────────────────────────────────────────────────

class _Timeout(Exception):
    pass


def _backtrack(
    assignment: dict[Slot, str],
    domains: dict[Slot, frozenset],
    unassigned: list[Slot],
    crossings: dict[Slot, list[tuple[Slot, int, int]]],
    pos_index: dict[tuple, frozenset],
    letter_freq: dict[tuple, dict],
    word_scores: dict[str, int],
    used: set[str],
    counter: list[int],
    deadline: float,
    rng: random.Random,
    noise: float = 0.15,
    banned: frozenset = frozenset(),
) -> Optional[dict[Slot, str]]:

    if not unassigned:
        return dict(assignment)

    if time.monotonic() > deadline:
        raise _Timeout

    counter[0] += 1

    # MRV: fewest candidates; degree (most crossings) as tiebreak
    slot = min(
        unassigned,
        key=lambda s: (len(domains[s]), -len(crossings[s])),
    )

    domain = domains[slot] - used - banned
    if not domain:
        return None

    # Sort candidates: word_score × crossing_letter_score × noise, descending.
    # The noise term (uniform in [1-noise, 1+noise]) breaks ties between
    # similarly-scored words so successive seeds produce varied fills.
    cx = crossings[slot]
    ranked = sorted(
        domain,
        key=lambda w: (
            word_scores.get(w, 0)
            * crossing_score(w, cx, pos_index, letter_freq)
            * (1.0 - noise + rng.random() * 2 * noise)
        ),
        reverse=True,
    )

    remaining = [s for s in unassigned if s is not slot]

    for word in ranked:
        # Forward checking: propagate to crossing slots
        new_domains = dict(domains)
        ok = True

        for cross_slot, my_pos, their_pos in cx:
            if cross_slot in assignment:
                if assignment[cross_slot][their_pos] != word[my_pos]:
                    ok = False
                    break
            else:
                key = (cross_slot.length, their_pos, word[my_pos])
                filtered = new_domains[cross_slot] & pos_index.get(key, frozenset())
                if not filtered - used - banned - {word}:
                    ok = False
                    break
                new_domains[cross_slot] = filtered

        if not ok:
            continue

        assignment[slot] = word
        used.add(word)

        result = _backtrack(
            assignment, new_domains, remaining,
            crossings, pos_index, letter_freq, word_scores,
            used, counter, deadline, rng, noise, banned,
        )

        del assignment[slot]
        used.discard(word)

        if result is not None:
            return result

    return None


def local_optimize(
    assignment: dict[Slot, str],
    crossings: dict[Slot, list[tuple[Slot, int, int]]],
    pos_index: dict[tuple, frozenset],
    length_index: dict[int, frozenset],
    word_scores: dict[str, int],
    banned: frozenset = frozenset(),
) -> tuple[dict[Slot, str], int]:
    """Greedy post-solve pass: for each slot, swap to a higher-scoring word
    that satisfies the exact same crossing letters.  Repeats until stable.
    Returns (improved_assignment, number_of_swaps).
    """
    result = dict(assignment)
    used = set(result.values())
    total_swaps = 0

    improved = True
    while improved:
        improved = False
        # Worst-scoring words first — most likely to benefit from a swap
        for slot in sorted(result, key=lambda s: word_scores.get(result[s], 0)):
            current = result[slot]

            # Intersect crossing constraints to get the exact compatible set
            compatible = length_index.get(slot.length, frozenset())
            for cross_slot, my_pos, their_pos in crossings[slot]:
                letter = result[cross_slot][their_pos]
                compatible = compatible & pos_index.get(
                    (slot.length, my_pos, letter), frozenset()
                )

            candidates = compatible - used - banned - {current}
            if not candidates:
                continue

            best = max(candidates, key=lambda w: word_scores.get(w, 0))
            if word_scores.get(best, 0) > word_scores.get(current, 0):
                used.discard(current)
                result[slot] = best
                used.add(best)
                improved = True
                total_swaps += 1

    return result, total_swaps


def fill(
    blocked: set[Cell],
    n: int,
    word_scores: dict[str, int],
    pos_index: dict[tuple, frozenset],
    letter_freq: dict[tuple, dict],
    length_index: dict[int, frozenset],
    min_len: int = 3,
    time_limit: float = 60.0,
    seed: int = 0,
    noise: float = 0.15,
    banned: frozenset = frozenset(),
) -> Optional[dict[Slot, str]]:
    """Attempt to fill the grid; return assignment dict or None on failure."""

    slots = extract_slots(blocked, n, min_len)
    crossings = build_crossings(slots)

    # Report slot inventory
    from collections import Counter
    dist = Counter(s.length for s in slots)
    print(f"Slots: {len(slots)} total  " +
          "  ".join(f"{l}-letter:{c}" for l, c in sorted(dist.items())))

    # Check coverage
    missing = [l for l in dist if l not in length_index]
    if missing:
        print(f"WARNING: no words of length {missing} in dictionary — fill will fail.")

    # Initialise domains (subtract banned words immediately)
    domains: dict[Slot, frozenset] = {
        slot: length_index.get(slot.length, frozenset()) - banned for slot in slots
    }

    unassigned = sorted(slots, key=lambda s: (-s.length, -len(crossings[s])))

    rng = random.Random(seed)
    counter = [0]
    deadline = time.monotonic() + time_limit

    ban_note = f", {len(banned)} banned" if banned else ""
    print(f"Searching (seed={seed}, noise={noise:.2f}{ban_note}, limit {time_limit:.0f}s) ...", flush=True)
    t0 = time.monotonic()
    try:
        result = _backtrack(
            {}, domains, unassigned, crossings,
            pos_index, letter_freq, word_scores,
            set(), counter, deadline, rng, noise, banned,
        )
    except _Timeout:
        elapsed = time.monotonic() - t0
        print(f"Time limit reached after {elapsed:.1f}s, {counter[0]:,} nodes.")
        return None

    elapsed = time.monotonic() - t0
    if result is None:
        print(f"No solution found — {elapsed:.2f}s, {counter[0]:,} nodes explored")
        return None

    print(f"SOLVED — {elapsed:.2f}s, {counter[0]:,} nodes explored")

    # Local optimizer: deterministic swap pass to upgrade low-scoring words
    result, n_swaps = local_optimize(result, crossings, pos_index, length_index,
                                     word_scores, banned)
    if n_swaps:
        print(f"Optimized: {n_swaps} word(s) upgraded by local swap")

    return result


# ── Rendering ─────────────────────────────────────────────────────────────

def render_filled_ascii(
    blocked: set[Cell],
    n: int,
    assignment: dict[Slot, str],
) -> str:
    grid = [
        ["█" if (r, c) in blocked else "·" for c in range(1, n + 1)]
        for r in range(1, n + 1)
    ]
    for slot, word in assignment.items():
        for pos, (r, c) in enumerate(slot.cells):
            grid[r - 1][c - 1] = word[pos]
    return "\n".join(" ".join(row) for row in grid)


def render_filled_png(
    blocked: set[Cell],
    n: int,
    assignment: dict[Slot, str],
    path: str,
    cell_px: int = 64,
    min_len: int = 3,
) -> None:
    from PIL import Image, ImageDraw, ImageFont
    from grid_gen import _number_cells

    BLACK       = (30, 30, 30)
    WHITE       = (255, 255, 255)
    GRID_LINE   = (180, 180, 180)
    NUM_COLOR   = (80, 80, 80)
    LETTER_COLOR = (15, 15, 15)

    outer = 3
    inner = 1
    size_px = outer * 2 + n * cell_px + (n - 1) * inner
    img = Image.new("RGB", (size_px, size_px), WHITE)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, size_px - 1, size_px - 1], fill=BLACK)
    draw.rectangle([outer, outer, size_px - outer - 1, size_px - outer - 1], fill=WHITE)

    def cell_rect(r: int, c: int) -> tuple[int, int, int, int]:
        x0 = outer + (c - 1) * (cell_px + inner)
        y0 = outer + (r - 1) * (cell_px + inner)
        return x0, y0, x0 + cell_px - 1, y0 + cell_px - 1

    # Black cells
    for r in range(1, n + 1):
        for c in range(1, n + 1):
            if (r, c) in blocked:
                draw.rectangle(cell_rect(r, c), fill=BLACK)

    # Grid lines between white cells
    for r in range(1, n + 1):
        for c in range(1, n + 1):
            if (r, c) in blocked:
                continue
            x0, y0, x1, y1 = cell_rect(r, c)
            if c < n and (r, c + 1) not in blocked:
                draw.line([(x1 + 1, y0), (x1 + 1, y1)], fill=GRID_LINE, width=inner)
            if r < n and (r + 1, c) not in blocked:
                draw.line([(x0, y1 + 1), (x1, y1 + 1)], fill=GRID_LINE, width=inner)

    # Fonts
    num_font = letter_font = None
    for candidate in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]:
        if Path(candidate).exists():
            try:
                num_font    = ImageFont.truetype(candidate, size=max(9, cell_px // 6))
                letter_font = ImageFont.truetype(candidate, size=max(14, int(cell_px * 0.52)))
                break
            except Exception:
                pass
    if num_font is None:
        num_font = letter_font = ImageFont.load_default()

    # Build letter grid from assignment
    letter_at: dict[Cell, str] = {}
    for slot, word in assignment.items():
        for pos, cell in enumerate(slot.cells):
            letter_at[cell] = word[pos]

    numbers = _number_cells(blocked, n, min_len)

    for r in range(1, n + 1):
        for c in range(1, n + 1):
            if (r, c) in blocked:
                continue
            x0, y0, x1, y1 = cell_rect(r, c)
            # Clue number
            if (r, c) in numbers:
                draw.text((x0 + 2, y0 + 1), str(numbers[(r, c)]),
                          fill=NUM_COLOR, font=num_font)
            # Letter (centred)
            letter = letter_at.get((r, c), "")
            if letter:
                bb = draw.textbbox((0, 0), letter, font=letter_font)
                lw, lh = bb[2] - bb[0], bb[3] - bb[1]
                draw.text(
                    (x0 + (cell_px - lw) // 2, y0 + (cell_px - lh) // 2),
                    letter, fill=LETTER_COLOR, font=letter_font,
                )

    img.save(path)
    print(f"PNG saved → {path}")


# ── Word-list display ─────────────────────────────────────────────────────

def print_word_list(
    blocked: set[Cell],
    n: int,
    assignment: dict[Slot, str],
    word_scores: dict[str, int],
    min_len: int = 3,
) -> None:
    """Print the fill as a numbered across/down list for easy review."""
    from grid_gen import _number_cells
    numbers = _number_cells(blocked, n, min_len)
    num_to_cell = {v: k for k, v in numbers.items()}

    def slot_num(slot: Slot) -> int:
        return numbers.get(slot.start, 0)

    across = sorted([s for s in assignment if s.direction == "A"], key=slot_num)
    down   = sorted([s for s in assignment if s.direction == "D"], key=slot_num)

    print("\nACROSS")
    for slot in across:
        word = assignment[slot]
        score = word_scores.get(word, 0)
        print(f"  {slot_num(slot):2d}. {word}  ({score})")

    print("\nDOWN")
    for slot in down:
        word = assignment[slot]
        score = word_scores.get(word, 0)
        print(f"  {slot_num(slot):2d}. {word}  ({score})")
    print()


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill a British crossword grid (CSP backtracking)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Grid generation
    parser.add_argument("-n", "--size",       type=int,   default=15)
    parser.add_argument("-s", "--seed",       type=int,   default=400)
    parser.add_argument("-e", "--extensions", type=int,   default=12)
    parser.add_argument("--sym",              choices=["90","180"], default="90")
    parser.add_argument("--improve",          action="store_true")
    parser.add_argument("--min-density",      type=float, default=0.18)
    parser.add_argument("--max-short",        type=int,   default=4,
                        help="Stop improving when short-word count drops to this")
    parser.add_argument("--min-word",         type=int,   default=3)
    # Word list
    parser.add_argument("--wordlist",  type=Path, default=DEFAULT_WORDLIST)
    parser.add_argument("--min-score", type=int,  default=50,
                        help="Minimum word-quality score to include")
    parser.add_argument("--download",  action="store_true",
                        help="Force re-download of word list")
    parser.add_argument("--allow-s-plurals", action="store_true",
                        help="Do not penalise trivial S-plurals (e.g. TASKS, SEEMS)")
    # Search
    parser.add_argument("--time-limit", type=float, default=60.0,
                        help="Backtracking time limit in seconds")
    parser.add_argument("--noise", type=float, default=0.15,
                        help="Scoring noise ±fraction to diversify fills (0=off)")
    parser.add_argument("--interactive", action="store_true",
                        help="After solving, enter a feedback loop to ban words and re-solve")
    # Output
    parser.add_argument("--png",     metavar="FILE", default=None)
    parser.add_argument("--cell-px", type=int, default=64)
    args = parser.parse_args()

    # Word list
    if args.download:
        download_wordlist(args.wordlist)
    word_scores, pos_index, letter_freq, length_index = load_wordlist(
        args.wordlist, min_score=args.min_score, min_len=args.min_word,
        penalize_s_plurals=not args.allow_s_plurals,
    )

    # Grid
    from grid_gen import generate, improve_grid, render, stats
    print(f"\nGenerating {args.size}×{args.size} grid (seed={args.seed}) …")
    blocked, applied = generate(
        args.size, args.seed, args.extensions, args.sym, args.min_word
    )
    if args.improve:
        blocked, removed = improve_grid(
            blocked, args.size, args.sym, args.min_word, 5,
            args.min_density, args.max_short,
        )
        print(f"Improved: removed {removed} black squares")

    print(render(blocked, args.size, show_numbers=True, min_len=args.min_word))
    print(stats(blocked, args.size))
    print()

    # Fill
    banned: frozenset = frozenset()
    assignment = fill(
        blocked, args.size, word_scores, pos_index, letter_freq, length_index,
        min_len=args.min_word, time_limit=args.time_limit,
        seed=args.seed, noise=args.noise, banned=banned,
    )

    if assignment is None:
        print("No complete fill found.")
        sys.exit(1)

    print("\n" + render_filled_ascii(blocked, args.size, assignment))
    print_word_list(blocked, args.size, assignment, word_scores, args.min_word)

    if args.png:
        render_filled_png(
            blocked, args.size, assignment, args.png, args.cell_px, args.min_word
        )

    # Interactive feedback loop
    if args.interactive:
        while True:
            try:
                raw = input("Ban words (comma-separated, blank to finish): ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not raw:
                break

            new_bans = {w.strip().upper() for w in raw.split(",") if w.strip()}
            banned = banned | frozenset(new_bans)
            print(f"Banned so far: {sorted(banned)}\n")

            assignment = fill(
                blocked, args.size, word_scores, pos_index, letter_freq, length_index,
                min_len=args.min_word, time_limit=args.time_limit,
                seed=args.seed, noise=args.noise, banned=banned,
            )

            if assignment is None:
                print("Could not find a complete fill with these bans — try banning fewer words.")
                continue

            print("\n" + render_filled_ascii(blocked, args.size, assignment))
            print_word_list(blocked, args.size, assignment, word_scores, args.min_word)

            if args.png:
                render_filled_png(
                    blocked, args.size, assignment, args.png, args.cell_px, args.min_word
                )
                print(f"(PNG updated)")


if __name__ == "__main__":
    main()
