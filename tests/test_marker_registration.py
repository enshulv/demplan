"""Registration of the pytest markers this suite uses.

A marker registered in two places carries two descriptions, and the one a reader sees from
``pytest --markers`` is whichever was appended last. ``pyproject.toml`` is the single place.
"""

from __future__ import annotations

SLOW_DESCRIPTION = (
    "slow: needs the dep1ex data files or a release build; deselect with -m 'not slow'"
)


def test_the_slow_marker_is_registered_once_with_the_pyproject_description(pytestconfig):
    registered = [line for line in pytestconfig.getini("markers") if line.startswith("slow:")]
    assert registered == [SLOW_DESCRIPTION]
