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
    "body_6x7": {
        # 6 rows × 7 cols — same dimensions as heart_6x7.
        # Body lies diagonally upper-left → lower-right.
        # Slot lengths: across all 5 — down 5,4,4,4,4,4,5
        # Short slots keep the CSP tractable; highlight_skip marks the bullet hole in red.
        "rows": 6, "cols": 7,
        "color": (35, 35, 35),           # near-black for the body silhouette
        "highlight_color": (190, 30, 30), # blood-red for the bullet hole
        "skip": {
            # head — diamond outline, upper-left
            (0,1),(0,2),
            (1,0),(1,3),
            (2,1),(2,2),
            # bullet hole — two cells on the torso (rendered red)
            (3,3),(3,4),
            # torso / lower body
            (4,4),(4,5),
            # feet, bottom-right
            (5,5),(5,6),
        },
        "highlight_skip": {
            (3,3),(3,4),   # bullet hole (coloured separately)
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


def _find_preassignment(
    include_words: list[str],
    slots:         list[Slot],
    crossings:     dict[Slot, list],
) -> "Optional[dict[Slot, str]]":
    """Assign every include word to a distinct slot.

    Only crossing constraints *between include-word slots* are checked here;
    the main backtracker enforces the rest.  Words sorted most-constrained
    first (fewest candidate slots) so we prune early.
    """
    length_to_slots: dict[int, list[Slot]] = defaultdict(list)
    for s in slots:
        length_to_slots[s.length].append(s)

    words = sorted(include_words, key=lambda w: len(length_to_slots[len(w)]))

    def bt(idx: int, assignment: dict[Slot, str], used: set) -> "Optional[dict[Slot, str]]":
        if idx == len(words):
            return dict(assignment)
        word = words[idx]
        for slot in length_to_slots[len(word)]:
            if slot in used:
                continue
            ok = True
            for my_pos, other_slot, other_pos in crossings.get(slot, []):
                if other_slot in assignment:
                    if assignment[other_slot][other_pos] != word[my_pos]:
                        ok = False
                        break
            if not ok:
                continue
            assignment[slot] = word
            result = bt(idx + 1, assignment, used | {slot})
            del assignment[slot]
            if result is not None:
                return result
        return None

    return bt(0, {}, set())


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

    # Pre-pin all include words using a mini-backtracker that checks
    # include-vs-include crossing constraints.  This prevents the main solver
    # from locking crossing slots with letters that make an include word impossible.
    pre_assignment: dict[Slot, str] = {}
    pre_used: set[str] = set()

    if include_words:
        found = _find_preassignment(include_words, slots, crossings)
        if found:
            pre_assignment = found
            pre_used       = set(include_words)
            # Forward-check: prune every unassigned slot's domain using the
            # crossing constraints imposed by each pre-pinned word.
            for slot, word in pre_assignment.items():
                for my_pos, other_slot, other_pos in crossings.get(slot, []):
                    if other_slot not in pre_assignment:
                        domains[other_slot] = [
                            w for w in domains[other_slot]
                            if w not in pre_used and w[other_pos] == word[my_pos]
                        ]
        else:
            print("Warning: could not assign all include words to distinct slots — "
                  "some may not appear.")

    unassigned = [s for s in slots if s not in pre_assignment]
    unassigned.sort(key=lambda s: len(domains[s]))

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
    highlight_skip: "set | None" = None,
    skip_char: str = "█",
    highlight_char: str = "•",
) -> str:
    hl = highlight_skip or set()
    cell_letter: dict[tuple, str] = {}
    if assignment:
        for slot, word in assignment.items():
            for cell, letter in zip(slot.cells, word):
                cell_letter[cell] = letter

    lines = []
    for r in range(rows):
        row = []
        for c in range(cols):
            if (r, c) in hl:
                row.append(highlight_char + " ")
            elif (r, c) in skip:
                row.append(skip_char + " ")
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
    highlight_skip: "set | None" = None,
    highlight_color: "tuple | None" = None,
    cell_px: int = 72,
    solved: bool = False,
    title: "str | None" = None,
    credit: "str | None" = None,
    thanks: "str | None" = None,
) -> None:
    from PIL import Image, ImageDraw, ImageFont

    hl_skip  = highlight_skip or set()
    hl_color = highlight_color or color

    MARGIN     = cell_px // 2
    CLUE_W     = 320
    GRID_W     = cols * cell_px
    GRID_H     = rows * cell_px

    # Header height: title + credit + thanks lines above the grid
    HDR_LINES  = [t for t in [title, credit, thanks] if t]
    HDR_H      = (len(HDR_LINES) * 20 + 10) if HDR_LINES else 0

    IMG_W      = MARGIN + GRID_W + MARGIN + (CLUE_W if clues else 0)
    IMG_H      = HDR_H + MARGIN + GRID_H + MARGIN

    BG         = (250, 248, 245)
    GRID_LINE  = (180, 180, 180)
    TEXT_C     = (30, 30, 30)
    SKIP_C     = color
    SKIP_LITE  = tuple(min(255, v + 60) for v in color)
    HL_C       = hl_color
    HL_LITE    = tuple(min(255, v + 60) for v in hl_color)

    img  = Image.new("RGB", (IMG_W, IMG_H), BG)
    draw = ImageDraw.Draw(img)

    try:
        font_letter = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", cell_px // 2)
        font_small  = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", cell_px // 5)
        font_clue   = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
        font_head   = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
        font_title  = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
        font_sub    = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 13)
    except Exception:
        font_letter = font_small = font_clue = font_head = ImageFont.load_default()
        font_title  = font_sub = ImageFont.load_default()

    # Draw header
    hy = 8
    if title:
        bb = draw.textbbox((0, 0), title, font=font_title)
        tw = bb[2] - bb[0]
        draw.text(((IMG_W - tw) // 2, hy), title, font=font_title, fill=(60, 60, 60))
        hy += 22
    for sub in [t for t in [credit, thanks] if t]:
        bb = draw.textbbox((0, 0), sub, font=font_sub)
        tw = bb[2] - bb[0]
        draw.text(((IMG_W - tw) // 2, hy), sub, font=font_sub, fill=(130, 130, 130))
        hy += 16

    # Build cell→letter
    cell_letter: dict[tuple, str] = {}
    if assignment:
        for slot, word in assignment.items():
            for cell, letter in zip(slot.cells, word):
                cell_letter[cell] = letter

    GRID_TOP = HDR_H + MARGIN   # vertical offset for grid top

    # Draw cells
    for r in range(rows):
        for c in range(cols):
            x = MARGIN + c * cell_px
            y = GRID_TOP + r * cell_px
            if (r, c) in hl_skip:
                draw.rectangle([x, y, x+cell_px, y+cell_px], fill=HL_C, outline=HL_LITE)
            elif (r, c) in skip:
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
        draw.text((MARGIN - lw - 4, GRID_TOP + r*cell_px + (cell_px-lh)//2),
                  label, font=font_small, fill=(120,120,120))
    for c in range(cols):
        label = str(c + 1)
        bb = draw.textbbox((0,0), label, font=font_small)
        lw, lh = bb[2]-bb[0], bb[3]-bb[1]
        draw.text((MARGIN + c*cell_px + (cell_px-lw)//2, GRID_TOP - lh - 4),
                  label, font=font_small, fill=(120,120,120))

    # Clue panel
    if clues:
        cx = MARGIN + GRID_W + MARGIN
        cy = GRID_TOP
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
                entry = f"{slot.index+1}. {clue_text}"
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
    parser.add_argument('--render-personal', metavar='KEY', default=None,
                        help='Render a puzzle from puzzles_personal.py by key')
    args = parser.parse_args()

    # ── render-personal: load puzzles_personal.py and render ──────────────────
    if args.render_personal:
        import importlib.util as _ilu
        _personal_path = Path(__file__).parent / 'puzzles_personal.py'
        if not _personal_path.exists():
            print(f"Error: {_personal_path} not found.", file=__import__('sys').stderr)
            return
        _spec = _ilu.spec_from_file_location('puzzles_personal', _personal_path)
        _mod  = _ilu.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        key = args.render_personal
        if key not in _mod.PUZZLES:
            print(f"Error: key {key!r} not found in puzzles_personal.py", file=__import__('sys').stderr)
            print(f"Keys: {', '.join(_mod.PUZZLES)}", file=__import__('sys').stderr)
            return
        _mod.render_puzzle(key, cell_px=args.cell_px)
        return

    shape           = SHAPES[args.shape]
    rows            = shape['rows']
    cols            = shape['cols']
    skip            = shape['skip']
    color           = shape.get('color', (220, 80, 100))
    highlight_skip  = shape.get('highlight_skip', set())
    highlight_color = shape.get('highlight_color', None)

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
    print(render_ascii(rows, cols, skip, result, highlight_skip=highlight_skip))
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
                   str(p), color=color, highlight_skip=highlight_skip,
                   highlight_color=highlight_color, cell_px=args.cell_px, solved=False)
        render_png(rows, cols, skip, result, slots, crossings,
                   answer_path, color=color, highlight_skip=highlight_skip,
                   highlight_color=highlight_color, cell_px=args.cell_px, solved=True)


if __name__ == '__main__':
    main()
