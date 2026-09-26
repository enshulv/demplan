"""Locations of the read-only reference implementation and of the dep1ex data files.

The reference scripts under ``research/bench`` are imported by absolute path so that
``repro`` and ``endowment`` resolve each other. The dep1ex archives are large and are not
checked into the repository, so their directory is resolved at run time and the tests that
need them skip when it is absent.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

BENCH_DIR = Path(os.environ.get("DEMPLAN_BENCH_DIR", REPO_ROOT / "research" / "bench")).resolve()
"""Directory holding ``repro.py``, ``endowment.py`` and ``confirm.py``."""

DATA_DIR = Path(os.environ.get("DEMPLAN_DATA_DIR", REPO_ROOT / "research" / "data")).resolve()
"""Directory holding ``dep1ex01.clj.gz`` .. ``dep1ex05.clj.gz``."""


def dep1ex_path(index: int) -> Path:
    """Path of the ``index``-th dep1ex archive, counting from 1."""
    return DATA_DIR / f"dep1ex{index:02d}.clj.gz"


def dep1ex_available(index: int) -> bool:
    return dep1ex_path(index).is_file()


def import_reference():
    """Import the numpy reference scripts and return ``(repro, endowment)``.

    ``endowment`` does ``import repro`` at module scope, so the bench directory has to be on
    ``sys.path`` before either import.
    """
    if str(BENCH_DIR) not in sys.path:
        sys.path.insert(0, str(BENCH_DIR))
    import endowment  # noqa: PLC0415
    import repro  # noqa: PLC0415

    return repro, endowment
