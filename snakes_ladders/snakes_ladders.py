#!/usr/bin/env python3
"""
snakes_ladders.py — Snakes & Ladders word puzzle builder.

Inspired by Eric Berlin's Jelly Roll puzzle (ericberlin.com).

Two vertical LADDERS, each a sequence of stacked words.
SNAKES coil around the two ladders.  Each snake is a sequence of
alternating CHUNKS — one chunk from L1, the next from L2, etc. (or
starting with L2).  Each chunk is a contiguous run of positions from
that ladder, in either direction (forward or backward).  Together the
chunks spell a valid word; together all snakes cover every position on
both ladders exactly once.

The chunk directions and sizes are completely flexible:
  L1[1,2] + L2[2,1]  →  4-letter snake (L1 forward, L2 backward)
  L1[1]   + L2[1,2,3]→  4-letter snake (L1 1-letter, L2 3-letter fwd)
  L2[3,2,1] + L1[1]  →  4-letter snake (L2 backward, L1 1-letter)

Usage:
  python snakes_ladders.py check "HITCH SENATE BOGUS" "ABATE EMIR EARNEST"
  python snakes_ladders.py generate --length 15 --seed 42 --min-score 60
  python snakes_ladders.py verify "HITCH SENATE BOGUS" "ABATE EMIR EARNEST" \\
                                  "HABITAT CHEESE MINARET EARBONE GUSTS"
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

WORDLIST_PATH = Path(__file__).parent.parent / "wordlist.dict"


# ── Wordlist ──────────────────────────────────────────────────────────────────

def load_wordlist(path: Path, min_score: int = 50) -> dict[str, int]:
    words: dict[str, int] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or ";" not in line:
                continue
            word, score_str = line.rsplit(";", 1)
            word = word.upper()
            try:
                score = int(score_str)
            except ValueError:
                continue
            if score >= min_score and word.isalpha():
                words[word] = score
    return words


def _build_next_letters(word_scores: dict[str, int], max_len: int) -> dict[str, set[str]]:
    """prefix → set of valid next letters ('' = valid first letters)."""
    nxt: dict[str, set[str]] = defaultdict(set)
    for word in word_scores:
        if len(word) <= max_len:
            for i in range(len(word)):
                nxt[word[:i]].add(word[i])
    return nxt


# ── Snake representation ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class Chunk:
    """One contiguous run of letters from a single ladder."""
    source: str    # 'L1' or 'L2'
    start: int     # first position consumed (0-based index into the ladder)
    length: int    # number of positions consumed
    forward: bool  # True → start, start+1, …; False → start, start-1, …

    def positions(self) -> list[int]:
        step = 1 if self.forward else -1
        return list(range(self.start, self.start + step * self.length, step))

    def letters(self, l1: list[str], l2: list[str]) -> str:
        src = l1 if self.source == 'L1' else l2
        return ''.join(src[p] for p in self.positions())


@dataclass(frozen=True)
class Snake:
    """A complete snake: alternating chunks that spell a word."""
    chunks: tuple[Chunk, ...]
    word: str

    def l1_positions(self) -> list[int]:
        return [p for c in self.chunks if c.source == 'L1' for p in c.positions()]

    def l2_positions(self) -> list[int]:
        return [p for c in self.chunks if c.source == 'L2' for p in c.positions()]


# ── Core search: find snakes for fixed ladders ────────────────────────────────

def find_snakes(
    l1: list[str],
    l2: list[str],
    l1_avail: frozenset[int],
    l2_avail: frozenset[int],
    word_scores: dict[str, int],
    snake_next: dict[str, set[str]],
    min_len: int,
    max_len: int,
    anchor_src: str,   # 'L1' or 'L2' — which ladder to anchor on
    anchor_pos: int,   # position that MUST be covered by this snake
    rng: random.Random,
    deadline: float,
):
    """
    Generator: yields Snake objects that include anchor_pos in anchor_src.

    A snake is built letter by letter.  At each step we either:
      (a) switch to the other ladder (tried first — encourages interleaving), or
      (b) continue on the current ladder one step in the same direction.

    Letter-indexed pruning: only positions whose letter extends the current
    word prefix are explored at each switch.
    """

    def rec(
        prefix: str,
        cur_src: str,
        cur_pos: int,
        cur_dir: int,
        cur_src_avail: frozenset[int],
        oth_src: str,
        oth_avail: frozenset[int],
        chunks_so_far: list[Chunk],
        chunk_start: int,
        chunk_len: int,
    ):
        if time.time() > deadline:
            return

        if len(prefix) >= min_len and prefix in word_scores:
            l1_in = any(c.source == 'L1' for c in chunks_so_far)
            l2_in = any(c.source == 'L2' for c in chunks_so_far)
            if l1_in and l2_in:
                yield Snake(tuple(chunks_so_far), prefix)

        if len(prefix) >= max_len:
            return

        cur_chars = l1 if cur_src == 'L1' else l2
        oth_chars = l2 if cur_src == 'L1' else l1

        valid_next = snake_next.get(prefix, set())
        if not valid_next:
            return

        # Option B first: switch to other ladder (encourages interleaving)
        oth_positions = list(oth_avail)
        rng.shuffle(oth_positions)
        oth_by_letter: dict[str, list[int]] = defaultdict(list)
        for p in oth_positions:
            oth_by_letter[oth_chars[p]].append(p)

        for c in valid_next:
            for p in oth_by_letter.get(c, []):
                for d in (1, -1):
                    new_chunk = Chunk(oth_src, p, 1, d > 0)
                    yield from rec(
                        prefix + c,
                        oth_src, p, d,
                        oth_avail - {p},
                        cur_src, cur_src_avail,
                        chunks_so_far + [new_chunk],
                        p, 1,
                    )

        # Option A second: continue on current ladder
        next_pos = cur_pos + cur_dir
        if next_pos in cur_src_avail:
            c = cur_chars[next_pos]
            if c in valid_next:
                new_chunk = Chunk(cur_src, chunk_start,
                                  chunk_len + 1, cur_dir > 0)
                yield from rec(
                    prefix + c,
                    cur_src, next_pos, cur_dir,
                    cur_src_avail - {next_pos},
                    oth_src, oth_avail,
                    chunks_so_far[:-1] + [new_chunk],
                    chunk_start, chunk_len + 1,
                )

    anchor_chars = l1 if anchor_src == 'L1' else l2
    oth_src = 'L2' if anchor_src == 'L1' else 'L1'
    anchor_avail = l1_avail if anchor_src == 'L1' else l2_avail
    oth_avail = l2_avail if anchor_src == 'L1' else l1_avail

    c0 = anchor_chars[anchor_pos]
    if c0 in snake_next.get('', set()):
        for d in (1, -1):
            yield from rec(
                c0,
                anchor_src, anchor_pos, d,
                anchor_avail - {anchor_pos},
                oth_src, oth_avail,
                [Chunk(anchor_src, anchor_pos, 1, d > 0)],
                anchor_pos, 1,
            )


# ── Puzzle checker ────────────────────────────────────────────────────────────

def check_puzzle(
    l1_words: list[str],
    l2_words: list[str],
    word_scores: dict[str, int],
    min_snake: int = 3,
    max_snake: int = 12,
    time_limit: float = 30.0,
) -> list[Snake] | None:
    """
    Given ladder words, find snakes that cover every position exactly once.
    Uses backtracking with letter-indexed pruning.
    """
    l1 = list(''.join(l1_words))
    l2 = list(''.join(l2_words))
    n = len(l1)
    if len(l2) != n:
        print(f"Error: L1={len(l1)} letters, L2={len(l2)} — must match.", file=sys.stderr)
        return None

    print(f"Building prefix index … ", end="", flush=True)
    snake_next = _build_next_letters(word_scores, max_snake)
    print("done")

    rng = random.Random(0)
    deadline = time.time() + time_limit

    def solve(
        l1_avail: frozenset[int],
        l2_avail: frozenset[int],
        committed: list[Snake],
    ) -> list[Snake] | None:
        if time.time() > deadline:
            return None
        if not l1_avail and not l2_avail:
            return committed

        # Anchor: smallest uncovered L1 position (or L2 if L1 exhausted)
        if l1_avail:
            anchor_src, anchor_pos = 'L1', min(l1_avail)
        else:
            anchor_src, anchor_pos = 'L2', min(l2_avail)

        tried = 0
        for snake in find_snakes(
            l1, l2, l1_avail, l2_avail,
            word_scores, snake_next,
            min_snake, max_snake,
            anchor_src, anchor_pos,
            rng, deadline,
        ):
            tried += 1
            if tried > 50:
                break
            new_l1 = l1_avail - frozenset(snake.l1_positions())
            new_l2 = l2_avail - frozenset(snake.l2_positions())
            result = solve(new_l1, new_l2, committed + [snake])
            if result is not None:
                return result

        return None

    return solve(frozenset(range(n)), frozenset(range(n)), [])


# ── Generator ─────────────────────────────────────────────────────────────────

def generate_puzzle(
    word_scores: dict[str, int],
    target_len: int = 15,
    min_ladder_word: int = 3,
    max_ladder_word: int = 7,
    min_snake: int = 3,
    max_snake: int = 10,
    max_l1_trials: int = 50,
    time_limit: float = 120.0,
    seed: int = 42,
) -> tuple[list[str], list[str], list[Snake]] | None:
    rng = random.Random(seed)
    deadline = time.time() + time_limit

    words_by_len: dict[int, list[str]] = defaultdict(list)
    for word in word_scores:
        if min_ladder_word <= len(word) <= max_ladder_word:
            words_by_len[len(word)].append(word)

    def random_seq(target: int) -> list[str] | None:
        words, remaining = [], target
        while remaining > 0:
            ok = [l for l in range(min_ladder_word, min(max_ladder_word, remaining) + 1)
                  if words_by_len.get(l)]
            if not ok:
                return None
            length = rng.choice(ok)
            words.append(rng.choice(words_by_len[length]))
            remaining -= length
        return words

    print(f"Building prefix index … ", end="", flush=True)
    snake_next = _build_next_letters(word_scores, max_snake)
    print("done")

    rng2 = random.Random(seed + 1)

    # Time budget per (L1, L2) pair — caps backtracking so we try many pairs.
    total_pairs = max_l1_trials * 5
    per_pair_secs = max(0.5, (deadline - time.time()) / total_pairs)

    print(f"Generating puzzle (ladder={target_len} letters, {per_pair_secs:.1f}s/pair) …")
    for trial in range(1, max_l1_trials + 1):
        if time.time() > deadline:
            print("  Time limit reached.")
            break

        l1_words = random_seq(target_len)
        if not l1_words:
            continue
        for _ in range(5):
            if time.time() > deadline:
                break
            l2_words = random_seq(target_len)
            if not l2_words:
                continue

            l1 = list(''.join(l1_words))
            l2 = list(''.join(l2_words))
            pair_deadline = time.time() + per_pair_secs

            print(f"  [{trial}] L1={' '.join(l1_words)}  L2={' '.join(l2_words)} … ", end="", flush=True)

            def solve(
                l1_avail: frozenset[int],
                l2_avail: frozenset[int],
                committed: list[Snake],
                max_per_anchor: int = 30,
            ) -> list[Snake] | None:
                if time.time() > pair_deadline:
                    return None
                if not l1_avail and not l2_avail:
                    return committed
                if l1_avail:
                    anchor_src, anchor_pos = 'L1', min(l1_avail)
                else:
                    anchor_src, anchor_pos = 'L2', min(l2_avail)
                tried = 0
                for snake in find_snakes(
                    l1, l2, l1_avail, l2_avail,
                    word_scores, snake_next,
                    min_snake, max_snake,
                    anchor_src, anchor_pos, rng2, pair_deadline,
                ):
                    tried += 1
                    if tried > max_per_anchor:
                        break
                    new_l1 = l1_avail - frozenset(snake.l1_positions())
                    new_l2 = l2_avail - frozenset(snake.l2_positions())
                    result = solve(new_l1, new_l2, committed + [snake])
                    if result is not None:
                        return result
                return None

            snakes = solve(frozenset(range(target_len)), frozenset(range(target_len)), [])
            if snakes is not None:
                print("found!")
                return l1_words, l2_words, snakes
            print("–")

    return None


# ── Display ───────────────────────────────────────────────────────────────────

def _chunk_label(chunk: Chunk) -> str:
    pos = chunk.positions()
    arrow = "→" if chunk.forward else "←"
    if len(pos) == 1:
        return f"{chunk.source}[{pos[0]+1}]{arrow}"
    return f"{chunk.source}[{pos[0]+1}‥{pos[-1]+1}]{arrow}"


def display_puzzle(
    l1_words: list[str],
    l2_words: list[str],
    snakes: list[Snake],
) -> None:
    l1 = list(''.join(l1_words))
    l2 = list(''.join(l2_words))

    bar = '═' * 60
    print(f"\n{bar}")
    print("  SNAKES & LADDERS WORD PUZZLE")
    print(bar)
    print(f"\n  LADDER 1 ({len(l1)} letters):  {'  '.join(l1_words)}")
    print(f"  {'  '.join(l1)}")
    print(f"\n  LADDER 2 ({len(l2)} letters):  {'  '.join(l2_words)}")
    print(f"  {'  '.join(l2)}")
    total = sum(len(s.word) for s in snakes)
    print(f"\n  SNAKES ({len(snakes)} words, {total} letters):")
    for snake in snakes:
        labels = '  +  '.join(_chunk_label(c) for c in snake.chunks)
        print(f"    {snake.word:<16}  ←  {labels}")
    print(f"\n{bar}\n")


# ── Verify ────────────────────────────────────────────────────────────────────

def find_decompositions(
    word: str,
    l1: list[str],
    l2: list[str],
    l1_avail: frozenset[int],
    l2_avail: frozenset[int],
):
    """
    Generator: yields every Snake that spells `word` exactly using
    available positions from L1 and L2, alternating chunks, each chunk
    contiguous and in one direction.  Both ladders must be used at least once.
    """
    def rec(
        wpos: int,
        cur_src: str,
        cur_pos: int,
        cur_dir: int,
        l1_av: frozenset[int],
        l2_av: frozenset[int],
        chunks: list[Chunk],
    ):
        if wpos == len(word):
            if any(c.source == 'L1' for c in chunks) and any(c.source == 'L2' for c in chunks):
                yield Snake(tuple(chunks), word)
            return

        c = word[wpos]
        cur_chars = l1 if cur_src == 'L1' else l2
        oth_src   = 'L2' if cur_src == 'L1' else 'L1'
        oth_chars = l2  if cur_src == 'L1' else l1
        cur_av    = l1_av if cur_src == 'L1' else l2_av
        oth_av    = l2_av if cur_src == 'L1' else l1_av

        # Option A: continue on the same ladder one step
        nxt = cur_pos + cur_dir
        if nxt in cur_av and cur_chars[nxt] == c:
            new_chunk = Chunk(cur_src, chunks[-1].start, chunks[-1].length + 1, cur_dir > 0)
            new_l1 = (l1_av - {nxt}) if cur_src == 'L1' else l1_av
            new_l2 = (l2_av - {nxt}) if cur_src == 'L2' else l2_av
            yield from rec(wpos + 1, cur_src, nxt, cur_dir, new_l1, new_l2, chunks[:-1] + [new_chunk])

        # Option B: switch to the other ladder at any matching position
        for p in oth_av:
            if oth_chars[p] != c:
                continue
            for d in (1, -1):
                new_chunk = Chunk(oth_src, p, 1, d > 0)
                new_l1 = (l1_av - {p}) if oth_src == 'L1' else l1_av
                new_l2 = (l2_av - {p}) if oth_src == 'L2' else l2_av
                yield from rec(wpos + 1, oth_src, p, d, new_l1, new_l2, chunks + [new_chunk])

    # Try every available starting position in either ladder
    for start_src in ('L1', 'L2'):
        start_avail = l1_avail if start_src == 'L1' else l2_avail
        start_chars = l1      if start_src == 'L1' else l2
        for start_pos in sorted(start_avail):
            if start_chars[start_pos] != word[0]:
                continue
            for d in (1, -1):
                init_chunk = Chunk(start_src, start_pos, 1, d > 0)
                new_l1 = (l1_avail - {start_pos}) if start_src == 'L1' else l1_avail
                new_l2 = (l2_avail - {start_pos}) if start_src == 'L2' else l2_avail
                yield from rec(1, start_src, start_pos, d, new_l1, new_l2, [init_chunk])


def verify_puzzle(
    l1_words: list[str],
    l2_words: list[str],
    snake_words: list[str],
    word_scores: dict[str, int],
    time_limit: float = 30.0,
) -> tuple[bool, list[Snake]]:
    """
    Verify a puzzle given as word strings.  Backtracks over all valid chunk
    decompositions so that every snake word can be placed simultaneously.
    """
    l1 = list(''.join(l1_words))
    l2 = list(''.join(l2_words))
    n = len(l1)
    if len(l2) != n:
        print(f"✗ L1={len(l1)}, L2={len(l2)} — must match.")
        return False, []

    deadline = time.time() + time_limit
    words = [w.upper() for w in snake_words]

    def solve(
        remaining: list[str],
        l1_av: frozenset[int],
        l2_av: frozenset[int],
        committed: list[Snake],
    ) -> list[Snake] | None:
        if time.time() > deadline:
            return None
        if not remaining:
            if not l1_av and not l2_av:
                return committed
            return None
        w = remaining[0]
        for snake in find_decompositions(w, l1, l2, l1_av, l2_av):
            if time.time() > deadline:
                return None
            new_l1 = l1_av - frozenset(snake.l1_positions())
            new_l2 = l2_av - frozenset(snake.l2_positions())
            result = solve(remaining[1:], new_l1, new_l2, committed + [snake])
            if result is not None:
                return result
        return None

    snake_objs = solve(words, frozenset(range(n)), frozenset(range(n)), [])

    if snake_objs is None:
        print("✗ No valid decomposition found (positions conflict or time limit reached).")
        return False, []

    if l1_av := frozenset(range(n)) - frozenset(p for s in snake_objs for p in s.l1_positions()):
        print(f"✗ Uncovered L1 positions: {sorted(l1_av)}")
        return False, []

    for w in words:
        if w not in word_scores:
            print(f"⚠  '{w}' not in wordlist")
    print("✓ Valid puzzle!")
    return True, snake_objs


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Snakes & Ladders word puzzle builder")
    sub = parser.add_subparsers(dest="cmd", required=True)

    chk = sub.add_parser("check", help="Given ladder words, find snakes")
    chk.add_argument("ladder1")
    chk.add_argument("ladder2")
    chk.add_argument("--min-snake", type=int, default=3)
    chk.add_argument("--max-snake", type=int, default=12)
    chk.add_argument("--min-score", type=int, default=50)
    chk.add_argument("--time-limit", type=float, default=30.0)

    gen = sub.add_parser("generate", help="Search for a valid puzzle")
    gen.add_argument("--length", type=int, default=15)
    gen.add_argument("--min-word", type=int, default=3)
    gen.add_argument("--max-word", type=int, default=7)
    gen.add_argument("--min-snake", type=int, default=3)
    gen.add_argument("--max-snake", type=int, default=10)
    gen.add_argument("--tries", type=int, default=50)
    gen.add_argument("--time-limit", type=float, default=120.0)
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--min-score", type=int, default=50)

    ver = sub.add_parser("verify", help="Verify a complete puzzle")
    ver.add_argument("ladder1")
    ver.add_argument("ladder2")
    ver.add_argument("snakes")
    ver.add_argument("--min-score", type=int, default=50)
    ver.add_argument("--time-limit", type=float, default=60.0)

    args = parser.parse_args()

    if not WORDLIST_PATH.exists():
        print(f"Error: wordlist not found at {WORDLIST_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading wordlist … ", end="", flush=True)
    word_scores = load_wordlist(WORDLIST_PATH, getattr(args, "min_score", 50))
    print(f"{len(word_scores):,} words")

    if args.cmd == "check":
        l1w = [w.upper() for w in args.ladder1.split()]
        l2w = [w.upper() for w in args.ladder2.split()]
        snakes = check_puzzle(l1w, l2w, word_scores, args.min_snake, args.max_snake, args.time_limit)
        if snakes:
            display_puzzle(l1w, l2w, snakes)
        else:
            print("No valid snake arrangement found within time limit.")

    elif args.cmd == "generate":
        result = generate_puzzle(
            word_scores,
            target_len=args.length,
            min_ladder_word=args.min_word,
            max_ladder_word=args.max_word,
            min_snake=args.min_snake,
            max_snake=args.max_snake,
            max_l1_trials=args.tries,
            time_limit=args.time_limit,
            seed=args.seed,
        )
        if result:
            display_puzzle(*result)
        else:
            print("No valid puzzle found. Try a different --seed.")

    elif args.cmd == "verify":
        l1w = [w.upper() for w in args.ladder1.split()]
        l2w = [w.upper() for w in args.ladder2.split()]
        sw = args.snakes.split()
        ok, snake_objs = verify_puzzle(l1w, l2w, sw, word_scores, time_limit=args.time_limit)
        if ok:
            display_puzzle(l1w, l2w, snake_objs)


if __name__ == "__main__":
    main()
