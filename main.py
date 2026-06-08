"""Standalone entry point for PyInstaller packaging."""

import sys
import os

# Force UTF-8 mode on Windows for Chinese support
os.environ.setdefault("PYTHONUTF8", "1")

# Ensure the package directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.__main__ import main

if __name__ == "__main__":
    main()
