"""What a plan leaves over or short: supply minus use, the budget difference, non-negativity.

:func:`plan_differences` works on any plan, whoever produced it: a run of
:func:`demplan.run`, a reference solution, a file, someone else's code. :func:`demplan.run`
calls it by default, so a researcher who did not know to look still gets the numbers.
:func:`period_differences` does the same over the periods of a trajectory.

Every report here states numbers and never a verdict. A difference is signed and carries no
tolerance, and nothing in a report says whether a plan passed. Where an input is missing the
number is ``None`` together with the reason, naming what is missing; the library never falls
back to another quantity in its place.

Which commodities are bads and which valuation key holds the prices are the caller's
statements, passed as arguments. The library reads no ``extra`` key of the economy or the plan.
"""

from __future__ import annotations

import dataclasses
from types import MappingProxyType
from typing import Collection, Mapping, Sequence

import numpy as np

from demplan.economy import Economy
from demplan.plan import (
    EXPENDITURE,
    INCOME,
    Plan,
    _VALUATION_ROWS,
    _commodity_declaration,
)

CUMULATIVE_RESOURCE_USE = "cumulative_resource_use"
"""Coverage row: the initial endowment of the declared resources minus their running use."""

CONSUMER_UNIT_COUNT = "consumer_unit_count"
"""Coverage row: the number of consumer units in each period and its change."""

CAPITAL_STOCK_NON_NEGATIVITY = "capital_stock_non_negativity"
"""Coverage row: a capital stock that stays at zero or above. Never computed."""

STOCK_FLOW_IDENTITY = "stock_flow_identity"
"""Coverage row: a stock carried between periods equals the last stock plus the net flow.
Never computed."""

_COVERAGE_ROWS = (
    CUMULATIVE_RESOURCE_USE,
    CONSUMER_UNIT_COUNT,
    CAPITAL_STOCK_NON_NEGATIVITY,
    STOCK_FLOW_IDENTITY,
)

_NOT_IN_THE_DATA_MODEL = {
    CAPITAL_STOCK_NON_NEGATIVITY: (
        "the data model has no capital stock, so there is no stock to test"
    ),
    STOCK_FLOW_IDENTITY: (
        "the data model has no stock carried from one period to the next, so there is no "
        "identity to form"
    ),
}

_NO_RESOURCES = (
    "no resources were declared: pass resources= with the commodities whose input use draws "
    "on the initial endowment"
)

_QUANTITIES = ("output", "input_use", "consumption", "shared_use")
"""The plan fields non-negativity reads, in the order :class:`demplan.Plan` declares them."""

_USE_BY_CONSUMER_UNITS = ("consumption", "shared_use")
"""The fields without which the use side of the material balance is not known."""

_PRICE_KEYS = frozenset(
    key for key, (count, _, _) in _VALUATION_ROWS.items() if count == "n_commodities"
)
"""The registered valuation keys that hold one number per commodity: the prices."""

_DECLARED_ABSENT = "declared absent by the plan"
_UNREGISTERED = "unregistered valuation key: the library does not know what it holds"
_NOTHING_TO_CHECK = "no entries to check"
_EVERY_ENTRY_NAN = "every entry is NaN"


@dataclasses.dataclass(frozen=True)
class MaterialBalance:
    """Supply minus use, per commodity, ``f64[n_commodities]`` throughout.

    ``supply`` is ``total_output + endowment`` and ``use`` is ``total_input_use +
    total_consumption + shared_use``; ``difference`` is ``supply - use``, signed. A plan that
    declares ``consumption`` or ``shared_use`` absent has no known use by consumer units, so
    ``use`` and ``difference`` are ``None`` for the whole vector and ``why_not_computed`` says
    which fields are missing. The components the plan does carry are still filled in.
    """

    total_output: np.ndarray
    """``plan.total_output(economy)``: every output entry under its own commodity."""
    endowment: np.ndarray
    total_input_use: np.ndarray
    total_consumption: np.ndarray | None
    """The consumption block summed over consumer units and filed under the commodity each
    column names; ``None`` when the plan declares ``consumption`` absent."""
    shared_use: np.ndarray | None
    supply: np.ndarray
    use: np.ndarray | None
    difference: np.ndarray | None
    why_not_computed: str | None


