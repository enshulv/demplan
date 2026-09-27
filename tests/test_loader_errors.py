"""The error types the loaders raise, as a researcher catches them.

``demplan.load_dep1ex`` and ``demplan.load_wiod`` hand the reading to the Rust core, which
reports a file it cannot read as ``demplan._core.LoadError`` and an economy that breaches the
data model as ``demplan._core.SchemaError``. A researcher catches neither of those: the package
names the two failures ``demplan.LoadError`` and ``demplan.SchemaError``, the second being the
same class every other schema check in the package raises. Each test here goes through the real
core where a file can produce the failure, and replaces the core's loader only where no small
file can.
"""

from __future__ import annotations

import pytest

import demplan
from demplan import _core
from reference.wiod_workbooks import release_entry
from test_core_load_dep1ex import consumer_record, unit_record, write_scenario

WIOD_YEAR = 2014


@pytest.fixture
def dep1ex_archive(tmp_path) -> str:
    """A small hand-written dep1ex archive that loads without error at a finite endowment."""
    consumers = [consumer_record([0.2, 0.3], [0.1], 1000 + i) for i in range(2)]
    units = [
        unit_record(0, 1, [1], [1], [1]),
        unit_record(0, 2, [1, 2], [2], [1]),
        unit_record(1, 1, [2], [1, 2], [2]),
        unit_record(2, 1, [1], [2], [1, 2]),
    ]
    return write_scenario(tmp_path / "small.clj.gz", consumers, units)


def damaged_dep1ex(tmp_path) -> str:
    """A file named like an archive that is plain text, not gzip."""
    path = tmp_path / "not-gzip.clj.gz"
    path.write_text("(def ccs [])\n(def wcs [])\n", encoding="utf-8")
    return str(path)


def damaged_wiod(tmp_path) -> str:
    """A file named like a WIOD workbook whose bytes are not a workbook."""
    path = tmp_path / release_entry(WIOD_YEAR)
    path.write_bytes(b"this is not an xlsb workbook")
    return str(path)


class TestSchemaErrorFromTheLoaders:
    def test_the_archive_loads_at_a_finite_endowment(self, dep1ex_archive):
        """The control for the next test: the archive itself is sound."""
        assert demplan.load_dep1ex(dep1ex_archive, endowment=1000.0).n_units == 4

    def test_a_dep1ex_schema_breach_is_caught_as_demplan_schema_error(self, dep1ex_archive):
        try:
            demplan.load_dep1ex(dep1ex_archive, endowment=float("nan"))
        except demplan.SchemaError as error:
            caught = error
        else:
            pytest.fail("load_dep1ex accepted a NaN endowment")
        assert "endowment" in str(caught)
        assert "NaN" in str(caught)

    def test_the_dep1ex_schema_error_keeps_the_core_message_and_chains_it(self, dep1ex_archive):
        with pytest.raises(demplan.SchemaError) as raised:
            demplan.load_dep1ex(dep1ex_archive, endowment=float("inf"))
        assert type(raised.value) is demplan.SchemaError
        cause = raised.value.__cause__
        assert isinstance(cause, _core.SchemaError)
        assert str(raised.value) == str(cause)

    def test_a_wiod_schema_breach_is_caught_as_demplan_schema_error(self, tmp_path, monkeypatch):
        """No small workbook makes the core report a schema breach, so the core's loader is
        replaced by one that raises the core's schema error with a known message."""
        message = "`input_coefficient[3]` is NaN, expected a finite number"

        def breach(*args):
            raise _core.SchemaError(message)

        monkeypatch.setattr(_core, "load_wiod", breach)
        with pytest.raises(demplan.SchemaError) as raised:
            demplan.load_wiod(tmp_path / release_entry(WIOD_YEAR), WIOD_YEAR)
        assert str(raised.value) == message
        assert isinstance(raised.value.__cause__, _core.SchemaError)

    def test_a_schema_error_is_still_a_value_error(self, dep1ex_archive):
        with pytest.raises(ValueError):
            demplan.load_dep1ex(dep1ex_archive, endowment=float("nan"))


class TestLoadErrorFromTheLoaders:
    def test_a_damaged_dep1ex_file_is_caught_as_demplan_load_error(self, tmp_path):
        try:
            demplan.load_dep1ex(damaged_dep1ex(tmp_path))
        except demplan.LoadError as error:
            caught = error
        else:
            pytest.fail("load_dep1ex read a plain text file as an archive")
        assert isinstance(caught.__cause__, _core.LoadError)
        assert str(caught) == str(caught.__cause__)

    def test_a_damaged_wiod_file_is_caught_as_demplan_load_error(self, tmp_path):
        with pytest.raises(demplan.LoadError) as raised:
            demplan.load_wiod(damaged_wiod(tmp_path), WIOD_YEAR)
        assert isinstance(raised.value.__cause__, _core.LoadError)
        assert str(raised.value) == str(raised.value.__cause__)

    def test_a_missing_dep1ex_file_is_a_load_error_naming_the_file(self, tmp_path):
        with pytest.raises(demplan.LoadError, match="absent.clj.gz"):
            demplan.load_dep1ex(tmp_path / "absent.clj.gz")

    def test_a_damaged_file_is_not_reported_as_a_schema_breach(self, tmp_path):
        with pytest.raises(demplan.LoadError) as raised:
            demplan.load_dep1ex(damaged_dep1ex(tmp_path))
        assert not isinstance(raised.value, demplan.SchemaError)

    def test_a_load_error_is_a_value_error(self):
        assert issubclass(demplan.LoadError, ValueError)

    def test_a_wrong_argument_is_still_a_plain_value_error(self, tmp_path):
        """A year outside the release is the caller's mistake, not a damaged file."""
        with pytest.raises(ValueError) as raised:
            demplan.load_wiod(damaged_wiod(tmp_path), 1999)
        assert not isinstance(raised.value, demplan.LoadError)


class TestExports:
    @pytest.mark.parametrize(
        "name", ["LoadError", "SchemaError", "WiodLaborGap", "WiodUnproducedInputs"]
    )
    def test_the_loader_error_and_warning_types_are_exported(self, name):
        assert name in demplan.__all__

    @pytest.mark.parametrize("name", ["LoadError", "WiodLaborGap", "WiodUnproducedInputs"])
    def test_each_export_is_the_class_the_loaders_use(self, name):
        assert getattr(demplan, name) is getattr(demplan.io, name)
