"""The councils and the facilitation board of the Hahnel participatory-planning procedure.

Each round every worker council proposes the output that maximises its own objective at the
current indicative prices, every consumer council states the bundle its entitlement buys at
those prices, and the facilitation board measures the relative imbalance of each commodity and
hands it to a price rule, which returns the next round's prices. The run stops when the worst
imbalance falls below the threshold.

The imbalance is measured on the proposals made at the current price, before the price is
moved, so the round that reports convergence is the round whose price is reported. That
belongs to the loop and holds whatever rule is plugged in.

This module is the half of the prefab that does not depend on which source's price rule runs.
The price rule is the seam: :class:`CouncilModel` takes any :class:`PriceRule`, including one
that carries state from one round to the next, and the rule a published run used lives in a
module of its own.

Public goods are priced per consumer unit: a consumer council facing a public good pays the
listed price divided by the number of consumer units, and its stated demand counts once for
the whole society rather than once per council. The two halves of that rule cancel, so it
moves no number the plan reports; :class:`CouncilModel` sets out why, and what it would take
to give the rule consequences.

The production function is ``Q = a * e**c * prod(x_j ** b_j)``: a Cobb-Douglas input bundle
with an effort factor, where ``e`` is the effort the worker council chose and ``c`` is
``effort_c``. The economy says so by labelling every unit
:data:`~demplan.prefabs.hahnel.TECHNOLOGY`, and says which class each commodity belongs to in
``commodity_extra["hahnel_kind"]``. Both the effort and the consumer councils' demand per
commodity go into ``Plan.extra``, because neither can be recovered from the physical layer.
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Protocol

import numpy as np

from demplan.economy import Economy
from demplan.plan import (
    CONSUMER_DEMAND,
    EFFORT,
    EXPENDITURE,
    INCOME,
    INDICATIVE_PRICE,
    Plan,
    StatedPlan,
)
from demplan.prefabs.hahnel.labels import PUBLIC_GOOD, TECHNOLOGY, kind_labels
from demplan.tools import _require_one_output_per_unit, segment_sum, unit_of_input

NEXT_INDICATIVE_PRICE = "next_indicative_price"
"""Valuation key: the price the rule returned in a round, the price the next round would use."""

PRICE_RULE_STATE = "price_rule_state"
"""Extra key: the state the rule returned in a round, the state the next round would receive."""

PERCENT = 100.0

_REQUIRED_UNIT_KEYS = ("effort_c", "effort_s", "effort_k")
_REQUIRED_CONSUMER_KEYS = ("entitlement", "utility_exponent", "utility_exponent_commodity")


class PriceRule(Protocol):
    """How the facilitation board turns one round's price into the next round's price.

    ``initial_state(n_commodities)`` returns the state the rule starts a run from: a float64
    array whose first dimension is ``n_commodities``, since the board files it on the plan as
    ``extra["price_rule_state"]``.

    ``__call__`` takes four arguments. The first three are ``f64[n_commodities]``: the price
    the proposals were made at, supply minus demand at that price, and the relative imbalance
    ``|2(supply - demand) / (supply + demand)|``. The fourth is the state the previous round
    returned, or the initial state in round one. It returns ``(next_price, next_state)``: the
    next price, ``f64[n_commodities]``, and the state the next round receives, under the same
    rules as the initial state.

    A rule object is reused across runs, and one procedure object solves many times, so a rule
    keeps no state of its own. Whatever it needs to remember between rounds goes into the state
    it returns, which the board carries: the board asks for an initial state once per run and
    hands each round the state the previous round returned. A rule that remembered on itself
    would carry one run's history into the next.

    The four arguments are read-only copies the board owns. Writing to one raises, and reaching
    around the flag reaches nothing: a copy owns its memory, so it has no ``base`` to write
    through. The board also keeps copies of both return values, so a rule may hold one output
    buffer for each and rewrite them every round.

    Ownership is worth stating because three of the four arguments carry figures the run
    reports. The board files the plan under the price it stepped with, as
    ``valuation["indicative_price"]``; it tests convergence on the imbalance it measured, which
    is the round count a prefab reproduces; and the state decides the next round's step.
    """

    def initial_state(self, n_commodities: int) -> np.ndarray:
        ...

    def __call__(
        self,
        price: np.ndarray,
        surplus: np.ndarray,
        imbalance: np.ndarray,
        state: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        ...


@dataclasses.dataclass(frozen=True)
class StatelessPriceRule:
    """A price function of ``(price, surplus, imbalance)`` as a :class:`PriceRule`.

    Its state is zero for every commodity and passes through every round unchanged, so the
    plan still carries a ``price_rule_state`` entry, of zeros. It is a dataclass rather than
    a closure so that a run configuration document records the wrapper and, as its parameter,
    the function it wraps.
    """

    price_function: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray]
    """The function that returns the next price from the price, the surplus and the imbalance."""

    def initial_state(self, n_commodities: int) -> np.ndarray:
        """Zero for every commodity."""
        return np.zeros(n_commodities, dtype=np.float64)

    def __call__(self, price, surplus, imbalance, state):
        """The wrapped function's next price, and the state it was handed."""
        return self.price_function(price, surplus, imbalance), state


