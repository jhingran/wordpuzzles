#!/usr/bin/env python3
"""
Back-and-Forth: a word-chain puzzle where a string of letters,
when read right-to-left, also forms a valid word chain — but with
word boundaries at entirely different physical positions.

    Forward chain:  S = W₁ · W₂ · … · Wₖ
    Backward chain: reverse(S) = U₁ · U₂ · … · Uₘ
    Constraint:     cut positions of forward and backward chains
                    are completely disjoint within S.

Usage:
    python back_and_forth.py
    python back_and_forth.py --seed 7 --length 15
    python back_and_forth.py --count 5
    python back_and_forth.py --include "LLAMA; NOD"
    python back_and_forth.py --include "TILE:forward; ROSE:backward"
    python back_and_forth.py --png puzzle.png

Include-word direction hints:
    WORD           must appear in either the forward or backward chain
    WORD:forward   must appear as a forward-chain word
    WORD:backward  must appear as a backward-chain word
"""

from __future__ import annotations
import sys
import argparse
import time
import random
from pathlib import Path

WORDLIST_PATH = Path(__file__).parent.parent / "wordlist.dict"

# Words to exclude even if they score well (compounds, abbreviations, proper nouns
# that the frequency-based wordlist doesn't filter out).
DEFAULT_SKIP: set[str] = {
    # internet slang / junk words
    'CATCAFE', 'CATBED', 'CATBEDS', 'UPTOP', 'WOOT', 'METOO', 'IMHOME',
    'GOGETEM', 'PRSTUNT', 'SAVEIT', 'BIGIF', 'DMED', 'FUCKBOY',
    'NSFWPIC', 'PETWEAR', 'SAKEBAR', 'LGBTICON', 'URHAMLET', 'NODUH',
    'RUHROH', 'WHOSWE', 'GOTUP', 'GOFAR', 'GOOUT', 'RUHRO',
    'ZIPUP', 'ZIPPY', 'GAYICON', 'HTMLTAGS', 'OFFICEDJ', 'SPINGYM',
    'NECKTAT', 'LSDTRIP', 'BUMCHINS', 'SPLOOSH', 'SYMBIOT', 'MADEHAY',
    'MAGAHATS', 'TREXPEN', 'FAQPAGE', 'AKNOCKIN', 'CHEATDAY', 'NICEDAY',
    'CATWATER', 'STDTEST', 'RATKINGS', 'HOUSEELF', 'YAKMILK', 'PEPSIOK',
    'BUMDROP', 'TREXARM', 'PRICEGUN', 'AFTERSIX', 'PREGAPS', 'OPENEDUP',
    'GOODGUY', 'FANFILM', 'GAMEFACE', 'DOIN', 'ROSIE', 'KATIE',
    'DRAGWIGS', 'GRASSLE', 'BARRUSH', 'TVWIVES', 'DROOLSON', 'CATTREAT',
    'GOTAHEAD', 'RIDEHERD', 'FAQPAGES', 'FUCKBOIS', 'ITME', 'SHEEPLE',
    'DOGDROOL', 'BANDGEEK', 'MYKONOS', 'SNIPPING',
    'NOVAPING', 'LSDTRIPS', 'SIGNNAME', 'RUMSHOT', 'DRORCHID', 'SHITCANS',
    'KPOPSTAN', 'FUCKBOI', 'DOGTREAT', 'ELMO', 'BRAD',
    # compound words / open compounds that appear fused
    'LASTNAME', 'TOPTENS', 'TOPTEN', 'PARTTIME', 'DOGBEDS', 'BACKLESS',
    'MEGABUCK', 'MEGABUCKS', 'SIDENOTE', 'ADDON', 'ADDONS', 'OLDAGE', 'TIELINE', 'OPEDS',
    # brand names / proper nouns that score high due to text frequency
    'REEBOK', 'REEBOKS', 'KOBE', 'LADADOG', 'EZPASS',
    'NIPSEY', 'BATISTA', 'MILANO', 'PARDONER', 'ROSANNA', 'TALIA',
    'STEVE', 'ANNA', 'ELLA', 'ELBA', 'OTTO', 'RIO', 'ALI', 'ABE',
    'LANA', 'DANA', 'GRETA', 'DRED', 'LUC', 'ROC', 'CELESTE', 'TODD', 'ERIC',
    'KRISTI', 'POOLE', 'RICCI', 'DUNNE', 'SNAPE',
    # acronyms / initialisms
    'NATO', 'OPEC', 'UEFA', 'NASA', 'NOAA', 'DNA', 'RNA', 'AIDS',
    # place names
    'BRISTOL', 'NILE', 'ROME', 'LIMA', 'OSLO', 'BALI',
    # programming/internet placeholders
    'FOO', 'BAR', 'BAZ', 'FOOBAR',
}



# ── Wordlist ───────────────────────────────────────────────────────────────────

def load_wordlist(path: Path, min_score: int = 50) -> dict[str, int]:
    words: dict[str, int] = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if ';' not in line:
                    continue
                w, s = line.split(';', 1)
                w = w.upper()
                if not w.isalpha():
                    continue
                try:
                    score = int(s)
                    if score >= min_score:
                        words[w] = score
                except ValueError:
                    pass
    except FileNotFoundError:
        print(f"Wordlist not found: {path}", file=sys.stderr)
        sys.exit(1)
    return words


# ── Include word parser ────────────────────────────────────────────────────────

def parse_include(s: str) -> dict[str, str]:
    """
    Parse --include string into {WORD: direction}.
    Direction is 'forward', 'backward', or 'any'.
    Format: "WORD; WORD:forward; WORD:backward"
    """
    result: dict[str, str] = {}
    for part in s.split(';'):
        part = part.strip()
        if not part:
            continue
        if ':' in part:
            word, hint = part.rsplit(':', 1)
            hint = hint.strip().lower()
            if hint not in ('forward', 'backward'):
                hint = 'any'
        else:
            word, hint = part, 'any'
        result[word.strip().upper()] = hint
    return result


# ── Core DP ───────────────────────────────────────────────────────────────────

def _parseable_avoiding(s: str, word_set: set[str],
                         bad_cuts: set[int],
                         min_len: int, max_len: int) -> bool:
    """True if s can be fully parsed into words with NO cut at any position in bad_cuts."""
    N = len(s)
    ok = bytearray(N + 1)
    ok[0] = 1
    for i in range(N):
        if not ok[i]:
            continue
        for j in range(i + min_len, min(i + max_len, N) + 1):
            if j < N and j in bad_cuts:
                continue
            if not ok[j] and s[i:j] in word_set:
                ok[j] = 1
    return bool(ok[N])


