#!/usr/bin/env python3
"""British-style crossword grid generator.

Strategy
--------
1. Start with "base" black squares at every (even_row, even_col) intersection.
   For an 11×11 grid this puts isolated squares at (2,2), (2,4), …, (10,10).
2. Grow them by adding "connectors" — cells between adjacent base squares —
   with rotational symmetry (90° or 180°).
   Shapes available: horizontal bar, vertical bar, L, + (cross).
3. Every candidate extension is rejected if it creates a word shorter than
   `min_word` or disconnects the white cells.
"""

import argparse
import random
import sys
from collections import deque
from pathlib import Path
from typing import Optional

Cell = tuple[int, int]


# ── Symmetry ──────────────────────────────────────────────────────────────

def _rot90(r: int, c: int, n: int) -> Cell:
    return (c, n + 1 - r)


def orbit_90(r: int, c: int, n: int) -> set[Cell]:
    cells, cur = set(), (r, c)
    for _ in range(4):
        cells.add(cur)
        cur = _rot90(cur[0], cur[1], n)
    return cells


def orbit_180(r: int, c: int, n: int) -> set[Cell]:
    return {(r, c), (n + 1 - r, n + 1 - c)}


# ── Core grid helpers ─────────────────────────────────────────────────────

def base_grid(n: int) -> set[Cell]:
    """Black squares at every (even_row, even_col) — 1-indexed."""
    return {(r, c) for r in range(2, n + 1, 2) for c in range(2, n + 1, 2)}


def _word_lengths(blocked: set[Cell], n: int) -> list[int]:
    lengths = []
    for r in range(1, n + 1):
        run = 0
        for c in range(1, n + 2):
            if c <= n and (r, c) not in blocked:
                run += 1
            else:
                if run:
                    lengths.append(run)
                run = 0
    for c in range(1, n + 1):
        run = 0
        for r in range(1, n + 2):
            if r <= n and (r, c) not in blocked:
                run += 1
            else:
                if run:
                    lengths.append(run)
                run = 0
    return lengths


def _connected(blocked: set[Cell], n: int) -> bool:
    white = [(r, c) for r in range(1, n + 1) for c in range(1, n + 1)
             if (r, c) not in blocked]
    if not white:
        return False
    white_set = set(white)
    visited = {white[0]}
    q = deque([white[0]])
    while q:
        r, c = q.popleft()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nb = (r + dr, c + dc)
            if nb not in visited and nb in white_set:
                visited.add(nb)
                q.append(nb)
    return len(visited) == len(white)


def _no_consecutive_unchecked(blocked: set[Cell], n: int, min_len: int) -> bool:
    """In every word of length ≥ min_len, no two adjacent cells may both be unchecked.

    A cell is unchecked if the perpendicular run through it is < min_len
    (i.e. the cell is only part of one real word).
    """
    # Build the set of cells that belong to a real word in each direction.
    in_across: set[Cell] = set()
    in_down: set[Cell] = set()

    for r in range(1, n + 1):
        run: list[Cell] = []
        for c in range(1, n + 2):
            if c <= n and (r, c) not in blocked:
                run.append((r, c))
            else:
                if len(run) >= min_len:
                    in_across.update(run)
                run = []

    for c in range(1, n + 1):
        run = []
        for r in range(1, n + 2):
            if r <= n and (r, c) not in blocked:
                run.append((r, c))
            else:
                if len(run) >= min_len:
                    in_down.update(run)
                run = []

    # Check each across word.
    for r in range(1, n + 1):
        run = []
        for c in range(1, n + 2):
            if c <= n and (r, c) not in blocked:
                run.append((r, c))
            else:
                if len(run) >= min_len:
                    for i in range(len(run) - 1):
                        if run[i] not in in_down and run[i + 1] not in in_down:
                            return False
                run = []

    # Check each down word.
    for c in range(1, n + 1):
        run = []
        for r in range(1, n + 2):
            if r <= n and (r, c) not in blocked:
                run.append((r, c))
            else:
                if len(run) >= min_len:
                    for i in range(len(run) - 1):
                        if run[i] not in in_across and run[i + 1] not in in_across:
                            return False
                run = []

    return True


def is_valid(blocked: set[Cell], n: int, min_len: int = 3) -> bool:
    # Runs of 1 are unchecked cells (OK in British style); reject only 2 ≤ len < min_len.
    if any(1 < w < min_len for w in _word_lengths(blocked, n)):
        return False
    if not _connected(blocked, n):
        return False
    return _no_consecutive_unchecked(blocked, n, min_len)


