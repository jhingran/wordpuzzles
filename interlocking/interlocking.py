#!/usr/bin/env python3
"""
Interlocking Squares word puzzle generator.

Grid: diamond-shaped rows that widen by 2 in the top half, narrow by 2 in the bottom.
Each row reads left-to-right as a word.  Each interior corner is shared by exactly
4 cells; those 4 letters also form a word (clockwise or counterclockwise, any start).

Usage:
  python interlocking.py generate --widths 3 5 5 3 --seed 42
  python interlocking.py generate --widths 3 5 7 5 3 --seed 42
"""

import argparse
import random
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

WORDLIST_PATH = Path(__file__).parent.parent / "wordlist.dict"


# ── Wordlist ──────────────────────────────────────────────────────────────────

def load_wordlist(path: Path, min_score: int = 50) -> dict[str, int]:
    words: dict[str, int] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if ";" in line:
                word, score_s = line.rsplit(";", 1)
                try:
                    s = int(score_s)
                except ValueError:
                    continue
                if s >= min_score:
                    words[word.upper()] = s
            else:
                words[line.upper()] = 50
    return words


# ── Grid geometry ─────────────────────────────────────────────────────────────

def square_groups(widths: list[int]) -> list[tuple]:
    """
    Return all square groups as (TL, TR, BR, BL) tuples of (row, col_in_row) pairs,
    listed clockwise.  An interior corner at an absolute column gap shared by two
    adjacent rows gives one group.
    """
    max_w = max(widths)
    offsets = [(max_w - w) // 2 for w in widths]
    groups = []
    for i in range(len(widths) - 1):
        off_top, off_bot = offsets[i], offsets[i + 1]
        w_top,   w_bot   = widths[i],  widths[i + 1]
        top_gaps = set(range(off_top + 1, off_top + w_top))
        bot_gaps = set(range(off_bot + 1, off_bot + w_bot))
        for gap in sorted(top_gaps & bot_gaps):
            TL = (i,     gap - 1 - off_top)
            TR = (i,     gap     - off_top)
            BL = (i + 1, gap - 1 - off_bot)
            BR = (i + 1, gap     - off_bot)
            groups.append((TL, TR, BR, BL))
    return groups


def standing_cells(widths: list) -> list:
    """
    Return (row, col) pairs that belong to no square group.
    These cells carry only a row-word letter and have no square constraint — a
    design flaw avoided by using two equal-width middle rows instead of one.
    """
    groups = square_groups(widths)
    covered = set()
    for (TL, TR, BR, BL) in groups:
        covered.update([TL, TR, BR, BL])
    standing = []
    for i, w in enumerate(widths):
        for j in range(w):
            if (i, j) not in covered:
                standing.append((i, j))
    return standing


# ── Square-word constraint ────────────────────────────────────────────────────

def build_valid_squares(words_4: list[str]) -> set[tuple]:
    """
    All valid (TL, TR, BR, BL) clockwise letter 4-tuples derived from 4-letter words.
    Reading the square CW or CCW from any starting corner must yield a dictionary word.
    That means: all 4 rotations of the CW string AND all 4 rotations of its reverse.
    """
    valid: set[tuple] = set()
    for word in words_4:
        rev = word[::-1]
        for i in range(4):
            rot  = word[i:] + word[:i]
            valid.add((rot[0], rot[1], rot[2], rot[3]))
            rotr = rev[i:] + rev[:i]
            valid.add((rotr[0], rotr[1], rotr[2], rotr[3]))
    return valid


def find_square_word(tl: str, tr: str, br: str, bl: str,
                     word_set_4: set[str]) -> str:
    """Return the actual dictionary word formed by this square group."""
    cw = tl + tr + br + bl
    for s in (cw, cw[::-1]):
        for i in range(4):
            rot = s[i:] + s[:i]
            if rot in word_set_4:
                return rot
    return cw  # shouldn't happen for a valid puzzle


# ── CSP solver ────────────────────────────────────────────────────────────────

def solve(
    widths: list[int],
    word_by_len: dict[int, list[str]],
    valid_sq: set[tuple],
    seed: int = 42,
    time_limit: float = 60.0,
) -> Optional[list]:
    """
    Backtracking CSP: one word per row, satisfying all square-group constraints.

    After placing row i, for each square group between rows i and i+1 we know
    (TL, TR); we precompute which (BR, BL) pairs are valid and use that to filter
    candidates for row i+1 (forward checking).
    """
    rng      = random.Random(seed)
    deadline = time.time() + time_limit
    groups   = square_groups(widths)

    # groups_above[r] = square groups whose BL/BR cells are in row r
    groups_above: list[list] = [[] for _ in range(len(widths))]
    for g in groups:
        TL, TR, BR, BL = g
        groups_above[BL[0]].append(g)

    # valid_given_top[(tl,tr)] = set of (br,bl) pairs that make a valid square word
    valid_given_top: dict[tuple, set[tuple]] = defaultdict(set)
    for (tl, tr, br, bl) in valid_sq:
        valid_given_top[(tl, tr)].add((br, bl))

    # Shuffle word lists once per seed
    shuffled: dict[int, list[str]] = {
        length: rng.sample(ws, len(ws))
        for length, ws in word_by_len.items()
    }

    def backtrack(row: int, placed: list) -> Optional[list]:
        if time.time() > deadline:
            return None
        if row == len(widths):
            return placed

        w    = widths[row]
        base = shuffled.get(w, [])

        # Build pair-constraints from the row above
        constraints = []   # (bl_col, br_col, valid_pairs_set)
        for (TL, TR, BR, BL) in groups_above[row]:
            tl = placed[TL[0]][TL[1]]
            tr = placed[TR[0]][TR[1]]
            constraints.append((BL[1], BR[1], valid_given_top.get((tl, tr), set())))

        placed_set = set(placed)
        for word in base:
            if word in placed_set:
                continue
            if all(
                (word[br_col], word[bl_col]) in vp
                for bl_col, br_col, vp in constraints
            ):
                result = backtrack(row + 1, placed + [word])
                if result is not None:
                    return result

        return None

    return backtrack(0, [])


# ── PNG output ───────────────────────────────────────────────────────────────

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL = True
except ImportError:
    _PIL = False

_CORNER_COLORS = [
    '#C1121F', '#2D6A4F', '#1D3557', '#7B2D8B', '#E76F51',
    '#0077B6', '#8B5E3C', '#6D6875', '#2B9348', '#9B2226',
    '#F4A261', '#3A0CA3', '#E63946', '#457B9D', '#A8DADC',
    '#D62828', '#B7E4C7', '#F1FAEE',
]


def _font(size: int):
    for path in (
        '/System/Library/Fonts/Helvetica.ttc',
        '/System/Library/Fonts/Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    ):
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            pass
    return ImageFont.load_default()


def draw_image(
    widths: list,
    words: Optional[list],      # None → blank puzzle cells
    word_set_4: set,
    output_path: str,
    solved: bool = True,
) -> None:
    if not _PIL:
        print("  Pillow not installed — skipping PNG.")
        return

    CELL    = 68          # px per cell
    PAD     = 36          # outer padding
    TITLE_H = 52
    DOT_R   = 11          # interior-corner dot radius
    BW      = 2           # cell border width

    max_w   = max(widths)
    n_rows  = len(widths)
    offsets = [(max_w - w) // 2 for w in widths]
    groups  = square_groups(widths)

    grid_w = max_w * CELL
    grid_h = n_rows * CELL
    img_w  = PAD + grid_w + PAD
    img_h  = PAD + TITLE_H + grid_h + PAD

    img  = Image.new('RGB', (img_w, img_h), '#F8F7F2')
    draw = ImageDraw.Draw(img)

    f_title  = _font(20)
    f_letter = _font(32)
    f_dot    = _font(13)

    # Title
    title = f"INTERLOCKING SQUARES  ({' · '.join(str(w) for w in widths)})"
    draw.text((img_w // 2, PAD + TITLE_H // 2), title,
              fill='#1A1A2E', font=f_title, anchor='mm')

    grid_top = PAD + TITLE_H

    def cell_rect(row, col):
        x0 = PAD + (offsets[row] + col) * CELL
        y0 = grid_top + row * CELL
        return [x0, y0, x0 + CELL, y0 + CELL]

    def cell_center(row, col):
        r = cell_rect(row, col)
        return ((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)

    # ── Cells ──
    for i, w in enumerate(widths):
        for j in range(w):
            rect = cell_rect(i, j)
            draw.rectangle(rect, fill='white', outline='#1A1A2E', width=BW)
            if solved and words:
                cx, cy = cell_center(i, j)
                letter = words[i][j]
                draw.text((cx, cy), letter, fill='#1A1A2E', font=f_letter, anchor='mm')

    # ── Interior-corner dots ──
    for si, (TL, TR, BR, BL) in enumerate(groups):
        # Absolute column gap = offset of TL's row + TL col + 1
        abs_gap = offsets[TL[0]] + TL[1] + 1
        cx = PAD + abs_gap * CELL
        cy = grid_top + (TL[0] + 1) * CELL

        color = '#888888' if solved else _CORNER_COLORS[si % len(_CORNER_COLORS)]
        draw.ellipse([cx - DOT_R, cy - DOT_R, cx + DOT_R, cy + DOT_R],
                     fill=color, outline='white', width=1)
        if not solved:
            draw.text((cx, cy), str(si + 1), fill='white', font=f_dot, anchor='mm')

    img.save(output_path)
    print(f"  → Saved: {output_path}")


def _emit_pngs(widths: list, words: list, word_set_4: set, base_path: str) -> None:
    from pathlib import Path as _Path
    p = _Path(base_path)
    draw_image(widths, words, word_set_4,
               str(p.with_stem(p.stem + '_solution')), solved=True)
    draw_image(widths, None, word_set_4,
               str(p.with_stem(p.stem + '_puzzle')), solved=False)


# ── Display ───────────────────────────────────────────────────────────────────

def display(widths: list[int], words: list[str], word_set_4: set[str]) -> None:
    max_w  = max(widths)
    groups = square_groups(widths)
    SEP    = "═" * 54

    print(f"\n  INTERLOCKING SQUARES  ({' · '.join(str(w) for w in widths)})")
    print(f"  {SEP}")
    print()

    for i, (w, word) in enumerate(zip(widths, words)):
        off  = (max_w - w) // 2
        pad  = "    " * off
        cells = "  ".join(f"[{c}]" for c in word)
        print(f"  Row {chr(65 + i)}:  {pad}{cells}")

    print()
    print(f"  Square words ({len(groups)} total):")
    for si, (TL, TR, BR, BL) in enumerate(groups):
        tl = words[TL[0]][TL[1]]
        tr = words[TR[0]][TR[1]]
        br = words[BR[0]][BR[1]]
        bl = words[BL[0]][BL[1]]
        sq = find_square_word(tl, tr, br, bl, word_set_4)
        loc = f"rows {TL[0]+1}–{BL[0]+1}, cols {TL[1]+1}–{TR[1]+1}/{BL[1]+1}–{BR[1]+1}"
        print(f"    {si+1:2}. {sq:<8}  ({loc})")

    print(f"\n  {SEP}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="Interlocking Squares puzzle generator")
    ap.add_argument(
        "--widths", type=int, nargs="+", default=[3, 5, 7, 7, 5, 3],
        help="Row widths, e.g. 3 5 7 7 5 3  (odd, widen then narrow by 2; two equal middle rows avoids standing squares)",
    )
    ap.add_argument("--seed",       type=int,   default=42)
    ap.add_argument("--min-score",  type=int,   default=70)
    ap.add_argument("--time-limit", type=float, default=120.0)
    ap.add_argument("--tries",      type=int,   default=20,
                    help="Seed variations to attempt (default: 20)")
    ap.add_argument("--png", metavar="FILE", help="Save solution + puzzle PNGs")
    args = ap.parse_args()

    widths = args.widths

    bad = standing_cells(widths)
    if bad:
        row_labels = [chr(65 + r) for r, c in bad]
        print(f"Warning: {len(bad)} standing cell(s) in row(s) {', '.join(row_labels)} "
              f"— they carry no square constraint. "
              f"Use two equal-width middle rows (e.g. 3 5 7 7 5 3) to avoid this.",
              file=sys.stderr)

    print(f"Loading wordlist … ", end="", flush=True)
    word_scores = load_wordlist(WORDLIST_PATH, args.min_score)
    print(f"{len(word_scores):,} words")

    word_by_len: dict[int, list[str]] = defaultdict(list)
    for word in word_scores:
        word_by_len[len(word)].append(word)

    word_set_4 = set(word_by_len.get(4, []))
    valid_sq   = build_valid_squares(word_set_4)

    groups     = square_groups(widths)
    total_cells = sum(widths)
    print(f"Grid: {widths}  —  {total_cells} cells, {len(groups)} square words")
    print(f"Solving", end="", flush=True)

    start  = time.time()
    result = None
    for attempt in range(args.tries):
        seed   = args.seed + attempt
        result = solve(
            widths, word_by_len, valid_sq,
            seed=seed,
            time_limit=args.time_limit / args.tries,
        )
        if result:
            print(f"  → found (seed {seed}, {time.time() - start:.2f}s)")
            break
        print(".", end="", flush=True)
    else:
        print("\nNo solution found — try a different --seed or looser --min-score.")
        sys.exit(1)

    display(widths, result, word_set_4)
    if args.png:
        _emit_pngs(widths, result, word_set_4, args.png)


if __name__ == "__main__":
    main()
