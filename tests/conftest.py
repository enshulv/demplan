"""Shared fixtures.

The dep1ex archives are several tens of megabytes each and take seconds to parse, so the
first one is parsed once per session and shared. Tests that need an archive skip when the
data directory is absent; see ``tests/reference/paths.py`` for how that directory is found.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from reference import dep1ex_numpy, synthetic  # noqa: E402
from reference.paths import dep1ex_available, dep1ex_path  # noqa: E402


@pytest.fixture(scope="session")
def dep1ex01_parsed():
    """``(wc, cc, layout)`` from the numpy reference parse of dep1ex01."""
    if not dep1ex_available(1):
        pytest.skip(f"dep1ex01 archive not found at {dep1ex_path(1)}")
    return dep1ex_numpy.parse_dep1ex(dep1ex_path(1))


@pytest.fixture(scope="session")
def dep1ex01_economy(dep1ex01_parsed):
    wc, cc, layout = dep1ex01_parsed
    return dep1ex_numpy.economy_from_repro(wc, cc, layout)


@pytest.fixture
def synthetic_economy():
    return synthetic.build_economy()


@pytest.fixture
def synthetic_reference_inputs():
    return synthetic.build_reference_inputs()
