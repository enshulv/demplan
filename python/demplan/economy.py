"""The data model: one period of an economy, held as columns.

``Economy`` is the one type in this library that is fixed rather than pluggable. Everything a
coordination procedure needs about the period is here; anything that carries a commitment to
one school of economics belongs in an ``extra`` bag or in the procedure's own state. In
particular there are no prices, no classes of commodity and no grouping of units: valuations
live on ``Plan``, and a label a prefab needs lives in an ``extra`` bag under a key the prefab
owns. The library never reads an ``extra`` key of ``Economy``.

The fields hold read-only views of the arrays passed in. A frozen dataclass stops fields from
being rebound but does nothing about writing through a numpy array, and a procedure that
quietly edited its input would break the promise that two runs on the same economy are
comparable. The caller's own arrays stay writeable; the read-only flag is a numpy flag, so a
caller who kept a handle on the underlying buffer can still write through it. Evolve an
economy with :func:`dataclasses.replace`, which revalidates the result.

Text columns -- ``technology_kind`` and any text array in an ``extra`` bag -- are numpy arrays
of dtype kind ``U``, one label per row, each label non-empty and encodable as UTF-8. A Python
list of ``str`` is accepted in their place and stored as such an array, which is the form the
Rust loaders hand text over in. Every other ``extra`` array holds numbers; an object array or
a bytes array is refused.
"""

from __future__ import annotations

import dataclasses
from types import MappingProxyType
from typing import Mapping

import numpy as np

from demplan._wording import counted, with_article

LEONTIEF = "leontief"
"""Technology label: fixed input proportions, ``input_coefficient`` read as input per run."""

COBB_DOUGLAS = "cobb_douglas"
"""Technology label: ``technology_scale * prod(input ** input_coefficient)``."""


class SchemaError(ValueError):
    """An ``Economy`` or ``Plan`` violates the structural schema.

    :func:`demplan.load_dep1ex` and :func:`demplan.load_wiod` raise it too, for an economy the
    Rust core finds in breach of the data model, so one class covers a breach found on either
    side of the binding. It derives from ``ValueError``, as :class:`demplan.LoadError` does.
    """


_TEXT = "text"
"""What a column spec says in place of a dtype when the column holds text labels."""

_COMMODITY_COLUMNS = {
    "commodity_id": np.int64,
    "endowment": np.float64,
}
_UNIT_COLUMNS = {
    "unit_id": np.int64,
    "technology_kind": _TEXT,
    "technology_scale": np.float64,
}
_INPUT_COLUMNS = {
    "input_commodity": np.int64,
    "input_coefficient": np.float64,
}
_OUTPUT_COLUMNS = {
    "output_commodity": np.int64,
    "output_coefficient": np.float64,
}
_CONSUMER_COLUMNS = {
    "consumer_id": np.int64,
}
_ALL_COLUMNS = {
    **_COMMODITY_COLUMNS,
    **_UNIT_COLUMNS,
    **_INPUT_COLUMNS,
    **_OUTPUT_COLUMNS,
    **_CONSUMER_COLUMNS,
    "input_offsets": np.int64,
    "output_offsets": np.int64,
}

_TEXT_COLUMNS = tuple(name for name, dtype in _ALL_COLUMNS.items() if dtype is _TEXT)

_TEXT_DTYPE_KIND = "U"

_NUMERIC_DTYPE_KINDS = "biufc"
"""Dtype kinds an ``extra`` array may hold numbers in: boolean, integer, unsigned, float, complex.

These are the kinds whose bytes are their values. An object array holds references to
arbitrary Python objects, among them the empty string and ``None``, and a bytes array holds
text in no stated encoding, so neither is a column the Rust core or the run configuration
digest can read.
"""

_EXTRA_BAGS = ("commodity_extra", "unit_extra", "consumer_extra")

_COLUMN_MAPPING_EXTRAS = {"consumer_extra": {"utility_exponent_commodity": "utility_exponent"}}
"""Convention keys that map the columns of another extra to commodities.

They are the one shape of extra whose leading dimension is not the row count of its table:
``utility_exponent`` is ``f64[n_consumers, k]`` and ``utility_exponent_commodity`` is
``int64[k]``. They are checked against the array they index instead.
"""


def _freeze_array(value):
    """Read-only view of ``value``, or ``value`` itself when it is not an array.

    A view rather than the array itself, so that constructing an ``Economy`` or a ``Plan``
    around a caller's buffer does not take that buffer away from the caller.
    """
    if not isinstance(value, np.ndarray):
        return value
    frozen = value.view()
    frozen.flags.writeable = False
    return frozen


