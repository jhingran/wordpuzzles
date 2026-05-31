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


# ── Non-crossing search ───────────────────────────────────────────────────────

def find_noncrossing_snakes(
    l1: list[str],
    l2: list[str],
    l1_ptr: int,       # next L1 position to consume (0-based)
    l2_ptr: int,       # next L2 position to consume (0-based)
    word_scores: dict[str, int],
    snake_next: dict[str, set[str]],
    min_len: int,
    max_len: int,
    deadline: float,
):
    """
    Generator: yields non-crossing Snakes starting at l1_ptr / l2_ptr.

    Each snake owns a contiguous block of L1 positions [l1_ptr..l1_end] and
    L2 positions [l2_ptr..l2_end].  Within those blocks, chunks may run
    forward (↑ ascending position) OR backward (↓ descending).  A backward
    chunk of jump-distance k reserves positions [ptr..ptr+k] and reads them
    in reverse; the block end advances to ptr+k+1.

    Consecutive snakes tile both ladders in the same left-to-right order —
    no two snakes share a position on either ladder.
    """
    n1, n2 = len(l1), len(l2)

    def rec(
        prefix: str,
        cur_src: str,
        l1_p: int,        # next available L1 position (floor of remaining L1)
        l2_p: int,        # next available L2 position (floor of remaining L2)
        l1_used: bool,
        l2_used: bool,
        chunks: list[Chunk],
        chunk_start: int,
        chunk_len: int,
    ):
        """Extend the word while on cur_src in forward mode."""
        if time.time() > deadline:
            return

        if len(prefix) >= min_len and prefix in word_scores and l1_used and l2_used:
            yield Snake(tuple(chunks), prefix)

        if len(prefix) >= max_len:
            return

        valid_next = snake_next.get(prefix, set())
        if not valid_next:
            return

        if cur_src == 'L1':
            # Option A: extend L1 forward
            if l1_p < n1 and l1[l1_p] in valid_next:
                c = l1[l1_p]
                new_chunk = Chunk('L1', chunk_start, chunk_len + 1, True)
                yield from rec(prefix + c, 'L1', l1_p + 1, l2_p, True, l2_used,
                               chunks[:-1] + [new_chunk], chunk_start, chunk_len + 1)
            # Option B: switch to L2 forward
            if l2_p < n2 and l2[l2_p] in valid_next:
                c = l2[l2_p]
                new_chunk = Chunk('L2', l2_p, 1, True)
                yield from rec(prefix + c, 'L2', l1_p, l2_p + 1, l1_used, True,
                               chunks + [new_chunk], l2_p, 1)
            # Option C: switch to L2 backward (jump k ahead, descend to l2_p)
            remaining = max_len - len(prefix)
            for k in range(1, min(remaining, n2 - l2_p)):
                jump = l2_p + k
                if l2[jump] not in valid_next:
                    continue
                c = l2[jump]
                new_chunk = Chunk('L2', jump, 1, False)
                yield from rec_back(prefix + c, 'L2', jump - 1, l2_p,
                                    l1_p, jump + 1, l1_used, True,
                                    chunks + [new_chunk], jump, 1)
        else:
            # Option A: extend L2 forward
            if l2_p < n2 and l2[l2_p] in valid_next:
                c = l2[l2_p]
                new_chunk = Chunk('L2', chunk_start, chunk_len + 1, True)
                yield from rec(prefix + c, 'L2', l1_p, l2_p + 1, l1_used, True,
                               chunks[:-1] + [new_chunk], chunk_start, chunk_len + 1)
            # Option B: switch to L1 forward
            if l1_p < n1 and l1[l1_p] in valid_next:
                c = l1[l1_p]
                new_chunk = Chunk('L1', l1_p, 1, True)
                yield from rec(prefix + c, 'L1', l1_p + 1, l2_p, True, l2_used,
                               chunks + [new_chunk], l1_p, 1)
            # Option C: switch to L1 backward (jump k ahead, descend to l1_p)
            remaining = max_len - len(prefix)
            for k in range(1, min(remaining, n1 - l1_p)):
                jump = l1_p + k
                if l1[jump] not in valid_next:
                    continue
                c = l1[jump]
                new_chunk = Chunk('L1', jump, 1, False)
                yield from rec_back(prefix + c, 'L1', jump - 1, l1_p,
                                    jump + 1, l2_p, True, l2_used,
                                    chunks + [new_chunk], jump, 1)

    def rec_back(
        prefix: str,
        back_src: str,
        cur_pos: int,       # current position descending toward floor
        floor: int,         # must reach this position before we can switch away
        l1_p_after: int,    # l1_p to use once this backward chunk is complete
        l2_p_after: int,    # l2_p to use once this backward chunk is complete
        l1_used: bool,
        l2_used: bool,
        chunks: list[Chunk],
        chunk_start: int,   # the jump position (highest pos in this chunk)
        chunk_len: int,
    ):
        """
        Forced descent: consume back_src from cur_pos down to floor, then
        switch to the other ladder in forward mode.
        """
        if time.time() > deadline:
            return

        back_chars = l1 if back_src == 'L1' else l2

        if cur_pos >= floor:
            # Still descending — must take the next letter, no choice.
            if len(prefix) >= max_len:
                return
            valid_next = snake_next.get(prefix, set())
            c = back_chars[cur_pos]
            if c not in valid_next:
                return
            new_chunk = Chunk(back_src, chunk_start, chunk_len + 1, False)
            yield from rec_back(prefix + c, back_src, cur_pos - 1, floor,
                                l1_p_after, l2_p_after, l1_used, l2_used,
                                chunks[:-1] + [new_chunk], chunk_start, chunk_len + 1)
        else:
            # Descent complete — switch to the other ladder in forward mode.
            if len(prefix) >= min_len and prefix in word_scores and l1_used and l2_used:
                yield Snake(tuple(chunks), prefix)
            if len(prefix) >= max_len:
                return
            valid_next = snake_next.get(prefix, set())
            if not valid_next:
                return
            fwd_src = 'L2' if back_src == 'L1' else 'L1'
            fwd_chars = l2 if back_src == 'L1' else l1
            fwd_p = l2_p_after if back_src == 'L1' else l1_p_after
            fwd_n = n2 if back_src == 'L1' else n1
            if fwd_p < fwd_n and fwd_chars[fwd_p] in valid_next:
                c = fwd_chars[fwd_p]
                new_chunk = Chunk(fwd_src, fwd_p, 1, True)
                if fwd_src == 'L1':
                    yield from rec(prefix + c, 'L1', fwd_p + 1, l2_p_after,
                                   True, l2_used, chunks + [new_chunk], fwd_p, 1)
                else:
                    yield from rec(prefix + c, 'L2', l1_p_after, fwd_p + 1,
                                   l1_used, True, chunks + [new_chunk], fwd_p, 1)

    # Try starting on L1 or L2, forward or backward
    valid_first = snake_next.get('', set())
    for start_src, start_ptr, start_chars, start_n, oth_ptr in [
        ('L1', l1_ptr, l1, n1, l2_ptr),
        ('L2', l2_ptr, l2, n2, l1_ptr),
    ]:
        if start_ptr >= start_n:
            continue
        # Forward start
        c0 = start_chars[start_ptr]
        if c0 in valid_first:
            init_chunk = Chunk(start_src, start_ptr, 1, True)
            if start_src == 'L1':
                yield from rec(c0, 'L1', l1_ptr + 1, l2_ptr, True, False,
                               [init_chunk], l1_ptr, 1)
            else:
                yield from rec(c0, 'L2', l1_ptr, l2_ptr + 1, False, True,
                               [init_chunk], l2_ptr, 1)
        # Backward start (jump k ahead from start_ptr, descend)
        for k in range(1, min(max_len, start_n - start_ptr)):
            jump = start_ptr + k
            c0 = start_chars[jump]
            if c0 not in valid_first:
                continue
            init_chunk = Chunk(start_src, jump, 1, False)
            if start_src == 'L1':
                yield from rec_back(c0, 'L1', jump - 1, l1_ptr,
                                    jump + 1, l2_ptr, True, False,
                                    [init_chunk], jump, 1)
            else:
                yield from rec_back(c0, 'L2', jump - 1, l2_ptr,
                                    l1_ptr, jump + 1, False, True,
                                    [init_chunk], jump, 1)


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
    noncrossing: bool = True,
) -> list[Snake] | None:
    """
    Given ladder words, find snakes that cover every position exactly once.

    noncrossing=True (default): each snake uses a contiguous forward block
    from each ladder; snakes tile both ladders in the same left-to-right order.
    noncrossing=False: snakes may jump anywhere (crossing allowed).
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

    if noncrossing:
        def solve(l1_ptr: int, l2_ptr: int, committed: list[Snake]) -> list[Snake] | None:
            if time.time() > deadline:
                return None
            if l1_ptr >= n and l2_ptr >= n:
                return committed
            if l1_ptr >= n or l2_ptr >= n:
                return None  # one side exhausted, can't form valid snake
            for snake in find_noncrossing_snakes(
                l1, l2, l1_ptr, l2_ptr,
                word_scores, snake_next, min_snake, max_snake, deadline,
            ):
                new_l1_ptr = max(snake.l1_positions()) + 1
                new_l2_ptr = max(snake.l2_positions()) + 1
                result = solve(new_l1_ptr, new_l2_ptr, committed + [snake])
                if result is not None:
                    return result
            return None
        return solve(0, 0, [])

    else:
        def solve_crossing(
            l1_avail: frozenset[int],
            l2_avail: frozenset[int],
            committed: list[Snake],
        ) -> list[Snake] | None:
            if time.time() > deadline:
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
                anchor_src, anchor_pos,
                rng, deadline,
            ):
                tried += 1
                if tried > 50:
                    break
                new_l1 = l1_avail - frozenset(snake.l1_positions())
                new_l2 = l2_avail - frozenset(snake.l2_positions())
                result = solve_crossing(new_l1, new_l2, committed + [snake])
                if result is not None:
                    return result
            return None
        return solve_crossing(frozenset(range(n)), frozenset(range(n)), [])


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
    noncrossing: bool = True,
    include_words: dict[str, str] | None = None,  # word → custom clue (or '')
    max_short_snakes: int = 2,   # reject puzzles with more than this many 3-letter snakes
) -> tuple[list[str], list[str], list[Snake]] | None:
    include_words = include_words or {}
    rng = random.Random(seed)
    deadline = time.time() + time_limit

    # Augment word_scores with include words not already present
    word_scores = dict(word_scores)
    for w in include_words:
        if w not in word_scores:
            word_scores[w] = 90   # treat as high-quality word

    words_by_len: dict[int, list[str]] = defaultdict(list)
    for word in word_scores:
        if min_ladder_word <= len(word) <= max_ladder_word:
            words_by_len[len(word)].append(word)

    # Include words short enough to be ladder words
    ladder_includes = [w for w in include_words
                       if min_ladder_word <= len(w) <= max_ladder_word]

    # Require at least this many theme words to appear in the final puzzle
    min_included = min(3, len(include_words)) if include_words else 0

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

    def themed_seq(target: int) -> list[str] | None:
        """Seed 1-2 include words then fill the rest randomly."""
        if not ladder_includes:
            return random_seq(target)
        for n_inc in range(min(2, len(ladder_includes)), 0, -1):
            for _ in range(20):
                chosen = rng.sample(ladder_includes, n_inc)
                remaining = target - sum(len(w) for w in chosen)
                if remaining < 0 or (0 < remaining < min_ladder_word):
                    continue
                if remaining == 0:
                    rng.shuffle(chosen)
                    return chosen
                filler = random_seq(remaining)
                if filler:
                    combined = chosen + filler
                    rng.shuffle(combined)
                    return combined
        return random_seq(target)

    print(f"Building prefix index … ", end="", flush=True)
    snake_next = _build_next_letters(word_scores, max_snake)
    print("done")

    rng2 = random.Random(seed + 1)

    # Non-crossing solve: just two integer pointers, no frozensets needed.
    def solve_nc(l1: list[str], l2: list[str], l1_ptr: int, l2_ptr: int,
                 committed: list[Snake], pair_deadline: float) -> list[Snake] | None:
        n = len(l1)
        if time.time() > pair_deadline:
            return None
        if l1_ptr >= n and l2_ptr >= n:
            return committed
        if l1_ptr >= n or l2_ptr >= n:
            return None
        # Collect up to 40 candidates and sort longest-first so the solver
        # prefers 4-5 letter snakes over 3-letter ones.
        candidates = []
        for snake in find_noncrossing_snakes(
            l1, l2, l1_ptr, l2_ptr,
            word_scores, snake_next, min_snake, max_snake, pair_deadline,
        ):
            candidates.append(snake)
            if len(candidates) >= 40:
                break
        candidates.sort(key=lambda s: len(s.word), reverse=True)
        for snake in candidates:
            result = solve_nc(l1, l2, max(snake.l1_positions()) + 1,
                              max(snake.l2_positions()) + 1,
                              committed + [snake], pair_deadline)
            if result is not None:
                return result
        return None

    # Crossing solve: slower fallback (frozenset-based).
    def solve_cross(l1: list[str], l2: list[str],
                    l1_avail: frozenset[int], l2_avail: frozenset[int],
                    committed: list[Snake], pair_deadline: float) -> list[Snake] | None:
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
            word_scores, snake_next, min_snake, max_snake,
            anchor_src, anchor_pos, rng2, pair_deadline,
        ):
            tried += 1
            if tried > 30:
                break
            new_l1 = l1_avail - frozenset(snake.l1_positions())
            new_l2 = l2_avail - frozenset(snake.l2_positions())
            result = solve_cross(l1, l2, new_l1, new_l2, committed + [snake], pair_deadline)
            if result is not None:
                return result
        return None

    # Non-crossing is much faster per pair, so give each pair less time.
    total_pairs = max_l1_trials * 5
    per_pair_secs = max(0.2 if noncrossing else 0.5, (deadline - time.time()) / total_pairs)

    mode = "non-crossing" if noncrossing else "crossing"
    print(f"Generating puzzle (ladder={target_len} letters, {mode}, {per_pair_secs:.1f}s/pair) …")
    for trial in range(1, max_l1_trials + 1):
        if time.time() > deadline:
            print("  Time limit reached.")
            break

        # Use themed sampling while time/budget allows; pure random as fallback
        use_theme = bool(include_words) and trial <= max(max_l1_trials * 0.8, 1)
        l1_words = themed_seq(target_len) if use_theme else random_seq(target_len)
        if not l1_words:
            continue
        for _ in range(5):
            if time.time() > deadline:
                break
            l2_words = themed_seq(target_len) if use_theme else random_seq(target_len)
            if not l2_words:
                continue

            l1 = list(''.join(l1_words))
            l2 = list(''.join(l2_words))
            pair_deadline = time.time() + per_pair_secs

            print(f"  [{trial}] L1={' '.join(l1_words)}  L2={' '.join(l2_words)} … ", end="", flush=True)

            n = len(l1)
            if noncrossing:
                snakes = solve_nc(l1, l2, 0, 0, [], pair_deadline)
            else:
                snakes = solve_cross(l1, l2, frozenset(range(n)), frozenset(range(n)), [], pair_deadline)

            if snakes is not None:
                all_words_list = l1_words + l2_words + [s.word for s in snakes]
                all_words_set  = set(all_words_list)

                # No duplicate words anywhere in the puzzle
                if len(all_words_set) != len(all_words_list):
                    print("(duplicate words)–")
                    continue

                # No word is a simple plural of another (CHART/CHARTS, etc.)
                def _is_plain_plural(a: str, b: str) -> bool:
                    return a == b + 'S' or a == b + 'ES'
                if any(
                    _is_plain_plural(w1, w2) or _is_plain_plural(w2, w1)
                    for i, w1 in enumerate(all_words_list)
                    for w2 in all_words_list[i + 1:]
                ):
                    print("(plural pair)–")
                    continue

                # No snake word repeats a ladder word (belt-and-suspenders after dedup)
                ladder_set = set(l1_words + l2_words)
                snake_set  = {s.word for s in snakes}
                if ladder_set & snake_set:
                    print("(word overlap)–")
                    continue

                # Reject if too many snakes are 3 letters (prefer 4-5 letter snakes)
                short_count = sum(1 for s in snakes if len(s.word) <= 3)
                if short_count > max_short_snakes:
                    print(f"(too many short snakes: {short_count})–")
                    continue

                # Check theme-word count
                included = [w for w in include_words if w in all_words_set]
                if len(included) < min_included:
                    print(f"(only {len(included)}/{min_included} theme words)–")
                    continue

                tag = f"  theme: {', '.join(included)}" if included else ""
                print(f"found!{tag}")
                return l1_words, l2_words, snakes
            else:
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


# ── Puzzle image ─────────────────────────────────────────────────────────────

def draw_puzzle_image(
    l1_words: list[str],
    l2_words: list[str],
    snakes: list[Snake],
    output_path: str,
    *,
    solved: bool = True,
    clues: dict[str, str] | None = None,
    cell: int = 52,
    gap: int = 70,
) -> None:
    """
    Render the puzzle as a PNG.

    solved=True  → fill letters into cells (solution image).
    solved=False → blank cells (puzzle image).
    clues        → dict word→definition; when provided, adds a clue panel
                   to the right of the ladders.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Error: Pillow not installed.  pip install Pillow", file=sys.stderr)
        return

    N = len(''.join(l1_words))

    RAIL    = 5
    PAD     = 40
    TITLE_H = 44
    LABEL_H = 26
    TOP     = PAD + TITLE_H + LABEL_H
    LINE_W  = 3

    l1_x  = PAD
    l2_x  = PAD + cell + gap
    l1_cx = l1_x + cell // 2
    l2_cx = l2_x + cell // 2

    # Clue panel sizing (right of ladders, only when clues provided)
    PANEL_GAP  = 28
    PANEL_W    = 210
    SECTION_H  = 20   # px per section header
    CLUE_H     = 17   # px per clue line
    SECTION_SP = 10   # extra gap before each section header

    base_w = l2_x + cell + PAD
    img_w  = base_w + PANEL_GAP + PANEL_W if clues is not None else base_w

    panel_lines = 0
    if clues is not None:
        panel_lines += 3 * (SECTION_H + SECTION_SP)                   # 3 headers
        panel_lines += (len(l1_words) + len(l2_words)) * CLUE_H
        panel_lines += len(snakes) * CLUE_H
    panel_h = panel_lines

    img_h = TOP + max(N * cell, panel_h) + PAD

    SNAKE_COLORS = ['#BBBBBB'] * 12   # light grey so solvers can write over the paths

    img  = Image.new('RGB', (img_w, img_h), '#F8F7F2')
    draw = ImageDraw.Draw(img)

    def _font(size: int):
        for path in [
            '/System/Library/Fonts/Helvetica.ttc',
            '/System/Library/Fonts/Arial.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        ]:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
        return ImageFont.load_default()

    f_title  = _font(20)
    f_label  = _font(14)
    f_marker = _font(11)
    f_legend = _font(13)

    def _cy(row: int) -> int:
        return TOP + row * cell + cell // 2

    def _cx(side: str) -> int:
        return l1_cx if side == 'L1' else l2_cx

    def _catmull_rom(points, steps: int = 30):
        """Smooth interpolating curve through all points (C1 continuous, like PowerPoint)."""
        if len(points) == 1:
            return [points[0]]
        # Phantom endpoints mirror the first/last segment so the curve starts/ends
        # tangent to the first/last segment direction.
        ext = [
            (2*points[0][0] - points[1][0], 2*points[0][1] - points[1][1]),
            *points,
            (2*points[-1][0] - points[-2][0], 2*points[-1][1] - points[-2][1]),
        ]
        out = []
        for i in range(1, len(ext) - 2):
            p0, p1, p2, p3 = ext[i-1], ext[i], ext[i+1], ext[i+2]
            for j in range(steps):
                t = j / steps
                t2, t3 = t*t, t*t*t
                x = 0.5*(2*p1[0] + (-p0[0]+p2[0])*t + (2*p0[0]-5*p1[0]+4*p2[0]-p3[0])*t2 + (-p0[0]+3*p1[0]-3*p2[0]+p3[0])*t3)
                y = 0.5*(2*p1[1] + (-p0[1]+p2[1])*t + (2*p0[1]-5*p1[1]+4*p2[1]-p3[1])*t2 + (-p0[1]+3*p1[1]-3*p2[1]+p3[1])*t3)
                out.append((x, y))
        out.append(points[-1])
        return out

    # ── Title & labels ────────────────────────────────────────────────────────
    draw.text((img_w // 2, PAD + TITLE_H // 2),
              'SNAKES & LADDERS', fill='#1A1A2E', font=f_title, anchor='mm')
    draw.text((l1_cx, PAD + TITLE_H + LABEL_H // 2),
              'LADDER 1', fill='#1A1A2E', font=f_label, anchor='mm')
    draw.text((l2_cx, PAD + TITLE_H + LABEL_H // 2),
              'LADDER 2', fill='#1A1A2E', font=f_label, anchor='mm')

    # ── Ladders — open top & bottom, interior rungs only ─────────────────────
    for lx in (l1_x, l2_x):
        # White cell backgrounds
        for row in range(N):
            draw.rectangle([lx, TOP + row * cell, lx + cell, TOP + (row + 1) * cell],
                           fill='white')
        # Interior rungs (horizontal bars between cells, not at top or bottom)
        for row in range(1, N):
            y = TOP + row * cell
            draw.line([(lx, y), (lx + cell, y)], fill='#555555', width=1)
        # Vertical rails — open-ended (no caps)
        draw.line([(lx,        TOP), (lx,        TOP + N * cell)], fill='#222222', width=RAIL)
        draw.line([(lx + cell, TOP), (lx + cell, TOP + N * cell)], fill='#222222', width=RAIL)

    # ── Snake paths — single Catmull-Rom spline per snake (fully smooth) ────────
    for si, snake in enumerate(snakes):
        color = SNAKE_COLORS[si % len(SNAKE_COLORS)]

        # Collect cell-centre waypoints in word order
        waypoints = []
        for chunk in snake.chunks:
            cx = _cx(chunk.source)
            for p in chunk.positions():
                waypoints.append((cx, _cy(p)))

        # One smooth interpolating curve through every waypoint
        curve = _catmull_rom(waypoints)
        for k in range(len(curve) - 1):
            draw.line([curve[k], curve[k + 1]], fill=color, width=LINE_W)

        # Numbered start marker
        sx, sy = waypoints[0]
        R = 9
        draw.ellipse([sx - R, sy - R, sx + R, sy + R], fill=color, outline='white', width=1)
        draw.text((sx, sy), str(si + 1), fill='white', font=f_marker, anchor='mm')

    # ── Letters — solution only ───────────────────────────────────────────────
    if solved:
        l1_letters = list(''.join(l1_words))
        l2_letters = list(''.join(l2_words))
        f_letter = _font(28)
        for row in range(N):
            for letter, cx in [(l1_letters[row], l1_cx), (l2_letters[row], l2_cx)]:
                x, y = cx, _cy(row)
                draw.text((x, y), letter, fill='white', font=f_letter, anchor='mm',
                          stroke_width=4, stroke_fill='white')
                draw.text((x, y), letter, fill='#1A1A2E', font=f_letter, anchor='mm',
                          stroke_width=1, stroke_fill='#1A1A2E')

    # ── Clue panel — puzzle only ──────────────────────────────────────────────
    if clues is not None:
        px   = base_w + PANEL_GAP   # left edge of panel text
        py   = TOP                  # start aligned with first cell
        INK  = '#1A1A2E'
        f_sec = _font(13)
        f_clu = _font(11)

        def _clue_line(word: str, index: int, length: int) -> None:
            nonlocal py
            marker = f"{'①②③④⑤⑥⑦⑧⑨⑩'[index]}" if index < 10 else f"{index+1}."
            defn   = clues.get(word.upper(), "")
            text   = f"{marker} ({length}) {defn}"
            # Simple word-wrap at ~34 chars
            words_q = text.split()
            line, line2 = "", ""
            for w in words_q:
                if not line:
                    line = w
                elif len(line) + 1 + len(w) <= 34:
                    line += " " + w
                else:
                    line2 += (" " if line2 else "") + w
            draw.text((px, py), line, fill=INK, font=f_clu, anchor='lm')
            py += CLUE_H
            if line2:
                draw.text((px + 12, py), line2, fill=INK, font=f_clu, anchor='lm')
                py += CLUE_H

        def _section(title: str) -> None:
            nonlocal py
            py += SECTION_SP
            draw.text((px, py), title, fill=INK, font=f_sec, anchor='lm')
            py += SECTION_H

        _section("LADDER 1")
        for i, w in enumerate(l1_words):
            _clue_line(w, i, len(w))

        _section("LADDER 2")
        for i, w in enumerate(l2_words):
            _clue_line(w, i, len(w))

        _section("SNAKES")
        for i, snake in enumerate(snakes):
            _clue_line(snake.word, i, len(snake.word))

    img.save(output_path)
    print(f"  → Saved: {output_path}")


# ── Include-word parser ───────────────────────────────────────────────────────

def _parse_include(s: str) -> dict[str, str]:
    """
    Parse --include string into {WORD: clue} dict.

    Format: semicolon-separated entries, each either:
      WORD: clue text
      WORD          (clue left blank; Claude API will generate it)

    Example:
      "RENU: my wife; POPPY: her nickname for me; JUNE; ARNIE"
    """
    result: dict[str, str] = {}
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


# ── Clue generation ──────────────────────────────────────────────────────────

def generate_clues(
    l1_words: list[str],
    l2_words: list[str],
    snakes: list[Snake],
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    """
    Generate simple one-line definitions via Claude API.
    Words in `overrides` that have non-empty clues skip the API call.
    Returns {} silently if ANTHROPIC_API_KEY is unset or anthropic not installed.
    """
    import os
    overrides = overrides or {}
    all_words = l1_words + l2_words + [s.word for s in snakes]

    # Start with any user-supplied clues
    clues: dict[str, str] = {}
    for w, clue in overrides.items():
        if clue:
            clues[w.upper()] = clue

    # Words that still need API-generated clues
    need_api = [w for w in all_words if w.upper() not in clues]
    if not need_api:
        return clues

    try:
        import anthropic
    except ImportError:
        return clues
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return clues

    client = anthropic.Anthropic(api_key=api_key)
    word_list = ", ".join(need_api)
    prompt = (
        "For each word below write ONE crossword clue of at most 5 words.\n"
        "Rules:\n"
        "- Use the single most common meaning only.\n"
        "- Never use the word 'or'.\n"
        "- No slashes, no alternatives, no parenthetical notes.\n"
        "- No leading article (a/an/the).\n"
        "- Format: WORD: clue  (one per line, nothing else)\n\n"
        + word_list
    )
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        for line in resp.content[0].text.strip().splitlines():
            if ":" in line:
                w, defn = line.split(":", 1)
                w = w.strip().upper()
                if w in {x.upper() for x in all_words}:
                    defn = defn.strip()
                    # Strip any trailing " or ..." alternative as a safety net
                    for sep in (" or ", "/", "; "):
                        if sep in defn:
                            defn = defn.split(sep)[0].rstrip(" ,")
                    clues[w] = defn
    except Exception:
        pass
    return clues


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


# ── PNG output helper ────────────────────────────────────────────────────────

def _emit_pngs(
    l1_words: list[str],
    l2_words: list[str],
    snakes: list[Snake],
    base_path: str,
    include_words: dict[str, str] | None = None,
) -> None:
    """Generate solution PNG and puzzle PNG (with clues) from a single --png path."""
    from pathlib import Path
    p = Path(base_path)
    solution_path = str(p.with_stem(p.stem + "_solution"))
    puzzle_path   = str(p.with_stem(p.stem + "_puzzle"))

    # Solution: letters filled, no clue panel
    draw_puzzle_image(l1_words, l2_words, snakes, solution_path, solved=True)

    # Clues: user-supplied overrides first, then Claude API for the rest
    print("  Generating clues … ", end="", flush=True)
    clues = generate_clues(l1_words, l2_words, snakes, overrides=include_words)
    print("done" if clues else "no API key — using blank clues")

    # Puzzle: blank cells + clue panel
    draw_puzzle_image(l1_words, l2_words, snakes, puzzle_path,
                      solved=False, clues=clues)


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
    chk.add_argument("--crossing", action="store_true",
                     help="Allow crossing snakes (default: non-crossing)")
    chk.add_argument("--png", metavar="FILE", help="Save puzzle image to FILE")

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
    gen.add_argument("--crossing", action="store_true",
                     help="Allow crossing snakes (default: non-crossing)")
    gen.add_argument("--png", metavar="FILE", help="Save puzzle image to FILE")
    gen.add_argument("--max-short-snakes", type=int, default=2,
                     help="Reject puzzles with more than this many 3-letter snakes (default: 2)")
    gen.add_argument(
        "--include", metavar="WORDS", default="",
        help=(
            'Semicolon-separated themed words (with optional clues) to include. '
            'Format: "WORD: clue text; WORD2: clue; WORD3". '
            'At least 3 of the provided words will appear in the puzzle.'
        ),
    )

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
        # Validate ladder words before searching
        all_ladder = l1w + l2w
        if len(set(all_ladder)) != len(all_ladder):
            print("Error: duplicate words in ladders.", file=sys.stderr)
            sys.exit(1)
        def _is_plain_plural(a: str, b: str) -> bool:
            return a == b + 'S' or a == b + 'ES'
        for i, w1 in enumerate(all_ladder):
            for w2 in all_ladder[i + 1:]:
                if _is_plain_plural(w1, w2) or _is_plain_plural(w2, w1):
                    print(f"Error: '{w1}' and '{w2}' are a plural pair.", file=sys.stderr)
                    sys.exit(1)
        snakes = check_puzzle(l1w, l2w, word_scores, args.min_snake, args.max_snake,
                              args.time_limit, noncrossing=not args.crossing)
        if snakes:
            display_puzzle(l1w, l2w, snakes)
            if args.png:
                _emit_pngs(l1w, l2w, snakes, args.png)
        else:
            print("No valid snake arrangement found within time limit.")

    elif args.cmd == "generate":
        include_words = _parse_include(args.include) if args.include else {}
        if include_words:
            print(f"Theme words: {', '.join(include_words)}")
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
            noncrossing=not args.crossing,
            include_words=include_words,
            max_short_snakes=args.max_short_snakes,
        )
        if result:
            display_puzzle(*result)
            if args.png:
                _emit_pngs(*result, args.png, include_words=include_words)
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
