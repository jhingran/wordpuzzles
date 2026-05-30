#!/usr/bin/env python3
"""
clue_gen.py — Interactive cryptic clue generator using Claude API.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python clue_gen.py WORD [WORD2 ...]   # clue specific words
    python clue_gen.py                    # prompts for words interactively

Commands during a session:
    <feedback>       — type anything to refine the clue
    save <clue>      — append the clue to claude_created_clues.txt
    next             — move to next word
    quit             — exit
"""

import os
import sys
from pathlib import Path

CLUE_BANK_FILE = Path("clues_with_answers.txt")
APPROVED_FILE = Path("claude_created_clues.txt")
MODEL = "claude-opus-4-7"

SYSTEM_PROMPT = """\
You are an expert cryptic crossword clue setter in the British style (Times Quick Cryptic standard).

TECHNIQUES:
- Anagram: letters rearranged; indicators: wild, confused, mixed, scrambled, recalculates, upset
- Charade: word parts concatenated in order; no indicator needed
- Hidden word: answer embedded in consecutive clue letters; indicators: in, inside, some, part of
- Reversal: spelled backward; indicators: returned, up (down clues), backs
- Deletion: letters removed; indicators: without, out of, nearly (remove last), shelled (remove outer)
- Containment: one word inside another; indicators: in, holding, around, embracing
- Homophone: sounds like; indicators: they say, reportedly, heard
- Double definition: two unrelated definitions, no indicator
- Cryptic definition: single whimsical definition, often ends with ?

RULES:
1. Definition is ALWAYS at the start or end — never buried in the middle.
2. Every non-definition word contributes to wordplay; nothing is filler.
3. Surface reading must be grammatically natural, vivid, and misleading.
4. Letter count goes in parentheses at the end: (9) or (3,5,4).
5. Break compound words at non-obvious boundaries — avoid splits that give the game away.
6. Avoid anagram fodder that shares too many letters with the answer (makes it too easy).
7. Gold standard: surface and wordplay pull in opposite directions simultaneously (&lit).

For each candidate clue show:
  - The clue itself with letter count
  - Technique used
  - Wordplay breakdown (e.g. X=Y, anagram of Z, etc.)
"""


def load_clue_bank() -> str:
    if CLUE_BANK_FILE.exists():
        return CLUE_BANK_FILE.read_text().strip()
    return ""


def save_clue(word: str, clue: str) -> None:
    APPROVED_FILE.touch(exist_ok=True)
    with APPROVED_FILE.open("a") as f:
        f.write(f"{word} ({len(word)}): {clue}\n")
    print(f"  → Saved to {APPROVED_FILE}")


def stream_response(client, history: list[dict]) -> str:
    """Stream Claude's response and return full text."""
    full_text = []
    print("\nClaude: ", end="", flush=True)
    with client.messages.stream(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=history,
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
            full_text.append(text)
    print()
    return "".join(full_text)


def run_word(word: str, client) -> None:
    word = word.upper()
    print(f"\n{'━' * 60}")
    print(f"  Word: {word}  ({len(word)} letters)")
    print(f"{'━' * 60}")

    bank = load_clue_bank()
    preamble = (
        f"Clue bank for reference (Times Quick Cryptic examples):\n\n{bank}\n\n---\n\n"
        if bank else ""
    )
    first_msg = (
        f"{preamble}"
        f"Generate 3 candidate cryptic clues for: **{word}** ({len(word)})\n\n"
        f"Try different techniques. Prefer non-obvious letter breaks."
    )

    history = [{"role": "user", "content": first_msg}]

    while True:
        reply = stream_response(client, history)
        history.append({"role": "assistant", "content": reply})

        print()
        print("  Commands: save <clue text>  |  next  |  quit")
        print("  Or type feedback to refine.\n")

        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

        if not user_input:
            continue

        lower = user_input.lower()
        if lower == "quit":
            sys.exit(0)
        elif lower == "next":
            break
        elif lower.startswith("save "):
            clue_text = user_input[5:].strip()
            save_clue(word, clue_text)
        else:
            history.append({"role": "user", "content": user_input})


def main() -> None:
    try:
        import anthropic
    except ImportError:
        print("Error: anthropic package not installed.")
        print("  pip install anthropic")
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    words = [w.upper() for w in sys.argv[1:]]
    if words:
        for word in words:
            run_word(word, client)
    else:
        print("Cryptic clue generator — powered by Claude")
        print("Enter words to clue, or 'quit' to exit.\n")
        while True:
            try:
                word = input("Word to clue: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not word or word.lower() == "quit":
                break
            run_word(word, client)


if __name__ == "__main__":
    main()
