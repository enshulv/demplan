"""Locations of the upstream check scripts, and the dep1ex data they read.

The scripts under ``research/upstream`` import each other as top-level modules (``fetch``,
``_price_rules`` and so on), and the two Docker directories import the top-level ones the same
way. Importing this module puts the three directories on ``sys.path`` so that the tests can
import the scripts by the names the scripts use themselves.

The dep1ex archives are not in the repository; their directory is resolved as in
``tests/reference/paths.py``, and the tests that need one skip when it is absent.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

UPSTREAM_DIR = REPO_ROOT / "research" / "upstream"
"""The check scripts and their private modules."""

PEQUOD_CLJS_DOCKER_DIR = UPSTREAM_DIR / "docker" / "pequod-cljs"
PEQUOD_PLUS_DOCKER_DIR = UPSTREAM_DIR / "docker" / "pequod-plus"

DATA_DIR = Path(os.environ.get("DEMPLAN_DATA_DIR", REPO_ROOT / "research" / "data")).resolve()
"""Directory holding ``dep1ex01.clj.gz`` .. ``dep1ex40.clj.gz``."""

for directory in (UPSTREAM_DIR, PEQUOD_CLJS_DOCKER_DIR, PEQUOD_PLUS_DOCKER_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


def dep1ex_path(index: int) -> Path:
    """Path of the public archive of book experiment ``index``."""
    return DATA_DIR / f"dep1ex{index:02d}.clj.gz"


def cached_upstream_file(name: str) -> Path | None:
    """The manifest entry ``name`` in fetch.py's default cache, or None when it is not there or
    its sha256 differs from the manifest. Never downloads."""
    import fetch

    entry = next(e for e in fetch.load_manifest() if e.name == name)
    path = fetch.DEFAULT_CACHE / entry.name
    if path.is_file() and fetch.sha256_of(path) == entry.sha256:
        return path
    return None
