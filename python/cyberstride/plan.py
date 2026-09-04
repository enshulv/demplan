"""A plan for one period: a physical layer plus a mechanism-specific valuation layer.

The physical layer is what every coordination mechanism produces, whatever it believes about
economics. The valuation layer is a named-array bag, because a mechanism that computes labour
times has no prices and a mechanism that iterates on prices has no labour times.

Input use is stored, not derived. Where technology allows substitution the input mix is a
decision the mechanism made, and recomputing it afterwards would silently replace that
decision with the recomputing tool's own theory. Endowment use, by contrast, is a pure
aggregation of input use and is derived by :meth:`Plan.endowment_use`.
"""

from __future__ import annotations

import dataclasses
from typing import Mapping

import numpy as np

from cyberstride.economy import (
    CommodityKind,
    Economy,
    SchemaError,
    _freeze_array,
    _freeze_bag,
    _require_finite,
)

INDICATIVE_PRICE = "indicative_price"
"""Valuation key: the price vector an iterative price mechanism converged on."""

LABOR_VALUE = "labor_value"
"""Valuation key: labour time embodied per unit of each commodity."""

SHADOW_PRICE = "shadow_price"
"""Valuation key: dual variables of a programming formulation."""

INCOME = "income"
"""Valuation key: income per consumer unit, ``f64[n_consumers]``."""

_PHYSICAL_ARRAYS = ("output", "input_use", "consumption", "provision")

_PHYSICAL_VECTORS = (
    ("output", "n_units", "units"),
    ("input_use", "n_inputs", "unit inputs"),
    ("provision", "n_commodities", "commodities"),
)
"""Field, the ``Economy`` count it is as long as, and what that count counts."""

_ENDOWED_KINDS = (CommodityKind.NATURAL_RESOURCE, CommodityKind.LABOR)