def add_symmetrically(blocked: set[Cell], cells: set[Cell], n: int,
                       sym: str) -> set[Cell]:
    new = set(blocked)
    fn = orbit_90 if sym == "90" else orbit_180
    for r, c in cells:
        new |= fn(r, c, n)
    return new


# ── Extension shapes (all relative to a base cell) ────────────────────────

def h_bar(r: int, c: int) -> set[Cell]:
    """Connect (r,c) rightward to (r,c+2)."""
    return {(r, c + 1)}


def v_bar(r: int, c: int) -> set[Cell]:
    """Connect (r,c) downward to (r+2,c)."""
    return {(r + 1, c)}


def l_shape(r: int, c: int, dirs: str) -> set[Cell]:
    """L from base cell; dirs is any subset of 'r','d','l','u'."""
    _off = {"r": (0, 1), "d": (1, 0), "l": (0, -1), "u": (-1, 0)}
    return {(r + _off[d][0], c + _off[d][1]) for d in dirs}


def plus_shape(r: int, c: int, n: int) -> set[Cell]:
    """All 4 connectors around a base cell."""
    result = set()
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = r + dr, c + dc
        if 1 <= nr <= n and 1 <= nc <= n:
            result.add((nr, nc))
    return result


# ── Generator ─────────────────────────────────────────────────────────────

_STRATEGIES = ("h_bar", "v_bar", "l_rd", "l_ru", "l_ld", "l_lu", "plus")


def generate(
    n: int = 11,
    seed: Optional[int] = None,
    n_ext: int = 6,
    sym: str = "90",
    min_len: int = 3,
) -> tuple[set[Cell], int]:
    """Return (blocked_set, extensions_applied)."""
    rng = random.Random(seed)
    blocked = base_grid(n)
    applied = 0

    for _ in range(n_ext * 60):
        if applied >= n_ext:
            break

        strategy = rng.choice(_STRATEGIES)
        r = rng.choice(range(2, n + 1, 2))
        c = rng.choice(range(2, n + 1, 2))

        if strategy == "h_bar":
            if c >= n:
                continue
            candidate = h_bar(r, c)
        elif strategy == "v_bar":
            if r >= n:
                continue
            candidate = v_bar(r, c)
        elif strategy == "l_rd":
            if r >= n or c >= n:
                continue
            candidate = l_shape(r, c, "rd")
        elif strategy == "l_ru":
            if r <= 1 or c >= n:
                continue
            candidate = l_shape(r, c, "ru")
        elif strategy == "l_ld":
            if r >= n or c <= 1:
                continue
            candidate = l_shape(r, c, "ld")
        elif strategy == "l_lu":
            if r <= 1 or c <= 1:
                continue
            candidate = l_shape(r, c, "lu")
        elif strategy == "plus":
            candidate = plus_shape(r, c, n)
        else:
            continue

        if candidate.issubset(blocked):
            continue

        new_blocked = add_symmetrically(blocked, candidate, n, sym)
        if is_valid(new_blocked, n, min_len):
            blocked = new_blocked
            applied += 1

    return blocked, applied


# ── Improvement pass ──────────────────────────────────────────────────────

def _short_word_count(blocked: set[Cell], n: int, min_len: int, target: int) -> int:
    """Count real words (≥ min_len) that are shorter than target."""
    return sum(1 for w in _word_lengths(blocked, n) if min_len <= w < target)


def improve_grid(
    blocked: set[Cell],
    n: int,
    sym: str = "90",
    min_len: int = 3,
    target_word: int = 5,
    min_density: float = 0.18,
    max_short_words: int = 4,
) -> tuple[set[Cell], int]:
    """Greedily remove orbits of black squares to reduce short words.

    At each iteration try every removable orbit and apply the one that
    reduces the count of words shorter than `target_word` the most.
    Stops when: count of short words ≤ max_short_words, density would
    drop below min_density, or no removal helps.
    Returns (new_blocked, n_removed).
    """
    fn = orbit_90 if sym == "90" else orbit_180
    current = set(blocked)
    total_cells = n * n

    while True:
        current_score = _short_word_count(current, n, min_len, target_word)
        if current_score <= max_short_words:
            break

        best_blocked: Optional[set[Cell]] = None
        best_gain = 0

        seen: set[frozenset] = set()
        for r, c in sorted(current):
            orb = frozenset(fn(r, c, n))
            if orb in seen or not orb.issubset(current):
                continue
            seen.add(orb)

            candidate = current - orb
            if len(candidate) / total_cells < min_density:
                continue
            if not is_valid(candidate, n, min_len):
                continue

            gain = current_score - _short_word_count(candidate, n, min_len, target_word)
            if gain > best_gain:
                best_gain = gain
                best_blocked = candidate

        if best_blocked is None:
            break
        current = best_blocked

    return current, len(blocked) - len(current)