def stateless(
    price_function: Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray],
) -> StatelessPriceRule:
    """Wrap a function ``(price, surplus, imbalance) -> next_price`` into a :class:`PriceRule`."""
    return StatelessPriceRule(price_function)


@dataclasses.dataclass(frozen=True)
class _State:
    """One round: the price and state it started from, what came out, and what comes next.

    ``next_price`` and ``next_rule_state`` are what the rule returned, which the next round
    starts from. The state :meth:`CouncilModel.initial_state` returns carries those two and
    nothing else.
    """

    next_price: np.ndarray
    next_rule_state: np.ndarray
    price: np.ndarray | None = None
    output: np.ndarray | None = None
    effort: np.ndarray | None = None
    input_use: np.ndarray | None = None
    consumption: np.ndarray | None = None
    shared_use: np.ndarray | None = None
    consumer_demand: np.ndarray | None = None
    expenditure: np.ndarray | None = None
    worst_imbalance: float = float("inf")


class CouncilModel:
    """The councils of the Hahnel procedure: what they propose and what they ask for, at a price.

    This is the theory-bearing half of the prefab, and using it commits you to all of it:
    worker councils that pick output and effort by the closed form maximising output value
    net of the disutility of effort, over a Cobb-Douglas technology with an effort factor;
    consumer councils with Cobb-Douglas utility that spend their whole entitlement; and public
    goods priced to a consumer council at the listed price divided by the number of consumer
    units, with the stated demand counting once for the whole society.

    The public-good pricing rule changes none of the numbers this model reports. A council
    facing a public good pays ``price / n_consumers`` and therefore states ``n_consumers``
    times the quantity; the aggregation divides that column's total by ``n_consumers`` again.
    The two cancel as algebra rather than as an approximation: Cobb-Douglas utility over a
    fully spent entitlement fixes each column's share of the spending whatever price that
    column is charged, so the factor that goes in comes straight back out. Remove both halves
    and the plan comes out with the same quantities, the same prices and the same round count.

    Measured on dep1ex01, at 30000 consumer units, under the rule of
    :class:`~demplan.prefabs.hahnel.Book2021Rule`, at the 5 percent and at the 3 percent
    threshold: the run converges in 12 rounds and in 19 rounds either way. Every array the plan
    carries -- ``output``, ``input_use``, ``consumption``, the public-good supply, both prices in
    ``valuation``, ``extra["effort"]`` and ``extra["consumer_demand"]`` -- stays within 6e-14
    relative of the run that applies the rule, and ``extra["price_rule_state"]``, a relative
    imbalance and so a difference of two nearly equal totals, within 1.1e-12. That is rounding
    error. The figures are what those runs measure, not a bound proved over the model.
    The upstream source divides both ways too, and so does the reference implementation these
    round counts are checked against, so reproducing the published counts puts the rule to no
    test.

    To give the rule consequences, take a utility function whose spending shares move with
    price, or let a consumer council leave part of its entitlement unspent. The rule is still
    observable one column at a time: on a public-good column :meth:`_demand` states
    ``n_consumers`` times what it states on a private-good column carrying the same exponent.

    A utility-exponent column names a commodity of any class, and the plan splits the columns
    by one question: is the column's commodity a public good. The public-good columns reach
    the plan as ``shared_use``, the councils' stated level of each public good: the sum of
    their stated demands divided by the number of consumer units. Every other column -- a
    private good, or a commodity of any other class -- is a column of the ``consumption``
    block, so the material balance of the plan counts it. ``extra["consumer_demand"]`` reports
    both together, as the quantity each commodity's columns put into this round's demand.

    The plan files the councils' budget in ``valuation``: ``income`` is the entitlement each
    council spent from, and ``expenditure`` the cost of the council's whole stated bundle at
    the prices its own demand function paid, public goods at the listed price divided by the
    number of consumer units.

    The economy has to label every unit :data:`~demplan.prefabs.hahnel.TECHNOLOGY`, give
    every unit exactly one output entry, and carry ``commodity_extra["hahnel_kind"]`` holding
    the five class labels; ``__init__`` raises ``ValueError`` saying which is missing.

    Everything that does not change with the price is computed once in ``__init__``: the flat
    input layout, the price-independent part of the worker councils' closed form, and the split
    of the utility-exponent columns into the public goods and the rest. ``initial_state``,
    ``step``, ``converged`` and ``plan_of`` are the four arguments :func:`demplan.iterate`
    takes, so a procedure that wants a different loop can drive this model directly. The price
    rule is an argument rather than a default, because which rule runs is a statement about a
    source and this module makes none.
    """

    def __init__(self, economy: Economy, threshold_pct: float, price_rule: PriceRule):
        _require_the_hahnel_technology(economy)
        _require_one_output_per_unit(economy, "CouncilModel")
        kinds = kind_labels(economy, "CouncilModel")
        _require_keys(economy.unit_extra, _REQUIRED_UNIT_KEYS, "unit_extra")
        _require_keys(economy.consumer_extra, _REQUIRED_CONSUMER_KEYS, "consumer_extra")

        self.economy = economy
        self.threshold_pct = threshold_pct
        self.price_rule = price_rule
        self.n_commodities = economy.n_commodities
        self.n_consumers = economy.n_consumers

        self.owner = unit_of_input(economy)
        self.exponent = np.asarray(economy.input_coefficient)
        self.log_exponent = np.log(self.exponent)
        self.exponent_sum = segment_sum(economy, self.exponent, self.owner)

        effort_c = np.asarray(economy.unit_extra["effort_c"])
        effort_s = np.asarray(economy.unit_extra["effort_s"])
        effort_k = np.asarray(economy.unit_extra["effort_k"])
        self.effort_c, self.effort_k = effort_c, effort_k
        self.denominator = effort_c - effort_k + effort_k * self.exponent_sum
        self.own_price_weight = effort_c + effort_k * self.exponent_sum
        self.intercept = (
            -effort_k * np.log(economy.technology_scale)
            - effort_k * segment_sum(economy, self.exponent * self.log_exponent, self.owner)
            - effort_c * np.log(effort_c)
            + effort_c * np.log(effort_k)
            + effort_c * np.log(effort_s)
        )
        self.effort_intercept = -np.log(economy.technology_scale) - segment_sum(
            economy, self.exponent * self.log_exponent, self.owner
        )

        self.entitlement = np.asarray(economy.consumer_extra["entitlement"])
        self.utility_exponent = np.asarray(economy.consumer_extra["utility_exponent"])
        self.exponent_commodity = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        self.total_exponent = self.utility_exponent.sum(axis=1)

        self.public_commodity = kinds == PUBLIC_GOOD

        # The split is by one question -- is the column's commodity a public good -- because
        # the public-good columns are the plan's shared use and every other column is its
        # consumption block.
        column_is_public = self.public_commodity[self.exponent_commodity]
        consumption_column = np.flatnonzero(~column_is_public)
        public_column = np.flatnonzero(column_is_public)
        self.consumption_commodity = self.exponent_commodity[consumption_column].astype(np.int64)
        self.public_column_commodity = self.exponent_commodity[public_column].astype(np.int64)
        self.consumption_exponent = self.utility_exponent[:, consumption_column]
        self.public_exponent = self.utility_exponent[:, public_column]

    def initial_state(
        self, initial_price: float | np.ndarray, rule_state: np.ndarray | None = None
    ) -> _State:
        """The state before round one: the price and the rule state round one starts from.

        ``initial_price`` is a scalar, every commodity starting at that price, or a float64
        vector of one price per commodity. Either way every price must be finite and above
        zero. ``rule_state`` is the state the rule receives in round one; ``None`` asks the rule
        for its initial state, once. Both are copied, so the caller's arrays stay the caller's.

        Raises ``ValueError`` naming the problem when either is refused.
        """
        price = _initial_price_vector(initial_price, self.n_commodities)
        if rule_state is None:
            rule_state = self.price_rule.initial_state(self.n_commodities)
            label = "the state price_rule.initial_state returned"
        else:
            label = "initial_rule_state"
        _require_rule_state(label, rule_state, self.n_commodities)
        return _State(next_price=price, next_rule_state=_owned_copy(rule_state))

    def step(self, state: _State) -> _State:
        """One round: proposals and stated demand at the state's next price, then the rule.

        The rule is handed read-only copies of the price, the surplus, the imbalance and the
        rule state; the board keeps copies of the next price and the next rule state it
        returns, after checking that the state can be carried and filed.
        """
        price = state.next_price
        output, effort, input_use = self._propose(price)
        consumption_demand, public_demand = self._demand(price)
        supply, demand, consumer_demand = self._aggregate(
            output, input_use, consumption_demand, public_demand
        )
        imbalance = _relative_imbalance(supply, demand)
        next_price, next_rule_state = self.price_rule(
            _frozen_copy(price),
            _frozen_copy(supply - demand),
            _frozen_copy(imbalance),
            _frozen_copy(state.next_rule_state),
        )
        _require_rule_state(
            "the state the price rule returned", next_rule_state, self.n_commodities
        )
        return _State(
            next_price=_owned_copy(next_price),
            next_rule_state=_owned_copy(next_rule_state),
            price=price,
            output=output,
            effort=effort,
            input_use=input_use,
            consumption=consumption_demand,
            shared_use=np.where(self.public_commodity, consumer_demand, 0.0),
            consumer_demand=consumer_demand,
            expenditure=self._expenditure(price, consumption_demand, public_demand),
            worst_imbalance=float(np.max(imbalance)),
        )

    def converged(self, state: _State) -> bool:
        """Whether the worst relative imbalance is under the threshold.

        ``worst_imbalance`` is a plain maximum rather than a NaN-skipping one, so a NaN
        anywhere in the imbalance vector keeps the answer False.
        """
        return bool(state.worst_imbalance * PERCENT < self.threshold_pct)

    def plan_of(self, state: _State) -> StatedPlan:
        """The state as a plan. ``consumption`` is what the consumer councils asked for.

        The councils' stated bundles are what the price rule iterates on, and the loop stops
        on a relative imbalance threshold rather than on a balance, so the plan is a statement
        of demand and not an allocation of supply.

        ``valuation["indicative_price"]`` is the price the round's proposals were made at, and
        ``valuation["next_indicative_price"]`` the price the rule returned, which the next
        round would use. ``extra["price_rule_state"]`` is the state the rule returned, which
        the next round would receive. The next price and that state are what a run that
        continues from this plan starts from. ``valuation["income"]`` is each council's
        entitlement and ``valuation["expenditure"]`` what its stated bundle costs at the prices
        it paid.

        It takes a state :meth:`step` produced. The state :meth:`initial_state` returns carries
        a price and nothing else, so this raises :class:`demplan.SchemaError` on it:
        ``Plan`` refuses ``output`` and ``input_use`` as ``None``, those being quantities no
        mechanism may declare absent. :func:`demplan.iterate` calls this after every
        ``step`` and never on the starting state, so a loop driven through it never meets that.
        """
        return StatedPlan(
            output=state.output,
            input_use=state.input_use,
            consumption=state.consumption,
            consumption_commodity=self.consumption_commodity,
            shared_use=state.shared_use,
            valuation={
                INDICATIVE_PRICE: state.price,
                NEXT_INDICATIVE_PRICE: state.next_price,
                INCOME: self.entitlement,
                EXPENDITURE: state.expenditure,
            },
            extra={
                EFFORT: state.effort,
                CONSUMER_DEMAND: state.consumer_demand,
                PRICE_RULE_STATE: state.next_rule_state,
            },
        )

    def _propose(self, price: np.ndarray):
        """Worker councils' closed-form output, effort and input bundle at ``price``.

        Effort follows from the other two: inverting ``Q = a * e**c * prod(x_j ** b_j)`` for
        the cost-minimising bundle gives ``c * log(e)`` as the residual of the log production
        function, which is what the expression below spells out.
        """
        input_price = price[self.economy.input_commodity]
        log_input_price = np.log(input_price)
        log_own_price = np.log(price[self.economy.output_commodity])
        log_spending = segment_sum(self.economy, self.exponent * log_input_price, self.owner)
        log_output = (
            self.intercept
            + self.effort_k * log_spending
            - self.own_price_weight * log_own_price
        ) / self.denominator
        log_effort = (
            self.effort_intercept
            + log_spending
            - self.exponent_sum * log_own_price
            + (1.0 - self.exponent_sum) * log_output
        ) / self.effort_c
        input_use = np.exp(
            self.log_exponent + log_own_price[self.owner] - log_input_price + log_output[self.owner]
        )
        return np.exp(log_output), np.exp(log_effort), input_use

    def _demand(self, price: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Consumer councils' stated bundle at ``price``, as two blocks of columns.

        The first block is every column whose commodity is not a public good, in the order of
        ``consumption_commodity``; it is what the plan reports as ``consumption``. The second
        is the public-good columns.

        A council facing a public good pays the listed price divided by the number of consumer
        units, :meth:`_public_price`. Every other column pays the listed price, which is why
        the first block has no price adjustment at all. A single column is the only
        place the public-good price is observable; :class:`CouncilModel` says why it leaves
        every commodity-level number of the plan alone.
        """
        consumption = (self.entitlement[:, None] * self.consumption_exponent) / (
            self.total_exponent[:, None] * price[self.consumption_commodity][None, :]
        )
        public = (self.entitlement[:, None] * self.public_exponent) / (
            self.total_exponent[:, None] * self._public_price(price)[None, :]
        )
        return consumption, public

    def _public_price(self, price: np.ndarray) -> np.ndarray:
        """What a council pays for each public-good column: the listed price per consumer unit."""
        return price[self.public_column_commodity] / self.n_consumers

    def _expenditure(
        self, price: np.ndarray, consumption_demand: np.ndarray, public_demand: np.ndarray
    ) -> np.ndarray:
        """Each council's spending on its whole stated bundle, at the prices :meth:`_demand` paid.

        A column outside the public goods costs the listed price; a public-good column costs
        :meth:`_public_price`. Cobb-Douglas demand spends the whole entitlement, so this equals
        ``income`` up to rounding; it is summed from the bundle rather than copied from the
        entitlement so that the budget difference measures what the councils stated.
        """
        # einsum sums each council's products in one pass without building the product
        # matrix, which on dep1ex is 30000 by 100 per block and would be built every round.
        on_consumption = np.einsum(
            "ij,j->i", consumption_demand, price[self.consumption_commodity]
        )
        on_public = np.einsum("ij,j->i", public_demand, self._public_price(price))
        return on_consumption + on_public

    def _aggregate(
        self,
        output: np.ndarray,
        input_use: np.ndarray,
        consumption_demand: np.ndarray,
        public_demand: np.ndarray,
    ):
        """Supply, total demand, and the consumer councils' part of it, one per commodity.

        The two blocks of stated demand scatter onto disjoint commodities, because a commodity
        carries one ``hahnel_kind`` and the blocks are split by that label. A public-good
        column contributes its total divided by the number of consumer units; every other
        column contributes its total whole.
        """
        supply = np.bincount(
            self.economy.output_commodity, weights=output, minlength=self.n_commodities
        ) + np.asarray(self.economy.endowment)
        demand = np.bincount(
            self.economy.input_commodity, weights=input_use, minlength=self.n_commodities
        )
        consumption = np.bincount(
            self.consumption_commodity,
            weights=consumption_demand.sum(axis=0),
            minlength=self.n_commodities,
        ) + np.bincount(
            self.public_column_commodity,
            weights=public_demand.sum(axis=0) / self.n_consumers,
            minlength=self.n_commodities,
        )
        demand += consumption
        return supply, demand, consumption


def _require_the_hahnel_technology(economy: Economy) -> None:
    """Refuse a unit whose ``technology_kind`` is not :data:`TECHNOLOGY`, naming it."""
    wrong = np.flatnonzero(np.asarray(economy.technology_kind) != TECHNOLOGY)
    if wrong.size:
        unit = int(wrong[0])
        raise ValueError(
            f"CouncilModel is the closed form of the Cobb-Douglas technology with an effort "
            f"factor, Q = a * e**c * prod(x_j ** b_j), which an economy labels {TECHNOLOGY!r}; "
            f"unit {unit} carries technology_kind {str(economy.technology_kind[unit])!r}. "
            "If that unit's technology is this one, label it "
            "demplan.prefabs.hahnel.TECHNOLOGY, as demplan.load_dep1ex does."
        )


def _require_keys(bag, keys, name: str) -> None:
    missing = [key for key in keys if key not in bag]
    if missing:
        raise ValueError(f"CouncilModel needs {name} keys {', '.join(missing)}")


def _initial_price_vector(initial_price, n_commodities: int) -> np.ndarray:
    """The price round one starts from, as a vector the board owns. Raises ``ValueError``.

    A scalar is spread over every commodity. An array of no dimensions counts as a scalar, so
    a numpy scalar is one; an array of one or more dimensions has to be a float64 vector of
    ``n_commodities`` entries, and is refused rather than converted otherwise, since a price in
    another type is a price the caller did not compute as a float64.
    """
    if np.ndim(initial_price) == 0:
        price = np.full(n_commodities, initial_price, dtype=np.float64)
    else:
        if not isinstance(initial_price, np.ndarray) or initial_price.dtype != np.float64:
            got = (
                initial_price.dtype
                if isinstance(initial_price, np.ndarray)
                else type(initial_price).__name__
            )
            raise ValueError(
                f"initial_price: expected a number or a float64 array, got {got}"
            )
        if initial_price.shape != (n_commodities,):
            raise ValueError(
                f"initial_price has shape {initial_price.shape}, but the economy has "
                f"n_commodities = {n_commodities}, one price each"
            )
        price = _owned_copy(initial_price)
    wrong = np.flatnonzero(~(np.isfinite(price) & (price > 0.0)))
    if wrong.size:
        at = int(wrong[0])
        raise ValueError(
            f"initial_price holds {price[at]} for commodity {at}; every price must be finite "
            "and above zero"
        )
    return price


def _require_rule_state(label: str, state, n_commodities: int) -> None:
    """Refuse a price-rule state that cannot be carried to the next round and filed on a plan.

    The plan files the state under ``extra["price_rule_state"]``, which takes a float64 array
    whose first dimension is one of the economy's counts, finite throughout; the board fixes
    that count at ``n_commodities``. The check runs on every state the board is about to hold,
    so a rule that returns something else stops the round that returned it.
    """
    if not isinstance(state, np.ndarray) or state.dtype != np.float64:
        got = state.dtype if isinstance(state, np.ndarray) else type(state).__name__
        raise ValueError(f"{label}: expected a float64 numpy array, got {got}")
    if state.ndim < 1 or state.shape[0] != n_commodities:
        raise ValueError(
            f"{label} has shape {state.shape}, but its first dimension has to be "
            f"n_commodities = {n_commodities}"
        )
    if not np.isfinite(state).all():
        raise ValueError(f"{label} holds a value that is not finite")


def _owned_copy(array: np.ndarray) -> np.ndarray:
    """A plain array of the board's own, holding the same numbers as ``array``.

    The board keeps the price and the state a rule returned for the whole of the next round
    and files them on the plan, while the rule is free to keep writing to whatever it handed
    back. Copying is what makes those two independent.
    """
    return np.array(array, copy=True)


def _frozen_copy(array: np.ndarray) -> np.ndarray:
    """A read-only array of the board's own, holding the same numbers as ``array``.

    :func:`demplan.economy._freeze_array` hands out a read-only view instead, so that
    building an ``Economy`` or a ``Plan`` around a caller's buffer leaves that buffer with the
    caller. The board's position is the other one: it owns the four arrays it shows the price
    rule, and a copy of an array it owns has no ``base`` for the rule to write through.
    """
    frozen = _owned_copy(array)
    frozen.flags.writeable = False
    return frozen


def relative_imbalance(economy: Economy, plan: Plan) -> np.ndarray:
    """The relative imbalance of every commodity, rebuilt from a plan :class:`CouncilModel` filed.

    Supply is ``plan.total_output(economy)`` plus the endowment; demand is
    ``plan.total_input_use(economy)`` plus ``plan.extra["consumer_demand"]``. The ratio is the
    one the model tests convergence on, ``|2(supply - demand) / (supply + demand)|``, zero
    where supply and demand are both zero and infinite where either is not finite. On a plan
    the model filed it equals, entry for entry, the imbalance the model measured in that round.

    Returns ``f64[n_commodities]``. Raises ``ValueError`` when the plan carries no
    ``extra["consumer_demand"]``, and :class:`demplan.SchemaError` when the plan is not shaped
    for ``economy``.
    """
    if CONSUMER_DEMAND not in plan.extra:
        raise ValueError(
            f"relative_imbalance needs plan.extra[{CONSUMER_DEMAND!r}], the consumer councils' "
            "share of demand, which a plan filed by CouncilModel carries"
        )
    supply = plan.total_output(economy) + np.asarray(economy.endowment)
    demand = plan.total_input_use(economy) + np.asarray(plan.extra[CONSUMER_DEMAND])
    return _relative_imbalance(supply, demand)


def _relative_imbalance(supply: np.ndarray, demand: np.ndarray) -> np.ndarray:
    """``|2(supply - demand) / (supply + demand)|``, zero where the commodity is untouched.

    A commodity whose supply or demand is not finite counts as fully imbalanced. The ratio
    itself would be ``inf/inf``, which is NaN, and NaN compares below every threshold: a plan
    that had overflowed would be reported as the most balanced plan of the run.
    """
    total = supply + demand
    measurable = np.isfinite(supply) & np.isfinite(demand)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(
            total > 0, np.abs(2 * (supply - demand)) / np.where(total > 0, total, 1.0), 0.0
        )
    return np.where(measurable, ratio, np.inf)