@dataclasses.dataclass(frozen=True, eq=False)
class Plan:
    """One period's plan.

    ``consumption`` is who gets how much of each private good: row per consumer unit, column
    per entry of ``consumption_commodity``. ``provision`` is the shared quantity of each public
    good, zero for every other commodity.

    ``extra`` is a named-array bag for physical quantities the fixed fields have no column
    for, on the same pattern as the ``extra`` bags of :class:`Economy`. Each array is one row
    per producing unit, per consumer unit or per commodity. Key names are a library
    convention that mechanisms write and readers interpret; nothing requires any key to be
    present. Two are in use:

    ``effort``
        ``f64[n_units]``, the effort each producing unit chose. A technology whose production
        function carries an effort factor cannot be read back from ``output`` and
        ``input_use`` alone.
    ``public_demand``
        ``f64[n_commodities]``, how much of each public good the consumer councils asked for,
        zero for every other commodity. ``provision`` is the supply side of a public good;
        without the demand side its material balance cannot be rebuilt from the plan.

    Equality is identity, for the same reason as on :class:`Economy`.
    """

    output: np.ndarray
    input_use: np.ndarray
    consumption: np.ndarray
    consumption_commodity: np.ndarray
    provision: np.ndarray
    valuation: Mapping[str, np.ndarray] = dataclasses.field(default_factory=dict)
    extra: Mapping[str, np.ndarray] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (*_PHYSICAL_ARRAYS, "consumption_commodity"):
            object.__setattr__(self, name, _freeze_array(getattr(self, name)))
        for bag in ("valuation", "extra"):
            object.__setattr__(self, bag, _freeze_bag(getattr(self, bag)))

    def validate(self, economy: Economy) -> None:
        """Check the plan against the economy it plans. Raises :class:`SchemaError`."""
        self._require_conformable(economy)
        for name in _PHYSICAL_ARRAYS:
            _require_finite(name, getattr(self, name))
        self._require_extra_rows(economy)

    def total_output(self, economy: Economy) -> np.ndarray:
        """Production per commodity, aggregated over the units that produce it."""
        self._require_conformable(economy)
        return np.bincount(
            economy.output_commodity, weights=self.output, minlength=economy.n_commodities
        )

    def total_input_use(self, economy: Economy) -> np.ndarray:
        """Input use per commodity, aggregated over every unit input."""
        self._require_conformable(economy)
        return np.bincount(
            economy.input_commodity, weights=self.input_use, minlength=economy.n_commodities
        )

    def total_consumption(self, economy: Economy) -> np.ndarray:
        """Private-good consumption per commodity, aggregated over consumer units.

        The result covers all ``n_commodities``; every commodity outside
        ``consumption_commodity`` is zero.
        """
        self._require_conformable(economy)
        return np.bincount(
            self.consumption_commodity,
            weights=self.consumption.sum(axis=0),
            minlength=economy.n_commodities,
        )

    def endowment_use(self, economy: Economy) -> np.ndarray:
        """How much of each natural resource and each kind of labour the plan draws on.

        Other commodities are zero: they are produced within the period, so their use is not
        a draw on the endowment.
        """
        self._require_conformable(economy)
        drawn = self.total_input_use(economy)
        endowed = np.isin(economy.commodity_kind, [int(kind) for kind in _ENDOWED_KINDS])
        return np.where(endowed, drawn, 0.0)

    def _require_extra_rows(self, economy: Economy) -> None:
        """Check the ``extra`` bag. Raises :class:`SchemaError`.

        Which of the three row counts an extra array carries comes from the key's meaning,
        which the library does not know, so the check is that the leading dimension is one of
        them.
        """
        counts = (economy.n_units, economy.n_consumers, economy.n_commodities)
        for key, value in self.extra.items():
            label = f"Plan.extra[{key!r}]"
            if not isinstance(value, np.ndarray):
                raise SchemaError(f"{label}: expected a numpy array, got {type(value).__name__}")
            if value.ndim < 1 or value.shape[0] not in counts:
                raise SchemaError(
                    f"{label} has shape {value.shape}, expected a leading dimension of "
                    f"{economy.n_units} producing units, {economy.n_consumers} consumer units "
                    f"or {economy.n_commodities} commodities"
                )
            _require_finite(label, value)

    def _require_conformable(self, economy: Economy) -> None:
        """Check that every array is shaped for ``economy``. Raises :class:`SchemaError`.

        The derived accessors run this on entry as well as :meth:`validate`. Without it
        :meth:`total_consumption` scatters a plan of any size into a commodity-length vector
        and answers with a wrong one instead of an error.
        """
        for name, count, subject in _PHYSICAL_VECTORS:
            column = getattr(self, name)
            expected = getattr(economy, count)
            if not isinstance(column, np.ndarray) or column.dtype != np.float64:
                raise SchemaError(f"Plan.{name}: expected a float64 array")
            if column.shape != (expected,):
                raise SchemaError(
                    f"Plan.{name} has {column.size} entries but the economy has "
                    f"{expected} {subject}"
                )

        columns = self.consumption_commodity
        if not isinstance(columns, np.ndarray) or columns.dtype != np.int64 or columns.ndim != 1:
            raise SchemaError(
                "Plan.consumption_commodity: expected a one-dimensional int64 array"
            )
        wrong = np.flatnonzero((columns < 0) | (columns >= economy.n_commodities))
        if wrong.size:
            at = int(wrong[0])
            raise SchemaError(
                f"Plan.consumption_commodity holds {int(columns[at])} at column {at}, "
                f"outside the commodity range [0, {economy.n_commodities})"
            )

        consumption = self.consumption
        if not isinstance(consumption, np.ndarray) or consumption.dtype != np.float64:
            raise SchemaError("Plan.consumption: expected a float64 array")
        if consumption.shape != (economy.n_consumers, columns.shape[0]):
            raise SchemaError(
                f"Plan.consumption has shape {consumption.shape} but the economy has "
                f"{economy.n_consumers} consumer units and the plan has "
                f"{columns.shape[0]} consumption columns"
            )
