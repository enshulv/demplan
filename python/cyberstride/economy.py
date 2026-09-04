"""The data model: one period of an economy, held as columns.

``Economy`` is the one type in this library that is fixed rather than pluggable. Everything a
coordination procedure needs about the period is here; anything that carries a commitment to
one school of economics belongs in an ``extra`` bag or in the procedure's own state. In
particular there are no prices: valuations live on ``Plan``.

The arrays are made read-only on construction. A frozen dataclass stops fields from being
rebound but does nothing about writing through a numpy array, and a procedure that quietly
edited its input would break the promise that two runs on the same economy are comparable.
Evolve an economy with :func:`dataclasses.replace`, which revalidates the result.
"""

from __future__ import annotations

import dataclasses
from enum import IntEnum
from types import MappingProxyType
from typing import Mapping

import numpy as np


class SchemaError(ValueError):
    """An ``Economy`` or ``Plan`` violates the structural schema.

    It derives from ``ValueError`` because the Rust core reports schema violations across the
    binding as ``ValueError`` as well, so callers can catch one type either side.
    """


class CommodityKind(IntEnum):
    """Class marker on the commodity table. New classes are new values, not new columns."""

    PRIVATE_GOOD = 0
    PUBLIC_GOOD = 1
    INTERMEDIATE = 2
    NATURAL_RESOURCE = 3
    LABOR = 4


class TechnologyKind(IntEnum):
    """How to read ``input_coefficient`` for a producing unit."""

    LEONTIEF = 0
    COBB_DOUGLAS = 1


_COMMODITY_COLUMNS = {
    "commodity_id": np.int64,
    "commodity_kind": np.int8,
    "endowment": np.float64,
}
_UNIT_COLUMNS = {
    "unit_id": np.int64,
    "unit_group": np.int64,
    "output_commodity": np.int64,
    "technology_kind": np.int8,
    "technology_scale": np.float64,
}
_INPUT_COLUMNS = {
    "input_commodity": np.int64,
    "input_coefficient": np.float64,
}
_CONSUMER_COLUMNS = {
    "consumer_id": np.int64,
    "consumer_group": np.int64,
}
_ALL_COLUMNS = {
    **_COMMODITY_COLUMNS,
    **_UNIT_COLUMNS,
    **_INPUT_COLUMNS,
    **_CONSUMER_COLUMNS,
    "input_offsets": np.int64,
}

_EXTRA_BAGS = ("commodity_extra", "unit_extra", "consumer_extra")

_COLUMN_MAPPING_EXTRAS = {"consumer_extra": {"utility_exponent_commodity": "utility_exponent"}}
"""Convention keys that map the columns of another extra to commodities.

They are the one shape of extra whose leading dimension is not the row count of its table:
``utility_exponent`` is ``f64[n_consumers, k]`` and ``utility_exponent_commodity`` is
``int64[k]``. They are checked against the array they index instead.
"""


def _freeze_array(value):
    if isinstance(value, np.ndarray):
        value.flags.writeable = False
    return value


def _freeze_bag(bag: Mapping[str, np.ndarray]) -> Mapping[str, np.ndarray]:
    return MappingProxyType({key: _freeze_array(value) for key, value in dict(bag).items()})


def _require_array(name: str, value, dtype) -> np.ndarray:
    if not isinstance(value, np.ndarray):
        raise SchemaError(f"{name}: expected a numpy array, got {type(value).__name__}")
    if value.dtype != np.dtype(dtype):
        raise SchemaError(f"{name}: expected dtype {np.dtype(dtype)}, got {value.dtype}")
    if value.ndim != 1:
        raise SchemaError(f"{name}: expected a one-dimensional column, got {value.ndim} dimensions")
    return value


def _require_length(name: str, value: np.ndarray, expected: int, reason: str) -> None:
    if value.shape[0] != expected:
        raise SchemaError(f"{name}: has {value.shape[0]} rows, expected {expected} ({reason})")


def _require_row_numbering(name: str, column: np.ndarray) -> None:
    expected = np.arange(column.shape[0], dtype=np.int64)
    wrong = np.flatnonzero(column != expected)
    if wrong.size:
        row = int(wrong[0])
        raise SchemaError(f"{name}: must equal the row number, found {int(column[row])} at row {row}")


def _require_known_kind(name: str, column: np.ndarray, kinds: type[IntEnum]) -> None:
    allowed = np.array([int(k) for k in kinds], dtype=column.dtype)
    wrong = np.flatnonzero(~np.isin(column, allowed))
    if wrong.size:
        row = int(wrong[0])
        raise SchemaError(
            f"{name}: {int(column[row])} at row {row} is not a {kinds.__name__} value"
        )


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


