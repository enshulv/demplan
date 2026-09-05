"""The iterative participatory-planning procedure of the 2020 simulation-experiment slides.

Each round every worker council proposes the output that maximises its own objective at the
current indicative prices, every consumer council states the bundle its entitlement buys at
those prices, the facilitation board measures the relative imbalance of each commodity and
moves prices against it. The run stops when the worst imbalance falls below the threshold.

Two details decide whether the round count matches the published figures. One belongs to the
loop: the imbalance is measured on the proposals made at the current price, before the price
is moved, so the round that reports convergence is the round whose price is reported. The
other belongs to the price rule and is stated on :func:`slides_2020_rule`.

The price rule is the seam. :class:`HahnelSlides2020` takes any :class:`PriceRule`; the
councils' closed forms and the aggregation stay as the slides describe them.

Public goods are priced per consumer unit: a consumer council facing a public good pays the
listed price divided by the number of consumer units, and its stated demand counts once for
the whole society rather than once per council. The two halves of that rule cancel, so it
moves no number the plan reports; :class:`CouncilModel` sets out why, and what it would take
to give the rule consequences.

The production function is ``Q = a * e**c * prod(x_j ** b_j)``: the Cobb-Douglas input bundle
of the data model with an effort factor, where ``e`` is the effort the worker council chose
and ``c`` is ``effort_c``. Both the effort and the consumer councils' demand per commodity
go into ``Plan.extra``, because neither can be recovered from the physical layer.
"""

from __future__ import annotations

import dataclasses
from typing import Protocol

import numpy as np

from cyberstride.economy import CommodityKind, Economy, TechnologyKind
from cyberstride.iterate import iterate
from cyberstride.plan import CONSUMER_DEMAND, EFFORT, INDICATIVE_PRICE, Plan
from cyberstride.tools import segment_sum, unit_of_input

IMBALANCE_CAP = 0.25
"""Above this relative imbalance the price step stops growing."""

PRICE_STEP_CEILING = 1.05
PRICE_STEP_DECAY_BASE = 0.5
PERCENT = 100.0

_REQUIRED_UNIT_KEYS = ("effort_c", "effort_s", "effort_k")
_REQUIRED_CONSUMER_KEYS = ("entitlement", "utility_exponent", "utility_exponent_commodity")


class PriceRule(Protocol):
    """How the facilitation board turns one round's price into the next round's price.

    The three arguments are ``f64[n_commodities]``: the price the proposals were made at,
    supply minus demand at that price, and the relative imbalance
    ``|2(supply - demand) / (supply + demand)|``. The return value is the next price, also
    ``f64[n_commodities]``.

    The three arguments are read-only copies the board owns. Writing to one raises, and
    reaching around the flag reaches nothing: a copy owns its memory, so it has no ``base``
    to write through. The board also keeps a copy of the return value, so a rule may hold one
    output buffer and rewrite it every round.

    Ownership is what those two say, and it is worth saying because two of the three arrays
    carry figures the run reports. The board files the plan under the price it stepped with,
    as ``valuation["indicative_price"]``, and it tests convergence on the imbalance it
    measured, which is the round count this prefab reproduces.
    """

    def __call__(
        self, price: np.ndarray, surplus: np.ndarray, imbalance: np.ndarray
    ) -> np.ndarray:
        ...


@dataclasses.dataclass(frozen=True)
class _State:
    """One round: the price it was proposed at, what came out, and the next price."""

    next_price: np.ndarray
    price: np.ndarray | None = None
    output: np.ndarray | None = None
    effort: np.ndarray | None = None
    input_use: np.ndarray | None = None
    consumption: np.ndarray | None = None
    provision: np.ndarray | None = None
    consumer_demand: np.ndarray | None = None
    worst_imbalance: float = float("inf")