def _one_parse(s: str, word_set: set[str],
               bad_cuts: set[int],
               min_len: int, max_len: int,
               ) -> tuple[list[str], set[int]] | None:
    """Return (word_list, cut_positions_in_s) for one valid parse avoiding bad_cuts, or None."""
    N = len(s)
    prev: list[tuple[int, str] | None] = [None] * (N + 1)
    ok = bytearray(N + 1)
    ok[0] = 1
    for i in range(N):
        if not ok[i]:
            continue
        for j in range(i + min_len, min(i + max_len, N) + 1):
            if j < N and j in bad_cuts:
                continue
            if not ok[j] and s[i:j] in word_set:
                ok[j] = 1
                prev[j] = (i, s[i:j])
    if not ok[N]:
        return None
    words: list[str] = []
    pos = N
    while pos:
        p, w = prev[pos]  # type: ignore[misc]
        words.append(w)
        pos = p
    words.reverse()
    cuts: set[int] = set()
    p = 0
    for w in words[:-1]:
        p += len(w)
        cuts.add(p)
    return words, cuts


# ── Search ─────────────────────────────────────────────────────────────────────

def _extend_once(
    s: str,
    fwd_words: list[str],
    fwd_cuts: set[int],
    fwd_pool: list[str],
    bwd_word_set: set[str],
    word_scores: dict[str, int],
    direction: str,
    min_len: int,
    max_len: int,
) -> tuple | None:
    """
    Try every word in fwd_pool as the next forward word (appended or prepended).
    Returns (score, s2, fwd_words2, fwd_cuts2, bwd_words_in_rev, bwd_cuts2) or None.
    Picks the candidate whose backward words have the highest average score.
    """
    N = len(s)
    best = None
    for W in fwd_pool:
        L = len(W)
        if direction == 'right':
            s2 = s + W
            shifted: set[int] = fwd_cuts | {N}
        else:
            s2 = W + s
            shifted = {L} | {L + c for c in fwd_cuts}
        N2 = len(s2)
        bad_rev = {N2 - c for c in shifted}
        if not _parseable_avoiding(s2[::-1], bwd_word_set, bad_rev, min_len, max_len):
            continue
        res = _one_parse(s2[::-1], bwd_word_set, bad_rev, min_len, max_len)
        if res is None:
            continue
        bwd_in_rev, bwd_cuts_rev = res
        bwd_cuts2 = {N2 - c for c in bwd_cuts_rev}
        if shifted & bwd_cuts2:
            continue
        score = sum(word_scores.get(w, 0) for w in bwd_in_rev) / max(1, len(bwd_in_rev))
        new_fwd = ([W] + fwd_words) if direction == 'left' else (fwd_words + [W])
        if best is None or score > best[0]:
            best = (score, s2, new_fwd, shifted, bwd_in_rev, bwd_cuts2)
    return best


def generate_by_extension(
    target_len: int,
    word_scores: dict[str, int],
    seed: int = 42,
    fwd_min_score: int = 88,
    bwd_min_score: int = 75,
    min_word: int = 3,
    max_word: int = 10,
    base_tries: int = 50_000,
    base_time: float = 15.0,
    skip: set[str] | None = None,
) -> tuple[list[str], list[str], str, set[int], set[int]] | None:
    """
    Find a long puzzle by iterative extension:
      1. Find a short base puzzle with the random algorithm.
      2. Repeatedly prepend or append a forward word, re-checking the full backward parse.
    """
    skip = skip or set()
    bwd_word_set = {w for w, sc in word_scores.items()
                    if sc >= bwd_min_score and min_word <= len(w) <= max_word
                    and w not in skip}
    fwd_pool = sorted(
        [w for w, sc in word_scores.items()
         if sc >= fwd_min_score and min_word <= len(w) <= max_word and w not in skip],
        key=lambda w: -word_scores[w],
    )

    # Step 1: find a short base puzzle
    base = generate(
        target_len=min(17, target_len),
        word_scores=word_scores,
        seed=seed,
        fwd_min_score=fwd_min_score,
        bwd_min_score=bwd_min_score,
        min_fwd_words=3,
        max_fwd_words=4,
        min_word=min_word,
        max_word=8,
        tries=base_tries,
        time_limit=base_time,
        skip=skip,
    )
    if base is None:
        return None
    fwd_words, _, s, fwd_cuts, _ = base

    # Step 2: extend until we hit target_len
    for _ in range(50):
        if len(s) >= target_len:
            break
        ext = _extend_once(s, fwd_words, fwd_cuts, fwd_pool, bwd_word_set,
                           word_scores, 'right', min_word, max_word)
        if ext is None:
            ext = _extend_once(s, fwd_words, fwd_cuts, fwd_pool, bwd_word_set,
                               word_scores, 'left', min_word, max_word)
        if ext is None:
            return None
        _, s, fwd_words, fwd_cuts, bwd_in_rev, bwd_cuts_rev = ext

    # Final parse to get clean bwd_words and bwd_cuts
    N = len(s)
    bad_rev = {N - c for c in fwd_cuts}
    res = _one_parse(s[::-1], bwd_word_set, bad_rev, min_word, max_word)
    if res is None:
        return None
    bwd_words_in_rev, bwd_cuts_in_rev = res
    bwd_cuts = {N - c for c in bwd_cuts_in_rev}
    if fwd_cuts & bwd_cuts:
        return None
    return fwd_words, bwd_words_in_rev, s, fwd_cuts, bwd_cuts

def join_original(
    p1: tuple, p2: tuple,
    bwd_word_set: set[str],
    min_len: int, max_len: int,
) -> tuple | None:
    """
    Try to join two original BnF puzzles by concatenation.
    Tries 4 combinations: (s1 or rev(s1)) × (s2 or rev(s2)).
    When we use rev(si), fwd and bwd roles swap.

    The seam position N1 is a forward cut, so the backward parse must BRIDGE
    it with a single word that spans the boundary — the DP finds this automatically.

    Returns (fwd_words, bwd_words_in_rev, s_T, F_T, B_T) or None.
    """
    fwd1, bwd1, s1, F1, B1 = p1
    fwd2, bwd2, s2, F2, B2 = p2
    N1, N2 = len(s1), len(s2)

    for flip1 in (False, True):
        for flip2 in (False, True):
            if flip1:
                s1_ = s1[::-1]
                fw1 = list(bwd1)          # bwd1[0] is rightmost in s1 = leftmost in rev(s1)
                F1_ = {N1 - b for b in B1}
            else:
                s1_ = s1
                fw1 = list(fwd1)
                F1_ = set(F1)

            if flip2:
                s2_ = s2[::-1]
                fw2 = list(bwd2)
                F2_ = {N2 - b for b in B2}
            else:
                s2_ = s2
                fw2 = list(fwd2)
                F2_ = set(F2)

            s_T = s1_ + s2_
            N_T = N1 + N2

            F_T = F1_ | {N1} | {N1 + f for f in F2_}
            bad_rev = {N_T - c for c in F_T}

            result = _one_parse(s_T[::-1], bwd_word_set, bad_rev, min_len, max_len)
            if result is None:
                continue

            bwd_words_rev, bwd_cuts_rev = result
            B_T = {N_T - c for c in bwd_cuts_rev}

            if F_T & B_T:
                continue

            return fw1 + fw2, bwd_words_rev, s_T, F_T, B_T

    return None


