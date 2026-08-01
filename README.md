# Word Puzzle Generator

A Python toolkit for generating and cluing word puzzles.

| Module | Description |
|--------|-------------|
| [`cryptic/`](cryptic/README.md) | British-style crossword grid generator, CSP filler, and cryptic clue generator |
| [`snakes_ladders/`](snakes_ladders/README.md) | Snakes & Ladders word puzzle (inspired by Eric Berlin's Jelly Roll) |
| [`interlocking/`](interlocking/README.md) | Interlocking Squares — diamond-shaped grid with shared corner words |
| `wordlist.dict` | Shared quality-scored word list (~252k entries) |

See [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md) for wordlist source, algorithm papers, and puzzle inspiration credits.

---

## Requirements

- Python 3.10+
- Pillow (`pip install Pillow`)
- anthropic (`pip install anthropic`) — only for clue generation via Claude API