class CouncilModel:
    """The councils of the 2020 slides: what they propose and what they ask for, at a price.

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

    Measured on dep1ex01, at 30000 consumer units, at the 5 percent and at the 3 percent
    threshold: the run converges in 14 rounds and in 23 rounds either way, and every array the
    plan carries -- ``output``, ``input_use``, ``consumption``, ``provision``,
    ``valuation["indicative_price"]``, ``extra["effort"]`` and ``extra["consumer_demand"]`` --
    stays within 1e-13 relative of the run that applies the rule, which is rounding error.
    That figure is what those runs measure, not a bound proved over the model. The upstream
    source divides both ways too, and so does the reference implementation these round counts
    are checked against, so reproducing the published counts puts the rule to no test.

    To give the rule consequences, take a utility function whose spending shares move with
    price, or let a consumer council leave part of its entitlement unspent. The rule is still
    observable one column at a time: on a public-good column :meth:`_demand` states
    ``n_consumers`` times what it states on a private-good column carrying the same exponent.

    A utility-exponent column names a commodity of any kind, so the columns fall into three
    cases and not two. The private-good columns are the plan's ``consumption`` block. The
    public-good columns, and the columns whose commodity is neither a private nor a public
    good, reach the plan only through ``extra["consumer_demand"]``; that array reports all
    three cases together, as the quantity each commodity's columns put into this round's
    demand.

    Everything that does not change with the price is computed once in ``__init__``: the flat
    input layout, the price-independent part of the worker councils' closed form, and the split
    of the utility-exponent columns into the private goods and the rest. ``initial_state``,
    ``step``, ``converged`` and ``plan_of`` are the four arguments :func:`cyberstride.iterate`
    takes, so a procedure that wants a different loop can drive this model directly.
    """

    def __init__(
        self,
        economy: Economy,
        threshold_pct: float,
        price_rule: PriceRule | None = None,
    ):
        _require_cobb_douglas(economy)
        _require_keys(economy.unit_extra, _REQUIRED_UNIT_KEYS, "unit_extra")
        _require_keys(economy.consumer_extra, _REQUIRED_CONSUMER_KEYS, "consumer_extra")

        self.economy = economy
        self.threshold_pct = threshold_pct
        self.price_rule = slides_2020_rule if price_rule is None else price_rule
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

        kinds = np.asarray(economy.commodity_kind)
        self.public_commodity = kinds == CommodityKind.PUBLIC_GOOD

        # The split is by one question -- is the column's commodity a private good -- because
        # the private-good columns are the plan's consumption block and nothing else is.
        column_kind = kinds[self.exponent_commodity]
        self.private_column = np.flatnonzero(column_kind == CommodityKind.PRIVATE_GOOD)
        other_column = np.flatnonzero(column_kind != CommodityKind.PRIVATE_GOOD)
        self.consumption_commodity = self.exponent_commodity[self.private_column].astype(np.int64)
        self.other_commodity = self.exponent_commodity[other_column].astype(np.int64)
        self.other_is_public = self.public_commodity[self.other_commodity]
        self.private_exponent = self.utility_exponent[:, self.private_column]
        self.other_exponent = self.utility_exponent[:, other_column]

    def initial_state(self, initial_price: float) -> _State:
        return _State(next_price=np.full(self.n_commodities, initial_price, dtype=np.float64))

    def step(self, state: _State) -> _State:
        price = state.next_price
        output, effort, input_use = self._propose(price)
        private_demand, other_demand = self._demand(price)
        supply, demand, consumer_demand = self._aggregate(
            output, input_use, private_demand, other_demand
        )
        imbalance = _relative_imbalance(supply, demand)
        next_price = self.price_rule(
            _frozen_copy(price), _frozen_copy(supply - demand), _frozen_copy(imbalance)
        )
        return _State(
            next_price=_owned_copy(next_price),
            price=price,
            output=output,
            effort=effort,
            input_use=input_use,
            consumption=private_demand,
            provision=np.where(self.public_commodity, supply, 0.0),
            consumer_demand=consumer_demand,
            worst_imbalance=float(np.max(imbalance)),
        )

    def converged(self, state: _State) -> bool:
        """Whether the worst relative imbalance is under the threshold.

        ``worst_imbalance`` is a plain maximum rather than a NaN-skipping one, so a NaN
        anywhere in the imbalance vector keeps the answer False.
        """
        return bool(state.worst_imbalance * PERCENT < self.threshold_pct)

    def plan_of(self, state: _State) -> Plan:
        return Plan(
            output=state.output,
            input_use=state.input_use,
            consumption=state.consumption,
            consumption_commodity=self.consumption_commodity,
            provision=state.provision,
            valuation={INDICATIVE_PRICE: state.price},
            extra={
                EFFORT: state.effort,
                CONSUMER_DEMAND: state.consumer_demand,
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

        The first block is the private-good columns, in the order of
        ``consumption_commodity``; it is what the plan reports as ``consumption``. The second
        is every other column, the public goods and the commodities that are neither.

        A council facing a public good pays the listed price divided by the number of consumer
        units. Every other column pays the listed price, private goods included, which is why
        the first block has no price adjustment at all. A single column is the only
        place the public-good price is observable; :class:`CouncilModel` says why it leaves
        every commodity-level number of the plan alone.
        """
        private_price = price[self.consumption_commodity]
        private = (self.entitlement[:, None] * self.private_exponent) / (
            self.total_exponent[:, None] * private_price[None, :]
        )
        listed = price[self.other_commodity]
        paid = np.where(self.other_is_public, listed / self.n_consumers, listed)
        other = (self.entitlement[:, None] * self.other_exponent) / (
            self.total_exponent[:, None] * paid[None, :]
        )
        return private, other

    def _aggregate(
        self,
        output: np.ndarray,
        input_use: np.ndarray,
        private_demand: np.ndarray,
        other_demand: np.ndarray,
    ):
        """Supply, total demand, and the consumer councils' part of it, one per commodity.

        The two blocks of stated demand scatter onto disjoint commodities, because a commodity
        carries one ``commodity_kind`` and the blocks are split by that kind. A public-good
        column contributes its total divided by the number of consumer units; every other
        column contributes its total whole.
        """
        supply = np.bincount(
            self.economy.output_commodity, weights=output, minlength=self.n_commodities
        ) + np.asarray(self.economy.endowment)
        demand = np.bincount(
            self.economy.input_commodity, weights=input_use, minlength=self.n_commodities
        )
        stated_other = other_demand.sum(axis=0)
        shared_other = np.where(
            self.other_is_public, stated_other / self.n_consumers, stated_other
        )
        consumption = np.bincount(
            self.consumption_commodity,
            weights=private_demand.sum(axis=0),
            minlength=self.n_commodities,
        ) + np.bincount(
            self.other_commodity, weights=shared_other, minlength=self.n_commodities
        )
        demand += consumption
        return supply, demand, consumption


def _require_cobb_douglas(economy: Economy) -> None:
    wrong = np.flatnonzero(np.asarray(economy.technology_kind) != TechnologyKind.COBB_DOUGLAS)
    if wrong.size:
        raise ValueError(
            f"HahnelSlides2020 is the Cobb-Douglas closed form, but unit {int(wrong[0])} "
            f"carries technology_kind {int(economy.technology_kind[wrong[0]])}"
        )


def _require_keys(bag, keys, name: str) -> None:
    missing = [key for key in keys if key not in bag]
    if missing:
        raise ValueError(f"HahnelSlides2020 needs {name} keys {', '.join(missing)}")


def _owned_copy(array: np.ndarray) -> np.ndarray:
    """A plain array of the board's own, holding the same numbers as ``array``.

    The board keeps the price a rule returned for the whole of the next round and files it on
    the plan, while the rule is free to keep writing to whatever it handed back. Copying is
    what makes those two independent.
    """
    return np.array(array, copy=True)


def _frozen_copy(array: np.ndarray) -> np.ndarray:
    """A read-only array of the board's own, holding the same numbers as ``array``.

    :func:`cyberstride.economy._freeze_array` hands out a read-only view instead, so that
    building an ``Economy`` or a ``Plan`` around a caller's buffer leaves that buffer with the
    caller. The board's position is the other one: it owns the three arrays it shows the price
    rule, and a copy of an array it owns has no ``base`` for the rule to write through.
    """
    frozen = _owned_copy(array)
    frozen.flags.writeable = False
    return frozen


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


def slides_2020_rule(
    price: np.ndarray, surplus: np.ndarray, imbalance: np.ndarray
) -> np.ndarray:
    """The price rule of the 2020 slides: move each price against its imbalance.

    The step caps the imbalance at 0.25 first and then computes the step from the capped
    value, ``w = v(1.05 - 0.5**v)``. Capping the step instead, or the 2023 paper's rule of
    scaling the previous step, does not converge on the same data. A commodity in surplus
    loses ``w`` of its price, one in shortage gains ``w``, one in balance keeps it.
    """
    capped = np.minimum(imbalance, IMBALANCE_CAP)
    step = capped * (PRICE_STEP_CEILING - PRICE_STEP_DECAY_BASE**capped)
    return price * np.where(surplus > 0, 1 - step, np.where(surplus < 0, 1 + step, 1.0))


@dataclasses.dataclass(frozen=True)
class HahnelSlides2020:
    """The 2020 slides procedure as a :class:`cyberstride.Procedure`.

    ``threshold_pct`` is the worst relative imbalance, in percent, at which the board declares
    the plan feasible; the slides report runs at 5 and at 3. ``initial_price`` is the flat
    price every commodity starts at, which is a cold start.

    ``price_rule`` replaces the board's rule while leaving the councils alone; ``None`` is
    :func:`slides_2020_rule`, the rule the published round counts come from.

    The rule is deterministic, so ``seed`` is accepted and ignored. Set
    ``record_trajectory`` to keep one plan per round, at the cost of holding all of them.
    Divergence is watched for either way.
    """

    threshold_pct: float = 5.0
    max_rounds: int = 250
    initial_price: float = 700.0
    record_trajectory: bool = False
    price_rule: PriceRule | None = None

    def solve(self, economy: Economy, seed: int) -> Plan:
        model = CouncilModel(economy, self.threshold_pct, price_rule=self.price_rule)
        result = iterate(
            lambda: model.initial_state(self.initial_price),
            model.step,
            model.converged,
            self.max_rounds,
            plan_of=model.plan_of,
            keep_trajectory=self.record_trajectory,
        )
        if result.trajectory:
            return result.trajectory[-1]
        return model.plan_of(result.state)