def generate_by_join(
    target_len: int,
    word_scores: dict[str, int],
    seed: int = 42,
    fwd_min_score: int = 90,
    bwd_min_score: int = 80,
    min_word: int = 3,
    max_word: int = 8,
    n_short: int = 200,
    short_time: float = 90.0,
    skip: set[str] | None = None,
) -> tuple | None:
    """
    Generate a long puzzle by joining two shorter ones.
    Generates a pool of short puzzles then tries all pairs via join_original.
    """
    skip = skip or set()
    bwd_word_set = {w for w, sc in word_scores.items()
                    if sc >= bwd_min_score and min_word <= len(w) <= max_word
                    and w not in skip}

    half = target_len // 2
    short_puzzles: list[tuple] = []
    s_seen: set[str] = set()
    t0 = time.time()

    for i in range(n_short):
        if time.time() - t0 > short_time * 0.6:
            break
        remaining = short_time * 0.6 - (time.time() - t0)
        p = generate(
            target_len=half,
            word_scores=word_scores,
            seed=seed + i,
            fwd_min_score=fwd_min_score,
            bwd_min_score=bwd_min_score,
            min_fwd_words=3,
            max_fwd_words=5,
            min_word=min_word,
            max_word=max_word,
            tries=300_000,
            time_limit=min(remaining, 8.0),
            skip=skip,
        )
        if p is None or p[2] in s_seen:
            continue
        s_seen.add(p[2])
        short_puzzles.append(p)

    print(f'  Pool: {len(short_puzzles)} short puzzles, now trying all pairs …')

    for i, p1 in enumerate(short_puzzles):
        for p2 in short_puzzles[i + 1:]:
            result = join_original(p1, p2, bwd_word_set, min_word, max_word)
            if result is not None:
                return result

    return None


def generate(
    target_len: int,
    word_scores: dict[str, int],
    seed: int = 42,
    fwd_min_score: int = 90,
    bwd_min_score: int = 80,
    min_fwd_words: int = 3,
    max_fwd_words: int = 5,
    min_word: int = 3,
    max_word: int = 8,
    tries: int = 500_000,
    time_limit: float = 30.0,
    include_words: dict[str, str] | None = None,
    len_tolerance: int = 3,
    skip: set[str] | None = None,
) -> tuple[list[str], list[str], str, set[int], set[int]] | None:
    """
    Search for a string S where:
      - S = forward word chain
      - reverse(S) = backward word chain
      - forward and backward cut positions are completely disjoint

    Returns (fwd_words, bwd_words, S, fwd_cuts, bwd_cuts) or None.
    bwd_words: listed in right-to-left reading order (first = rightmost in S).
    All cut positions are in original string (left-to-right) coordinates.
    """
    include_words = include_words or {}
    skip = skip or set()

    bwd_word_set = {w for w, sc in word_scores.items()
                    if sc >= bwd_min_score and min_word <= len(w) <= max_word
                    and w not in skip}

    fwd_candidates = [
        w for w, sc in word_scores.items()
        if sc >= fwd_min_score and min_word <= len(w) <= max_word
        and w not in skip
    ]
    fwd_candidates.sort(key=lambda w: -word_scores[w])

    if not fwd_candidates:
        return None

    # Include-words bypass the score filter so names/special words always work
    for w, direction in include_words.items():
        if min_word <= len(w) <= max_word and w not in skip:
            if direction in ('backward',):
                bwd_word_set.add(w)
            else:  # 'forward' or 'any' — add to both so backward parse can use it too
                bwd_word_set.add(w)

    pin_fwd = [w for w, d in include_words.items() if d in ('forward', 'any')]
    pin_bwd = [w for w, d in include_words.items() if d == 'backward']
    pin_any = [w for w, d in include_words.items() if d == 'any']

    rng = random.Random(seed)
    lo = target_len - len_tolerance
    hi = target_len + len_tolerance
    t0 = time.time()

    for _ in range(tries):
        if time.time() - t0 > time_limit:
            break

        n = rng.randint(min_fwd_words, max_fwd_words)

        # Build forward word list, inserting any pinned-forward words
        if pin_fwd:
            pin = rng.choice(pin_fwd)
            rest_count = max(1, n - 1)
            if len(fwd_candidates) < rest_count:
                continue
            rest = rng.sample(fwd_candidates, rest_count)
            insert_at = rng.randint(0, len(rest))
            fwd_words = rest[:insert_at] + [pin] + rest[insert_at:]
        else:
            if len(fwd_candidates) < n:
                continue
            fwd_words = rng.sample(fwd_candidates, n)
            rng.shuffle(fwd_words)

        s = ''.join(fwd_words)
        N = len(s)
        if not (lo <= N <= hi):
            continue

        # Forward cut positions (internal only)
        fwd_cuts: set[int] = set()
        p = 0
        for w in fwd_words[:-1]:
            p += len(w)
            fwd_cuts.add(p)

        # Positions to forbid as cuts in the reversed string
        bad_rev = {N - c for c in fwd_cuts}

        rev = s[::-1]
        if not _parseable_avoiding(rev, bwd_word_set, bad_rev, min_word, max_word):
            continue

        result = _one_parse(rev, bwd_word_set, bad_rev, min_word, max_word)
        if result is None:
            continue

        bwd_words_in_rev, bwd_cuts_rev = result
        # Convert cut positions from reversed-string coords to original-string coords
        bwd_cuts = {N - c for c in bwd_cuts_rev}

        if fwd_cuts & bwd_cuts:   # should not happen, but guard anyway
            continue

        # Check pinned-backward words
        if pin_bwd:
            bwd_set = set(bwd_words_in_rev)
            if not any(w in bwd_set for w in pin_bwd):
                continue

        # Check 'any' include words
        if pin_any:
            fwd_set = set(fwd_words)
            bwd_set = set(bwd_words_in_rev)
            if not any(w in fwd_set or w in bwd_set for w in pin_any):
                continue

        return fwd_words, bwd_words_in_rev, s, fwd_cuts, bwd_cuts

    return None


# ── Display ────────────────────────────────────────────────────────────────────

SEP = '═' * 64

