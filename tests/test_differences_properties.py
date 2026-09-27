"""Properties of the difference report over generated Leontief economies.

Economies have at most six commodities, six producing units and four consumer units, units
may list several output entries, and a plan's consumption columns may name one commodity more
than once. Every number is an integer-valued float small enough that
sums and products are exact, so each property is asserted with ``==`` rather than a tolerance.

The feasible plans are built from the definition of feasibility, not from the report: an
activity level per unit, input use of coefficient times activity, output of output coefficient
times activity, and a leftover of supply minus input use that is split into consumption and
shared use, with some of it possibly left unallocated.
"""

from __future__ import annotations

import dataclasses

import numpy as np
from hypothesis import find, given, settings
from hypothesis import strategies as st

from demplan import (
    EXPENDITURE,
    INCOME,
    INDICATIVE_PRICE,
    Economy,
    Plan,
    input_use_on,
    plan_differences,
)

MAX_COMMODITIES = 6
MAX_UNITS = 6
MAX_CONSUMERS = 4


@dataclasses.dataclass(frozen=True)
class Case:
    """A generated economy, a feasible plan for it, and what the construction left unallocated."""

    economy: Economy
    plan: Plan
    unallocated: np.ndarray
    """Per commodity, the part of the leftover the construction gave to nobody."""


@st.composite
def feasible_cases(draw) -> tuple[Case, np.ndarray]:
    """A :class:`Case` and a set of commodities declared bads."""
    n_commodities = draw(st.integers(1, MAX_COMMODITIES))
    n_units = draw(st.integers(1, MAX_UNITS))
    n_consumers = draw(st.integers(1, MAX_CONSUMERS))
    commodity = st.integers(0, n_commodities - 1)

    input_commodity, input_coefficient, input_counts = [], [], []
    output_commodity, output_coefficient, output_counts = [], [], []
    activity = []
    for _ in range(n_units):
        inputs = draw(st.lists(commodity, max_size=3))
        input_commodity += inputs
        input_coefficient += [float(draw(st.integers(0, 3))) for _ in inputs]
        input_counts.append(len(inputs))
        outputs = draw(st.lists(commodity, min_size=1, max_size=3, unique=True))
        output_commodity += outputs
        output_coefficient += [float(draw(st.integers(1, 3))) for _ in outputs]
        output_counts.append(len(outputs))
        activity.append(float(draw(st.integers(0, 5))))

    owner_of_input = np.repeat(np.arange(n_units), input_counts)
    owner_of_output = np.repeat(np.arange(n_units), output_counts)
    activity = np.array(activity)
    input_use = np.array(input_coefficient) * activity[owner_of_input]
    output = np.array(output_coefficient) * activity[owner_of_output]

    produced = np.zeros(n_commodities)
    used = np.zeros(n_commodities)
    for entry, c in enumerate(output_commodity):
        produced[c] += output[entry]
    for entry, c in enumerate(input_commodity):
        used[c] += input_use[entry]
    endowment = np.array(
        [max(0.0, used[c] - produced[c]) + draw(st.integers(0, 6)) for c in range(n_commodities)]
    )
    leftover = produced + endowment - used

    # Columns may repeat a commodity: a plan may split one commodity over several columns.
    columns = draw(st.lists(commodity, max_size=n_commodities + 2))
    consumption = np.zeros((n_consumers, len(columns)))
    shared_use = np.zeros(n_commodities)
    unallocated = np.zeros(n_commodities)
    for c in range(n_commodities):
        remaining = int(leftover[c])
        shared_use[c] = draw(st.integers(0, remaining))
        remaining -= int(shared_use[c])
        for column in [index for index, named in enumerate(columns) if named == c]:
            for unit in range(n_consumers):
                take = draw(st.integers(0, remaining))
                consumption[unit, column] = take
                remaining -= take
        unallocated[c] = remaining

    economy = Economy(
        period=0,
        commodity_id=np.arange(n_commodities, dtype=np.int64),
        endowment=endowment,
        unit_id=np.arange(n_units, dtype=np.int64),
        technology_kind=np.array(["leontief"] * n_units),
        technology_scale=np.ones(n_units),
        input_offsets=np.concatenate([[0], np.cumsum(input_counts)]).astype(np.int64),
        input_commodity=np.array(input_commodity, dtype=np.int64),
        input_coefficient=np.array(input_coefficient, dtype=np.float64),
        output_offsets=np.concatenate([[0], np.cumsum(output_counts)]).astype(np.int64),
        output_commodity=np.array(output_commodity, dtype=np.int64),
        output_coefficient=np.array(output_coefficient, dtype=np.float64),
        consumer_id=np.arange(n_consumers, dtype=np.int64),
    )
    price = np.array([float(draw(st.integers(-3, 5))) for _ in range(n_commodities)])
    plan = Plan(
        output=output,
        input_use=input_use,
        consumption=consumption,
        consumption_commodity=np.array(columns, dtype=np.int64),
        shared_use=shared_use,
        valuation={
            INDICATIVE_PRICE: price,
            INCOME: np.array([float(draw(st.integers(0, 50))) for _ in range(n_consumers)]),
            EXPENDITURE: np.array([float(draw(st.integers(0, 50))) for _ in range(n_consumers)]),
        },
    )
    bads = np.array(
        draw(st.lists(commodity, max_size=n_commodities, unique=True)), dtype=np.int64
    )
    return Case(economy, plan, unallocated), bads


