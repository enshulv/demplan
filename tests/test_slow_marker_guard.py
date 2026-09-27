"""The guard in ``tests/conftest.py`` that keeps dep1ex archives out of the fast layer.

``pytest -m "not slow"`` is the fast layer. A test that reads a dep1ex archive takes seconds, so
it has to carry the ``slow`` marker; the guard fails any test that reads one without it. Two
ways in count as reading an archive: the Rust loader ``demplan._core.load_dep1ex`` (which
``demplan.load_dep1ex`` calls) and the numpy reference parser ``repro.parse`` (which
``reference.dep1ex_numpy.parse_dep1ex`` calls). An archive is a file named like
``dep1ex01.clj.gz`` in the data directory the tests read from.

The guard is checked by running pytest in a subprocess on a scratch project laid out like the
repository, whose ``tests/conftest.py`` is a copy of the real one, with ``DEMPLAN_DATA_DIR``
pointing at a small hand-written archive. A fixture that loads an archive and is cached for the session is the
case a check on the load call alone would miss: the test that first sets it up is charged with
the load, and every later test only receives the result.
"""

from __future__ import annotations

import gzip
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent

INNER_TESTS = '''
import shutil

import pytest

import demplan
from demplan import _core
from reference import dep1ex_numpy
from reference.paths import dep1ex_path


@pytest.mark.slow
def test_marked_sets_up_the_session_fixture(dep1ex01_parsed):
    pass


def test_unmarked_receives_the_cached_session_fixture(dep1ex01_parsed):
    pass


def test_unmarked_rust_loader():
    _core.load_dep1ex(str(dep1ex_path(1)), 1000.0)


def test_unmarked_python_loader():
    demplan.load_dep1ex(dep1ex_path(1))


def test_unmarked_numpy_parser():
    dep1ex_numpy.parse_dep1ex(dep1ex_path(1))


@pytest.mark.slow
def test_marked_rust_loader():
    _core.load_dep1ex(str(dep1ex_path(1)), 1000.0)


@pytest.mark.slow
class TestMarkedClass:
    def test_numpy_parser(self):
        dep1ex_numpy.parse_dep1ex(dep1ex_path(1))


@pytest.fixture(scope="module")
def loaded_in_a_module_fixture():
    return _core.load_dep1ex(str(dep1ex_path(1)), 1000.0)


@pytest.fixture
def depends_on_the_module_fixture(loaded_in_a_module_fixture):
    return loaded_in_a_module_fixture


@pytest.mark.slow
def test_marked_sets_up_the_module_fixture(loaded_in_a_module_fixture):
    pass


def test_unmarked_reaches_the_module_fixture_through_another(depends_on_the_module_fixture):
    pass


def test_unmarked_copy_outside_the_data_directory(tmp_path):
    copy = tmp_path / "dep1ex01.clj.gz"
    shutil.copyfile(dep1ex_path(1), copy)
    _core.load_dep1ex(str(copy), 1000.0)


def test_unmarked_without_any_archive():
    assert 1 + 1 == 2
'''

INNER_INI = """[pytest]
markers =
    slow: needs the dep1ex data files or a release build; deselect with -m 'not slow'
"""

GUARD_FAILURE = "has no 'slow' marker"
"""Part of the guard's failure message; a failure without it failed for another reason."""

FULL_RUN = {
    "test_marked_sets_up_the_session_fixture": "passed",
    "test_unmarked_receives_the_cached_session_fixture": "failed by the guard",
    "test_unmarked_rust_loader": "failed by the guard",
    "test_unmarked_python_loader": "failed by the guard",
    "test_unmarked_numpy_parser": "failed by the guard",
    "test_marked_rust_loader": "passed",
    "test_numpy_parser": "passed",
    "test_marked_sets_up_the_module_fixture": "passed",
    "test_unmarked_reaches_the_module_fixture_through_another": "failed by the guard",
    "test_unmarked_copy_outside_the_data_directory": "passed",
    "test_unmarked_without_any_archive": "passed",
}
"""Every inner test's outcome when the whole inner file runs."""

FAST_LAYER = {
    name: outcome
    for name, outcome in FULL_RUN.items()
    if name.startswith("test_unmarked")
}
"""Every inner test's outcome under ``-m "not slow"``: the marked ones are not run, so each
unmarked test that reaches an archive is the one that loads it."""


def unit_record(industry: int, product: int) -> str:
    """One ``wcs`` map with two intermediate inputs, three natural resources and three labours."""
    return (
        f"{{:industry {industry}, :product {product}, :s 1, :du 3.0, :c 0.61, :a 2.0, "
        ":production-inputs [[1 2] [1 2 3] [1 2 3]], :input-exponents [0.1 0.1], "
        ":nature-exponents [0.1 0.1 0.1], :labor-exponents [0.1 0.1 0.1]}"
    )