def _freeze_bag(bag: Mapping[str, np.ndarray]) -> Mapping[str, np.ndarray]:
    return MappingProxyType({key: _freeze_array(value) for key, value in dict(bag).items()})


def _text_array_of(name: str, value):
    """``value`` as a numpy text array when it is a list of ``str``; anything else unchanged.

    A list holding anything but ``str`` is refused here, since no later check could say what
    was wrong with it. numpy's text dtype drops trailing NUL characters, so a label ending in
    one is refused rather than stored shorter than it was given.
    """
    if not isinstance(value, list):
        return value
    wrong = [index for index, label in enumerate(value) if not isinstance(label, str)]
    if wrong:
        at = wrong[0]
        raise SchemaError(
            f"{name}: a list is accepted as a text column only when it holds str, and "
            f"position {at} holds {with_article(type(value[at]).__name__)}"
        )
    array = np.array(value, dtype=str) if value else np.zeros(0, dtype="<U1")
    shortened = [index for index, label in enumerate(value) if str(array[index]) != label]
    if shortened:
        raise SchemaError(
            f"{name}: the label at row {shortened[0]} ends in a NUL character, which a numpy "
            "text array cannot hold"
        )
    return array


def _require_array(name: str, value, dtype) -> np.ndarray:
    if dtype is _TEXT:
        return _require_text_column(name, value)
    if not isinstance(value, np.ndarray):
        raise SchemaError(f"{name}: expected a numpy array, got {type(value).__name__}")
    if value.dtype != np.dtype(dtype):
        raise SchemaError(f"{name}: expected dtype {np.dtype(dtype)}, got {value.dtype}")
    if value.ndim != 1:
        raise SchemaError(f"{name}: expected a one-dimensional column, got {value.ndim} dimensions")
    return value


def _require_text_column(name: str, value) -> np.ndarray:
    """Check a column of text labels: one-dimensional, dtype kind ``U``, no empty label."""
    if not isinstance(value, np.ndarray):
        raise SchemaError(
            f"{name}: expected a numpy text array or a list of str, got {type(value).__name__}"
        )
    if value.dtype.kind != _TEXT_DTYPE_KIND:
        raise SchemaError(
            f"{name}: expected text labels (a numpy array of dtype kind 'U' or a list of "
            f"str), got dtype {value.dtype}"
        )
    if value.ndim != 1:
        raise SchemaError(
            f"{name}: a text column is one-dimensional, one label per row; got "
            f"{value.ndim} dimensions"
        )
    empty = np.flatnonzero(value == "")
    if empty.size:
        raise SchemaError(f"{name}: the label at row {int(empty[0])} is empty")
    _require_utf8_labels(name, value)
    return value


def _require_utf8_labels(name: str, value: np.ndarray) -> None:
    """Refuse a label UTF-8 cannot encode, naming its row.

    A lone surrogate is a valid Python ``str`` and a valid numpy text label, and UTF-8 has no
    encoding for it, so the Rust core, a file and the run configuration digest would each
    refuse the column later. The whole column is encoded at once; the rows are searched only
    when that fails.
    """
    labels = value.tolist()
    try:
        "".join(labels).encode("utf-8")
    except UnicodeEncodeError:
        row = next(row for row, label in enumerate(labels) if not _encodes_as_utf8(label))
        raise SchemaError(
            f"{name}: the label at row {row} holds a lone surrogate, which cannot be encoded as "
            "UTF-8"
        ) from None


def _encodes_as_utf8(label: str) -> bool:
    try:
        label.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _require_length(name: str, value: np.ndarray, expected: int, reason: str) -> None:
    if value.shape[0] != expected:
        raise SchemaError(
            f"{name}: has {counted(value.shape[0], 'row')}, expected {expected} ({reason})"
        )


def _require_row_numbering(name: str, column: np.ndarray) -> None:
    expected = np.arange(column.shape[0], dtype=np.int64)
    wrong = np.flatnonzero(column != expected)
    if wrong.size:
        row = int(wrong[0])
        raise SchemaError(f"{name}: must equal the row number, found {int(column[row])} at row {row}")


def _require_commodity_index(name: str, column: np.ndarray, n_commodities: int) -> None:
    wrong = np.flatnonzero((column < 0) | (column >= n_commodities))
    if wrong.size:
        row = int(wrong[0])
        raise SchemaError(
            f"{name}: {int(column[row])} at row {row} is outside "
            f"the commodity range [0, {n_commodities})"
        )