# ── Rendering ─────────────────────────────────────────────────────────────

def _number_cells(blocked: set[Cell], n: int, min_len: int) -> dict[Cell, int]:
    numbers: dict[Cell, int] = {}
    num = 1
    for r in range(1, n + 1):
        for c in range(1, n + 1):
            if (r, c) in blocked:
                continue
            left_blocked = c == 1 or (r, c - 1) in blocked
            right_open = c < n and (r, c + 1) not in blocked
            top_blocked = r == 1 or (r - 1, c) in blocked
            down_open = r < n and (r + 1, c) not in blocked
            starts_across = left_blocked and right_open
            starts_down = top_blocked and down_open
            if starts_across or starts_down:
                numbers[(r, c)] = num
                num += 1
    return numbers


def render(blocked: set[Cell], n: int, show_numbers: bool = False,
           min_len: int = 3) -> str:
    numbers = _number_cells(blocked, n, min_len) if show_numbers else {}
    lines = []
    for r in range(1, n + 1):
        row = []
        for c in range(1, n + 1):
            if (r, c) in blocked:
                row.append("██")
            elif show_numbers and (r, c) in numbers:
                row.append(f"{numbers[(r, c)]:2d}")
            else:
                row.append(" ·")
        lines.append("".join(row))
    return "\n".join(lines)


def stats(blocked: set[Cell], n: int) -> str:
    total = n * n
    pct = 100 * len(blocked) // total

    words_a: list[int] = []
    for r in range(1, n + 1):
        run = 0
        for c in range(1, n + 2):
            if c <= n and (r, c) not in blocked:
                run += 1
            else:
                if run >= 1:
                    words_a.append(run)
                run = 0
    words_a = [w for w in words_a if w >= 3]

    words_d: list[int] = []
    for c in range(1, n + 1):
        run = 0
        for r in range(1, n + 2):
            if r <= n and (r, c) not in blocked:
                run += 1
            else:
                if run >= 1:
                    words_d.append(run)
                run = 0
    words_d = [w for w in words_d if w >= 3]

    all_words = words_a + words_d
    dist: dict[int, int] = {}
    for w in all_words:
        dist[w] = dist.get(w, 0) + 1
    dist_str = "  ".join(f"len{k}:{v}" for k, v in sorted(dist.items()))

    return (
        f"Size {n}×{n}  black={len(blocked)}/{total} ({pct}%)  "
        f"across={len(words_a)}  down={len(words_d)}\n"
        f"Word-length distribution: {dist_str}"
    )


# ── PNG rendering ─────────────────────────────────────────────────────────