@dataclasses.dataclass(frozen=True)
class BudgetDifference:
    """Income minus expenditure per consumer unit, ``f64[n_consumers]``.

    All three inputs are what the mechanism filed in ``Plan.valuation``: the price under the
    key the caller names, :data:`demplan.INCOME` and :data:`demplan.EXPENDITURE`.
    ``difference`` is computed only when all three are there; ``income`` and ``expenditure``
    are filled in whenever the plan carries them.

    ``priced_consumption`` is each unit's row of ``consumption`` valued at the declared price.
    It is a reconciliation column: ``expenditure - priced_consumption`` is what the unit spent
    outside the consumption block. It is ``None`` when the plan has no consumption block or no
    declared price.
    """

    price_key: str | None
    """The valuation key the caller named with ``price=``; ``None`` when none was named."""
    income: np.ndarray | None
    expenditure: np.ndarray | None
    difference: np.ndarray | None
    priced_consumption: np.ndarray | None
    why_not_computed: str | None


@dataclasses.dataclass(frozen=True)
class NonNegativity:
    """The smallest value and the count of negative values of each quantity and price.

    Entries are named after the plan field (``output``, ``input_use``, ``consumption``,
    ``shared_use``) or as ``valuation.<key>`` for a price. A price skips the commodities the
    caller declared bads; a quantity never skips any. NaN is ignored.

    ``minimum`` and ``negative_count`` hold every entry that was read; ``minimum`` is ``None``
    for one with nothing left to check. ``not_checked`` holds every entry that was not checked,
    with the reason: a field the plan declares absent, a valuation key the library does not
    know, an entry with nothing left to check (``"no entries to check"``), or an entry whose
    every value left to check is NaN (``"every entry is NaN"``).
    """

    minimum: Mapping[str, float | None]
    negative_count: Mapping[str, int]
    not_checked: Mapping[str, str]


@dataclasses.dataclass(frozen=True)
class PlanDifferences:
    """The three reports :func:`plan_differences` returns for one plan."""

    material_balance: MaterialBalance
    budget: BudgetDifference
    non_negativity: NonNegativity


@dataclasses.dataclass(frozen=True)
class Coverage:
    """One cross-period quantity: whether it was computed, why not, and whether it was declared.

    ``declared_constraint`` repeats what the caller passed in ``constraints=``. The library does
    not judge a declared constraint against the numbers.
    """

    name: str
    computed: bool
    why_not_computed: str | None
    declared_constraint: bool


@dataclasses.dataclass(frozen=True)
class PeriodDifferences:
    """Differences over the periods of a trajectory.

    ``initial_endowment`` is period 0's endowment of the declared resources, ``f64[k]``.
    ``cumulative_use`` is ``f64[periods, k]``: row ``t`` is the input use of those resources
    summed over periods 0 to ``t``. ``resource_difference`` is ``initial_endowment -
    cumulative_use``, signed. The three are ``None`` together, with
    ``why_resources_not_computed`` saying why.

    ``consumer_units`` is the number of consumer units in each period, ``int64[periods]``, and
    ``consumer_unit_change`` its change from one period to the next, ``int64[periods - 1]``.

    ``coverage`` has one row for each of the four cross-period quantities, in the order
    :data:`CUMULATIVE_RESOURCE_USE`, :data:`CONSUMER_UNIT_COUNT`,
    :data:`CAPITAL_STOCK_NON_NEGATIVITY`, :data:`STOCK_FLOW_IDENTITY`.
    """

    initial_endowment: np.ndarray | None
    cumulative_use: np.ndarray | None
    resource_difference: np.ndarray | None
    why_resources_not_computed: str | None
    consumer_units: np.ndarray
    consumer_unit_change: np.ndarray
    coverage: tuple[Coverage, ...]