def _require_finite(name: str, values: np.ndarray) -> None:
    if values.size == 0 or not np.issubdtype(values.dtype, np.floating):
        return
    wrong = np.flatnonzero(~np.isfinite(values.reshape(values.shape[0], -1)).all(axis=1))
    if wrong.size:
        raise SchemaError(f"{name}: row {int(wrong[0])} is not finite")


def _require_offsets(name: str, offsets: np.ndarray, n_units: int, n_entries: int, entries: str):
    """Check one flat layout's offsets: one bound per unit plus one, from 0 to ``n_entries``,
    never decreasing."""
    _require_length(name, offsets, n_units + 1, "one bound per unit plus a sentinel")
    if int(offsets[0]) != 0:
        raise SchemaError(f"{name}: must start at 0, starts at {int(offsets[0])}")
    if int(offsets[-1]) != n_entries:
        raise SchemaError(
            f"{name}: must end at the {entries} count {n_entries}, ends at {int(offsets[-1])}"
        )
    falling = np.flatnonzero(np.diff(offsets) < 0)
    if falling.size:
        row = int(falling[0])
        raise SchemaError(
            f"{name}: must not decrease, drops from {int(offsets[row])} "
            f"to {int(offsets[row + 1])} at row {row}"
        )


def _require_positive_output_coefficients(offsets: np.ndarray, coefficient: np.ndarray) -> None:
    """Refuse an output coefficient of zero or below, naming the entry and the unit owning it.

    An output coefficient is what one unit of activity delivers of that output entry. Zero
    lists an output the unit never delivers, and the tools that recover a unit's activity from
    its output divide by the coefficient. Runs after the finiteness check, so NaN never gets
    here.
    """
    wrong = np.flatnonzero(~(coefficient > 0.0))
    if wrong.size:
        entry = int(wrong[0])
        unit = int(np.searchsorted(offsets, entry, side="right")) - 1
        raise SchemaError(
            f"output_coefficient: entry {entry} (unit {unit}) is {float(coefficient[entry])}; "
            "an output coefficient has to be above zero"
        )


def _index_array(name: str, indices) -> np.ndarray:
    """``indices`` checked as a one-dimensional int64 array of distinct entries.

    For declarations that name commodities by index, such as the commodities an accessor or
    an objective counts. A repeated index says the caller meant something one array of
    indices cannot hold, so it is refused rather than read as one. Raises ``ValueError``
    naming ``name``; the range is checked by :func:`_require_indices_in_range` once the
    commodity count is known.
    """
    if not isinstance(indices, np.ndarray) or indices.dtype != np.int64 or indices.ndim != 1:
        got = (
            f"dtype {indices.dtype} with {counted(indices.ndim, 'dimension')}"
            if isinstance(indices, np.ndarray)
            else with_article(type(indices).__name__)
        )
        raise ValueError(
            f"{name}: expected a one-dimensional int64 array of commodity indices, got {got}"
        )
    values, counts = np.unique(indices, return_counts=True)
    repeated = values[counts > 1]
    if repeated.size:
        raise ValueError(f"{name}: commodity {int(repeated[0])} is listed more than once")
    return indices


def _require_indices_in_range(name: str, indices: np.ndarray, n_commodities: int) -> None:
    """Refuse an index outside ``[0, n_commodities)``. Raises ``ValueError`` naming ``name``.

    An index outside the table selects nothing, or wraps around to the wrong end of it, so a
    declaration holding one would be read as a different declaration without a word.
    """
    outside = np.flatnonzero((indices < 0) | (indices >= n_commodities))
    if outside.size:
        raise ValueError(
            f"{name}: {int(indices[outside[0]])} is outside the commodity range "
            f"[0, {n_commodities})"
        )


