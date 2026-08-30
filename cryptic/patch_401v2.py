#!/usr/bin/env python3
"""Re-render filled_401v2 images from puzzles_data.py."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from puzzles_data import render_puzzle
render_puzzle("filled_401v2")