def plan_differences(
    economy: Economy,
    plan: Plan,
    bads: np.ndarray | None = None,
    price: str | None = None,
) -> PlanDifferences:
    """Supply minus use, the budget difference and non-negativity of ``plan`` on ``economy``.

    ``bads`` is a one-dimensional int64 array of the commodities the caller counts as bads, or
    ``None`` for none; a bad's price is not checked for non-negativity. ``price`` is the
    ``Plan.valuation`` key the prices are filed under; without it the budget difference is not
    computed, since the library never guesses which key holds prices.

    Raises ``TypeError`` when ``plan`` is not a :class:`demplan.Plan`; :class:`demplan.SchemaError`
    when the plan is not shaped for ``economy``, a malformed plan being an error rather than a
    missing number; ``ValueError`` when ``bads`` is not a declaration of distinct commodities
    in range, or when ``price`` names a valuation key registered as one entry per consumer unit
    (:data:`demplan.INCOME`, :data:`demplan.EXPENDITURE`) or an array that is not one entry per
    commodity.
    Non-finite values in the plan are not refused; IEEE arithmetic carries them into the
    result.
    """
    _require_a_plan(plan)
    _require_conformable(economy, plan)
    exempt = np.zeros(economy.n_commodities, dtype=bool)
    if bads is not None:
        exempt[_commodity_declaration("bads", bads, economy.n_commodities)] = True
    return PlanDifferences(
        material_balance=_material_balance(economy, plan),
        budget=_budget_difference(economy, plan, price),
        non_negativity=_non_negativity(plan, exempt),
    )


def period_differences(
    economies: Sequence[Economy],
    plans: Sequence[Plan],
    resources: np.ndarray | None = None,
    constraints: Collection[str] = (),
) -> PeriodDifferences:
    """Differences over a trajectory: ``plans[t]`` is the plan for ``economies[t]``.

    ``resources`` is a one-dimensional int64 array of the commodities whose input use draws on
    the initial endowment, or ``None``. ``constraints`` names the coverage rows the caller
    treats as constraints of the study; they are echoed in :attr:`PeriodDifferences.coverage`.

    Raises ``ValueError`` when the two sequences differ in length or are empty, when
    ``resources`` is not a declaration of distinct commodities in period 0's range, or when
    ``constraints`` holds a name that is not a coverage row; ``TypeError`` when an entry of
    ``plans`` is not a :class:`demplan.Plan`; :class:`demplan.SchemaError` when a plan is not
    shaped for its period's economy.
    """
    economies, plans = tuple(economies), tuple(plans)
    if len(economies) != len(plans):
        raise ValueError(
            f"period_differences takes one plan per economy, got {len(economies)} economies "
            f"and {len(plans)} plans"
        )
    if not economies:
        raise ValueError("period_differences needs at least one period, got none")
    declared = _declared_constraints(constraints)
    for economy, plan in zip(economies, plans):
        _require_a_plan(plan)
        _require_conformable(economy, plan)

    consumer_units = np.array([economy.n_consumers for economy in economies], dtype=np.int64)
    initial, cumulative, why_not = _cumulative_resource_use(economies, plans, resources)
    difference = None if cumulative is None else _frozen(initial[None, :] - cumulative)
    computed = {
        CUMULATIVE_RESOURCE_USE: (why_not is None, why_not),
        CONSUMER_UNIT_COUNT: (True, None),
        **{name: (False, reason) for name, reason in _NOT_IN_THE_DATA_MODEL.items()},
    }
    coverage = tuple(
        Coverage(name, *computed[name], declared_constraint=name in declared)
        for name in _COVERAGE_ROWS
    )
    return PeriodDifferences(
        initial_endowment=initial,
        cumulative_use=cumulative,
        resource_difference=difference,
        why_resources_not_computed=why_not,
        consumer_units=_frozen(consumer_units, np.int64),
        consumer_unit_change=_frozen(np.diff(consumer_units), np.int64),
        coverage=coverage,
    )


def _require_a_plan(plan) -> None:
    if not isinstance(plan, Plan):
        raise TypeError(f"expected a demplan.Plan, got {type(plan).__name__}")