@dataclasses.dataclass(frozen=True, eq=False)
class Economy:
    """One period of an economy: a commodity table, a producing-unit table, a consumer table.

    Producing units hold their variable-length input lists in flat arrays: unit ``i`` owns
    ``input_commodity[input_offsets[i]:input_offsets[i + 1]]`` and the matching slice of
    ``input_coefficient``. :meth:`inputs_of` returns that window.

    ``commodity_extra``, ``unit_extra`` and ``consumer_extra`` carry named arrays whose leading
    dimension is the row count of their table. Key names are a library convention that
    prefabs interpret; nothing here requires any particular key to be present.

    Equality is identity: the fields are numpy arrays, which have no scalar ``==``.
    """

    period: int
    commodity_id: np.ndarray
    commodity_kind: np.ndarray
    endowment: np.ndarray
    unit_id: np.ndarray
    unit_group: np.ndarray
    output_commodity: np.ndarray
    technology_kind: np.ndarray
    technology_scale: np.ndarray
    input_offsets: np.ndarray
    input_commodity: np.ndarray
    input_coefficient: np.ndarray
    consumer_id: np.ndarray
    consumer_group: np.ndarray
    commodity_extra: Mapping[str, np.ndarray] = dataclasses.field(default_factory=dict)
    unit_extra: Mapping[str, np.ndarray] = dataclasses.field(default_factory=dict)
    consumer_extra: Mapping[str, np.ndarray] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in _ALL_COLUMNS:
            _freeze_array(getattr(self, name))
        for bag in _EXTRA_BAGS:
            object.__setattr__(self, bag, _freeze_bag(getattr(self, bag)))
        self.validate()

    @classmethod
    def from_arrays(cls, mapping: Mapping[str, object]) -> "Economy":
        """Build an economy from a mapping whose keys are the field names.

        This is the shape the Rust loaders return. The three ``extra`` bags may be omitted.
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

    def commodities_of_kind(self, kind: CommodityKind | int) -> np.ndarray:
        """Commodity ids carrying ``kind``, in ascending order."""
        return np.flatnonzero(self.commodity_kind == int(kind)).astype(np.int64)

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
        n_units = self._validate_units(columns, n_commodities)
        self._validate_inputs(columns, n_units, n_commodities)
        n_consumers = self._validate_consumers(columns)
        self._validate_extras(n_commodities, n_units, n_consumers)

    def _validate_commodities(self, columns) -> int:
        n_commodities = columns["commodity_id"].shape[0]
        for name in _COMMODITY_COLUMNS:
            _require_length(name, columns[name], n_commodities, "one row per commodity")
        _require_row_numbering("commodity_id", columns["commodity_id"])
        _require_known_kind("commodity_kind", columns["commodity_kind"], CommodityKind)
        _require_finite("endowment", columns["endowment"])
        return n_commodities

    def _validate_units(self, columns, n_commodities: int) -> int:
        n_units = columns["unit_id"].shape[0]
        for name in _UNIT_COLUMNS:
            _require_length(name, columns[name], n_units, "one row per producing unit")
        _require_row_numbering("unit_id", columns["unit_id"])
        _require_known_kind("technology_kind", columns["technology_kind"], TechnologyKind)
        _require_commodity_index("output_commodity", columns["output_commodity"], n_commodities)
        _require_finite("technology_scale", columns["technology_scale"])
        return n_units

    def _validate_inputs(self, columns, n_units: int, n_commodities: int) -> None:
        offsets = columns["input_offsets"]
        _require_length("input_offsets", offsets, n_units + 1, "one bound per unit plus a sentinel")
        n_inputs = columns["input_commodity"].shape[0]
        for name in _INPUT_COLUMNS:
            _require_length(name, columns[name], n_inputs, "one row per unit input")
        if int(offsets[0]) != 0:
            raise SchemaError(f"input_offsets: must start at 0, starts at {int(offsets[0])}")
        if int(offsets[-1]) != n_inputs:
            raise SchemaError(
                f"input_offsets: must end at the input count {n_inputs}, ends at {int(offsets[-1])}"
            )
        falling = np.flatnonzero(np.diff(offsets) < 0)
        if falling.size:
            row = int(falling[0])
            raise SchemaError(
                f"input_offsets: must not decrease, drops from {int(offsets[row])} "
                f"to {int(offsets[row + 1])} at row {row}"
            )
        _require_commodity_index("input_commodity", columns["input_commodity"], n_commodities)
        _require_finite("input_coefficient", columns["input_coefficient"])

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
                    raise SchemaError(f"{label}: expected a numpy array, got {type(value).__name__}")
                if key in mappings:
                    self._validate_column_mapping(bag, key, mappings[key], n_commodities)
                    continue
                if value.ndim < 1 or value.shape[0] != rows:
                    raise SchemaError(
                        f"{label}: leading dimension is {value.shape}, expected {rows} rows "
                        f"(one per {subject})"
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
                f"{label}: has {mapping.shape[0]} entries, expected one per column of "
                f"{base_key}, which has {base.shape[1]}"
            )