def write_archive(path: Path) -> None:
    """A dep1ex archive with four private goods, two public goods and three of each input."""
    consumers = [
        "{:utility-exponents [0.2 0.2 0.2 0.2], :public-good-exponents [0.2 0.2], :income 5000}"
    ] * 2
    units = [unit_record(0, product) for product in range(1, 5)]
    units += [unit_record(1, product) for product in range(1, 4)]
    units += [unit_record(2, product) for product in range(1, 3)]
    body = "(ns fixture)\n\n(def ccs \n[{}]\n)\n\n(def wcs \n[{}]\n)\n".format(
        "\n ".join(consumers), "\n ".join(units)
    )
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(body)


def run_inner(tmp_path: Path, *arguments: str) -> tuple[dict[str, str], str]:
    """Run the inner file under a copy of the real conftest.

    Returns each inner test's name with its outcome, read from the JUnit XML report, and the
    console output. An outcome is ``"passed"``, ``"skipped"``, ``"failed by the guard"`` when
    the failure message is the guard's, and ``"failed otherwise"``.
    """
    project = tmp_path / "project"
    inner_tests = project / "tests"
    data = tmp_path / "data"
    inner_tests.mkdir(parents=True)
    data.mkdir()
    write_archive(data / "dep1ex01.clj.gz")
    # The same layout as the repository: the ini file at the root, the conftest one level down.
    # A hook in that conftest is not consulted for a session-scoped fixture, whose node is the
    # session at the root, so the layout decides whether such a fixture's reads are seen.
    (project / "pytest.ini").write_text(INNER_INI, encoding="utf-8")
    (inner_tests / "conftest.py").write_text(
        (TESTS_DIR / "conftest.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (inner_tests / "test_inner.py").write_text(INNER_TESTS, encoding="utf-8")
    report = tmp_path / "report.xml"

    environment = dict(os.environ)
    environment["DEMPLAN_DATA_DIR"] = str(data)
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(TESTS_DIR), *filter(None, [environment.get("PYTHONPATH")])]
    )
    completed = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "-p", "no:cacheprovider", "-p", "no:xdist", "-p", "no:hypothesispytest",
            "-q", f"--junitxml={report}", "tests", *arguments,
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert report.is_file(), completed.stdout + completed.stderr
    outcomes = {}
    for case in ET.parse(report).getroot().iter("testcase"):
        failure = case.find("failure")
        if failure is None:
            failure = case.find("error")
        if failure is not None:
            by_guard = GUARD_FAILURE in (failure.get("message", "") + (failure.text or ""))
            outcomes[case.get("name")] = "failed by the guard" if by_guard else "failed otherwise"
        elif case.find("skipped") is not None:
            outcomes[case.get("name")] = "skipped"
        else:
            outcomes[case.get("name")] = "passed"
    return outcomes, completed.stdout


@pytest.fixture(scope="module")
def whole_file(tmp_path_factory):
    """The inner file run in full."""
    return run_inner(tmp_path_factory.mktemp("whole_file"))


@pytest.fixture(scope="module")
def fast_layer(tmp_path_factory):
    """The inner file run under ``-m "not slow"``."""
    return run_inner(tmp_path_factory.mktemp("fast_layer"), "-m", "not slow")


class TestTheGuard:
    def test_the_whole_file(self, whole_file):
        outcomes, output = whole_file
        assert outcomes == FULL_RUN, output

    def test_the_fast_layer(self, fast_layer):
        outcomes, output = fast_layer
        assert outcomes == FAST_LAYER, output

    def test_the_failure_names_the_test_the_marker_and_the_archive(self, whole_file):
        _, output = whole_file
        message = next(
            line for line in output.splitlines()
            if line.startswith("tests/test_inner.py::test_unmarked_rust_loader ")
        )
        assert GUARD_FAILURE in message
        assert "dep1ex01.clj.gz" in message

    def test_the_failure_names_the_fixture_that_read_the_archive(self, whole_file):
        _, output = whole_file
        assert "uses the fixture 'dep1ex01_parsed', which read a dep1ex archive" in output


def test_the_scratch_archive_is_one_the_loaders_accept(tmp_path):
    """Without this, an unmarked test could fail on a parse error and look like the guard."""
    from demplan import _core
    from reference import dep1ex_numpy

    path = tmp_path / "dep1ex01.clj.gz"
    write_archive(path)
    loaded = _core.load_dep1ex(str(path), 1000.0)
    assert loaded["commodity_id"].shape == (4 + 2 + 3 * 3,)
    _, _, layout = dep1ex_numpy.parse_dep1ex(path)
    assert layout.n_commodities == 4 + 2 + 3 * 3