def _require_conformable(economy: Economy, plan: Plan) -> None:
    """Check that every array of ``plan`` is shaped for ``economy``. Raises ``SchemaError``.

    The physical columns and the registered valuation keys are checked; finiteness is not,
    since a non-finite value is a number the report carries rather than a malformed plan.
    """
    plan._require_conformable(economy)
    plan._require_valuation_length(economy)


def _frozen(values, dtype=np.float64) -> np.ndarray:
    """A read-only array of the report's own, holding ``values``."""
    array = np.array(values, dtype=dtype, copy=True)
    array.flags.writeable = False
    return array


def _material_balance(economy: Economy, plan: Plan) -> MaterialBalance:
    """Build :class:`MaterialBalance`: each component, and use only when it is known."""
    total_output = plan.total_output(economy)
    endowment = np.asarray(economy.endowment, dtype=np.float64)
    total_input_use = plan.total_input_use(economy)
    total_consumption = None if plan.consumption is None else plan.total_consumption(economy)
    shared_use = None if plan.shared_use is None else np.asarray(plan.shared_use)
    supply = total_output + endowment

    absent = [name for name in _USE_BY_CONSUMER_UNITS if getattr(plan, name) is None]
    if absent:
        use = difference = None
        verb = "is" if len(absent) == 1 else "are"
        why_not = (
            f"Plan.{' and '.join(absent)} {verb} declared absent, so use by consumer units is "
            "not known and supply minus use cannot be formed; output, input use and endowment "
            "are still reported"
        )
    else:
        use = total_input_use + total_consumption + shared_use
        difference = supply - use
        why_not = None

    return MaterialBalance(
        total_output=_frozen(total_output),
        endowment=_frozen(endowment),
        total_input_use=_frozen(total_input_use),
        total_consumption=_optional_frozen(total_consumption),
        shared_use=_optional_frozen(shared_use),
        supply=_frozen(supply),
        use=_optional_frozen(use),
        difference=_optional_frozen(difference),
        why_not_computed=why_not,
    )


def _optional_frozen(values) -> np.ndarray | None:
    return None if values is None else _frozen(values)


def _budget_difference(economy: Economy, plan: Plan, price: str | None) -> BudgetDifference:
    """Build :class:`BudgetDifference` from the three valuation keys it needs.

    The reason lists what is missing in a fixed order: the price (undeclared, or declared and
    not in the plan), then income, then expenditure.
    """
    valuation = plan.valuation
    _require_a_price_key(price)
    missing = []
    if price is None:
        carried = ", ".join(f"'{key}'" for key in sorted(valuation)) or "no valuation key"
        missing.append(
            "no declared price (pass price= naming the valuation key the prices are filed "
            f"under; this plan carries {carried})"
        )
    elif price not in valuation:
        missing.append(f"no valuation['{price}'] (the declared price)")
    for key in (INCOME, EXPENDITURE):
        if key not in valuation:
            missing.append(f"no valuation['{key}']")

    prices = None if price is None else valuation.get(price)
    if prices is not None:
        _require_one_price_per_commodity(economy, price, prices)
    income = valuation.get(INCOME)
    expenditure = valuation.get(EXPENDITURE)

    priced_consumption = None
    if prices is not None and plan.consumption is not None:
        priced_consumption = (plan.consumption * prices[plan.consumption_commodity]).sum(axis=1)

    if missing:
        difference = None
        why_not = (
            "the budget difference needs a price, income per consumer unit and total "
            "expenditure per consumer unit, all filed by the mechanism in Plan.valuation; "
            f"this plan has {'; '.join(missing)}"
        )
    else:
        difference = income - expenditure
        why_not = None

    return BudgetDifference(
        price_key=price,
        income=_optional_frozen(income),
        expenditure=_optional_frozen(expenditure),
        difference=_optional_frozen(difference),
        priced_consumption=_optional_frozen(priced_consumption),
        why_not_computed=why_not,
    )


