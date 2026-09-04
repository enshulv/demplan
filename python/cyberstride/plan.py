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

_ENDOWED_KINDS = (CommodityKind.NATURAL_RESOURCE, CommodityKind.LABOR)


@dataclasses.dataclass(frozen=True, eq=False)
class Plan:
    """One period's plan.

    ``consumption`` is who gets how much of each private good: row per consumer unit, column
    per entry of ``consumption_commodity``. ``provision`` is the shared quantity of each public
    good, zero for every other commodity.

    Equality is identity, for the same reason as on :class:`Economy`.
    """

    output: np.ndarray
    input_use: np.ndarray
    consumption: np.ndarray
    consumption_commodity: np.ndarray
    provision: np.ndarray
    valuation: Mapping[str, np.ndarray] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (*_PHYSICAL_ARRAYS, "consumption_commodity"):
            _freeze_array(getattr(self, name))
        object.__setattr__(self, "valuation", _freeze_bag(self.valuation))

    def validate(self, economy: Economy) -> None:
        """Check the plan against the economy it plans. Raises :class:`SchemaError`."""
        self._validate_shapes(economy)
        for name in _PHYSICAL_ARRAYS:
            _require_finite(name, getattr(self, name))

    def total_output(self, economy: Economy) -> np.ndarray:
        """Production per commodity, aggregated over the units that produce it."""
        return np.bincount(
            economy.output_commodity, weights=self.output, minlength=economy.n_commodities
        )

    def total_input_use(self, economy: Economy) -> np.ndarray:
        """Input use per commodity, aggregated over every unit input."""
        return np.bincount(
            economy.input_commodity, weights=self.input_use, minlength=economy.n_commodities
        )

    def total_consumption(self, economy: Economy) -> np.ndarray:
        """Private-good consumption per commodity, aggregated over consumer units."""
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
        drawn = self.total_input_use(economy)
        endowed = np.isin(economy.commodity_kind, [int(kind) for kind in _ENDOWED_KINDS])
        return np.where(endowed, drawn, 0.0)

    def _validate_shapes(self, economy: Economy) -> None:
        expected = {
            "output": (economy.n_units,),
            "input_use": (economy.n_inputs,),
            "provision": (economy.n_commodities,),
        }
        for name, shape in expected.items():
            column = getattr(self, name)
            if not isinstance(column, np.ndarray) or column.dtype != np.float64:
                raise SchemaError(f"{name}: expected a float64 array")
            if column.shape != shape:
                raise SchemaError(f"{name}: shape {column.shape}, expected {shape}")

        columns = self.consumption_commodity
        if not isinstance(columns, np.ndarray) or columns.dtype != np.int64 or columns.ndim != 1:
            raise SchemaError("consumption_commodity: expected a one-dimensional int64 array")
        wrong = np.flatnonzero((columns < 0) | (columns >= economy.n_commodities))
        if wrong.size:
            row = int(wrong[0])
            raise SchemaError(
                f"consumption_commodity: {int(columns[row])} at column {row} is outside "
                f"the commodity range [0, {economy.n_commodities})"
            )

        if not isinstance(self.consumption, np.ndarray) or self.consumption.dtype != np.float64:
            raise SchemaError("consumption: expected a float64 array")
        if self.consumption.shape != (economy.n_consumers, columns.shape[0]):
            raise SchemaError(
                f"consumption: shape {self.consumption.shape}, expected "
                f"{(economy.n_consumers, columns.shape[0])} "
                "(one row per consumer unit, one column per consumption_commodity entry)"
            )