def _permuted(case: Case, order: np.ndarray) -> tuple[Economy, Plan]:
    """The same economy and plan with commodity ``c`` renamed ``new[c]``.

    ``order`` lists the old commodity that becomes each new index; ``new`` is its inverse.
    Every commodity-index column is renamed and every per-commodity array is reordered.
    """
    new = np.empty_like(order)
    new[order] = np.arange(order.size)
    economy, plan = case.economy, case.plan
    renamed = dataclasses.replace(
        economy,
        endowment=np.asarray(economy.endowment)[order],
        input_commodity=new[np.asarray(economy.input_commodity)],
        output_commodity=new[np.asarray(economy.output_commodity)],
    )
    replanned = dataclasses.replace(
        plan,
        consumption_commodity=new[np.asarray(plan.consumption_commodity)],
        shared_use=np.asarray(plan.shared_use)[order],
        valuation={
            **plan.valuation,
            INDICATIVE_PRICE: np.asarray(plan.valuation[INDICATIVE_PRICE])[order],
        },
    )
    return renamed, replanned


SETTINGS = settings(max_examples=300, deadline=None)


@SETTINGS
@given(feasible_cases())
def test_a_feasible_plan_has_no_negative_difference(drawn):
    case, _ = drawn
    difference = plan_differences(case.economy, case.plan).material_balance.difference
    assert np.all(difference >= 0.0)
    np.testing.assert_array_equal(difference, case.unallocated)


@SETTINGS
@given(feasible_cases(), st.randoms(use_true_random=False))
def test_permuting_commodities_permutes_the_report(drawn, random):
    case, bads = drawn
    n = case.economy.n_commodities
    order = np.array(random.sample(range(n), n), dtype=np.int64)
    new = np.empty_like(order)
    new[order] = np.arange(n)
    economy, plan = _permuted(case, order)

    before = plan_differences(case.economy, case.plan, bads=bads, price=INDICATIVE_PRICE)
    after = plan_differences(economy, plan, bads=new[bads], price=INDICATIVE_PRICE)
    for name in ("difference", "supply", "use"):
        original = getattr(before.material_balance, name)[order]
        assert getattr(after.material_balance, name).tobytes() == original.tobytes(), name
    assert after.budget.difference.tobytes() == before.budget.difference.tobytes()
    assert after.budget.priced_consumption.tobytes() == (
        before.budget.priced_consumption.tobytes()
    )
    assert dict(after.non_negativity.negative_count) == dict(before.non_negativity.negative_count)
    assert dict(after.non_negativity.minimum) == dict(before.non_negativity.minimum)
    assert dict(after.non_negativity.not_checked) == dict(before.non_negativity.not_checked)


@SETTINGS
@given(feasible_cases())
def test_the_differences_reconcile_with_the_plan_totals(drawn):
    case, _ = drawn
    economy, plan = case.economy, case.plan
    balance = plan_differences(economy, plan).material_balance

    total = (
        plan.output.sum() + economy.endowment.sum() - plan.input_use.sum()
        - plan.consumption.sum() - plan.shared_use.sum()
    )
    assert balance.difference.sum() == total

    for c in range(economy.n_commodities):
        supply = economy.endowment[c]
        for entry, commodity in enumerate(economy.output_commodity):
            if commodity == c:
                supply += plan.output[entry]
        use = plan.shared_use[c]
        for entry, commodity in enumerate(economy.input_commodity):
            if commodity == c:
                use += plan.input_use[entry]
        for column, commodity in enumerate(plan.consumption_commodity):
            if commodity == c:
                use += plan.consumption[:, column].sum()
        assert balance.difference[c] == supply - use, c

    every = np.arange(economy.n_commodities, dtype=np.int64)
    assert input_use_on(economy, plan, every) == plan.input_use.sum()


def test_the_generator_draws_repeated_consumption_columns():
    """Property 1 sees repeated columns only if the generator produces them."""

    def repeats_a_column(drawn):
        columns = drawn[0].plan.consumption_commodity.tolist()
        return len(set(columns)) < len(columns)

    drawn = find(feasible_cases(), repeats_a_column, settings=settings(database=None))
    assert repeats_a_column(drawn)
