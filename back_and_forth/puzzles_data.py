# Saved puzzle data for Back-and-Forth puzzles.
#
# Each puzzle is a dict with keys:
#   s          – the letter string
#   fwd_words  – forward chain (left to right)
#   bwd_words  – backward chain (right to left, stated left to right)
#   fwd_cuts   – cut positions in s (set of ints)
#   bwd_cuts   – cut positions in s (set of ints)
#   clues      – dict[word -> clue string]
#   aid_words  – list of (word, row, col_start, 'fwd'|'bwd'), or None
#   aid_clues  – list of clue strings aligned with aid_words, or None
#
# To render:
#   from back_and_forth import draw_puzzle_png_spiral
#   p = PUZZLES['hundred']
#   draw_puzzle_png_spiral(
#       p['fwd_words'], p['bwd_words'], p['s'],
#       p['fwd_cuts'],  p['bwd_cuts'],  p['clues'],
#       'images/hundred_spiral.png', solved=False,
#       aid_words=p['aid_words'], aid_clues=p['aid_clues'],
#   )

PUZZLES = {

    # ── 100-letter puzzle (10×10 spiral) ─────────────────────────────────────
    # Built by joining two sub-puzzles; see back_and_forth/README.md §Building long puzzles
    # Aid words: MOD, ASP, TAP, UTI, ALE, CAL, LET, APE (left→right, rows 1,1,2,2,7,7,8,8)
    'hundred': {
        's': (
            'LECTURESLEEPYTWOSTARBALDNESSBACKSIDE'
            'MODEGASPIPETILEPANATELABEERTAPSMUTATE'
            'MACEBELTBUSKNITSTIRPLUCKSUM'
        ),
        'fwd_words': [
            'LECTURE', 'SLEEPY', 'TWOSTAR', 'BALDNESS', 'BACKSIDE',
            'MODE', 'GASPIPE', 'TILE', 'PANATELA', 'BEERTAP',
            'SMU', 'TATE', 'MACE', 'BELT', 'BUSK', 'NIT', 'STIR', 'PLUCK', 'SUM',
        ],
        'bwd_words': [
            'MUSK', 'CULPRIT', 'STINK', 'SUBTLE', 'BECAME', 'TATUM',
            'SPA', 'TREE', 'BALE', 'TAN', 'APE', 'LITE', 'PIP', 'SAGE',
            'DOME', 'DISK', 'CABS', 'SEND', 'LABRAT', 'SOW', 'TYPE', 'ELSE', 'RUT', 'CEL',
        ],
        'fwd_cuts': {7, 13, 20, 28, 36, 40, 47, 51, 59, 66, 69, 73, 77, 81, 85, 88, 92, 97},
        'bwd_cuts': {3, 6, 10, 14, 17, 23, 27, 31, 35, 39, 43, 46, 50, 53, 56, 60, 64, 67, 72, 78, 84, 89, 96},
        'clues': {
            'LECTURE':  'scold',
            'SLEEPY':   'drowsy',
            'TWOSTAR':  'mediocre rating',
            'BALDNESS': 'state of hairlessness',
            'BACKSIDE': 'rear end',
            'MODE':     'a statistical figure',
            'GASPIPE':  'tight trouser leg',
            'TILE':     'floor covering piece',
            'PANATELA': 'long thin cigar',
            'BEERTAP':  'keg dispenser',
            'SMU':      'Dallas university, commonly called',
            'TATE':     'art gallery in London',
            'MACE':     'spice from nutmeg',
            'BELT':     'waist fastener',
            'BUSK':     'perform on street',
            'NIT':      'louse egg',
            'STIR':     'mix with spoon',
            'PLUCK':    'pull out forcefully',
            'SUM':      'total amount',
            'MUSK':     'strong animal scent',
            'CULPRIT':  'person who committed crime',
            'STINK':    'bad smell',
            'SUBTLE':   'not obvious',
            'BECAME':   'turned into',
            'TATUM':    'actor Channing',
            'SPA':      'relaxation resort',
            'TREE':     'woody plant',
            'BALE':     'bundle of hay',
            'TAN':      'brown skin color',
            'APE':      'large primate',
            'LITE':     'low-alcohol beer suffix',
            'PIP':      'small seed',
            'SAGE':     'wise person',
            'DOME':     'rounded roof',
            'DISK':     'flat circular object',
            'CABS':     'taxi vehicles',
            'SEND':     'mail something',
            'LABRAT':   'research animal',
            'SOW':      'plant seeds',
            'TYPE':     'category',
            'ELSE':     'otherwise',
            'RUT':      'groove in ground',
            'CEL':      'animation frame',
        },
        # aid_words: (word, row, col_start, direction) — all left→right
        'aid_words': [
            ('MOD', 1, 1, 'fwd'),
            ('ASP', 1, 6, 'fwd'),
            ('TAP', 2, 1, 'fwd'),
            ('UTI', 2, 6, 'fwd'),
            ('ALE', 7, 1, 'fwd'),
            ('CAL', 7, 6, 'fwd'),
            ('LET', 8, 1, 'fwd'),
            ('APE', 8, 6, 'fwd'),
        ],
        'aid_clues': [
            'stylish 1960s fashion',  # MOD
            'venomous snake',          # ASP
            'faucet',                  # TAP
            'bladder infection',       # UTI
            'type of beer',            # ALE
            'unit of heat energy',     # CAL
            'allow',                   # LET
            'copy',                    # APE
        ],
    },

}