def render_png(
    blocked: set[Cell],
    n: int,
    path: str,
    cell_px: int = 52,
    border_px: int = 3,
    show_numbers: bool = False,
    min_len: int = 3,
) -> None:
    """Render the grid as a clean PNG file."""
    from PIL import Image, ImageDraw, ImageFont

    BLACK      = (30, 30, 30)
    WHITE      = (255, 255, 255)
    GRID_LINE  = (160, 160, 160)
    NUM_COLOR  = (50, 50, 50)

    outer = border_px          # border around the whole grid
    inner = 1                  # thin line between white cells
    size_px = outer * 2 + n * cell_px + (n - 1) * inner
    img = Image.new("RGB", (size_px, size_px), WHITE)
    draw = ImageDraw.Draw(img)

    # Fill the entire border zone black
    draw.rectangle([0, 0, size_px - 1, size_px - 1], fill=BLACK)
    # White canvas inside border
    draw.rectangle(
        [outer, outer, size_px - outer - 1, size_px - outer - 1],
        fill=WHITE,
    )

    def cell_rect(r: int, c: int) -> tuple[int, int, int, int]:
        x0 = outer + (c - 1) * (cell_px + inner)
        y0 = outer + (r - 1) * (cell_px + inner)
        return x0, y0, x0 + cell_px - 1, y0 + cell_px - 1

    # Draw black cells
    for r in range(1, n + 1):
        for c in range(1, n + 1):
            if (r, c) in blocked:
                draw.rectangle(cell_rect(r, c), fill=BLACK)

    # Draw grid lines between white cells only (skip if neighbour is black)
    for r in range(1, n + 1):
        for c in range(1, n + 1):
            if (r, c) in blocked:
                continue
            x0, y0, x1, y1 = cell_rect(r, c)
            # right border
            if c < n and (r, c + 1) not in blocked:
                draw.line([(x1 + 1, y0), (x1 + 1, y1)], fill=GRID_LINE, width=inner)
            # bottom border
            if r < n and (r + 1, c) not in blocked:
                draw.line([(x0, y1 + 1), (x1, y1 + 1)], fill=GRID_LINE, width=inner)

    # Word numbers
    if show_numbers:
        numbers = _number_cells(blocked, n, min_len)
        # Try to load a small system font; fall back to default if unavailable
        font = None
        for candidate in [
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]:
            if Path(candidate).exists():
                try:
                    font = ImageFont.truetype(candidate, size=max(9, cell_px // 5))
                    break
                except Exception:
                    pass
        if font is None:
            font = ImageFont.load_default()

        for (r, c), num in numbers.items():
            x0, y0, _, _ = cell_rect(r, c)
            draw.text((x0 + 3, y0 + 2), str(num), fill=NUM_COLOR, font=font)

    img.save(path)


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="British-style crossword grid generator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-n", "--size", type=int, default=11, metavar="N",
                        help="Grid size (must be odd)")
    parser.add_argument("-s", "--seed", type=int, default=None,
                        help="Random seed (random if omitted)")
    parser.add_argument("-e", "--extensions", type=int, default=6,
                        help="Extension groups to apply")
    parser.add_argument("--sym", choices=["90", "180"], default="90",
                        help="Rotational symmetry")
    parser.add_argument("--min-word", type=int, default=3,
                        help="Minimum word length allowed")
    parser.add_argument("--base", action="store_true",
                        help="Show the base grid before extensions")
    parser.add_argument("--numbers", action="store_true",
                        help="Show word-start numbers in the grid")
    parser.add_argument("--count", type=int, default=1,
                        help="Number of grids to generate")
    parser.add_argument("--png", metavar="FILE",
                        help="Save grid as PNG (use {seed} as placeholder when --count > 1)")
    parser.add_argument("--cell-px", type=int, default=52,
                        help="Cell size in pixels for PNG output")
    parser.add_argument("--improve", action="store_true",
                        help="After generating, greedily remove black squares to lengthen short words")
    parser.add_argument("--target-word", type=int, default=5,
                        help="Improvement target: try to eliminate words shorter than this")
    parser.add_argument("--min-density", type=float, default=0.18,
                        help="Minimum black-square density during improvement (0–1)")
    parser.add_argument("--max-short", type=int, default=4,
                        help="Stop improving when short-word count drops to this")
    args = parser.parse_args()

    if args.size % 2 == 0:
        parser.error("Grid size must be odd")

    n = args.size

    if args.base:
        b = base_grid(n)
        print("=== Base grid (no extensions) ===")
        print(render(b, n))
        print()
        print(stats(b, n))
        print()

    base_seed = args.seed if args.seed is not None else random.randint(0, 999_999)
    for i in range(args.count):
        seed = base_seed + i
        blocked, applied = generate(n, seed, args.extensions, args.sym, args.min_word)

        if args.improve:
            blocked, n_removed = improve_grid(blocked, n, args.sym, args.min_word,
                                              args.target_word, args.min_density,
                                              args.max_short)
            improve_note = f"  improved: -{n_removed} black squares"
        else:
            improve_note = ""

        label = f"Grid {i + 1}/{args.count}" if args.count > 1 else "Generated grid"
        print(f"=== {label}  seed={seed}  ({applied}/{args.extensions} extensions){improve_note} ===")
        print(render(blocked, n, args.numbers, args.min_word))
        print()
        print(stats(blocked, n))

        if args.png:
            png_path = args.png.replace("{seed}", str(seed))
            render_png(blocked, n, png_path, args.cell_px, show_numbers=args.numbers,
                       min_len=args.min_word)
            print(f"PNG saved → {png_path}")

        if i < args.count - 1:
            print()


if __name__ == "__main__":
    main()
