#!/usr/bin/env python3
"""
Themed Blocks puzzle generator.

A rectangular grid where certain cells form a decorative shape (e.g. a heart).
Every row and column is one word slot. Words span the full row/column but
skip over the shape cells — a 7-letter word might physically span 9 cells
if two shape cells sit in its path.

Crossing constraints apply only at non-shape cells.

Usage:
  python3 themedblocks.py --shape heart_6x7 --include "LOVE; HOPE" --png out.png
  python3 themedblocks.py --shape heart_6x7 --seed 100 --png out.png
"""

from __future__ import annotations
import argparse, random, time
from pathlib import Path
from typing import Optional
from collections import defaultdict

# ── Built-in pixel-art shapes ─────────────────────────────────────────────────
# Each shape defines the grid size and which cells are "skip" cells
# (visually coloured, no letter, words pass through them).

SHAPES: dict[str, dict] = {
    "heart_6x7": {
        "rows": 6, "cols": 7,
        "color": (220, 80, 100),   # rose/pink for the heart cells
        "skip": {
            (0,1),(0,2),(0,4),(0,5),
            (1,0),(1,3),(1,6),
            (2,0),(2,6),
            (3,1),(3,5),
            (4,2),(4,4),
            (5,3),
        },
    },
}


# ── Slot ──────────────────────────────────────────────────────────────────────

class Slot:
    def __init__(self, direction: str, index: int, cells: list[tuple[int,int]]):
        self.direction = direction   # 'A' (across) or 'D' (down)
        self.index     = index       # row number (A) or col number (D)
        self.cells     = cells       # (row, col) of letter cells in order
        self.length    = len(cells)

    def __repr__(self):
        return f"{self.direction}{self.index+1}({self.length})"

    def __hash__(self):
        return id(self)

    def __eq__(self, other):
        return self is other


def build_slots_and_crossings(
    rows: int, cols: int, skip: set
) -> tuple[list[Slot], dict[Slot, list]]:
    slots: list[Slot] = []

    for r in range(rows):
        cells = [(r, c) for c in range(cols) if (r, c) not in skip]
        if len(cells) >= 3:
            slots.append(Slot('A', r, cells))

    for c in range(cols):
        cells = [(r, c) for r in range(rows) if (r, c) not in skip]
        if len(cells) >= 3:
            slots.append(Slot('D', c, cells))

    # cell → [(slot, pos_in_slot), ...]
    cell_map: dict[tuple, list] = defaultdict(list)
    for slot in slots:
        for pos, cell in enumerate(slot.cells):
            cell_map[cell].append((slot, pos))

    # crossings[slot] = [(my_pos, other_slot, other_pos), ...]
    crossings: dict[Slot, list] = defaultdict(list)
    for cell, entries in cell_map.items():
        if len(entries) == 2:
            (s1, p1), (s2, p2) = entries
            crossings[s1].append((p1, s2, p2))
            crossings[s2].append((p2, s1, p1))

    return slots, dict(crossings)


# ── Wordlist ──────────────────────────────────────────────────────────────────

