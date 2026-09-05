"""A plan for one period: a physical layer plus a mechanism-specific valuation layer.

The physical layer is what every coordination mechanism produces, whatever it believes about
economics. The valuation layer is a named-array bag, because a mechanism that computes labour
times has no prices and a mechanism that iterates on prices has no labour times.

Not every mechanism has every physical quantity, so three of the fixed fields may be declared
absent by passing ``None``. Absence is a declaration the researcher makes, never a default:
the fields carry no default value, so leaving one out of the call is still a missing argument.

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

EFFORT = "effort"
"""Extra key: the effort each producing unit chose, ``f64[n_units]``."""

CONSUMER_DEMAND = "consumer_demand"
"""Extra key: what the consumer units asked for per commodity, ``f64[n_commodities]``."""

_VALUATION_ROWS = {
    INDICATIVE_PRICE: ("n_commodities", "commodity", "commodities"),
    LABOR_VALUE: ("n_commodities", "commodity", "commodities"),
    SHADOW_PRICE: ("n_commodities", "commodity", "commodities"),
    INCOME: ("n_consumers", "consumer unit", "consumer units"),
}
"""Row count each convention ``valuation`` key is registered with, and what that count counts.

Prices are one entry per commodity and income is one per consumer unit, so the bag has no
single length. A key outside this table means something the library cannot read, and its
length is checked the way ``extra`` is instead.
"""

_PHYSICAL_ARRAYS = ("output", "input_use", "consumption", "provision")

_REQUIRED_ARRAYS = ("output", "input_use")
"""Fixed fields no mechanism may declare absent, in the order :class:`Plan` declares them."""

_OPTIONAL_ARRAYS = ("consumption", "consumption_commodity", "provision")
"""Fixed fields a mechanism may declare absent, in the order :class:`Plan` declares them."""

_PHYSICAL_VECTORS = (
    ("output", "n_units", "units"),
    ("input_use", "n_inputs", "unit inputs"),
    ("provision", "n_commodities", "commodities"),
)
"""Field, the ``Economy`` count it is as long as, and what that count counts."""

_ENDOWED_KINDS = (CommodityKind.NATURAL_RESOURCE, CommodityKind.LABOR)


class PlanFieldAbsent(SchemaError):
    """An accessor needs a fixed field that the plan declares absent.

    The plan's mechanism said it has no such quantity, so the accessor has nothing to answer
    with. It refuses rather than answering zero: a zero would enter one side of a balance as a
    quantity the other side never carried, and the two sides would then not close.
    """


@dataclasses.dataclass(frozen=True, eq=False)
class Plan:
    """One period's plan.

    ``consumption`` is who gets how much of each private good: row per consumer unit, column
    per entry of ``consumption_commodity``. ``provision`` is the shared quantity of each public
    good, zero for every other commodity.

    ``consumption``, ``consumption_commodity`` and ``provision`` may be ``None``, which says
    the mechanism has no such quantity: a mechanism that balances totals alone has no
    consumption per consumer unit, and one whose public supply is regional cannot state it as
    a single society-wide scalar. ``None`` is the whole declaration, and :attr:`absent_fields`
    reads it back. ``consumption`` and ``consumption_commodity`` describe one quantity between
    them, so they are absent together or present together. ``output`` and ``input_use`` are
    required: every mechanism that plans production has both, and ``None`` in either is
    refused at construction.

    ``extra`` is a named-array bag for physical quantities the fixed fields have no column
    for, on the same pattern as the ``extra`` bags of :class:`Economy`. Each array is one row
    per producing unit, per consumer unit or per commodity. Key names are a library
    convention that mechanisms write and readers interpret; nothing requires any key to be
    present. Two are in use:

    ``effort``
        ``f64[n_units]``, the effort each producing unit chose. A technology whose production
        function carries an effort factor cannot be read back from ``output`` and
        ``input_use`` alone.
    ``consumer_demand``
        ``f64[n_commodities]``, how much of each commodity the consumer councils asked for, as
        it entered this round's material balance: a private good carries the same total
        ``consumption`` holds, a public good carries the quantity shared once over the whole
        society, and a commodity that is neither carries the councils' whole stated total.
        Zero where no council asked for the commodity. ``consumption`` covers the private
        goods alone and ``provision`` is a public good's supply side, so without this key the
        demand side of every other commodity is missing and the material balance cannot be
        rebuilt from the plan.

    Both carry a constant, :data:`EFFORT` and :data:`CONSUMER_DEMAND`, because a reader needs
    them to take a plan apart: two researchers comparing their runs have to spell such a key
    the same way, or the two sets of output do not line up. The ``extra`` keys of
    :class:`Economy` carry no constant, being parameters a mechanism reads on the way in
    rather than vocabulary for reading a plan back; each prefab says what its own mean.

    Equality is identity, for the same reason as on :class:`Economy`.
    """

    output: np.ndarray
    input_use: np.ndarray
    consumption: np.ndarray | None
    consumption_commodity: np.ndarray | None
    provision: np.ndarray | None
    valuation: Mapping[str, np.ndarray] = dataclasses.field(default_factory=dict)
    extra: Mapping[str, np.ndarray] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in (*_PHYSICAL_ARRAYS, "consumption_commodity"):
            object.__setattr__(self, name, _freeze_array(getattr(self, name)))
        for bag in ("valuation", "extra"):
            object.__setattr__(self, bag, _freeze_bag(getattr(self, bag)))
        self._require_the_required_arrays()
        self._require_consumption_pairing()
        self._require_valuation_dtype()

    @property
    def absent_fields(self) -> tuple[str, ...]:
        """The fixed fields this plan declares absent, in the order they are declared.

        This is where a reader finds out which quantities the plan does not carry, so that a
        report over several mechanisms says "this mechanism has no such quantity" instead of
        printing a zero none of them computed.
        """
        return tuple(name for name in _OPTIONAL_ARRAYS if getattr(self, name) is None)

    def validate(self, economy: Economy) -> None:
        """Check the plan against the economy it plans. Raises :class:`SchemaError`."""
        self._require_conformable(economy)
        for name in _PHYSICAL_ARRAYS:
            column = getattr(self, name)
            if column is not None:
                _require_finite(name, column)
        self._require_valuation_length(economy)
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
        ``consumption_commodity`` is zero. Raises :class:`PlanFieldAbsent` when the plan
        declares the consumption block absent.
        """
        self._require_present(
            ("consumption", "consumption_commodity"),
            "total_consumption",
            "it sums the consumption block over consumer units and files each column under "
            "the commodity that column stands for",
        )
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

    def _require_present(self, names: tuple[str, ...], accessor: str, needs: str) -> None:
        """Raise :class:`PlanFieldAbsent` for the first of ``names`` this plan declares absent.

        The message names the field, says what the accessor wanted it for, and says that an
        accessor over a quantity the mechanism does not have is an accessor that does not
        apply to it. The reader is a researcher, who should not have to read a stack trace to
        find out which of the two it is.
        """
        for name in names:
            if getattr(self, name) is None:
                raise PlanFieldAbsent(
                    f"Plan.{name} is absent from this plan, and {accessor} needs it because "
                    f"{needs}. If your mechanism has no such quantity, {accessor} does not "
                    f"apply to it; if it has one, pass it instead of None."
                )

    def _require_the_required_arrays(self) -> None:
        """Check that ``output`` and ``input_use`` carry arrays. Raises :class:`SchemaError`.

        Absence is a declaration a mechanism makes about a quantity it does not compute, and
        these two are not among the quantities it may make it about. The check is at
        construction rather than in :meth:`validate` because nothing obliges a researcher to
        call :meth:`validate` -- ``run`` does not -- and a plan carrying neither column leaves
        every tool that reads the columns a plan carries with nothing to read: the divergence
        watch of :func:`cyberstride.iterate` finds no array to test and reports the loop as
        finite, and :func:`cyberstride.check_determinism` finds no column to compare.
        """
        for name in _REQUIRED_ARRAYS:
            if getattr(self, name) is None:
                raise SchemaError(
                    f"Plan.{name} is None, but it is a required field: every mechanism that "
                    f"plans production has both of {', '.join(_REQUIRED_ARRAYS)}. The fields a "
                    f"mechanism may declare absent are {', '.join(_OPTIONAL_ARRAYS)}."
                )

    def _require_consumption_pairing(self) -> None:
        """Check that the consumption block and its column mapping agree. Raises ``SchemaError``.

        The two describe one quantity between them, and either one alone says nothing: a
        consumption block with no mapping is a matrix of unnamed columns, and a mapping with no
        block names columns that do not exist.
        """
        if (self.consumption is None) == (self.consumption_commodity is None):
            return
        absent = "consumption" if self.consumption is None else "consumption_commodity"
        present = "consumption_commodity" if self.consumption is None else "consumption"
        raise SchemaError(
            f"Plan.{absent} is None while Plan.{present} carries an array. The two describe "
            "one quantity -- who gets how much of which commodity -- so a plan either "
            "declares both absent or gives both."
        )

    def _require_valuation_dtype(self) -> None:
        """Check that every ``valuation`` array is float64. Raises :class:`SchemaError`.

        Dtype is checked at construction rather than from :meth:`validate` because nothing
        obliges a researcher to call :meth:`validate` -- ``run`` does not -- and a mechanism
        that computes its prices in an integer type would otherwise file truncated numbers
        with nothing raised. The length half of the same check needs the economy's commodity
        count, which construction does not have, so it runs from :meth:`validate`.
        """
        for key, value in self.valuation.items():
            if isinstance(value, np.ndarray) and value.dtype == np.float64:
                continue
            got = value.dtype if isinstance(value, np.ndarray) else type(value).__name__
            raise SchemaError(
                f"Plan.valuation[{key!r}]: expected a float64 array, got {got}. A valuation "
                "is refused rather than converted, because converting it would hide that the "
                "mechanism computed the quantity in another type."
            )

    def _require_valuation_length(self, economy: Economy) -> None:
        """Check the length of every ``valuation`` array. Raises :class:`SchemaError`.

        A key in :data:`_VALUATION_ROWS` is checked against the row count it is registered
        with, because the library knows what that key holds. Any other key is checked the way
        the ``extra`` bag is, against the three row counts a plan's arrays can carry: the
        library cannot read what an unregistered key counts across, so all it can ask is that
        the leading dimension is one of the three.

        This is the half of the valuation check that needs the economy;
        :meth:`_require_valuation_dtype` runs the other half at construction.
        """
        counts = (economy.n_units, economy.n_consumers, economy.n_commodities)
        for key, value in self.valuation.items():
            label = f"Plan.valuation[{key!r}]"
            registered = _VALUATION_ROWS.get(key)
            if registered is None:
                if value.ndim < 1 or value.shape[0] not in counts:
                    raise SchemaError(
                        f"{label} has shape {value.shape}, expected a leading dimension of "
                        f"{economy.n_units} producing units, {economy.n_consumers} consumer "
                        f"units or {economy.n_commodities} commodities"
                    )
                continue
            count, singular, plural = registered
            expected = getattr(economy, count)
            if value.shape != (expected,):
                raise SchemaError(
                    f"{label} has shape {value.shape}, but this key is registered as one "
                    f"entry per {singular} and the economy has {expected} {plural}"
                )

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

        A field the plan declares absent is skipped, but only where absence is a declaration a
        mechanism may make. ``output`` and ``input_use`` are not among those, and construction
        has already refused ``None`` in either, so what reaches the checks below is an array
        whose dtype and length are still open questions.
        """
        for name, count, subject in _PHYSICAL_VECTORS:
            column = getattr(self, name)
            if column is None and name in _OPTIONAL_ARRAYS:
                continue
            expected = getattr(economy, count)
            if not isinstance(column, np.ndarray) or column.dtype != np.float64:
                raise SchemaError(f"Plan.{name}: expected a float64 array")
            if column.shape != (expected,):
                raise SchemaError(
                    f"Plan.{name} has {column.size} entries but the economy has "
                    f"{expected} {subject}"
                )

        columns = self.consumption_commodity
        if columns is None:
            return
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


class StatedPlan(Plan):
    """A plan whose ``consumption`` is what the consumer units asked for.

    It adds an identity and nothing else: no field, and no narrowing of anything
    :class:`Plan` accepts or promises. A plan filed without an identity is the widest reading,
    "the consumption-side quantity", which is what :class:`Plan` itself means.
    """


class AllocatedPlan(Plan):
    """A plan whose ``consumption`` is what the mechanism allocated to the consumer units.

    It adds an identity and nothing else, on the same terms as :class:`StatedPlan`.
    """


def require_comparable(first: Plan, other: Plan) -> None:
    """Check that two plans' ``consumption`` fields mean the same thing. Raises ``ValueError``.

    A stated quantity and an allocated one differ by whatever the mechanism could not satisfy,
    so a reader who subtracts one from the other reads that difference as economics. Two plans
    of the same kind pass, and so does a plain :class:`Plan` on either side, that being the
    widest reading rather than a third one.
    """
    if {_consumption_reading(first), _consumption_reading(other)} == {"stated", "allocated"}:
        raise ValueError(
            f"{type(first).__name__} and {type(other).__name__} are not comparable: "
            "consumption on a StatedPlan is what the consumer units asked for, and on an "
            "AllocatedPlan it is what the mechanism allocated to them. Subtracting one from "
            "the other reports a difference in meaning as if it were a difference in the "
            "economy. Compare two plans of the same kind, or either against a plain Plan."
        )


def _consumption_reading(plan: Plan) -> str | None:
    """Which reading of ``consumption`` a plan declares, or ``None`` for the widest one."""
    if isinstance(plan, StatedPlan):
        return "stated"
    if isinstance(plan, AllocatedPlan):
        return "allocated"
    return None
