"""
Saved cryptic crossword puzzles — Anant + Claude.

Each entry stores the complete filled grid and all locked clues.
Nothing is personal; this file is committed to the public repo.

To re-render a puzzle's images:
    python3 cryptic/puzzles_data.py filled_401v2

That produces:
    cryptic/images/filled_401v2.png          (answer key)
    cryptic/images/puzzle_401v2_blank.png    (blank solver grid)
"""

from __future__ import annotations

PUZZLES: dict[str, dict] = {

    # ── filled_401v2  (15×15 British cryptic) ─────────────────────────────────
    # Worked through clues together — Anant + Claude
    # '.' = black square
    "filled_401v2": {
        "size": 15,
        "grid": [
            "GASPRICES.TASED",   # row  1
            "U.T.A.A.I.E.E.U",   # row  2
            "STRAITS.TERRACE",   # row  3
            "T.A.S.E...M.S.L",   # row  4
            "SPIRITS.TRIVIAL",   # row  5
            "..N.N.T.E.T.D.I",   # row  6
            "SOS.SQUANDERERS",   # row  7
            "I.....D.N.....T",   # row  8
            "NECESSITIES.SIS",   # row  9
            "K.Y.W.E.S.E.E..",   # row 10
            "BEANIES.SEAHAWK",   # row 11
            "A.N.V...H.L.G.A",   # row 12
            "TRICEPS.OTOLOGY",   # row 13
            "H.D.T.O.E.F.E.O",   # row 14
            "STEMS.BUSHFIRES",   # row 15
        ],
        "clues": {
            # ── ACROSS ────────────────────────────────────────────────────────
            "1A":  "Radon, say, costs at the pump (3,6)",
            "6A":  "Stunned by rotten dates (5)",
            "9A":  "Tight spots between lands (7)",
            "10A": "Caterer stumbles on the patio (7)",
            "11A": "Drunk, I strip somewhat early for shots (7)",
            "12A": "Easy six in a test (7)",
            "13A": "Distress call either way (3)",
            "14A": "Short nerds and squares dancing away their fortune? (11)",
            "15A": "Boston, Plymouth etc. welcome English ship as needed? (11)",
            "19A": "Spy sibling (3)",
            "20A": "Tropical bird in workers' caps? (7)",
            "21A": "Footballer is militant at sea (7)",
            "23A": "Muscle caught in gastric Epsom treatment (7)",
            "25A": "Study sounds always true, but not true (7)",
            "26A": "Stalks discovered in ecosystem survey (5)",
            "27A": "Scorching, furbishes recklessly (9)",
            # ── DOWN ──────────────────────────────────────────────────────────
            "1D":  "Bursts found in august surroundings (5)",
            "2D":  "Son exercises too hard? (7)",
            "3D":  "Naked praising, second to Sultanas (7)",
            "4D":  "Mystery investigations in Harvard Business Review? (11)",
            "5D":  "Take the chair? (3)",
            "6D":  "Pest destroys emitter (7)",
            "7D":  "Main team's resort (7)",
            "8D":  "",   # DUELLISTS — WIP
            "12D": "",   # TENNISSHOES — WIP
            "13D": "",   # SINKBATHS — WIP
            "16D": "",   # CYANIDE — WIP
            "17D": "",   # SWIVETS — WIP
            "18D": "",   # SEALOFF — WIP
            "19D": "",   # SEAGOER — WIP
            "22D": "",   # KAYOS — WIP
            "24D": "",   # SOB — WIP
        },
    },

}


# ── Rendering ──────────────────────────────────────────────────────────────────

def render_puzzle(key: str, cell_px: int = 64) -> None:
    """Re-render filled + blank PNGs for a saved puzzle."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from filler import Slot, extract_slots, render_filled_png, render_puzzle_png

    p = PUZZLES[key]
    grid: list[str] = p["grid"]
    n: int = p["size"]
    clues: dict[str, str] = {k: v for k, v in p["clues"].items() if v}

    # Build blocked set and slot assignment from the grid
    blocked: set[tuple[int, int]] = set()
    for r, row in enumerate(grid, 1):
        for c, ch in enumerate(row, 1):
            if ch == ".":
                blocked.add((r, c))

    slots = extract_slots(blocked, n, min_len=3)
    assignment: dict[Slot, str] = {}
    for slot in slots:
        word = "".join(grid[r - 1][c - 1] for r, c in slot.cells)
        if "." not in word:
            assignment[slot] = word

    out = Path(__file__).parent / "images"
    out.mkdir(exist_ok=True)

    filled = str(out / f"{key}.png")
    render_filled_png(blocked, n, assignment, filled, cell_px, 3)
    print(f"Filled  → {filled}")

    blank = str(out / f"{key}_blank.png")
    render_puzzle_png(blocked, n, assignment, blank, clues, cell_px, 3)
    print(f"Blank   → {blank}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(f"Usage: python3 puzzles_data.py <key>")
        print(f"Keys: {', '.join(PUZZLES)}")
        sys.exit(1)
    render_puzzle(sys.argv[1])
