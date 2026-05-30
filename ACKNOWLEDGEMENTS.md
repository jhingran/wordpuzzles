# Acknowledgements

This project builds on a body of work in constraint satisfaction, crossword construction AI, and open wordlist curation. We are grateful to the following.

---

## Wordlist

**spread the wordlist**
https://www.spreadthewordlist.com/

The `wordlist.dict` file used in this project is from *spread the wordlist*, a freely available, quality-scored crossword wordlist (~303,000 entries). Words are scored 0–100; this project filters to score ≥ 50 ("clean" entries). Format: `WORD;SCORE` (semicolon-separated).

---

## Algorithms

### Constraint Satisfaction — Backtracking, MRV, Forward Checking

**Russell, S.J. and Norvig, P.**
*Artificial Intelligence: A Modern Approach*, 4th Edition.
Pearson, 2021. ISBN: 9780134610993.

Chapter 5 covers backtracking search for CSPs, the Minimum Remaining Values (MRV) heuristic, degree heuristic for tiebreaking, and forward checking. These are the core techniques used in `filler.py`.

### Crossword Filling as a Search Problem

**Ginsberg, M.L., Frank, M.C., Halpin, M.P., and Torrance, M.C.**
"Search Lessons Learned from Crossword Puzzles."
*Proceedings of the Eighth National Conference on Artificial Intelligence (AAAI-90)*, pp. 210–215, 1990.
https://cdn.aaai.org/AAAI/1990/AAAI90-032.pdf

The paper that established crossword grid filling as a canonical CSP benchmark and analysed the relative merits of backjumping, arc consistency, and dynamic constraint ordering — lessons that directly inform this project's variable ordering and pruning strategy.

### Dr.Fill — Weighted CSP Crossword Solver

**Ginsberg, M.L.**
"Dr.Fill: Crosswords and an Implemented Solver for Singly Weighted CSPs."
arXiv:1401.4597, 2014.
https://arxiv.org/abs/1401.4597

Dr.Fill frames crossword filling as a *weighted* CSP (maximising total word quality) and introduces limited discrepancy search and post-processing passes. Our local optimizer (`local_optimize()`) and quality-score-driven value ordering are inspired by this framing.

### PROVERB — Probabilistic Crossword Solving

**Littman, M.L., Keim, G.A., and Shazeer, N.M.**
"Solving Crosswords with PROVERB."
*Proceedings of the Sixteenth National Conference on Artificial Intelligence (AAAI-99)*, 1999.
https://cdn.aaai.org/AAAI/1999/AAAI99-135.pdf

PROVERB combines probabilistic clue-answer scoring with CSP grid filling — a two-stage architecture that cleanly separates clue interpretation from layout constraint satisfaction.

### Complexity of Crossword Filling

**Gourvès, L., Harutyunyan, A., Lampis, M., and Melissinos, N.**
"Filling Crosswords is Very Hard."
*Theoretical Computer Science*, 2023. Also: arXiv:2109.11203.
https://arxiv.org/abs/2109.11203

Establishes NP-hardness of crossword filling even under structural restrictions — good theoretical context for why a backtracking CSP approach (rather than a polynomial-time algorithm) is the right tool.

---

## Further Reading

- Dechter, R. *Constraint Processing*. Morgan Kaufmann, 2003. — comprehensive reference on arc consistency (AC-3) and constraint propagation.
- Wehar, M. *Automatic Crossword Puzzle Filling*. https://github.com/MichaelWehar/Automatic-Crossword-Puzzle-Filling — open-source backtracking implementation with pruning heuristics.