def display(fwd_words: list[str], bwd_words: list[str], s: str,
            fwd_cuts: set[int], bwd_cuts: set[int]) -> None:
    N = len(s)
    print(f'\n  {SEP}')
    print(f'  BACK-AND-FORTH  ({N} letters, '
          f'{len(fwd_words)} fwd / {len(bwd_words)} bwd words)')
    print(f'  {SEP}')
    print()
    print(f'  →  Forward:   {" · ".join(fwd_words)}')
    print(f'  ←  Backward:  {" · ".join(bwd_words)}  (right-to-left)')
    print()

    # Physical grid: one row per reading direction, cuts shown as '|'
    fwd_row: list[str] = []
    bwd_row: list[str] = []
    for i, ch in enumerate(s):
        fwd_row.append(ch)
        bwd_row.append(ch)
        if i < N - 1:
            pos = i + 1
            fwd_row.append('|' if pos in fwd_cuts else ' ')
            bwd_row.append('|' if pos in bwd_cuts else ' ')

    print(f'  →  {" ".join(fwd_row)}')
    print(f'  ←  {" ".join(bwd_row)}')
    print()

    fwd_list = sorted(fwd_cuts)
    bwd_list = sorted(bwd_cuts)
    n_cuts = len(fwd_list) + len(bwd_list)
    print(f'  Forward cuts:  {fwd_list}')
    print(f'  Backward cuts: {bwd_list}')
    shared = fwd_cuts & bwd_cuts
    if shared:
        print(f'  WARNING — shared cuts: {sorted(shared)}')
    else:
        print(f'  All {n_cuts} cuts disjoint ✓')

    print(f'\n  {SEP}\n')


# ── Clue generation ───────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    """Load variables from .env in the project root (one level up from this file)."""
    import os
    for candidate in [
        Path(__file__).parent / '.env',
        Path(__file__).parent.parent / '.env',
    ]:
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())
            break


def generate_clues(
    fwd_words: list[str],
    bwd_words: list[str],
) -> dict[str, str]:
    """
    Call Claude Haiku to write a clue for each word.
    Instructs the model to pick the LEAST common meaning — not the obvious one.
    Returns {} if no API key is found or the anthropic package is missing.
    """
    import os
    _load_dotenv()
    all_words = list(dict.fromkeys(fwd_words + bwd_words))  # dedup, preserve order

    try:
        import anthropic
    except ImportError:
        print('Warning: anthropic package not installed — skipping clues.', file=sys.stderr)
        return {}
    # Accept both the canonical name and the common typo in the .env
    api_key = (os.environ.get('ANTHROPIC_API_KEY')
               or os.environ.get('ANTHOROPIC_KEY')
               or os.environ.get('ANTHROPIC_KEY'))
    if not api_key:
        print('Warning: no Anthropic API key found — skipping clues.', file=sys.stderr)
        return {}

    client = anthropic.Anthropic(api_key=api_key)
    word_list = '\n'.join(all_words)
    prompt = (
        'You are writing clues for a word puzzle. For each word below, write one clue '
        'of 2–5 words.\n\n'
        'Always use the MOST COMMON everyday meaning — the first sense that would come '
        'to mind for a native English speaker. Do NOT use obscure, technical, or secondary '
        'meanings. If a word is commonly known as one thing, clue that thing.\n\n'
        'Good examples:\n'
        '  SLEEPY   → "drowsy"              (everyday sense — not a poppy reference)\n'
        '  STIR     → "mix with a spoon"    (everyday sense — not prison slang)\n'
        '  RING     → "circular band"       (everyday sense)\n'
        '  BALDNESS → "state of hairlessness"\n'
        '  LECTURE  → "educational talk"    (everyday sense — not "to rebuke")\n\n'
        'Rules:\n'
        '- ONE meaning only. Never use "or", slashes, or parenthetical alternatives.\n'
        '- No leading "a", "an", or "the".\n'
        '- Accuracy first. Common sense over cleverness.\n'
        '- Format exactly: WORD: clue text   (one per line, nothing else)\n\n'
        f'Words:\n{word_list}'
    )

    clues: dict[str, str] = {}
    try:
        resp = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=700,
            messages=[{'role': 'user', 'content': prompt}],
        )
        word_set_upper = {w.upper() for w in all_words}
        for line in resp.content[0].text.strip().splitlines():
            if ':' not in line:
                continue
            w, defn = line.split(':', 1)
            w = w.strip().upper()
            if w not in word_set_upper:
                continue
            defn = defn.strip()
            # Safety-net: strip any "or …" alternative that slipped through
            for sep in (' or ', ' / ', '; '):
                if sep in defn:
                    defn = defn.split(sep)[0].rstrip(' ,')
            if defn:
                # Drop placeholder responses the model gives when it can't clue
                _bad_phrases = ('cannot clue', 'proper name', 'proper noun',
                                'unable to', 'no clue', 'n/a', 'not applicable')
                if any(p in defn.lower() for p in _bad_phrases):
                    continue
                clues[w] = defn
    except Exception as e:
        print(f'Warning: clue API call failed: {e}', file=sys.stderr)

    # For any word the model couldn't clue, try again with a simpler prompt
    missing = [w for w in all_words if w not in clues]
    if missing:
        fallback_prompt = (
            'For each word or name below, write a short factual clue of 2–4 words. '
            'Just describe what it is — no cleverness needed. '
            'For proper names give a well-known description (e.g. EINSTEIN: theoretical physicist).\n'
            'Format exactly: WORD: clue text   (one per line, nothing else)\n\n'
            'Words:\n' + '\n'.join(missing)
        )
        try:
            resp2 = client.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=300,
                messages=[{'role': 'user', 'content': fallback_prompt}],
            )
            word_set_upper = {w.upper() for w in missing}
            for line in resp2.content[0].text.strip().splitlines():
                if ':' not in line:
                    continue
                w, defn = line.split(':', 1)
                w = w.strip().upper()
                if w not in word_set_upper:
                    continue
                defn = defn.strip()
                if defn:
                    clues[w] = defn
        except Exception:
            pass

    return clues


# ── PNG helpers ────────────────────────────────────────────────────────────────

import math as _math


def _make_spiral_map(rows: int, cols: int) -> tuple[dict, dict]:
    """Clockwise spiral: return (idx→(row,col), (row,col)→idx) for rows×cols grid."""
    idx_to_pos: dict[int, tuple[int, int]] = {}
    pos_to_idx: dict[tuple[int, int], int] = {}
    idx = 0
    top, bottom, left, right = 0, rows - 1, 0, cols - 1
    while top <= bottom and left <= right:
        for col in range(left, right + 1):
            idx_to_pos[idx] = (top, col); pos_to_idx[(top, col)] = idx; idx += 1
        top += 1
        for row in range(top, bottom + 1):
            idx_to_pos[idx] = (row, right); pos_to_idx[(row, right)] = idx; idx += 1
        right -= 1
        if top <= bottom:
            for col in range(right, left - 1, -1):
                idx_to_pos[idx] = (bottom, col); pos_to_idx[(bottom, col)] = idx; idx += 1
            bottom -= 1
        if left <= right:
            for row in range(bottom, top - 1, -1):
                idx_to_pos[idx] = (row, left); pos_to_idx[(row, left)] = idx; idx += 1
            left += 1
    return idx_to_pos, pos_to_idx


