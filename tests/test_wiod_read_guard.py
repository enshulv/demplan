"""The guard in ``tests/conftest.py`` also keeps WIOD files out of the fast layer.

A test that reads anything under ``<DEMPLAN_DATA_DIR>/wiod`` has to carry the ``slow`` marker:
the release tables take about a second each. The guard catches a read whichever function makes it:
the loader (``demplan.load_wiod`` or the Rust function ``demplan._core.load_wiod`` it calls), which
is charged for every file it is given -- the table, the socio-economic accounts and the exchange
rates -- and any Python code that opens a file there, such as
``reference.wiod_workbooks.read_xlsx_rows`` or a plain ``open``. A file in a subdirectory of
``wiod`` counts, and so does a relative path or a path through ``..`` that leads there.

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
import os

import pytest

import demplan
from demplan import _core
from reference.paths import DATA_DIR

from reference.wiod_workbooks import read_xlsx_rows

TABLE = DATA_DIR / "wiod" / "WIOT2014_Nov16_ROW.xlsb"
SEA = DATA_DIR / "wiod" / "Socio_Economic_Accounts.xlsx"
TABLE_IN_A_SUBDIRECTORY = DATA_DIR / "wiod" / "xlsb" / "WIOT2014_Nov16_ROW.xlsb"
COPIES = DATA_DIR.parent / "copies"
"""The same workbooks outside the data directory, written before pytest starts: copying a WIOD
file inside a test would read it."""


def test_unmarked_python_loader():
    demplan.load_wiod(TABLE, 2014)


def test_unmarked_rust_loader():
    _core.load_wiod(str(TABLE), 2014, None, None, None)


def test_unmarked_accounts_from_the_data_directory():
    demplan.load_wiod(COPIES / TABLE.name, 2014, labor="hours", sea=SEA)


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


def test_unmarked_copies_outside_the_data_directory():
    demplan.load_wiod(COPIES / TABLE.name, 2014, labor="hours", sea=COPIES / SEA.name)


def test_unmarked_without_any_file():
    assert 1 + 1 == 2


def test_unmarked_loader_on_a_file_in_a_subdirectory():
    demplan.load_wiod(TABLE_IN_A_SUBDIRECTORY, 2014)


def test_unmarked_loader_on_a_relative_path():
    demplan.load_wiod(os.path.relpath(TABLE), 2014)


def test_unmarked_loader_on_a_path_through_a_sibling_directory():
    demplan.load_wiod(DATA_DIR / "other" / ".." / "wiod" / TABLE.name, 2014)


def test_unmarked_reads_the_accounts_with_the_reference_reader():
    read_xlsx_rows(SEA, "DATA")


def test_unmarked_opens_the_table_with_open():
    with open(TABLE, "rb") as handle:
        handle.read(4)


def test_unmarked_opens_a_file_in_a_subdirectory_on_a_relative_path():
    with open(os.path.relpath(TABLE_IN_A_SUBDIRECTORY), "rb") as handle:
        handle.read(4)


def test_unmarked_reads_a_copy_with_the_reference_reader():
    read_xlsx_rows(COPIES / SEA.name, "DATA")


@pytest.fixture(scope="module")
def accounts_read_in_a_module_fixture():
    return read_xlsx_rows(SEA, "DATA")


@pytest.mark.slow
def test_marked_sets_up_the_reading_module_fixture(accounts_read_in_a_module_fixture):
    pass


def test_unmarked_uses_the_reading_module_fixture(accounts_read_in_a_module_fixture):
    pass
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
    "test_unmarked_loader_on_a_file_in_a_subdirectory": "failed by the guard",
    "test_unmarked_loader_on_a_relative_path": "failed by the guard",
    "test_unmarked_loader_on_a_path_through_a_sibling_directory": "failed by the guard",
    "test_unmarked_reads_the_accounts_with_the_reference_reader": "failed by the guard",
    "test_unmarked_opens_the_table_with_open": "failed by the guard",
    "test_unmarked_opens_a_file_in_a_subdirectory_on_a_relative_path": "failed by the guard",
    "test_unmarked_reads_a_copy_with_the_reference_reader": "passed",
    "test_marked_sets_up_the_reading_module_fixture": "passed",
    "test_unmarked_uses_the_reading_module_fixture": "failed by the guard",
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
    (wiod / "xlsb").mkdir(parents=True)
    (tmp_path / "data" / "other").mkdir()
    (tmp_path / "copies").mkdir()
    for directory in (wiod, wiod / "xlsb", tmp_path / "copies"):
        write_xlsb(
            directory / f"WIOT{YEAR}_Nov16_ROW.xlsb", {str(YEAR): standard_table().cells()}
        )
    for directory in (wiod, tmp_path / "copies"):
        write_xlsx(directory / "Socio_Economic_Accounts.xlsx", {"DATA": sea_rows()})
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

    def test_the_failure_names_the_file_a_python_reader_opened(self, whole_file):
        _, output = whole_file
        message = next(
            line for line in output.splitlines()
            if line.startswith(
                "tests/test_inner.py::test_unmarked_reads_the_accounts_with_the_reference_reader "
            )
        )
        assert GUARD_FAILURE in message
        assert "Socio_Economic_Accounts.xlsx" in message


def test_the_scratch_workbooks_are_ones_the_loader_accepts(tmp_path):
    """Without this, an unmarked test could fail on a read error and look like the guard."""
    from demplan import load_wiod

    table = write_xlsb(tmp_path / f"WIOT{YEAR}_Nov16_ROW.xlsb", {str(YEAR): standard_table().cells()})
    sea = write_xlsx(tmp_path / "Socio_Economic_Accounts.xlsx", {"DATA": sea_rows()})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        loaded = load_wiod(table, YEAR, labor="hours", sea=sea)
    assert loaded.economy.n_units == 4
