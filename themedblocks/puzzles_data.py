"""
Saved Themed Blocks puzzles — public examples.

Edit the clues dict freely — re-run to regenerate images.

To re-render:
    python3 themedblocks/puzzles_data.py heart_love
"""

from __future__ import annotations

PUZZLES: dict[str, dict] = {

    # ── heart_love  (heart 6×7, public example) ───────────────────────────────
    "heart_love": {
        # ── editable fields ───────────────────────────────────────────────────
        "title":  None,
        "credit": "Anant Jhingran and Claude",
        "thanks": None,
        # ─────────────────────────────────────────────────────────────────────
        "shape": "heart_6x7",
        "seed":  42,
        "words": {
            "1A": "ACE",
            "2A": "LOVE",
            "3A": "IKNEW",
            "4A": "GREET",
            "5A": "ESTES",
            "6A": "STARRY",
            "1D": "AGES",
            "2D": "LIST",
            "3D": "OKRA",
            "4D": "CNET",
            "5D": "VEER",
            "6D": "EWER",
            "7D": "ETSY",
        },
        "clues": {
            "1A": "serve that wins the point outright",
            "2A": "deep affection",
            "3A": "phrase of sudden recognition",
            "4A": "welcome warmly",
            "5A": "town in Colorado famous for its hot springs",
            "6A": "filled with stars",
            "1D": "periods of time",
            "2D": "inventory",
            "3D": "pod vegetable used in gumbo",
            "4D": "tech news site",
            "5D": "swing back and forth",
            "6D": "water pitcher with a wide spout",
            "7D": "online craft marketplace",
        },
    },

}


# ── Rendering ──────────────────────────────────────────────────────────────────

def render_puzzle(key: str, cell_px: int = 72) -> None:
    """Re-render blank + answer PNGs into examples/."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).parent))
    from themedblocks import SHAPES, build_slots_and_crossings, render_png

    p      = PUZZLES[key]
    shape  = SHAPES[p["shape"]]
    rows, cols = shape["rows"], shape["cols"]
    skip   = shape["skip"]
    color  = shape.get("color", (220, 80, 100))
    hl_skip  = shape.get("highlight_skip", set())
    hl_color = shape.get("highlight_color", None)

    slots, crossings = build_slots_and_crossings(rows, cols, skip)
    assignment: dict = {}
    for slot in slots:
        word = p["words"].get(f"{slot.index + 1}{slot.direction}")
        if word:
            assignment[slot] = word

    out = Path(__file__).parent / "examples"
    out.mkdir(exist_ok=True)

    kwargs = dict(clues=p.get("clues", {}), color=color,
                  highlight_skip=hl_skip, highlight_color=hl_color,
                  cell_px=cell_px,
                  title=p.get("title"), credit=p.get("credit"), thanks=p.get("thanks"))

    render_png(rows, cols, skip, assignment, slots, crossings,
               str(out / f"{key}.png"), solved=False, **kwargs)
    print(f"Blank  → {out / f'{key}.png'}")

    render_png(rows, cols, skip, assignment, slots, crossings,
               str(out / f"{key}_answer.png"), solved=True, **kwargs)
    print(f"Answer → {out / f'{key}_answer.png'}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(f"Usage: python3 themedblocks/puzzles_data.py <key>")
        print(f"Keys: {', '.join(PUZZLES)}")
        sys.exit(1)
    render_puzzle(sys.argv[1])
