"""Shared fixtures, and the guard that keeps the dep1ex archives and WIOD files out of the fast layer.

The dep1ex archives are several tens of megabytes each and take seconds to parse, so the
first one is parsed once per session and shared. Tests that need an archive skip when the
data directory is absent; see ``tests/reference/paths.py`` for how that directory is found.

``pytest -m "not slow"`` is the fast layer, so every test that reads an archive carries the
``slow`` marker. The guard below fails a test that reads one without it. It watches the two
functions every archive read goes through, the Rust loader ``demplan._core.load_dep1ex`` and
the numpy reference parser ``repro.parse``, and charges a read to the test being run and to
every fixture being set up at that moment. A test is also charged when it uses such a fixture
after another test set it up, since a cached fixture is not set up again.

The WIOD release files under ``<DATA_DIR>/wiod`` take about a second each to read and are held
to the same rule. Every WIOD read goes through the Rust loader ``demplan._core.load_wiod``, and a
call is charged when any file it is given lies under that directory.
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

WIOD_DIR = DATA_DIR / "wiod"
"""Directory of the WIOD release files; reading anything under it makes a test slow."""

DEP1EX_ARCHIVE = "dep1ex archive"
WIOD_FILE = "WIOD file"


def _is_archive(path) -> bool:
    """Whether ``path`` names a dep1ex archive in the data directory the tests read from."""
    candidate = Path(os.fspath(path)).resolve()
    return candidate.parent == DATA_DIR and ARCHIVE_NAME.fullmatch(candidate.name) is not None


def _archive_in(args, kwargs) -> str | None:
    """The dep1ex archive a reader call names as its first argument, or ``None``."""
    path = args[0] if args else kwargs.get("path")
    return None if path is None or not _is_archive(path) else str(path)


def _wiod_file_in(args, kwargs) -> str | None:
    """The first argument of a reader call that names a path under ``WIOD_DIR``, or ``None``."""
    for value in (*args, *kwargs.values()):
        if not isinstance(value, (str, os.PathLike)):
            continue
        candidate = Path(os.fspath(value)).resolve()
        if candidate == WIOD_DIR or WIOD_DIR in candidate.parents:
            return str(value)
    return None


class ArchiveReadGuard:
    """Fails every test that reads a dep1ex archive or a WIOD file, itself or through a fixture,
    unmarked.

    Registered as a plugin in :func:`pytest_configure` rather than written as conftest hooks:
    pytest consults a conftest's hooks only for nodes under the conftest's directory, and a
    session-scoped fixture is set up for the session node at the repository root, so a
    ``pytest_fixture_setup`` hook here would never see ``dep1ex01_parsed`` being set up.
    """

    def __init__(self):
        self.fixtures_being_set_up: list = []
        """The ``FixtureDef`` of every fixture whose setup is running, innermost last."""
        self.fixtures_that_read_an_archive: dict = {}
        """``FixtureDef`` objects whose setup read an archive at least once in this session, each
        with what it read (``DEP1EX_ARCHIVE`` or ``WIOD_FILE``)."""
        self.test_being_run: pytest.Item | None = None
        self.tests_that_read_an_archive: dict[str, str] = {}
        """Node id of each test that read an archive while it ran, with what and which path."""

    def watch(self, read, file_in, what: str):
        """``read`` with every call on a watched file charged to the running test and fixtures.

        ``file_in(args, kwargs)`` returns the watched file a call names, or ``None``; ``what``
        says what kind of file it is, for the failure message.
        """

        @functools.wraps(read)
        def watched(*args, **kwargs):
            path = file_in(args, kwargs)
            if path is not None:
                for fixture in self.fixtures_being_set_up:
                    self.fixtures_that_read_an_archive.setdefault(fixture, what)
                if self.test_being_run is not None:
                    self.tests_that_read_an_archive.setdefault(
                        self.test_being_run.nodeid, f"{what} {path}"
                    )
            return read(*args, **kwargs)

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
            f"{item.nodeid} {reason} but has no '{SLOW}' marker. A dep1ex archive or a WIOD "
            f"file takes a second or more to read, and 'pytest -m \"not {SLOW}\"' is meant to "
            f"leave every such test out. Mark the test (or its class or module) with "
            f"@pytest.mark.{SLOW}."
        )

    def archive_reached_by(self, item) -> str | None:
        """How ``item`` reached a dep1ex archive or a WIOD file, or ``None`` when it did not.

        A fixture counts through the definition the item actually uses, so a fixture of the
        same name defined elsewhere is not confused with one that read an archive.
        """
        read = self.tests_that_read_an_archive.get(item.nodeid)
        if read is not None:
            return f"read the {read}"
        definitions = getattr(item, "_fixtureinfo", None)
        if definitions is None:
            return None
        for name in item.fixturenames:
            active = definitions.name2fixturedefs.get(name)
            if active and active[-1] in self.fixtures_that_read_an_archive:
                what = self.fixtures_that_read_an_archive[active[-1]]
                return f"uses the fixture '{name}', which read a {what}"
        return None


def pytest_configure(config):
    """Install the archive-read guard.

    Every module that reads an archive or a WIOD file looks its reader up as a module attribute
    at call time (``_core.load_dep1ex``, ``repro.parse``, ``_core.load_wiod``), so replacing
    them reaches every caller, including ``demplan.load_dep1ex``, ``demplan.load_wiod`` and
    ``reference.dep1ex_numpy.parse_dep1ex``.
    """
    guard = ArchiveReadGuard()
    config.pluginmanager.register(guard, "dep1ex-archive-read-guard")
    _core.load_dep1ex = guard.watch(_core.load_dep1ex, _archive_in, DEP1EX_ARCHIVE)
    repro.parse = guard.watch(repro.parse, _archive_in, DEP1EX_ARCHIVE)
    _core.load_wiod = guard.watch(_core.load_wiod, _wiod_file_in, WIOD_FILE)


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