def _best_grid(N: int) -> tuple[int, int]:
    """Return (rows, cols) with rows<=cols, rows*cols==N, minimising cols/rows ratio."""
    best_r, best_c = 1, N
    for r in range(1, _math.isqrt(N) + 1):
        if N % r == 0:
            best_r, best_c = r, N // r   # isqrt loop keeps best closest to square
    return best_r, best_c


def find_aid_words(
    s: str,
    word_scores: dict[str, int],
    fwd_words: list[str],
    bwd_words: list[str],
) -> list[tuple[str, int, int, str] | None]:
    """
    For each row in the spiral grid, find the best-scoring 3-letter word
    (reading left→right or right→left) that is not in the puzzle chains.
    Returns a list of (word, row, col_start, 'fwd'|'bwd') or None per row.
    """
    N = len(s)
    rows, cols = _best_grid(N)
    _, pos_to_idx = _make_spiral_map(rows, cols)
    puzzle_words = set(fwd_words) | set(bwd_words)
    results: list[tuple[str, int, int, str] | None] = []
    for r in range(rows):
        row_str = ''.join(s[pos_to_idx[(r, c)]] for c in range(cols))
        best: tuple[str, int, int, str] | None = None
        best_score = -1
        for start in range(cols - 2):
            sub = row_str[start:start + 3]
            for word, dirn in [(sub, 'fwd'), (sub[::-1], 'bwd')]:
                score = word_scores.get(word, 0)
                if score > best_score and word not in puzzle_words:
                    best_score = score
                    best = (word, r, start, dirn)
        results.append(best)
    return results


def find_specified_aid_words(
    s: str,
    words: list[str],
) -> list[tuple[str, int, int, str]]:
    """
    Find each specified word reading left to right in the spiral grid.
    Returns list of (word, row, col_start, 'fwd'), sorted by (row, col_start).
    Raises ValueError if any word cannot be found.
    """
    N = len(s)
    rows, cols = _best_grid(N)
    _, pos_to_idx = _make_spiral_map(rows, cols)

    results = []
    for raw in words:
        word = raw.strip().upper()
        if not word:
            continue
        found = None
        for r in range(rows):
            row_str = ''.join(s[pos_to_idx[(r, c)]] for c in range(cols))
            idx = row_str.find(word)
            if idx != -1:
                found = (word, r, idx, 'fwd')
                break
        if found is None:
            raise ValueError(f'aid word {word!r} not found reading left to right in any grid row')
        results.append(found)

    results.sort(key=lambda x: (x[1], x[2]))
    return results


def _flow_clue_row(
    draw_obj,
    x0: int, max_x: int, y: int,
    f_hdr, f_clue, row_h: int,
    hdr_text: str, hdr_color: str,
    clue_texts: list[str],
    clue_color: str = '#444444',
    sep_color: str  = '#AAAAAA',
    do_draw: bool   = True,
) -> int:
    """
    Render one flowing clue row (header + semicolon-separated clues, line-wrapped).
    Returns the total height used.
    """
    def tw(text, font) -> int:
        bb = draw_obj.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0]

    x = x0
    cur_y = y
    indent = x0 + 22

    if do_draw:
        draw_obj.text((x, cur_y), hdr_text, fill=hdr_color, font=f_hdr)
    x += tw(hdr_text, f_hdr) + 6

    for i, clue_text in enumerate(clue_texts):
        has_sep = i < len(clue_texts) - 1
        sep = ';  ' if has_sep else ''
        item_w = tw(clue_text, f_clue)

        if x + item_w > max_x and x > indent:
            cur_y += row_h
            x = indent

        if do_draw:
            draw_obj.text((x, cur_y), clue_text, fill=clue_color, font=f_clue)
        x += item_w

        if has_sep:
            sep_w = tw(sep, f_clue)
            if do_draw:
                draw_obj.text((x, cur_y), sep, fill=sep_color, font=f_clue)
            x += sep_w

    return cur_y + row_h - y