@dataclasses.dataclass(frozen=True, eq=False)
class Economy:
    """One period of an economy: a commodity table, a producing-unit table, a consumer table.

    Producing units hold their variable-length input and output lists in flat arrays laid out
    the same way: unit ``i`` owns ``input_commodity[input_offsets[i]:input_offsets[i + 1]]``
    and the matching slice of ``input_coefficient``, and it owns the output entries
    ``output_offsets[i]`` up to ``output_offsets[i + 1]`` of ``output_commodity`` and
    ``output_coefficient``. :meth:`inputs_of` returns the input window. Every unit has at least
    one output entry and lists a commodity at most once among its outputs; a unit with two or
    more is a unit with joint products. What ``input_coefficient`` and ``output_coefficient``
    mean is set by the unit's technology, which ``technology_kind`` names with a text label;
    the data model records no ratio between a unit's outputs and assumes none. Every output
    coefficient is above zero.

    ``commodity_extra``, ``unit_extra`` and ``consumer_extra`` carry named arrays whose leading
    dimension is the row count of their table, numeric or text; an object or bytes array is
    refused. Key names are a convention the prefabs that write them interpret; nothing here
    requires any key to be present.

    Equality is identity: the fields are numpy arrays, which have no scalar ``==``.
    """

    period: int
    commodity_id: np.ndarray
    endowment: np.ndarray
    unit_id: np.ndarray
    technology_kind: np.ndarray
    technology_scale: np.ndarray
    input_offsets: np.ndarray
    input_commodity: np.ndarray
    input_coefficient: np.ndarray
    output_offsets: np.ndarray
    output_commodity: np.ndarray
    output_coefficient: np.ndarray
    consumer_id: np.ndarray
    commodity_extra: Mapping[str, np.ndarray] = dataclasses.field(default_factory=dict)
    unit_extra: Mapping[str, np.ndarray] = dataclasses.field(default_factory=dict)
    consumer_extra: Mapping[str, np.ndarray] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in _TEXT_COLUMNS:
            object.__setattr__(self, name, _text_array_of(name, getattr(self, name)))
        for name in _ALL_COLUMNS:
            object.__setattr__(self, name, _freeze_array(getattr(self, name)))
        for bag in _EXTRA_BAGS:
            contents = {
                key: _text_array_of(f"{bag}[{key!r}]", value)
                for key, value in dict(getattr(self, bag)).items()
            }
            object.__setattr__(self, bag, _freeze_bag(contents))
        self.validate()

    @classmethod
    def from_arrays(cls, mapping: Mapping[str, object]) -> "Economy":
        """Build an economy from a mapping whose keys are the field names.

        This is the shape the Rust loaders return, text columns as lists of ``str``. The three
        ``extra`` bags may be omitted.
        """
        known = {field.name for field in dataclasses.fields(cls)}
        unknown = sorted(set(mapping) - known)
        if unknown:
            raise SchemaError(f"from_arrays: unknown keys {', '.join(unknown)}")
        return cls(**{key: value for key, value in mapping.items()})

    @property
    def n_commodities(self) -> int:
        return int(self.commodity_id.shape[0])

    @property
    def n_units(self) -> int:
        return int(self.unit_id.shape[0])

    @property
    def n_consumers(self) -> int:
        return int(self.consumer_id.shape[0])

    @property
    def n_inputs(self) -> int:
        return int(self.input_commodity.shape[0])

    @property
    def n_outputs(self) -> int:
        """Number of output entries over all units; ``n_units`` when every unit has one."""
        return int(self.output_commodity.shape[0])

    def inputs_of(self, unit: int) -> slice:
        """Window of the flat input arrays that belongs to one producing unit."""
        return slice(int(self.input_offsets[unit]), int(self.input_offsets[unit + 1]))

    def validate(self) -> None:
        """Check the structural schema. Raises :class:`SchemaError` on the first violation."""
        columns = {
            name: _require_array(name, getattr(self, name), dtype)
            for name, dtype in _ALL_COLUMNS.items()
        }
        if not isinstance(self.period, (int, np.integer)) or isinstance(self.period, bool):
            raise SchemaError(f"period: expected an integer, got {type(self.period).__name__}")

        n_commodities = self._validate_commodities(columns)
        n_units = self._validate_units(columns)
        self._validate_inputs(columns, n_units, n_commodities)
        self._validate_outputs(columns, n_units, n_commodities)
        n_consumers = self._validate_consumers(columns)
        self._validate_extras(n_commodities, n_units, n_consumers)

    def _validate_commodities(self, columns) -> int:
        n_commodities = columns["commodity_id"].shape[0]
        for name in _COMMODITY_COLUMNS:
            _require_length(name, columns[name], n_commodities, "one row per commodity")
        _require_row_numbering("commodity_id", columns["commodity_id"])
        _require_finite("endowment", columns["endowment"])
        return n_commodities

    def _validate_units(self, columns) -> int:
        n_units = columns["unit_id"].shape[0]
        for name in _UNIT_COLUMNS:
            _require_length(name, columns[name], n_units, "one row per producing unit")
        _require_row_numbering("unit_id", columns["unit_id"])
        _require_finite("technology_scale", columns["technology_scale"])
        return n_units

    def _validate_inputs(self, columns, n_units: int, n_commodities: int) -> None:
        n_inputs = columns["input_commodity"].shape[0]
        for name in _INPUT_COLUMNS:
            _require_length(name, columns[name], n_inputs, "one row per unit input")
        _require_offsets("input_offsets", columns["input_offsets"], n_units, n_inputs, "input")
        _require_commodity_index("input_commodity", columns["input_commodity"], n_commodities)
        _require_finite("input_coefficient", columns["input_coefficient"])

    def _validate_outputs(self, columns, n_units: int, n_commodities: int) -> None:
        """Check the flat output layout.

        Beyond what the input layout is held to, every unit owns at least one output entry,
        no unit lists one commodity twice among its outputs, and every output coefficient is
        above zero.
        """
        offsets = columns["output_offsets"]
        commodity = columns["output_commodity"]
        n_outputs = commodity.shape[0]
        for name in _OUTPUT_COLUMNS:
            _require_length(name, columns[name], n_outputs, "one row per output entry")
        _require_offsets("output_offsets", offsets, n_units, n_outputs, "output entry")
        without_output = np.flatnonzero(np.diff(offsets) == 0)
        if without_output.size:
            raise SchemaError(
                f"output_offsets: unit {int(without_output[0])} owns no output entry, and every "
                "producing unit has at least one"
            )
        _require_commodity_index("output_commodity", commodity, n_commodities)
        _require_finite("output_coefficient", columns["output_coefficient"])
        _require_positive_output_coefficients(offsets, columns["output_coefficient"])
        self._require_distinct_outputs_per_unit(offsets, commodity, n_units)

    @staticmethod
    def _require_distinct_outputs_per_unit(offsets, commodity, n_units: int) -> None:
        """Refuse a unit that lists the same commodity twice among its output entries.

        Sorting the entries by owner and then by commodity puts any repeat next to its twin.
        """
        owner = np.repeat(np.arange(n_units, dtype=np.int64), np.diff(offsets))
        order = np.lexsort((commodity, owner))
        repeated = np.flatnonzero(
            (np.diff(owner[order]) == 0) & (np.diff(commodity[order]) == 0)
        )
        if repeated.size:
            entry = order[int(repeated[0])]
            raise SchemaError(
                f"output_commodity: unit {int(owner[entry])} lists commodity "
                f"{int(commodity[entry])} more than once among its output entries"
            )

    def _validate_consumers(self, columns) -> int:
        n_consumers = columns["consumer_id"].shape[0]
        for name in _CONSUMER_COLUMNS:
            _require_length(name, columns[name], n_consumers, "one row per consumer unit")
        _require_row_numbering("consumer_id", columns["consumer_id"])
        return n_consumers

    def _validate_extras(self, n_commodities: int, n_units: int, n_consumers: int) -> None:
        sizes = {
            "commodity_extra": (n_commodities, "commodity"),
            "unit_extra": (n_units, "producing unit"),
            "consumer_extra": (n_consumers, "consumer unit"),
        }
        for bag, (rows, subject) in sizes.items():
            mappings = _COLUMN_MAPPING_EXTRAS.get(bag, {})
            for key, value in getattr(self, bag).items():
                label = f"{bag}[{key!r}]"
                if not isinstance(value, np.ndarray):
                    raise SchemaError(
                        f"{label}: expected a numpy array or a list of str, "
                        f"got {type(value).__name__}"
                    )
                if key in mappings:
                    self._validate_column_mapping(bag, key, mappings[key], n_commodities)
                    continue
                if value.dtype.kind == _TEXT_DTYPE_KIND:
                    _require_text_column(label, value)
                elif value.dtype.kind not in _NUMERIC_DTYPE_KINDS:
                    raise SchemaError(
                        f"{label}: expected numbers, text labels of dtype kind 'U' or a list of "
                        f"str, got dtype {value.dtype}"
                    )
                if value.ndim < 1 or value.shape[0] != rows:
                    raise SchemaError(
                        f"{label}: leading dimension is {value.shape}, expected "
                        f"{counted(rows, 'row')} (one per {subject})"
                    )
                _require_finite(label, value)

    def _validate_column_mapping(self, bag: str, key: str, base_key: str, n_commodities: int):
        mapping = getattr(self, bag)[key]
        label = f"{bag}[{key!r}]"
        if mapping.dtype != np.int64 or mapping.ndim != 1:
            raise SchemaError(f"{label}: expected a one-dimensional int64 array")
        _require_commodity_index(label, mapping, n_commodities)
        base = getattr(self, bag).get(base_key)
        if base is None:
            return
        if base.ndim != 2:
            raise SchemaError(
                f"{bag}[{base_key!r}]: expected two dimensions, got {base.ndim}, "
                f"because {key} maps its columns to commodities"
            )
        if base.shape[1] != mapping.shape[0]:
            raise SchemaError(
                f"{label}: has {counted(mapping.shape[0], 'entry', 'entries')}, expected one "
                f"per column of {base_key}, which has {base.shape[1]}"
            )
