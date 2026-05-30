#!/usr/bin/env python3
"""
snakes_ladders.py — Snakes & Ladders word puzzle builder.

Inspired by Eric Berlin's Jelly Roll puzzle (ericberlin.com).

Two vertical LADDERS, each a sequence of stacked words.
SNAKES wind between the ladders, consuming letters from both in alternating
pairs — 1 from L1, then 2 from L2, 2 from L1, 2 from L2 ... until both
ladders are exhausted. Snakes are cut from this continuous braid.

Usage:
  python snakes_ladders.py check "HITCH SENATE BOGUS" "ABATE EMIR EARNEST"
  python snakes_ladders.py generate --length 15 --seed 42
  python snakes_ladders.py verify "HITCH SENATE BOGUS" "ABATE EMIR EARNEST" \\
                                  "HABITAT CHEESE MINARET EARBONE GUSTS"
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import defaultdict
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


# ── Braid mechanics ───────────────────────────────────────────────────────────

def braid_positions(n: int) -> tuple[list[int], list[int]]:
    """
    Return (l1_positions, l2_positions) in a braid of length 2n.

    Pattern: start with 1 letter from L1, then alternate 2 from L2 / 2 from L1
    until both ladders are exhausted.

    For n=16 (even) the braid ends: ... L2(2) L1(1)
    For n=15 (odd)  the braid ends: ... L1(2) L2(1)
    """
    l1_pos: list[int] = []
    l2_pos: list[int] = []
    braid_idx = 0
    l1_idx = l2_idx = 0

    # First letter from L1
    l1_pos.append(braid_idx)
    braid_idx += 1
    l1_idx += 1

    while l1_idx < n or l2_idx < n:
        for _ in range(2):
            if l2_idx < n:
                l2_pos.append(braid_idx)
                braid_idx += 1
                l2_idx += 1
        for _ in range(2):
            if l1_idx < n:
                l1_pos.append(braid_idx)
                braid_idx += 1
                l1_idx += 1

    return l1_pos, l2_pos


def make_braid(l1: list[str], l2: list[str]) -> list[str]:
    """Interleave two letter sequences into the braid."""
    n = len(l1)
    assert len(l2) == n, f"Ladders must be equal length ({len(l1)} vs {len(l2)})"
    l1_pos, l2_pos = braid_positions(n)
    braid = [''] * (2 * n)
    for i, p in enumerate(l1_pos):
        braid[p] = l1[i]
    for i, p in enumerate(l2_pos):
        braid[p] = l2[i]
    return braid


def extract_ladders(braid: list[str], n: int) -> tuple[list[str], list[str]]:
    l1_pos, l2_pos = braid_positions(n)
    return [braid[p] for p in l1_pos], [braid[p] for p in l2_pos]


# ── Word segmentation (DP) ────────────────────────────────────────────────────

def best_segment(
    chars: list[str],
    word_scores: dict[str, int],
    min_len: int = 3,
    max_len: int = 12,
) -> list[str] | None:
    """
    Find the highest-quality segmentation of chars into valid words.
    Score = sum of wordlist scores. Returns None if no segmentation exists.
    """
    n = len(chars)
    # dp[i] = (best_score, prev_pos, word) for chars[0:i]; None = unreachable
    dp: list[tuple[float, int, str] | None] = [None] * (n + 1)
    dp[0] = (0.0, -1, '')

    for end in range(1, n + 1):
        for start in range(max(0, end - max_len), end):
            if dp[start] is None:
                continue
            length = end - start
            if length < min_len:
                continue
            word = ''.join(chars[start:end])
            if word in word_scores:
                score = dp[start][0] + word_scores[word]
                if dp[end] is None or score > dp[end][0]:
                    dp[end] = (score, start, word)

    if dp[n] is None:
        return None

    words: list[str] = []
    pos = n
    while pos > 0:
        _, prev, word = dp[pos]  # type: ignore[misc]
        words.append(word)
        pos = prev
    return list(reversed(words))


def can_segment(
    chars: list[str],
    word_scores: dict[str, int],
    min_len: int = 3,
    max_len: int = 7,
) -> bool:
    """Quick reachability check — no score tracking, just True/False."""
    n = len(chars)
    reachable = [False] * (n + 1)
    reachable[0] = True
    for end in range(1, n + 1):
        for start in range(max(0, end - max_len), end):
            if not reachable[start]:
                continue
            length = end - start
            if length < min_len:
                continue
            if ''.join(chars[start:end]) in word_scores:
                reachable[end] = True
                break
    return reachable[n]


# ── Puzzle checker ────────────────────────────────────────────────────────────

def check_puzzle(
    l1_words: list[str],
    l2_words: list[str],
    word_scores: dict[str, int],
    min_snake: int = 3,
    max_snake: int = 12,
) -> list[str] | None:
    """Given ladder words, find the best snake segmentation. Returns None if impossible."""
    l1 = list(''.join(l1_words))
    l2 = list(''.join(l2_words))
    if len(l1) != len(l2):
        print(f"Error: L1={len(l1)} letters, L2={len(l2)} letters — must match.", file=sys.stderr)
        return None
    braid = make_braid(l1, l2)
    return best_segment(braid, word_scores, min_snake, max_snake)


# ── Puzzle generator ──────────────────────────────────────────────────────────

def _random_word_sequence(
    words_by_len: dict[int, list[str]],
    target: int,
    min_len: int,
    max_len: int,
    rng: random.Random,
) -> list[str] | None:
    """Random sequence of words whose lengths sum to target."""
    words: list[str] = []
    remaining = target
    while remaining > 0:
        possible = [l for l in range(min_len, min(max_len, remaining) + 1)
                    if words_by_len.get(l)]
        if not possible:
            return None
        length = rng.choice(possible)
        word = rng.choice(words_by_len[length])
        words.append(word)
        remaining -= length
    return words


def _build_next_letters(word_scores: dict[str, int], max_len: int) -> dict[str, set[str]]:
    """
    For each prefix of a valid word (up to max_len), the set of letters
    that can legally follow it.  Empty-string key = valid first letters.
    """
    nxt: dict[str, set[str]] = defaultdict(set)
    for word in word_scores:
        if len(word) > max_len:
            continue
        for i in range(len(word)):
            nxt[word[:i]].add(word[i])
    return nxt


def _csp_solve(
    l1_chars: list[str],
    word_scores: dict[str, int],
    snake_next: dict[str, set[str]],
    ladder_next: dict[str, set[str]],
    l1_pos: list[int],
    l2_pos: list[int],
    n: int,
    min_snake: int,
    max_snake: int,
    min_ladder: int,
    max_ladder: int,
    rng: random.Random,
    deadline: float,
) -> tuple[list[str], list[str], list[str]] | None:
    """
    Backtracking CSP: given fixed L1, find L2 letters and word cuts
    such that both ladders segment cleanly and the braid segments into snakes.

    Processes braid positions left to right. At L1 positions the letter is
    fixed; at L2 positions we try letters from snake_next ∩ ladder_next
    (the intersection of what can legally extend the current snake prefix
    and the current L2-word prefix). At every position we also decide
    whether to commit a word boundary for the snake track and, at L2
    positions, for the L2-word track.
    """
    import time

    l2_chars: list[str] = [''] * n
    braid_to_l1 = {p: i for i, p in enumerate(l1_pos)}
    braid_to_l2 = {p: i for i, p in enumerate(l2_pos)}
    total = 2 * n

    def rec(
        bp: int,              # braid position
        sp: str,              # snake prefix
        snakes: list[str],    # committed snakes
        lp: str,              # L2-word prefix
        lwords: list[str],    # committed L2 words
    ) -> tuple | None:
        if time.time() > deadline:
            return None
        if bp == total:
            # Commit trailing snake word
            if sp and (sp not in word_scores or len(sp) < min_snake):
                return None
            final_snakes = snakes + ([sp] if sp else [])
            # Commit trailing L2 word
            if lp and (lp not in word_scores or len(lp) < min_ladder):
                return None
            final_lwords = lwords + ([lp] if lp else [])
            if not final_snakes or not final_lwords:
                return None
            return l2_chars[:], final_lwords, final_snakes

        is_l1 = bp in braid_to_l1
        fixed_letter = l1_chars[braid_to_l1[bp]] if is_l1 else None
        is_last = (bp == total - 1)

        # Candidate letters: for L1 it's fixed; for L2 take the intersection
        # of letters that validly extend the snake prefix AND the L2-word prefix.
        if is_l1:
            candidates = [fixed_letter]
        else:
            s_nexts = snake_next.get(sp, set())
            l_nexts = ladder_next.get(lp, set())
            candidates = list(s_nexts & l_nexts)
            rng.shuffle(candidates)

        for c in candidates:
            new_sp = sp + c
            new_lp = lp + c if not is_l1 else lp

            if not is_l1:
                l2_chars[braid_to_l2[bp]] = c

            # Determine what commits are legal here
            can_commit_snake = (new_sp in word_scores and len(new_sp) >= min_snake)
            can_cont_snake = (new_sp in snake_next and len(new_sp) < max_snake
                              and not is_last)

            can_commit_l2 = (not is_l1 and new_lp in word_scores
                             and len(new_lp) >= min_ladder)
            can_cont_l2 = (not is_l1 and new_lp in ladder_next
                           and len(new_lp) < max_ladder)

            # At the last braid position we MUST commit the snake.
            if is_last and not can_commit_snake:
                if not is_l1:
                    l2_chars[braid_to_l2[bp]] = ''
                continue

            # Build the set of (snake_commit, l2_commit) options to try
            options: list[tuple[bool, bool]] = []
            for sc in ([True, False] if not is_last else [True]):
                if sc and not can_commit_snake:
                    continue
                if not sc and not can_cont_snake:
                    continue
                if is_l1:
                    options.append((sc, False))
                else:
                    for lc in [True, False]:
                        if lc and not can_commit_l2:
                            continue
                        if not lc and not can_cont_l2:
                            continue
                        options.append((sc, lc))

            for sc, lc in options:
                next_sp = '' if sc else new_sp
                next_snakes = (snakes + [new_sp]) if sc else snakes
                next_lp = '' if (lc and not is_l1) else new_lp
                next_lwords = (lwords + [new_lp]) if (lc and not is_l1) else lwords

                result = rec(bp + 1, next_sp, next_snakes, next_lp, next_lwords)
                if result is not None:
                    return result

            if not is_l1:
                l2_chars[braid_to_l2[bp]] = ''

        return None

    return rec(0, '', [], '', [])


def generate_puzzle(
    word_scores: dict[str, int],
    target_len: int = 15,
    min_ladder_word: int = 3,
    max_ladder_word: int = 7,
    min_snake: int = 3,
    max_snake: int = 12,
    max_tries: int = 200,
    time_limit: float = 60.0,
    seed: int = 42,
) -> tuple[list[str], list[str], list[str]] | None:
    """
    Generate a valid puzzle using CSP backtracking.

    Strategy: randomly sample L1 word sequences; for each L1, backtrack
    over L2 letter choices enforcing snake-prefix and L2-word-prefix
    constraints simultaneously (intersection pruning).  Much more efficient
    than blind random search.
    """
    import time

    rng = random.Random(seed)
    deadline = time.time() + time_limit

    l1_pos, l2_pos = braid_positions(target_len)

    words_by_len: dict[int, list[str]] = defaultdict(list)
    for word, score in word_scores.items():
        if min_ladder_word <= len(word) <= max_ladder_word:
            words_by_len[len(word)].append(word)

    print(f"Building prefix index …", end=" ", flush=True)
    snake_next = _build_next_letters(word_scores, max_snake)
    ladder_next = _build_next_letters(word_scores, max_ladder_word)
    print("done")
    print(f"Generating puzzle (ladder={target_len} letters, seed={seed}, "
          f"time limit={time_limit:.0f}s) …")

    for attempt in range(1, max_tries + 1):
        if time.time() > deadline:
            print(f"  Time limit reached after {attempt-1} L1 trials.")
            break

        l1_words = _random_word_sequence(words_by_len, target_len,
                                          min_ladder_word, max_ladder_word, rng)
        if l1_words is None:
            continue

        l1_chars = list(''.join(l1_words))
        print(f"  L1 trial {attempt}: {' '.join(l1_words)} … ", end="", flush=True)

        result = _csp_solve(
            l1_chars, word_scores, snake_next, ladder_next,
            l1_pos, l2_pos, target_len,
            min_snake, max_snake, min_ladder_word, max_ladder_word,
            rng, deadline,
        )

        if result is not None:
            l2_chars, l2_words, snakes = result
            print("found!")
            return l1_words, l2_words, snakes
        else:
            print("no solution")

    return None


# ── Display ───────────────────────────────────────────────────────────────────

def _snake_breakdown(
    snake: str,
    braid_offset: int,
    pos_source: dict[int, tuple[str, int]],
    braid: list[str],
) -> str:
    """Return human-readable breakdown like 'H(L1) + AB(L2) + IT(L1) + AT(L2)'."""
    parts: list[str] = []
    i = braid_offset
    end = braid_offset + len(snake)
    while i < end:
        src = pos_source[i][0]
        run = 1
        while i + run < end and pos_source[i + run][0] == src:
            run += 1
        letters = ''.join(braid[i:i + run])
        parts.append(f"{letters}({src})")
        i += run
    return ' + '.join(parts)


def display_puzzle(
    l1_words: list[str],
    l2_words: list[str],
    snake_words: list[str],
) -> None:
    l1 = list(''.join(l1_words))
    l2 = list(''.join(l2_words))
    n = len(l1)
    l1_pos, l2_pos = braid_positions(n)
    braid = make_braid(l1, l2)

    pos_source: dict[int, tuple[str, int]] = {}
    for i, p in enumerate(l1_pos):
        pos_source[p] = ('L1', i)
    for i, p in enumerate(l2_pos):
        pos_source[p] = ('L2', i)

    bar = '═' * 56
    print(f"\n{bar}")
    print("  SNAKES & LADDERS WORD PUZZLE")
    print(bar)

    def ladder_line(words: list[str]) -> str:
        return '  '.join(w for w in words)

    print(f"\n  LADDER 1 ({n} letters):  {ladder_line(l1_words)}")
    print(f"  {'  '.join(l1)}")
    print(f"\n  LADDER 2 ({n} letters):  {ladder_line(l2_words)}")
    print(f"  {'  '.join(l2)}")

    print(f"\n  SNAKES ({len(snake_words)} words, {sum(len(s) for s in snake_words)} letters total):")
    offset = 0
    for snake in snake_words:
        breakdown = _snake_breakdown(snake, offset, pos_source, braid)
        print(f"    {snake:<16} ←  {breakdown}")
        offset += len(snake)

    print(f"\n{bar}\n")


# ── Verify ────────────────────────────────────────────────────────────────────

def verify_puzzle(
    l1_words: list[str],
    l2_words: list[str],
    snake_words: list[str],
    word_scores: dict[str, int],
) -> bool:
    l1 = list(''.join(l1_words))
    l2 = list(''.join(l2_words))
    if len(l1) != len(l2):
        print(f"✗ L1 has {len(l1)} letters, L2 has {len(l2)} — must match.")
        return False

    braid = make_braid(l1, l2)
    expected = ''.join(braid)
    actual = ''.join(snake_words)

    if expected != actual:
        print("✗ Snake letters don't match braid.")
        print(f"  Braid:  {expected}")
        print(f"  Snakes: {actual}")
        return False

    bad_words = []
    for w in l1_words + l2_words + snake_words:
        if w not in word_scores:
            bad_words.append(w)
    if bad_words:
        print(f"⚠ Words not in wordlist: {', '.join(bad_words)}")

    print("✓ Valid puzzle!")
    return True


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Snakes & Ladders word puzzle builder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # check
    chk = sub.add_parser("check", help="Given ladder words, find snakes")
    chk.add_argument("ladder1", help='Ladder 1 words, space-separated (quote it): "HITCH SENATE BOGUS"')
    chk.add_argument("ladder2", help='Ladder 2 words, space-separated')
    chk.add_argument("--min-snake", type=int, default=3)
    chk.add_argument("--max-snake", type=int, default=12)
    chk.add_argument("--min-score", type=int, default=50)

    # generate
    gen = sub.add_parser("generate", help="Search for a valid puzzle")
    gen.add_argument("--length", type=int, default=15, help="Ladder length in letters (default 15)")
    gen.add_argument("--min-word", type=int, default=3, help="Min letters per ladder word")
    gen.add_argument("--max-word", type=int, default=7, help="Max letters per ladder word")
    gen.add_argument("--min-snake", type=int, default=3)
    gen.add_argument("--max-snake", type=int, default=12)
    gen.add_argument("--tries", type=int, default=200, help="Max L1 sequences to try")
    gen.add_argument("--time-limit", type=float, default=60.0, help="Total time budget in seconds")
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--min-score", type=int, default=50)

    # verify
    ver = sub.add_parser("verify", help="Verify a complete puzzle")
    ver.add_argument("ladder1")
    ver.add_argument("ladder2")
    ver.add_argument("snakes", help='Snake words space-separated: "HABITAT CHEESE MINARET EARBONE GUSTS"')
    ver.add_argument("--min-score", type=int, default=50)

    args = parser.parse_args()

    if not WORDLIST_PATH.exists():
        print(f"Error: wordlist not found at {WORDLIST_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading wordlist … ", end="", flush=True)
    word_scores = load_wordlist(WORDLIST_PATH, getattr(args, "min_score", 50))
    print(f"{len(word_scores):,} words")

    if args.cmd == "check":
        l1_words = [w.upper() for w in args.ladder1.split()]
        l2_words = [w.upper() for w in args.ladder2.split()]
        for w in l1_words + l2_words:
            if w not in word_scores:
                print(f"  Warning: '{w}' not in wordlist")
        snakes = check_puzzle(l1_words, l2_words, word_scores, args.min_snake, args.max_snake)
        if snakes:
            display_puzzle(l1_words, l2_words, snakes)
        else:
            print("No valid snake segmentation found for these ladders.")

    elif args.cmd == "generate":
        result = generate_puzzle(
            word_scores,
            target_len=args.length,
            min_ladder_word=args.min_word,
            max_ladder_word=args.max_word,
            min_snake=args.min_snake,
            max_snake=args.max_snake,
            max_tries=args.tries,
            time_limit=args.time_limit,
            seed=args.seed,
        )
        if result:
            l1_words, l2_words, snakes = result
            display_puzzle(l1_words, l2_words, snakes)
        else:
            print(f"No valid puzzle found after {args.tries:,} attempts. Try a different --seed.")

    elif args.cmd == "verify":
        l1_words = [w.upper() for w in args.ladder1.split()]
        l2_words = [w.upper() for w in args.ladder2.split()]
        snake_words = [w.upper() for w in args.snakes.split()]
        ok = verify_puzzle(l1_words, l2_words, snake_words, word_scores)
        if ok:
            display_puzzle(l1_words, l2_words, snake_words)


if __name__ == "__main__":
    main()