def _load_font(size: int):
    from PIL import ImageFont
    for path in [
        '/System/Library/Fonts/Helvetica.ttc',
        '/System/Library/Fonts/Arial.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    ]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def draw_puzzle_png(
    fwd_words: list[str],
    bwd_words: list[str],
    s: str,
    fwd_cuts: set[int],
    bwd_cuts: set[int],
    clues: dict[str, str],
    output_path: str,
    *,
    solved: bool = False,
) -> None:
    """
    Render the puzzle as a PNG.

    solved=False  →  blank cells (for the solver).
    solved=True   →  filled letters (answer key).

    Layout (top to bottom):
      title / subtitle
      letter cells (forward numbers in top-left corners, backward in bottom-right)
      clue section: two columns, forward on left, backward on right
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print('Error: Pillow not installed — pip install Pillow', file=sys.stderr)
        return

    N    = len(s)
    n_fw = len(fwd_words)
    n_bw = len(bwd_words)

    # ── Geometry constants ──
    PAD_H    = 30    # horizontal padding
    PAD_V    = 26    # vertical padding (top and bottom)
    TITLE_H  = 44
    SUB_H    = 22
    GGAP     = 18    # subtitle → cells
    CLUE_GAP = 34    # cells → clue section
    HDR_H    = 28    # clue-section header height
    DIV_H    = 8
    ROW_H    = 22

    MAX_W = 900
    CELL  = max(28, min(50, (MAX_W - 2 * PAD_H) // N))
    grid_w = N * CELL
    img_w  = max(MAX_W, grid_w + 2 * PAD_H)
    gx0    = (img_w - grid_w) // 2   # grid x-origin (centred)

    n_rows  = max(n_fw, n_bw)
    clue_h  = HDR_H + DIV_H + n_rows * ROW_H + 10
    img_h   = PAD_V + TITLE_H + SUB_H + GGAP + CELL + CLUE_GAP + clue_h + PAD_V

    # ── Colour palette ──
    BG          = '#F8F7F2'
    CELL_BG     = '#FFFFFF'
    CELL_FILLED = '#EEE8DE'
    BORDER      = '#2A2A2A'
    LETTER_C    = '#1A1A2E'
    TITLE_C     = '#1A1A2E'
    SUB_C       = '#666666'
    NUM_C       = '#1A1A2E'
    WORD_C      = '#1A1A2E'
    CLUE_C      = '#555555'
    FWD_HDR_C   = '#1E4D8C'
    BWD_HDR_C   = '#8C3000'
    DIVIDER_C   = '#CCCCCC'
    WATERMARK_C = '#AAAAAA'

    img  = Image.new('RGB', (img_w, img_h), BG)
    draw = ImageDraw.Draw(img)

    f_title  = _load_font(26)
    f_sub    = _load_font(13)
    f_letter = _load_font(max(12, int(CELL * 0.56)))
    f_hdr    = _load_font(15)
    f_clue   = _load_font(13)

    def tw(text: str, font) -> int:
        bb = draw.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0]

    def cx_text(text: str, font, cx: int, y: int, color: str) -> None:
        draw.text((cx - tw(text, font) // 2, y), text, fill=color, font=font)

    # ── Title ──
    y = PAD_V
    cx_text('BACK-AND-FORTH', f_title, img_w // 2, y, TITLE_C)
    y += TITLE_H
    cx_text(f'{N} letters  ·  {n_fw} forward  ·  {n_bw} backward',
            f_sub, img_w // 2, y, SUB_C)
    y += SUB_H + GGAP

    # ── Letter cells ──
    cell_y = y
    for i, ch in enumerate(s):
        cx = gx0 + i * CELL
        fill = CELL_FILLED if solved else CELL_BG
        draw.rectangle([cx, cell_y, cx + CELL - 1, cell_y + CELL - 1],
                       fill=fill, outline=BORDER, width=2)
        if solved:
            bb  = draw.textbbox((0, 0), ch, font=f_letter)
            lw  = bb[2] - bb[0]; lh = bb[3] - bb[1]
            lx  = cx      + (CELL - lw) // 2 - bb[0]
            ly  = cell_y  + (CELL - lh) // 2 - bb[1]
            draw.text((lx, ly), ch, fill=LETTER_C, font=f_letter)

    y += CELL + CLUE_GAP

    # ── Clue section ──
    mid   = img_w // 2
    col1x = PAD_H
    col2x = mid + 12

    draw.text((col1x, y), '→  FORWARD   (left to right)', fill=FWD_HDR_C, font=f_hdr)
    draw.text((col2x, y), '←  BACKWARD  (right to left)', fill=BWD_HDR_C, font=f_hdr)
    y += HDR_H
    draw.line([(col1x, y), (mid - 12, y)], fill=DIVIDER_C, width=1)
    draw.line([(col2x, y), (img_w - PAD_H, y)], fill=DIVIDER_C, width=1)
    y += DIV_H

    for i in range(n_rows):
        ry = y + i * ROW_H
        if i < n_fw:
            w = fwd_words[i]; clue = clues.get(w, '—')
            draw.text((col1x,      ry), f'{i+1}.', fill=FWD_HDR_C, font=f_clue)
            draw.text((col1x + 24, ry), clue,      fill=CLUE_C,    font=f_clue)
        if i < n_bw:
            w = bwd_words[i]; clue = clues.get(w, '—')
            draw.text((col2x,      ry), f'{i+1}.', fill=BWD_HDR_C, font=f_clue)
            draw.text((col2x + 24, ry), clue,      fill=CLUE_C,    font=f_clue)

    # Watermark: PUZZLE or ANSWER in bottom-right corner
    label = 'ANSWER' if solved else 'PUZZLE'
    draw.text((img_w - PAD_H - tw(label, f_sub), img_h - PAD_V // 2 - 10),
              label, fill=WATERMARK_C, font=f_sub)

    img.save(output_path, dpi=(150, 150))
    print(f'  Saved: {output_path}')


def draw_puzzle_png_spiral(
    fwd_words: list[str],
    bwd_words: list[str],
    s: str,
    fwd_cuts: set[int],
    bwd_cuts: set[int],
    clues: dict[str, str],
    output_path: str,
    *,
    solved: bool = False,
    aid_words: list | None = None,
    aid_clues: list[str] | None = None,
) -> None:
    """
    Render the puzzle in a clockwise spiral grid layout.

    aid_words: output of find_aid_words() — list of (word, row, col_start, dirn) or None
    aid_clues: list of clue strings, one per row (aligned with aid_words)
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print('Error: Pillow not installed — pip install Pillow', file=sys.stderr)
        return

    N = len(s)
    rows, cols = _best_grid(N)
    idx_to_pos, _ = _make_spiral_map(rows, cols)

    # ── Geometry ──
    PAD_H    = 30
    PAD_V    = 26
    TITLE_H  = 44
    SUB_H    = 22
    GGAP     = 18
    CLUE_GAP = 28
    ROW_H    = 22
    SEC_GAP  = 10   # vertical gap between clue sections

    CELL   = max(32, min(58, 580 // max(rows, cols)))
    grid_w = cols * CELL
    grid_h = rows * CELL
    img_w  = max(900, grid_w + 2 * PAD_H)
    gx0    = (img_w - grid_w) // 2
    THANKS_H = 18 if aid_words else 0
    gy0    = PAD_V + TITLE_H + SUB_H + THANKS_H + GGAP

    # ── Colours ──
    BG          = '#F8F7F2'
    CELL_BG     = '#FFFFFF'
    CELL_FILLED = '#EEE8DE'
    AID_BG      = '#D6EAF8'    # light blue for aid-word cells
    BORDER      = '#CCCCCC'
    LETTER_C    = '#1A1A2E'
    TITLE_C     = '#1A1A2E'
    SUB_C       = '#666666'
    GROOVE_C    = '#1A1A2E'
    FWD_HDR_C   = '#1E4D8C'
    BWD_HDR_C   = '#8C3000'
    AID_HDR_C   = '#2E7D32'
    CLUE_C      = '#444444'
    SEP_C       = '#AAAAAA'
    DIVIDER_C   = '#DDDDDD'
    WATERMARK_C = '#AAAAAA'

    # ── Fonts (loaded before image creation so we can pre-measure heights) ──
    f_title  = _load_font(26)
    f_sub    = _load_font(13)
    f_letter = _load_font(max(10, int(CELL * 0.45)))
    f_hdr    = _load_font(14)
    f_clue   = _load_font(12)

    # ── Aid-word cell set ──
    aid_cells: set[tuple[int, int]] = set()
    if aid_words:
        for _, r, col_start, _ in aid_words:
            for dc in range(3):
                aid_cells.add((r, col_start + dc))

    # Label for the aid section; show direction arrow(s)
    if aid_words:
        all_fwd = all(dirn == 'fwd' for _, _, _, dirn in aid_words)
        _aid_hdr = 'Aid to solve (left to right):' if all_fwd else 'Aid to solve:'
    else:
        _aid_hdr = 'Aid to solve:'

    # ── Clue section header strings ──
    fwd_hdr = f'Clockwise (starting from 1):'
    bwd_hdr = f'Anticlockwise (starting from {N}):'

    # ── Pre-compute clue section height (dummy draw for text measurement) ──
    from PIL import Image as _PILImage, ImageDraw as _PILDraw
    _dummy = _PILImage.new('RGB', (img_w, 100))
    _dd    = _PILDraw.Draw(_dummy)

    fwd_clue_texts = [clues.get(w, '—') for w in fwd_words]
    bwd_clue_texts = [clues.get(w, '—') for w in bwd_words]
    aid_texts      = ([c if c else '—' for c in aid_clues] if aid_clues else [])

    clue_h  = _flow_clue_row(_dd, PAD_H, img_w - PAD_H, 0, f_hdr, f_clue, ROW_H,
                              fwd_hdr, FWD_HDR_C, fwd_clue_texts,
                              CLUE_C, SEP_C, do_draw=False)
    clue_h += SEC_GAP + 5   # divider line gap
    clue_h += _flow_clue_row(_dd, PAD_H, img_w - PAD_H, 0, f_hdr, f_clue, ROW_H,
                              bwd_hdr, BWD_HDR_C, bwd_clue_texts,
                              CLUE_C, SEP_C, do_draw=False)
    if aid_texts:
        clue_h += SEC_GAP + 5
        clue_h += _flow_clue_row(_dd, PAD_H, img_w - PAD_H, 0, f_hdr, f_clue, ROW_H,
                                 _aid_hdr, AID_HDR_C, aid_texts,
                                 CLUE_C, SEP_C, do_draw=False)
    clue_h += 10  # bottom padding

    img_h = gy0 + grid_h + CLUE_GAP + clue_h + PAD_V

    img  = Image.new('RGB', (img_w, img_h), BG)
    draw = ImageDraw.Draw(img)

    def tw(text: str, font) -> int:
        bb = draw.textbbox((0, 0), text, font=font)
        return bb[2] - bb[0]

    def cx_text(text: str, font, cx: int, y: int, color: str) -> None:
        draw.text((cx - tw(text, font) // 2, y), text, fill=color, font=font)

    # ── Title ──
    y = PAD_V
    cx_text('BACK-AND-FORTH', f_title, img_w // 2, y, TITLE_C)
    y += TITLE_H
    cx_text('Anant Jhingran and Claude, inspired by Will Shortz\'s NY Times puzzles',
            f_sub, img_w // 2, y, SUB_C)
    if aid_words:
        f_thanks = _load_font(11)
        y += SUB_H
        cx_text('(special thanks to Manbir Khurana for helping improve the puzzle)',
                f_thanks, img_w // 2, y, SUB_C)

    # ── Grid cells ──
    f_num = _load_font(9)
    NUM_C = '#555555'
    for idx in range(N):
        row, col = idx_to_pos[idx]
        cx = gx0 + col * CELL
        cy = gy0 + row * CELL
        if (row, col) in aid_cells:
            fill = AID_BG
        elif solved:
            fill = CELL_FILLED
        else:
            fill = CELL_BG
        draw.rectangle([cx, cy, cx + CELL - 1, cy + CELL - 1],
                       fill=fill, outline=BORDER, width=1)
        if solved:
            ch = s[idx]
            bb = draw.textbbox((0, 0), ch, font=f_letter)
            lw, lh = bb[2] - bb[0], bb[3] - bb[1]
            draw.text((cx + (CELL - lw) // 2 - bb[0],
                       cy + (CELL - lh) // 2 - bb[1]),
                      ch, fill=LETTER_C, font=f_letter)
        if idx == 0 or idx == N - 1:
            num = '1' if idx == 0 else str(N)
            draw.text((cx + 2, cy + 2), num, fill=NUM_C, font=f_num)

    # ── Spiral groove ──
    GROOVE_W   = 3
    num_layers = min(rows, cols) // 2
    for layer in range(num_layers):
        by_top    = gy0 + (layer + 1) * CELL
        bx_right  = gx0 + (cols - 1 - layer) * CELL
        by_bottom = gy0 + (rows - 1 - layer) * CELL
        bx_left   = gx0 + (layer + 1) * CELL
        y_next    = gy0 + (layer + 2) * CELL

        draw.line([(gx0 + layer * CELL, by_top), (bx_right, by_top)],
                  fill=GROOVE_C, width=GROOVE_W)
        if by_top < by_bottom:
            draw.line([(bx_right, by_top), (bx_right, by_bottom)],
                      fill=GROOVE_C, width=GROOVE_W)
        if by_top < by_bottom and bx_left < bx_right:
            draw.line([(bx_right, by_bottom), (bx_left, by_bottom)],
                      fill=GROOVE_C, width=GROOVE_W)
        if layer < num_layers - 1:
            draw.line([(bx_left, by_bottom), (bx_left, y_next)],
                      fill=GROOVE_C, width=GROOVE_W)

    # ── Clue section (flowing horizontal rows) ──
    yc = gy0 + grid_h + CLUE_GAP

    def _render_section(hdr_text: str, hdr_color: str, clue_texts: list[str]) -> None:
        nonlocal yc
        yc += _flow_clue_row(draw, PAD_H, img_w - PAD_H, yc, f_hdr, f_clue, ROW_H,
                             hdr_text, hdr_color, clue_texts, CLUE_C, SEP_C, do_draw=True)

    def _divider() -> None:
        nonlocal yc
        yc += SEC_GAP
        draw.line([(PAD_H, yc), (img_w - PAD_H, yc)], fill=DIVIDER_C, width=1)
        yc += 5

    _render_section(fwd_hdr, FWD_HDR_C, fwd_clue_texts)
    _divider()
    _render_section(bwd_hdr, BWD_HDR_C, bwd_clue_texts)
    if aid_texts:
        _divider()
        _render_section(_aid_hdr, AID_HDR_C, aid_texts)

    label = 'ANSWER' if solved else 'PUZZLE'
    draw.text((img_w - PAD_H - tw(label, f_sub), img_h - PAD_V // 2 - 10),
              label, fill=WATERMARK_C, font=f_sub)

    img.save(output_path, dpi=(150, 150))
    print(f'  Saved: {output_path}')


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description='Back-and-Forth word puzzle generator',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument('--seed',           type=int,   default=42)
    ap.add_argument('--length',         type=int,   default=14,
                    help='Target string length (default 14, ±tolerance)')
    ap.add_argument('--len-tolerance',  type=int,   default=3,
                    help='±tolerance on target length (default 3)')
    ap.add_argument('--min-score',      type=int,   default=90,
                    help='Min quality score for forward-chain words (default 90)')
    ap.add_argument('--min-score-bwd',  type=int,   default=80,
                    help='Min quality score for backward-chain words (default 80)')
    ap.add_argument('--min-words',      type=int,   default=3,
                    help='Min words in forward chain (default 3)')
    ap.add_argument('--max-words',      type=int,   default=5,
                    help='Max words in forward chain (default 5)')
    ap.add_argument('--min-word',       type=int,   default=3,
                    help='Min word length (default 3)')
    ap.add_argument('--max-word',       type=int,   default=8,
                    help='Max word length (default 8)')
    ap.add_argument('--tries',          type=int,   default=500_000,
                    help='Search attempts (default 500,000)')
    ap.add_argument('--time-limit',     type=float, default=30.0,
                    help='Time budget in seconds (default 30)')
    ap.add_argument('--count',          type=int,   default=1,
                    help='Number of distinct puzzles to find (default 1)')
    ap.add_argument('--include',        metavar='WORDS', default='',
                    help='Semicolon-separated words; append :forward or :backward')
    ap.add_argument('--skip',           metavar='WORDS', default='',
                    help='Additional semicolon-separated words to exclude')
    ap.add_argument('--png',            metavar='FILE', default=None,
                    help='Save puzzle PNG (and a companion _answer.png)')
    ap.add_argument('--strategy',       choices=['random', 'extend', 'join'],
                    default=None,
                    help='Search strategy: random (default for short), extend (default for long), '
                         'or join (pool of short puzzles joined in pairs)')
    ap.add_argument('--aid-to-solve',  action='store_true',
                    help='Auto-find one 3-letter hidden word per row; shade and clue them')
    ap.add_argument('--aid-words',     metavar='WORDS', default='',
                    help='Semicolon-separated words to highlight as solving aids (read left to right)')
    args = ap.parse_args()

    print('Loading wordlist … ', end='', flush=True)
    min_score_load = min(args.min_score, args.min_score_bwd)
    word_scores = load_wordlist(WORDLIST_PATH, min_score_load)
    print(f'{len(word_scores):,} words')

    skip_words = DEFAULT_SKIP.copy()
    if args.skip:
        skip_words.update(w.strip().upper() for w in args.skip.split(';') if w.strip())

    include_words = parse_include(args.include) if args.include else {}
    if include_words:
        print(f'Include words: {", ".join(f"{w}({d})" for w, d in include_words.items())}')

    # Determine strategy
    strategy = args.strategy
    if strategy is None:
        strategy = 'extend' if args.length > 22 else 'random'

    if strategy == 'join':
        print(f'Searching via join (target≈{args.length}, seed={args.seed}) …')
    elif strategy == 'extend':
        print(f'Searching via extension (target≥{args.length}, seed={args.seed}) …')
    else:
        print(f'Searching (length≈{args.length}±{args.len_tolerance}, seed={args.seed}) …')
    t0 = time.time()

    found = 0
    seed = args.seed
    seen: set[str] = set()
    per_try = max(50_000, args.tries // max(1, args.count))

    while found < args.count:
        remaining = args.time_limit - (time.time() - t0)
        if remaining <= 0:
            break

        if strategy == 'join':
            result = generate_by_join(
                target_len=args.length,
                word_scores=word_scores,
                seed=seed,
                fwd_min_score=args.min_score,
                bwd_min_score=args.min_score_bwd,
                min_word=args.min_word,
                max_word=args.max_word,
                n_short=300,
                short_time=min(remaining, args.time_limit),
                skip=skip_words,
            )
        elif strategy == 'extend':
            result = generate_by_extension(
                target_len=args.length,
                word_scores=word_scores,
                seed=seed,
                fwd_min_score=args.min_score,
                bwd_min_score=args.min_score_bwd,
                min_word=args.min_word,
                max_word=args.max_word,
                base_tries=per_try,
                base_time=min(remaining, 30.0),
                skip=skip_words,
            )
        else:
            result = generate(
                target_len=args.length,
                word_scores=word_scores,
                seed=seed,
                fwd_min_score=args.min_score,
                bwd_min_score=args.min_score_bwd,
                min_fwd_words=args.min_words,
                max_fwd_words=args.max_words,
                min_word=args.min_word,
                max_word=args.max_word,
                tries=per_try,
                time_limit=remaining,
                include_words=include_words,
                len_tolerance=args.len_tolerance,
                skip=skip_words,
            )
        seed += 1

        if result is None:
            continue

        fwd_words, bwd_words, s, fwd_cuts, bwd_cuts = result
        if s in seen:
            continue
        seen.add(s)

        elapsed = time.time() - t0
        if args.count > 1:
            print(f'Puzzle {found + 1} found in {elapsed:.2f}s.')
        else:
            print(f'Found in {elapsed:.2f}s.')

        display(fwd_words, bwd_words, s, fwd_cuts, bwd_cuts)

        if args.png:
            p = Path(args.png)
            # When count > 1, number each output file
            stem   = f'{p.stem}_{found}' if args.count > 1 else p.stem
            suffix = p.suffix or '.png'
            puzzle_path = str(p.parent / f'{stem}{suffix}')
            answer_path = str(p.parent / f'{stem}_answer{suffix}')

            print('Generating clues … ', end='', flush=True)
            clues = generate_clues(fwd_words, bwd_words)
            if clues:
                print(f'{len(clues)} clues.')
            else:
                print('none (set ANTHROPIC_API_KEY to enable).')

            # Aid-to-solve: specified words or auto-found, one per row
            aid_words = None
            aid_clues_list = None
            if args.aid_words:
                specified = [w.strip() for w in args.aid_words.split(';') if w.strip()]
                try:
                    aid_words = find_specified_aid_words(s, specified)
                except ValueError as e:
                    print(f'Warning: {e}', file=sys.stderr)
                    aid_words = []
            elif args.aid_to_solve:
                raw = find_aid_words(s, word_scores, fwd_words, bwd_words)
                aid_words = [item for item in raw if item is not None]

            if aid_words:
                print('Generating aid clues … ', end='', flush=True)
                aid_clue_dict = generate_clues([w for w, *_ in aid_words], [])
                aid_clues_list = [aid_clue_dict.get(w, '—') for w, *_ in aid_words]
                print(f'{len(aid_clue_dict)} aid clues.')

            N = len(s)
            use_spiral = N > 30
            if use_spiral:
                draw_puzzle_png_spiral(fwd_words, bwd_words, s, fwd_cuts, bwd_cuts,
                                       clues, puzzle_path, solved=False,
                                       aid_words=aid_words, aid_clues=aid_clues_list)
                draw_puzzle_png_spiral(fwd_words, bwd_words, s, fwd_cuts, bwd_cuts,
                                       clues, answer_path, solved=True,
                                       aid_words=aid_words, aid_clues=aid_clues_list)
            else:
                draw_puzzle_png(fwd_words, bwd_words, s, fwd_cuts, bwd_cuts,
                                clues, puzzle_path, solved=False)
                draw_puzzle_png(fwd_words, bwd_words, s, fwd_cuts, bwd_cuts,
                                clues, answer_path, solved=True)

        found += 1

    if found == 0:
        elapsed = time.time() - t0
        print(f'\nNo solution found in {elapsed:.1f}s.')
        print('Try: --length different value, --min-score lower, --len-tolerance larger.')
        sys.exit(1)


if __name__ == '__main__':
    main()