def load_wordlist(path: Path, min_score: int = 50) -> dict[int, list[str]]:
    by_length: dict[int, list[str]] = defaultdict(list)
    seen: set[str] = set()
    with open(path, encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line or ';' not in line:
                continue
            word, score_s = line.split(';', 1)
            if not word.isalpha():
                continue
            word = word.upper()
            try:
                score = int(score_s)
            except ValueError:
                continue
            if score >= min_score and word not in seen:
                seen.add(word)
                by_length[len(word)].append(word)
    return by_length


# ── CSP solver ────────────────────────────────────────────────────────────────

class _Timeout(Exception):
    pass


def _backtrack(
    assignment: dict[Slot, str],
    domains:    dict[Slot, list[str]],
    unassigned: list[Slot],
    crossings:  dict[Slot, list],
    used:       set[str],
    deadline:   float,
) -> Optional[dict[Slot, str]]:
    if not unassigned:
        return dict(assignment)
    if time.monotonic() > deadline:
        raise _Timeout

    # MRV: fewest candidates; degree tiebreak
    slot = min(unassigned, key=lambda s: (len(domains[s]), -len(crossings.get(s, []))))
    remaining = [s for s in unassigned if s is not slot]

    for word in domains[slot]:
        if word in used:
            continue

        # Check already-assigned crossings
        ok = True
        for my_pos, other_slot, other_pos in crossings.get(slot, []):
            if other_slot in assignment:
                if assignment[other_slot][other_pos] != word[my_pos]:
                    ok = False
                    break
        if not ok:
            continue

        # Forward check
        new_domains: dict[Slot, list[str]] = {}
        for s in remaining:
            filtered = []
            for w in domains[s]:
                if w in used or w == word:
                    continue
                consistent = True
                for p, os, op in crossings.get(s, []):
                    if os is slot:
                        if w[p] != word[op]:
                            consistent = False
                            break
                    elif os in assignment:
                        if w[p] != assignment[os][op]:
                            consistent = False
                            break
                if consistent:
                    filtered.append(w)
            if not filtered:
                ok = False
                break
            new_domains[s] = filtered

        if not ok:
            continue

        assignment[slot] = word
        used.add(word)
        result = _backtrack(assignment, {**domains, **new_domains},
                            remaining, crossings, used, deadline)
        del assignment[slot]
        used.discard(word)
        if result is not None:
            return result

    return None


def solve(
    slots:         list[Slot],
    crossings:     dict[Slot, list],
    by_length:     dict[int, list[str]],
    include_words: list[str],
    seed:          int,
    time_limit:    float,
) -> Optional[dict[Slot, str]]:
    rng = random.Random(seed)
    include_set = set(include_words)

    # Build domains: include words first, then shuffled rest
    domains: dict[Slot, list[str]] = {}
    for slot in slots:
        pinned = [w for w in include_words if len(w) == slot.length]
        rest   = [w for w in by_length.get(slot.length, []) if w not in include_set]
        rng.shuffle(rest)
        domains[slot] = pinned + rest

    # Pre-pin: deterministically assign include words before backtracking starts.
    # Priority: (1) unique total match, (2) unique across match, (3) unique down match.
    # Pre-pinning prevents the backtracker from locking crossing slots in a direction
    # that makes an include word impossible to place later.
    length_to_slots: dict[int, list[Slot]] = defaultdict(list)
    length_to_across: dict[int, list[Slot]] = defaultdict(list)
    length_to_down:   dict[int, list[Slot]] = defaultdict(list)
    for slot in slots:
        length_to_slots[slot.length].append(slot)
        if slot.direction == 'A':
            length_to_across[slot.length].append(slot)
        else:
            length_to_down[slot.length].append(slot)

    pre_assignment: dict[Slot, str] = {}
    pre_used: set[str] = set()

    for word in include_words:
        n = len(word)
        all_cands    = length_to_slots[n]
        across_cands = length_to_across[n]
        down_cands   = length_to_down[n]

        target = None
        if len(all_cands) == 1:
            target = all_cands[0]
        elif len(across_cands) == 1:
            target = across_cands[0]
        elif len(down_cands) == 1:
            target = down_cands[0]

        if target is not None and target not in pre_assignment:
            pre_assignment[target] = word
            pre_used.add(word)

    # Forward-check from each pre-assignment
    for slot, word in pre_assignment.items():
        for my_pos, other_slot, other_pos in crossings.get(slot, []):
            if other_slot not in pre_assignment:
                domains[other_slot] = [
                    w for w in domains[other_slot]
                    if w not in pre_used and w[other_pos] == word[my_pos]
                ]

    unassigned = [s for s in slots if s not in pre_assignment]

    # Sort: include-word slots first (highest priority for the backtracker), then MRV
    unassigned = sorted(
        unassigned,
        key=lambda s: (0 if any(len(w) == s.length for w in include_words) else 1,
                       len(domains[s])),
    )

    deadline = time.monotonic() + time_limit
    try:
        return _backtrack(pre_assignment, domains, unassigned, crossings, pre_used, deadline)
    except _Timeout:
        print("Time limit reached.")
        return None


# ── ASCII rendering ───────────────────────────────────────────────────────────

def render_ascii(
    rows: int, cols: int, skip: set,
    assignment: Optional[dict[Slot, str]] = None,
) -> str:
    cell_letter: dict[tuple, str] = {}
    if assignment:
        for slot, word in assignment.items():
            for cell, letter in zip(slot.cells, word):
                cell_letter[cell] = letter

    lines = []
    for r in range(rows):
        row = []
        for c in range(cols):
            if (r, c) in skip:
                row.append("♥ ")
            elif assignment:
                row.append(cell_letter.get((r, c), '?') + ' ')
            else:
                row.append("_ ")
        lines.append(''.join(row))
    return '\n'.join(lines)


# ── PNG rendering ─────────────────────────────────────────────────────────────

def render_png(
    rows: int, cols: int, skip: set,
    assignment: dict[Slot, str],
    slots: list[Slot],
    crossings: dict[Slot, list],
    output_path: str,
    clues: "dict[str, str] | None" = None,
    color: tuple = (220, 80, 100),
    cell_px: int = 72,
    solved: bool = False,
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    MARGIN     = cell_px // 2
    CLUE_W     = 320
    GRID_W     = cols * cell_px
    GRID_H     = rows * cell_px
    IMG_W      = MARGIN + GRID_W + MARGIN + (CLUE_W if clues else 0)
    IMG_H      = MARGIN + GRID_H + MARGIN

    BG         = (250, 248, 245)
    GRID_LINE  = (180, 180, 180)
    TEXT_C     = (30, 30, 30)
    SKIP_C     = color
    SKIP_LITE  = tuple(min(255, v + 60) for v in color)

    img  = Image.new("RGB", (IMG_W, IMG_H), BG)
    draw = ImageDraw.Draw(img)

    try:
        font_letter = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", cell_px // 2)
        font_small  = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", cell_px // 5)
        font_clue   = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
        font_head   = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
    except Exception:
        font_letter = font_small = font_clue = font_head = ImageFont.load_default()

    # Build cell→letter
    cell_letter: dict[tuple, str] = {}
    if assignment:
        for slot, word in assignment.items():
            for cell, letter in zip(slot.cells, word):
                cell_letter[cell] = letter

    # Draw cells
    for r in range(rows):
        for c in range(cols):
            x = MARGIN + c * cell_px
            y = MARGIN + r * cell_px
            if (r, c) in skip:
                draw.rectangle([x, y, x+cell_px, y+cell_px], fill=SKIP_C, outline=SKIP_LITE)
            else:
                draw.rectangle([x, y, x+cell_px, y+cell_px], fill="white", outline=GRID_LINE)
                if solved:
                    letter = cell_letter.get((r, c), '')
                    if letter:
                        bb = draw.textbbox((0,0), letter, font=font_letter)
                        lw, lh = bb[2]-bb[0], bb[3]-bb[1]
                        draw.text((x+(cell_px-lw)//2, y+(cell_px-lh)//2),
                                  letter, font=font_letter, fill=TEXT_C)

    # Row and column labels
    for r in range(rows):
        label = str(r + 1)
        bb = draw.textbbox((0,0), label, font=font_small)
        lw, lh = bb[2]-bb[0], bb[3]-bb[1]
        draw.text((MARGIN - lw - 4, MARGIN + r*cell_px + (cell_px-lh)//2),
                  label, font=font_small, fill=(120,120,120))
    for c in range(cols):
        label = str(c + 1)
        bb = draw.textbbox((0,0), label, font=font_small)
        lw, lh = bb[2]-bb[0], bb[3]-bb[1]
        draw.text((MARGIN + c*cell_px + (cell_px-lw)//2, MARGIN - lh - 4),
                  label, font=font_small, fill=(120,120,120))

    # Clue panel
    if clues:
        cx = MARGIN + GRID_W + MARGIN
        cy = MARGIN
        across_slots = sorted([s for s in slots if s.direction == 'A'], key=lambda s: s.index)
        down_slots   = sorted([s for s in slots if s.direction == 'D'], key=lambda s: s.index)

        for header, slot_list, prefix in [
            ("ACROSS", across_slots, 'A'),
            ("DOWN",   down_slots,   'D'),
        ]:
            draw.text((cx, cy), header, font=font_head, fill=(60,60,60))
            cy += 20
            for slot in slot_list:
                key = f"{slot.index+1}{slot.direction}"
                clue_text = clues.get(key, '')
                entry = f"{slot.index+1}. ({slot.length}) {clue_text}"
                # Simple word-wrap
                words_in_clue = entry.split()
                line, lines_out = '', []
                for w in words_in_clue:
                    test = (line + ' ' + w).strip()
                    bb = draw.textbbox((0,0), test, font=font_clue)
                    if bb[2]-bb[0] > CLUE_W - 10:
                        lines_out.append(line)
                        line = w
                    else:
                        line = test
                if line:
                    lines_out.append(line)
                clue_color = SKIP_C if clue_text else TEXT_C
                for l in lines_out:
                    if cy + 16 > IMG_H:
                        break
                    draw.text((cx, cy), l, font=font_clue, fill=clue_color)
                    cy += 15
                cy += 3

    img.save(output_path)
    print(f"  Saved: {output_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

DEFAULT_WORDLIST = Path(__file__).parent.parent / 'wordlist.dict'


def main():
    parser = argparse.ArgumentParser(
        description='Themed Blocks puzzle generator',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('--shape',      default='heart_6x7', choices=list(SHAPES))
    parser.add_argument('--include',    metavar='WORDS', default=None,
                        help='Semicolon-separated words to include, e.g. "LOVE; HOPE"')
    parser.add_argument('--seed',       type=int,   default=42)
    parser.add_argument('--time-limit', type=float, default=30.0)
    parser.add_argument('--wordlist',   type=Path,  default=DEFAULT_WORDLIST)
    parser.add_argument('--min-score',  type=int,   default=50)
    parser.add_argument('--png',        metavar='FILE', default=None)
    parser.add_argument('--cell-px',    type=int,   default=72)
    args = parser.parse_args()

    shape  = SHAPES[args.shape]
    rows   = shape['rows']
    cols   = shape['cols']
    skip   = shape['skip']
    color  = shape.get('color', (220, 80, 100))

    slots, crossings = build_slots_and_crossings(rows, cols, skip)

    print(f"Shape : {args.shape}  ({rows}×{cols}, {len(skip)} skip cells)")
    print(f"Slots : {len(slots)}")
    for s in slots:
        print(f"  {s}")

    print(f"\nLoading wordlist …")
    by_length = load_wordlist(args.wordlist, args.min_score)

    include_words: list[str] = []
    if args.include:
        include_words = [w.strip().upper() for w in args.include.split(';') if w.strip()]
        # Ensure include words are in the wordlist
        for w in include_words:
            by_length[len(w)] = [w] + [x for x in by_length.get(len(w), []) if x != w]
        print(f"Include: {include_words}")

    print(f"\nSolving (seed={args.seed}) …")
    t0 = time.monotonic()
    result = solve(slots, crossings, by_length, include_words, args.seed, args.time_limit)
    elapsed = time.monotonic() - t0

    if result is None:
        print("No solution found.")
        return

    print(f"Solved in {elapsed:.2f}s\n")
    print(render_ascii(rows, cols, skip, result))
    print()
    across = sorted([s for s in result if s.direction == 'A'], key=lambda s: s.index)
    down   = sorted([s for s in result if s.direction == 'D'], key=lambda s: s.index)
    print("ACROSS:")
    for s in across:
        print(f"  {s.index+1}. {result[s]}  ({s.length} letters)")
    print("DOWN:")
    for s in down:
        print(f"  {s.index+1}. {result[s]}  ({s.length} letters)")

    if args.png:
        p = Path(args.png)
        answer_path = str(p.parent / f"{p.stem}_answer{p.suffix or '.png'}")
        render_png(rows, cols, skip, result, slots, crossings,
                   str(p), color=color, cell_px=args.cell_px, solved=False)
        render_png(rows, cols, skip, result, slots, crossings,
                   answer_path, color=color, cell_px=args.cell_px, solved=True)


if __name__ == '__main__':
    main()