def _require_a_price_key(price: str | None) -> None:
    """Refuse a declared price that names a registered key holding something other than prices.

    The library knows what its registered keys hold, and income and expenditure are one entry
    per consumer unit. On an economy with as many consumer units as commodities the shape
    check below would pass either of them, so the key itself is refused. Raises ``ValueError``.
    """
    if price is None or price in _PRICE_KEYS or price not in _VALUATION_ROWS:
        return
    _, singular, _ = _VALUATION_ROWS[price]
    raise ValueError(
        f"price={price!r} names a valuation key registered as one entry per {singular}; a "
        "price is one entry per commodity"
    )


def _require_one_price_per_commodity(economy: Economy, key: str, prices: np.ndarray) -> None:
    """Refuse a declared price that is not one entry per commodity. Raises ``ValueError``."""
    if prices.shape != (economy.n_commodities,):
        raise ValueError(
            f"price={key!r} names Plan.valuation[{key!r}], which has shape {prices.shape}; a "
            f"price is one entry per commodity, and the economy has {economy.n_commodities}"
        )


def _non_negativity(plan: Plan, exempt: np.ndarray) -> NonNegativity:
    """Build :class:`NonNegativity`: the quantities in field order, then the prices by key."""
    minimum: dict[str, float | None] = {}
    negative_count: dict[str, int] = {}
    not_checked: dict[str, str] = {}

    def record(entry: str, values: np.ndarray) -> None:
        readable = values[~np.isnan(values)]
        negative_count[entry] = int(np.count_nonzero(readable < 0.0))
        if readable.size:
            minimum[entry] = float(readable.min())
            return
        minimum[entry] = None
        not_checked[entry] = _NOTHING_TO_CHECK if values.size == 0 else _EVERY_ENTRY_NAN

    for name in _QUANTITIES:
        values = getattr(plan, name)
        if values is None:
            not_checked[name] = _DECLARED_ABSENT
        else:
            record(name, np.ravel(values))

    for key in sorted(plan.valuation):
        entry = f"valuation.{key}"
        if key in _PRICE_KEYS:
            record(entry, np.asarray(plan.valuation[key])[~exempt])
        elif key not in _VALUATION_ROWS:
            not_checked[entry] = _UNREGISTERED

    return NonNegativity(
        minimum=MappingProxyType(minimum),
        negative_count=MappingProxyType(negative_count),
        not_checked=MappingProxyType(not_checked),
    )


def _declared_constraints(constraints: Collection[str]) -> frozenset[str]:
    """The coverage rows named in ``constraints``. Raises ``ValueError`` on any other name."""
    declared = frozenset(constraints)
    unknown = sorted(declared - set(_COVERAGE_ROWS))
    if unknown:
        raise ValueError(
            f"constraints names {', '.join(repr(name) for name in unknown)}, which "
            f"{'is' if len(unknown) == 1 else 'are'} not a cross-period quantity; the "
            f"quantities are {', '.join(repr(name) for name in _COVERAGE_ROWS)}"
        )
    return declared


def _cumulative_resource_use(
    economies: tuple[Economy, ...], plans: tuple[Plan, ...], resources: np.ndarray | None
) -> tuple[np.ndarray | None, np.ndarray | None, str | None]:
    """``(initial_endowment, cumulative_use, why_not)`` for the declared resources.

    The same index names the same commodity across periods only while the commodity count
    stays put, so a change in it anywhere leaves the three quantities uncomputed.
    """
    if resources is None:
        return None, None, _NO_RESOURCES
    first = economies[0].n_commodities
    listed = _commodity_declaration("resources", resources, first)
    for period, economy in enumerate(economies):
        if economy.n_commodities != first:
            return None, None, (
                f"the number of commodities changed from {first} in period 0 to "
                f"{economy.n_commodities} in period {period}, so the same index does not name "
                "the same commodity across periods"
            )
    per_period = np.stack(
        [plan.endowment_use(economy, listed)[listed] for economy, plan in zip(economies, plans)]
    )
    initial = np.asarray(economies[0].endowment, dtype=np.float64)[listed]
    return _frozen(initial), _frozen(np.cumsum(per_period, axis=0)), None
