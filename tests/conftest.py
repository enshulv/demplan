"""Shared fixtures, and the guard that keeps the dep1ex archives out of the fast layer.

The dep1ex archives are several tens of megabytes each and take seconds to parse, so the
first one is parsed once per session and shared. Tests that need an archive skip when the
data directory is absent; see ``tests/reference/paths.py`` for how that directory is found.

``pytest -m "not slow"`` is the fast layer, so every test that reads an archive carries the
``slow`` marker. The guard below fails a test that reads one without it. It watches the two
functions every archive read goes through, the Rust loader ``demplan._core.load_dep1ex`` and
the numpy reference parser ``repro.parse``, and charges a read to the test being run and to
every fixture being set up at that moment. A test is also charged when it uses such a fixture
after another test set it up, since a cached fixture is not set up again.
"""

from __future__ import annotations

import functools
import os
import re
import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from demplan import _core  # noqa: E402
from reference import dep1ex_numpy, synthetic  # noqa: E402
from reference.paths import BENCH_DIR, DATA_DIR, dep1ex_available, dep1ex_path  # noqa: E402

if str(BENCH_DIR) not in sys.path:
    sys.path.insert(0, str(BENCH_DIR))
import repro  # noqa: E402  (needs the sys.path entry above)

SLOW = "slow"

ARCHIVE_NAME = re.compile(r"dep1ex\d+\.clj\.gz")
"""File name of a dep1ex archive; an archive also has to sit in ``DATA_DIR``."""


def _is_archive(path) -> bool:
    """Whether ``path`` names a dep1ex archive in the data directory the tests read from."""
    candidate = Path(os.fspath(path)).resolve()
    return candidate.parent == DATA_DIR and ARCHIVE_NAME.fullmatch(candidate.name) is not None


class ArchiveReadGuard:
    """Fails every test that reads a dep1ex archive, itself or through a fixture, unmarked.

    Registered as a plugin in :func:`pytest_configure` rather than written as conftest hooks:
    pytest consults a conftest's hooks only for nodes under the conftest's directory, and a
    session-scoped fixture is set up for the session node at the repository root, so a
    ``pytest_fixture_setup`` hook here would never see ``dep1ex01_parsed`` being set up.
    """

    def __init__(self):
        self.fixtures_being_set_up: list = []
        """The ``FixtureDef`` of every fixture whose setup is running, innermost last."""
        self.fixtures_that_read_an_archive: set = set()
        """``FixtureDef`` objects whose setup read an archive at least once in this session."""
        self.test_being_run: pytest.Item | None = None
        self.tests_that_read_an_archive: dict[str, str] = {}
        """Node id of each test that read an archive while it ran, with that archive's path."""

    def watch(self, read):
        """``read`` with every call on an archive charged to the running test and fixtures."""

        @functools.wraps(read)
        def watched(path, *args, **kwargs):
            if _is_archive(path):
                self.fixtures_that_read_an_archive.update(self.fixtures_being_set_up)
                if self.test_being_run is not None:
                    self.tests_that_read_an_archive.setdefault(
                        self.test_being_run.nodeid, str(path)
                    )
            return read(path, *args, **kwargs)

        return watched

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        """Remember which test is running, so an archive read can be charged to it."""
        self.test_being_run = item
        yield
        self.test_being_run = None

    @pytest.hookimpl(hookwrapper=True)
    def pytest_fixture_setup(self, fixturedef, request):
        """Keep the stack of fixtures being set up, so an archive read can be charged to them."""
        self.fixtures_being_set_up.append(fixturedef)
        yield
        self.fixtures_being_set_up.pop()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        """Turn the passing call phase of an unmarked test that reached an archive into a failure.

        A test that already failed or skipped keeps its own report.
        """
        outcome = yield
        report = outcome.get_result()
        if call.when != "call" or item.get_closest_marker(SLOW) is not None:
            return
        reason = self.archive_reached_by(item)
        if reason is None or not report.passed:
            return
        report.outcome = "failed"
        report.longrepr = (
            f"{item.nodeid} {reason} but has no '{SLOW}' marker. A dep1ex archive takes "
            f"seconds to read, and 'pytest -m \"not {SLOW}\"' is meant to leave every such test "
            f"out. Mark the test (or its class or module) with @pytest.mark.{SLOW}."
        )

    def archive_reached_by(self, item) -> str | None:
        """How ``item`` reached a dep1ex archive, or ``None`` when it did not.

        A fixture counts through the definition the item actually uses, so a fixture of the
        same name defined elsewhere is not confused with one that read an archive.
        """
        path = self.tests_that_read_an_archive.get(item.nodeid)
        if path is not None:
            return f"read the dep1ex archive {path}"
        definitions = getattr(item, "_fixtureinfo", None)
        if definitions is None:
            return None
        for name in item.fixturenames:
            active = definitions.name2fixturedefs.get(name)
            if active and active[-1] in self.fixtures_that_read_an_archive:
                return f"uses the fixture '{name}', which read a dep1ex archive"
        return None


def pytest_configure(config):
    """Install the archive-read guard.

    Every module that reads an archive looks the two readers up as module attributes at call
    time (``_core.load_dep1ex``, ``repro.parse``), so replacing them reaches every caller,
    including ``demplan.load_dep1ex`` and ``reference.dep1ex_numpy.parse_dep1ex``.
    """
    guard = ArchiveReadGuard()
    config.pluginmanager.register(guard, "dep1ex-archive-read-guard")
    _core.load_dep1ex = guard.watch(_core.load_dep1ex)
    repro.parse = guard.watch(repro.parse)


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
