"""Shared pytest fixtures + path setup.

Adds the repo's ``analysis/`` and ``design/`` directories to sys.path so
tests can import the modules without packaging gymnastics.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for sub in ("analysis", "design", "py"):
    p = str(REPO_ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)
