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


# ── Include words ─────────────────────────────────────────────────────────────

def _parse_include(s: str) -> dict:
    """Parse 'WORD: clue; WORD2' into {WORD: clue, WORD2: ''} (uppercase keys)."""
    result = {}
    for entry in s.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        if ":" in entry:
            word, clue = entry.split(":", 1)
            result[word.strip().upper()] = clue.strip()
        else:
            result[entry.upper()] = ""
    return result


def _found_include(widths: list, words: list, word_set_4: set,
                   include_words: dict) -> list:
    """Return which include words appear in the solution (rows or square groups)."""
    inc = set(include_words)
    found = []
    for w in words:
        if w in inc:
            found.append(w)
    groups = square_groups(widths)
    for (TL, TR, BR, BL) in groups:
        sq = find_square_word(
            words[TL[0]][TL[1]], words[TR[0]][TR[1]],
            words[BR[0]][BR[1]], words[BL[0]][BL[1]],
            word_set_4,
        )
        if sq in inc and sq not in found:
            found.append(sq)
    return found


# ── CSP solver ────────────────────────────────────────────────────────────────

def solve(
    widths: list[int],
    word_by_len: dict[int, list[str]],
    valid_sq: set[tuple],
    word_set_4: set[str],
    seed: int = 42,
    time_limit: float = 60.0,
    include_words: Optional[dict] = None,
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

    # Shuffle word lists; put include words of matching length at the front
    inc_set = set(include_words or {})
    shuffled: dict[int, list[str]] = {}
    for length, ws in word_by_len.items():
        rest = rng.sample([w for w in ws if w not in inc_set], len([w for w in ws if w not in inc_set]))
        front = [w for w in inc_set if len(w) == length and w in set(ws)]
        shuffled[length] = front + rest

    def backtrack(row: int, placed: list, seen_sq: frozenset) -> Optional[list]:
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
            if not all(
                (word[br_col], word[bl_col]) in vp
                for bl_col, br_col, vp in constraints
            ):
                continue
            # Reject if any newly formed square word duplicates an earlier one
            new_sqs: list = []
            dup = False
            for (TL, TR, BR, BL) in groups_above[row]:
                sq = find_square_word(
                    placed[TL[0]][TL[1]], placed[TR[0]][TR[1]],
                    word[BR[1]], word[BL[1]], word_set_4,
                )
                if sq in seen_sq or sq in new_sqs:
                    dup = True
                    break
                new_sqs.append(sq)
            if dup:
                continue
            result = backtrack(row + 1, placed + [word], seen_sq | frozenset(new_sqs))
            if result is not None:
                return result

        return None

    return backtrack(0, [], frozenset())


# ── Targeted CSP solver (forced row words) ───────────────────────────────────

def solve_forced(
    widths: list,
    word_by_len: dict,
    valid_sq: set,
    word_set_4: set,
    forced: dict,           # {row_idx: word} — these rows are fixed
    seed: int = 42,
    time_limit: float = 2.0,
    include_words: Optional[dict] = None,
) -> Optional[list]:
    """
    Like solve(), but one or more rows are pinned to a specific word.
    Free rows still use the shuffled word list (include words front-loaded).
    """
    rng      = random.Random(seed)
    deadline = time.time() + time_limit
    groups   = square_groups(widths)

    groups_above: list[list] = [[] for _ in range(len(widths))]
    for g in groups:
        TL, TR, BR, BL = g
        groups_above[BL[0]].append(g)

    valid_given_top: dict[tuple, set[tuple]] = defaultdict(set)
    for (tl, tr, br, bl) in valid_sq:
        valid_given_top[(tl, tr)].add((br, bl))

    inc_set = set(forced.values()) | set(include_words or {})
    shuffled: dict[int, list] = {}
    for length, ws in word_by_len.items():
        rest  = rng.sample([w for w in ws if w not in inc_set], len([w for w in ws if w not in inc_set]))
        front = [w for w in inc_set if len(w) == length and w in set(ws) and w not in forced.values()]
        shuffled[length] = front + rest

    def backtrack(row: int, placed: list, seen_sq: frozenset) -> Optional[list]:
        if time.time() > deadline:
            return None
        if row == len(widths):
            return placed

        w = widths[row]
        if row in forced:
            fw = forced[row]
            candidates = [fw] if fw in set(word_by_len.get(w, [])) else []
        else:
            candidates = shuffled.get(w, [])

        constraints = []
        for (TL, TR, BR, BL) in groups_above[row]:
            tl = placed[TL[0]][TL[1]]
            tr = placed[TR[0]][TR[1]]
            constraints.append((BL[1], BR[1], valid_given_top.get((tl, tr), set())))

        placed_set = set(placed)
        for word in candidates:
            if word in placed_set:
                continue
            if not all(
                (word[br_col], word[bl_col]) in vp
                for bl_col, br_col, vp in constraints
            ):
                continue
            new_sqs: list = []
            dup = False
            for (TL, TR, BR, BL) in groups_above[row]:
                sq = find_square_word(
                    placed[TL[0]][TL[1]], placed[TR[0]][TR[1]],
                    word[BR[1]], word[BL[1]], word_set_4,
                )
                if sq in seen_sq or sq in new_sqs:
                    dup = True
                    break
                new_sqs.append(sq)
            if dup:
                continue
            result = backtrack(row + 1, placed + [word], seen_sq | frozenset(new_sqs))
            if result is not None:
                return result

        return None

    return backtrack(0, [], frozenset())


# ── PNG output ───────────────────────────────────────────────────────────────

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL = True
except ImportError:
    _PIL = False

_REGION_COLOR = {
    'green': '#2E7D32',
    'blue':  '#1565C0',
    'red':   '#B71C1C',
}


def region_for_groups(widths: list) -> list:
    """Return 'green', 'blue', or 'red' for each square group.

    Top-half boundaries → green, exact-middle boundary → blue,
    bottom-half boundaries → red.  For 6 rows (5 boundaries) this
    gives 6 green + 6 blue + 6 red groups.
    """
    n_bounds = len(widths) - 1
    mid      = n_bounds // 2
    max_w    = max(widths)
    offsets  = [(max_w - w) // 2 for w in widths]
    regions: list = []
    for b in range(n_bounds):
        top_gaps = set(range(offsets[b]     + 1, offsets[b]     + widths[b]))
        bot_gaps = set(range(offsets[b + 1] + 1, offsets[b + 1] + widths[b + 1]))
        n   = len(top_gaps & bot_gaps)
        reg = 'green' if b < mid else ('blue' if b == mid else 'red')
        regions.extend([reg] * n)
    return regions


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


def generate_clues(sq_words: list, include_words: Optional[dict] = None) -> dict:
    """Return {word: clue_text} for each unique word in sq_words.

    Uses user-supplied clues first, then calls Claude Haiku for the rest.
    Falls back to the word itself if the API is unavailable.
    """
    import os
    inc    = include_words or {}
    result = {}
    unique = list(dict.fromkeys(sq_words))

    need_api = []
    for w in unique:
        if w in inc and inc[w]:
            result[w] = inc[w]
        else:
            need_api.append(w)

    if not need_api:
        return result

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        for w in need_api:
            result[w] = f"({w})"
        return result

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            "Give a short, precise crossword-style clue (3–7 words) for each word below. "
            "One per line, format: WORD: clue. No extra commentary.\n\n"
            + "\n".join(need_api)
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        for line in resp.content[0].text.strip().split('\n'):
            line = line.strip()
            if ':' in line:
                w, clue = line.split(':', 1)
                w = w.strip().upper()
                if w in set(need_api):
                    result[w] = clue.strip()
    except Exception as e:
        print(f"  (Clue generation failed: {e})", file=sys.stderr)

    for w in need_api:
        if w not in result:
            result[w] = f"({w})"

    return result


def draw_image(
    widths: list,
    words: Optional[list],
    word_set_4: set,
    output_path: str,
    solved: bool = True,
    clues: Optional[dict] = None,   # {word: clue_text} — triggers clue panel
    clue_seed: int = 0,
    theme_cells: Optional[set] = None,  # {(row, col)} cells to mark with an inscribed circle
    no_rows: bool = False,              # omit row-word clues from panel
) -> None:
    if not _PIL:
        print("  Pillow not installed — skipping PNG.")
        return

    CELL    = 68
    PAD     = 36
    TITLE_H = 52
    DOT_R   = 11
    BW      = 2
    LABEL_W = 28     # left column for A–F row labels
    # clue panel constants
    INSTR_H  = 72
    CLUE_W   = 286
    CLUE_GAP = 22
    HDR_H    = 23
    LINE_H   = 18
    SEC_GAP  = 9

    max_w   = max(widths)
    n_rows  = len(widths)
    offsets = [(max_w - w) // 2 for w in widths]
    groups  = square_groups(widths)
    regions = region_for_groups(widths)

    grid_w = max_w * CELL
    grid_h = n_rows * CELL
    GX     = PAD + LABEL_W   # x-origin of the grid

    has_panel = (not solved) and bool(clues) and (words is not None)

    if has_panel:
        n_per_reg = sum(1 for r in regions if r == 'green')
        rows_h    = 0 if no_rows else (HDR_H + n_rows * LINE_H + SEC_GAP)
        clue_h    = (INSTR_H + SEC_GAP + rows_h
                     + 3 * (HDR_H + n_per_reg * LINE_H) + 2 * SEC_GAP)
        img_w     = GX + grid_w + CLUE_GAP + CLUE_W + PAD
        img_h     = PAD + TITLE_H + max(grid_h, clue_h) + PAD
    else:
        img_w = GX + grid_w + PAD
        img_h = PAD + TITLE_H + grid_h + PAD

    img  = Image.new('RGB', (img_w, img_h), '#F8F7F2')
    draw = ImageDraw.Draw(img)

    f_title    = _font(20)
    f_letter   = _font(32)
    f_dot      = _font(13)
    f_clue_hdr = _font(13)
    f_clue     = _font(12)
    f_label    = _font(14)
    f_instr    = _font(10)

    title = "INTERLOCKING SQUARES"
    draw.text((img_w // 2, PAD + TITLE_H // 2), title,
              fill='#1A1A2E', font=f_title, anchor='mm')

    grid_top = PAD + TITLE_H

    def cell_rect(row, col):
        x0 = GX + (offsets[row] + col) * CELL
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
                draw.text((cx, cy), words[i][j], fill='#1A1A2E',
                          font=f_letter, anchor='mm')

    # ── Row labels A–F ──
    for i in range(n_rows):
        lx = PAD + LABEL_W // 2
        ly = grid_top + i * CELL + CELL // 2
        draw.text((lx, ly), chr(ord('A') + i), fill='#1A1A2E', font=f_label, anchor='mm')

    # ── Inscribed circles for theme word cells ──
    if theme_cells:
        circ_r = CELL // 2 - 5
        for (ri, ci) in theme_cells:
            r = cell_rect(ri, ci)
            mx = (r[0] + r[2]) // 2
            my = (r[1] + r[3]) // 2
            draw.ellipse([mx - circ_r, my - circ_r, mx + circ_r, my + circ_r],
                         outline='#1A1A2E', width=2)

    # ── Build randomised clue lists per region ──
    region_clues: dict = {'green': [], 'blue': [], 'red': []}

    if has_panel:
        rng_c = random.Random(clue_seed)
        region_idxs: dict = {'green': [], 'blue': [], 'red': []}
        for si, reg in enumerate(regions):
            region_idxs[reg].append(si)

        for reg in ('green', 'blue', 'red'):
            cl = []
            for grp_idx in region_idxs[reg]:
                TL, TR, BR, BL = groups[grp_idx]
                sq = find_square_word(
                    words[TL[0]][TL[1]], words[TR[0]][TR[1]],
                    words[BR[0]][BR[1]], words[BL[0]][BL[1]], word_set_4,
                )
                cl.append(clues.get(sq, sq))
            rng_c.shuffle(cl)
            region_clues[reg] = cl

    # ── Interior-corner dots ──
    for si, (TL, TR, BR, BL) in enumerate(groups):
        abs_gap = offsets[TL[0]] + TL[1] + 1
        cx = GX + abs_gap * CELL
        cy = grid_top + (TL[0] + 1) * CELL

        color = '#888888' if solved else _REGION_COLOR[regions[si]]
        draw.ellipse([cx - DOT_R, cy - DOT_R, cx + DOT_R, cy + DOT_R],
                     fill=color, outline='white', width=1)

    # ── Clue panel ──
    if has_panel:
        px = GX + grid_w + CLUE_GAP
        py = grid_top

        # Instruction text (no box)
        ix = px + 10
        iy = py + 10
        ls = 15   # line spacing
        for txt, col in [
            ("Fill in rows A–F using corner clues only." if no_rows else "Fill in rows A–F. Each row is a word.", '#1A1A2E'),
            ("Green / blue / red clues go around dots of the same colour.", '#1A1A2E'),
            ("Each answer is 4 letters, winding around the dot —", '#444444'),
            ("clockwise or anticlockwise from any corner. Clues in random order.", '#444444'),
        ]:
            draw.text((ix, iy), txt, fill=col, font=f_instr, anchor='lm')
            iy += ls
        py += INSTR_H + SEC_GAP

        # ROWS section (omitted in --no-rows mode)
        if not no_rows:
            draw.rectangle([px, py, px + CLUE_W, py + HDR_H], fill='#444444')
            draw.text((px + CLUE_W // 2, py + HDR_H // 2), 'ROWS',
                      fill='white', font=f_clue_hdr, anchor='mm')
            py += HDR_H
            for i, w in enumerate(widths):
                row_label = chr(ord('A') + i)
                row_word  = words[i] if isinstance(words[i], str) else ''.join(words[i])
                clue_txt  = clues.get(row_word, f'({w})')
                line      = f"{row_label} ({w})  {clue_txt}"
                if len(line) > 42:
                    line = line[:40] + '…'
                draw.text((px + 8, py + LINE_H // 2), line,
                          fill='#1A1A2E', font=f_clue, anchor='lm')
                py += LINE_H
            py += SEC_GAP

        for reg in ('green', 'blue', 'red'):
            hdr_color = _REGION_COLOR[reg]
            # Colored header bar
            draw.rectangle([px, py, px + CLUE_W, py + HDR_H], fill=hdr_color)
            draw.text((px + CLUE_W // 2, py + HDR_H // 2), reg.upper(),
                      fill='white', font=f_clue_hdr, anchor='mm')
            py += HDR_H

            # Clue lines — randomised within region, no numbers shown
            for clue_text in region_clues[reg]:
                line = clue_text if len(clue_text) <= 42 else clue_text[:40] + '…'
                draw.text((px + 8, py + LINE_H // 2), line,
                          fill='#1A1A2E', font=f_clue, anchor='lm')
                py += LINE_H

            py += SEC_GAP

    img.save(output_path)
    print(f"  → Saved: {output_path}")


def _emit_pngs(
    widths: list, words: list, word_set_4: set, base_path: str,
    clues: Optional[dict] = None, clue_seed: int = 0,
    theme_cells: Optional[set] = None, no_rows: bool = False,
) -> None:
    from pathlib import Path as _Path
    p = _Path(base_path)
    draw_image(widths, words, word_set_4,
               str(p.with_stem(p.stem + '_solution')), solved=True,
               theme_cells=theme_cells)
    draw_image(widths, words, word_set_4,
               str(p.with_stem(p.stem + '_puzzle')), solved=False,
               clues=clues, clue_seed=clue_seed,
               theme_cells=theme_cells, no_rows=no_rows)


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
    ap.add_argument("--no-rows", action="store_true",
                    help="Puzzle image omits row-word clues (harder mode)")
    ap.add_argument(
        "--include", metavar="WORDS", default="",
        help='Semicolon-separated theme words, e.g. "LOVE; HAPPY: birthday wish; MAMA"',
    )
    ap.add_argument("--min-included", type=int, default=2,
                    help="Minimum theme words that must appear (default: 2)")
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

    include_words = _parse_include(args.include) if args.include else {}
    if include_words:
        print(f"Theme words: {', '.join(include_words)}")
        # Add include words to the word pool and augment valid squares
        for word in include_words:
            w = len(word)
            if word not in set(word_by_len.get(w, [])):
                word_by_len[w] = [word] + word_by_len.get(w, [])

    word_set_4 = set(word_by_len.get(4, []))
    valid_sq   = build_valid_squares(word_set_4)

    groups     = square_groups(widths)
    total_cells = sum(widths)
    print(f"Grid: {widths}  —  {total_cells} cells, {len(groups)} square words")
    start     = time.time()
    result    = None
    found_inc = []

    if include_words:
        # Build forced-word search plans.
        # Singles: one include word pinned to one matching-width row.
        # Pairs: two distinct include words pinned to two distinct rows.
        forceable_singles = [
            (inc_word, row_idx)
            for inc_word in include_words
            for row_idx, row_w in enumerate(widths)
            if len(inc_word) == row_w and inc_word in set(word_by_len.get(row_w, []))
        ]
        forceable_pairs = [
            {r1: w1, r2: w2}
            for i, (w1, r1) in enumerate(forceable_singles)
            for (w2, r2) in forceable_singles[i + 1:]
            if r1 != r2 and w1 != w2
        ]

        # Try pairs first — any valid solution automatically has ≥2 include words.
        # Then singles — check whether a square word supplies the second include.
        search_plan: list[tuple] = (
            [(fm, '+'.join(f"{v}@{chr(65+k)}" for k, v in sorted(fm.items())))
             for fm in forceable_pairs]
            + [({r: w}, f"{w}@{chr(65+r)}") for w, r in forceable_singles]
        )

        n_comb       = max(1, len(search_plan))
        tries_each   = max(args.tries, 20)
        time_each    = max(0.5, args.time_limit / (n_comb * tries_each))

        for forced_map, label in search_plan:
            print(f"\n  Forcing {label} …", end="", flush=True)
            for attempt in range(tries_each):
                if time.time() - start > args.time_limit:
                    break
                seed      = args.seed + attempt
                candidate = solve_forced(
                    widths, word_by_len, valid_sq, word_set_4, forced_map,
                    seed=seed, time_limit=time_each,
                    include_words=include_words,
                )
                if candidate is None:
                    print(".", end="", flush=True)
                    continue
                fi = _found_include(widths, candidate, word_set_4, include_words)
                if len(fi) >= args.min_included:
                    result    = candidate
                    found_inc = fi
                    print(f"  → found (seed {seed}, {time.time()-start:.2f}s)")
                    break
                print("x", end="", flush=True)
            if result:
                break

    # Fallback (or no include words): regular random search.
    if not result:
        print(f"\n  {'Fallback: ' if include_words else ''}random search …",
              end="", flush=True)
        for attempt in range(args.tries):
            if time.time() - start > args.time_limit:
                break
            seed      = args.seed + attempt
            candidate = solve(
                widths, word_by_len, valid_sq, word_set_4,
                seed=seed,
                time_limit=args.time_limit / args.tries,
                include_words=include_words,
            )
            if candidate is None:
                print(".", end="", flush=True)
                continue
            if include_words:
                fi = _found_include(widths, candidate, word_set_4, include_words)
                if len(fi) < args.min_included:
                    print("x", end="", flush=True)
                    continue
                found_inc = fi
            result = candidate
            print(f"  → found (seed {seed}, {time.time()-start:.2f}s)")
            break

    if not result:
        print("\nNo solution found — try a different --seed, more --tries, or looser --min-score.")
        sys.exit(1)

    if found_inc:
        print(f"\n  Theme words included: {', '.join(found_inc)}")
    display(widths, result, word_set_4)
    if args.png:
        # Compute all square words for clue generation
        sq_words = [
            find_square_word(
                result[TL[0]][TL[1]], result[TR[0]][TR[1]],
                result[BR[0]][BR[1]], result[BL[0]][BL[1]], word_set_4,
            )
            for (TL, TR, BR, BL) in square_groups(widths)
        ]
        import os
        if os.environ.get('ANTHROPIC_API_KEY'):
            print("  Generating clues …", end="", flush=True)
            words_for_clues = sq_words if args.no_rows else list(result) + sq_words
            clues = generate_clues(words_for_clues, include_words)
            print(" done")
        else:
            clues = None
        # Collect cells belonging to theme words (rows + square corners)
        theme_cells: set = set()
        if include_words:
            inc_set = set(include_words)
            for i, row_word in enumerate(result):
                if row_word in inc_set:
                    for j in range(widths[i]):
                        theme_cells.add((i, j))
            for sq_w, (TL, TR, BR, BL) in zip(sq_words, square_groups(widths)):
                if sq_w in inc_set:
                    theme_cells.update([(TL[0], TL[1]), (TR[0], TR[1]),
                                        (BR[0], BR[1]), (BL[0], BL[1])])
        _emit_pngs(widths, result, word_set_4, args.png,
                   clues=clues, clue_seed=args.seed,
                   theme_cells=theme_cells or None, no_rows=args.no_rows)


if __name__ == "__main__":
    main()
