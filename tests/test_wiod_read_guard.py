"""The guard in ``tests/conftest.py`` also keeps WIOD files out of the fast layer.

A test that reads anything under ``<DEMPLAN_DATA_DIR>/wiod`` through the loader
(``demplan.load_wiod`` or the Rust function ``demplan._core.load_wiod`` it calls) has to carry the
``slow`` marker: the release tables take about a second each. The guard counts every file the
loader is given -- the table, the socio-economic accounts and the exchange rates -- so a test that
reads only the accounts from the data directory is caught as well.

As in ``test_slow_marker_guard.py``, the guard is checked by running pytest in a subprocess on a
scratch project whose ``tests/conftest.py`` is a copy of the real one, with ``DEMPLAN_DATA_DIR``
pointing at a directory that holds small workbooks written by the test.
"""

from __future__ import annotations

import os
import subprocess
import sys
import warnings
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from reference.wiod_workbooks import write_xlsb, write_xlsx
from test_load_wiod import YEAR, sea_rows, standard_table

TESTS_DIR = Path(__file__).resolve().parent

INNER_TESTS = '''
import shutil

import pytest

import demplan
from demplan import _core
from reference.paths import DATA_DIR

TABLE = DATA_DIR / "wiod" / "WIOT2014_Nov16_ROW.xlsb"
SEA = DATA_DIR / "wiod" / "Socio_Economic_Accounts.xlsx"


def test_unmarked_python_loader():
    demplan.load_wiod(TABLE, 2014)


def test_unmarked_rust_loader():
    _core.load_wiod(str(TABLE), 2014, None, None, None)


def test_unmarked_accounts_from_the_data_directory(tmp_path):
    copy = tmp_path / TABLE.name
    shutil.copyfile(TABLE, copy)
    demplan.load_wiod(copy, 2014, labor="hours", sea=SEA)


@pytest.mark.slow
def test_marked_python_loader():
    demplan.load_wiod(TABLE, 2014)


@pytest.fixture(scope="module")
def loaded_in_a_module_fixture():
    return demplan.load_wiod(TABLE, 2014)


@pytest.fixture
def depends_on_the_module_fixture(loaded_in_a_module_fixture):
    return loaded_in_a_module_fixture


@pytest.mark.slow
def test_marked_sets_up_the_module_fixture(loaded_in_a_module_fixture):
    pass


def test_unmarked_reaches_the_module_fixture_through_another(depends_on_the_module_fixture):
    pass


def test_unmarked_copies_outside_the_data_directory(tmp_path):
    table = tmp_path / TABLE.name
    sea = tmp_path / SEA.name
    shutil.copyfile(TABLE, table)
    shutil.copyfile(SEA, sea)
    demplan.load_wiod(table, 2014, labor="hours", sea=sea)


def test_unmarked_without_any_file():
    assert 1 + 1 == 2
'''

INNER_INI = """[pytest]
markers =
    slow: needs the data files or a release build; deselect with -m 'not slow'
filterwarnings =
    ignore::UserWarning
"""

GUARD_FAILURE = "has no 'slow' marker"
"""Part of the guard's failure message; a failure without it failed for another reason."""

FULL_RUN = {
    "test_unmarked_python_loader": "failed by the guard",
    "test_unmarked_rust_loader": "failed by the guard",
    "test_unmarked_accounts_from_the_data_directory": "failed by the guard",
    "test_marked_python_loader": "passed",
    "test_marked_sets_up_the_module_fixture": "passed",
    "test_unmarked_reaches_the_module_fixture_through_another": "failed by the guard",
    "test_unmarked_copies_outside_the_data_directory": "passed",
    "test_unmarked_without_any_file": "passed",
}
"""Every inner test's outcome when the whole inner file runs."""


def run_inner(tmp_path: Path, *arguments: str) -> tuple[dict[str, str], str]:
    """Run the inner file under a copy of the real conftest; return outcomes and console output.

    An outcome is ``"passed"``, ``"skipped"``, ``"failed by the guard"`` when the failure message
    is the guard's, and ``"failed otherwise"``.
    """
    project = tmp_path / "project"
    inner_tests = project / "tests"
    wiod = tmp_path / "data" / "wiod"
    inner_tests.mkdir(parents=True)
    wiod.mkdir(parents=True)
    write_xlsb(wiod / f"WIOT{YEAR}_Nov16_ROW.xlsb", {str(YEAR): standard_table().cells()})
    write_xlsx(wiod / "Socio_Economic_Accounts.xlsx", {"DATA": sea_rows()})
    (project / "pytest.ini").write_text(INNER_INI, encoding="utf-8")
    (inner_tests / "conftest.py").write_text(
        (TESTS_DIR / "conftest.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (inner_tests / "test_inner.py").write_text(INNER_TESTS, encoding="utf-8")
    report = tmp_path / "report.xml"

    environment = dict(os.environ)
    environment["DEMPLAN_DATA_DIR"] = str(tmp_path / "data")
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
    return run_inner(tmp_path_factory.mktemp("wiod_whole_file"))


class TestTheGuardOnWiodFiles:
    def test_the_whole_file(self, whole_file):
        outcomes, output = whole_file
        assert outcomes == FULL_RUN, output

    def test_the_failure_names_the_test_the_marker_and_the_file(self, whole_file):
        _, output = whole_file
        message = next(
            line for line in output.splitlines()
            if line.startswith("tests/test_inner.py::test_unmarked_python_loader ")
        )
        assert GUARD_FAILURE in message
        assert "WIOT2014_Nov16_ROW.xlsb" in message

    def test_the_failure_names_the_accounts_when_only_they_were_read(self, whole_file):
        _, output = whole_file
        message = next(
            line for line in output.splitlines()
            if line.startswith("tests/test_inner.py::test_unmarked_accounts_from_the_data_directory ")
        )
        assert "Socio_Economic_Accounts.xlsx" in message

    def test_the_failure_names_the_fixture_that_read_the_file(self, whole_file):
        _, output = whole_file
        assert (
            "uses the fixture 'loaded_in_a_module_fixture', which read a WIOD file" in output
        )


def test_the_scratch_workbooks_are_ones_the_loader_accepts(tmp_path):
    """Without this, an unmarked test could fail on a read error and look like the guard."""
    from demplan import load_wiod

    table = write_xlsb(tmp_path / f"WIOT{YEAR}_Nov16_ROW.xlsb", {str(YEAR): standard_table().cells()})
    sea = write_xlsx(tmp_path / "Socio_Economic_Accounts.xlsx", {"DATA": sea_rows()})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        loaded = load_wiod(table, YEAR, labor="hours", sea=sea)
    assert loaded.economy.n_units == 4
