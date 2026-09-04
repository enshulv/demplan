"""The iterative participatory-planning procedure of the 2020 simulation-experiment slides.

Each round every worker council proposes the output that maximises its own objective at the
current indicative prices, every consumer council states the bundle its entitlement buys at
those prices, the facilitation board measures the relative imbalance of each commodity and
moves prices against it. The run stops when the worst imbalance falls below the threshold.

Two details decide whether the round count matches the published figures:

* The imbalance is measured on the proposals made at the current price, before the price is
  moved, so the round that reports convergence is the round whose price is reported.
* The price step caps the imbalance at 0.25 first and then computes the step from the capped
  value, ``w = v(1.05 - 0.5**v)``. Capping the step instead, or the 2023 paper's rule of
  scaling the previous step, does not converge on the same data.

Public goods are priced per consumer unit: a consumer council facing a public good pays the
listed price divided by the number of consumer units, and its stated demand counts once for
the whole society rather than once per council.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from cyberstride.economy import CommodityKind, Economy, TechnologyKind
from cyberstride.iterate import iterate
from cyberstride.plan import INDICATIVE_PRICE, Plan
from cyberstride.tools import segment_sum, unit_of_input

IMBALANCE_CAP = 0.25
"""Above this relative imbalance the price step stops growing."""

PRICE_STEP_CEILING = 1.05
PRICE_STEP_DECAY_BASE = 0.5
PERCENT = 100.0

_REQUIRED_UNIT_KEYS = ("effort_c", "effort_s", "effort_k")
_REQUIRED_CONSUMER_KEYS = ("entitlement", "utility_exponent", "utility_exponent_commodity")


@dataclasses.dataclass(frozen=True)
class _State:
    """One round: the price it was proposed at, what came out, and the next price."""

    next_price: np.ndarray
    price: np.ndarray | None = None
    output: np.ndarray | None = None
    input_use: np.ndarray | None = None
    consumption_demand: np.ndarray | None = None
    provision: np.ndarray | None = None
    worst_imbalance: float = float("inf")


class _Model:
    """Per-solve constants of one economy, plus the round the procedure repeats.

    Everything that does not change with the price is computed once here: the flat input
    layout, the price-independent part of the worker councils' closed form, and which columns
    of the utility exponents are public goods.
    """

    def __init__(self, economy: Economy, threshold_pct: float):
        _require_cobb_douglas(economy)
        _require_keys(economy.unit_extra, _REQUIRED_UNIT_KEYS, "unit_extra")
        _require_keys(economy.consumer_extra, _REQUIRED_CONSUMER_KEYS, "consumer_extra")

        self.economy = economy
        self.threshold_pct = threshold_pct
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

        self.entitlement = np.asarray(economy.consumer_extra["entitlement"])
        self.utility_exponent = np.asarray(economy.consumer_extra["utility_exponent"])
        self.exponent_commodity = np.asarray(economy.consumer_extra["utility_exponent_commodity"])
        self.total_exponent = self.utility_exponent.sum(axis=1)

        kinds = np.asarray(economy.commodity_kind)
        self.public_commodity = kinds == CommodityKind.PUBLIC_GOOD
        self.public_column = self.public_commodity[self.exponent_commodity]
        self.private_column = np.flatnonzero(
            kinds[self.exponent_commodity] == CommodityKind.PRIVATE_GOOD
        )
        self.consumption_commodity = self.exponent_commodity[self.private_column].astype(np.int64)

    def initial_state(self, initial_price: float) -> _State:
        return _State(next_price=np.full(self.n_commodities, initial_price, dtype=np.float64))

    def step(self, state: _State) -> _State:
        price = state.next_price
        output, input_use = self._propose(price)
        consumption_demand = self._demand(price)
        supply, demand = self._aggregate(output, input_use, consumption_demand)
        imbalance = _relative_imbalance(supply, demand)
        return _State(
            next_price=_adjusted(price, supply - demand, imbalance),
            price=price,
            output=output,
            input_use=input_use,
            consumption_demand=consumption_demand,
            provision=np.where(self.public_commodity, supply, 0.0),
            worst_imbalance=float(np.nanmax(imbalance)),
        )

    def converged(self, state: _State) -> bool:
        return bool(state.worst_imbalance * PERCENT < self.threshold_pct)

    def plan_of(self, state: _State) -> Plan:
        return Plan(
            output=state.output,
            input_use=state.input_use,
            consumption=state.consumption_demand[:, self.private_column],
            consumption_commodity=self.consumption_commodity,
            provision=state.provision,
            valuation={INDICATIVE_PRICE: state.price},
        )

    def _propose(self, price: np.ndarray):
        """Worker councils' closed-form output and input bundle at ``price``."""
        input_price = price[self.economy.input_commodity]
        log_input_price = np.log(input_price)
        log_own_price = np.log(price[self.economy.output_commodity])
        log_output = (
            self.intercept
            + self.effort_k * segment_sum(self.economy, self.exponent * log_input_price, self.owner)
            - self.own_price_weight * log_own_price
        ) / self.denominator
        input_use = np.exp(
            self.log_exponent + log_own_price[self.owner] - log_input_price + log_output[self.owner]
        )
        return np.exp(log_output), input_use

    def _demand(self, price: np.ndarray) -> np.ndarray:
        """Consumer councils' stated bundle, one row per council, one column per exponent."""
        listed = price[self.exponent_commodity]
        paid = np.where(self.public_column, listed / self.n_consumers, listed)
        return (self.entitlement[:, None] * self.utility_exponent) / (
            self.total_exponent[:, None] * paid[None, :]
        )

    def _aggregate(self, output: np.ndarray, input_use: np.ndarray, consumption_demand: np.ndarray):
        supply = np.bincount(
            self.economy.output_commodity, weights=output, minlength=self.n_commodities
        ) + np.asarray(self.economy.endowment)
        demand = np.bincount(
            self.economy.input_commodity, weights=input_use, minlength=self.n_commodities
        )
        stated = consumption_demand.sum(axis=0)
        shared = np.where(self.public_column, stated / self.n_consumers, stated)
        demand += np.bincount(
            self.exponent_commodity, weights=shared, minlength=self.n_commodities
        )
        return supply, demand


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


def _relative_imbalance(supply: np.ndarray, demand: np.ndarray) -> np.ndarray:
    """``|2(supply - demand) / (supply + demand)|``, zero where the commodity is untouched."""
    total = supply + demand
    return np.where(
        total > 0, np.abs(2 * (supply - demand)) / np.where(total > 0, total, 1.0), 0.0
    )


def _adjusted(price: np.ndarray, surplus: np.ndarray, imbalance: np.ndarray) -> np.ndarray:
    capped = np.minimum(imbalance, IMBALANCE_CAP)
    step = capped * (PRICE_STEP_CEILING - PRICE_STEP_DECAY_BASE**capped)
    return price * np.where(surplus > 0, 1 - step, np.where(surplus < 0, 1 + step, 1.0))


@dataclasses.dataclass(frozen=True)
class HahnelSlides2020:
    """The 2020 slides procedure as a :class:`cyberstride.Procedure`.

    ``threshold_pct`` is the worst relative imbalance, in percent, at which the board declares
    the plan feasible; the slides report runs at 5 and at 3. ``initial_price`` is the flat
    price every commodity starts at, which is a cold start.

    The rule is deterministic, so ``seed`` is accepted and ignored. Set
    ``record_trajectory`` to keep one plan per round, at the cost of holding all of them.
    """

    threshold_pct: float = 5.0
    max_rounds: int = 250
    initial_price: float = 700.0
    record_trajectory: bool = False

    def solve(self, economy: Economy, seed: int) -> Plan:
        model = _Model(economy, self.threshold_pct)
        result = iterate(
            lambda: model.initial_state(self.initial_price),
            model.step,
            model.converged,
            self.max_rounds,
            plan_of=model.plan_of if self.record_trajectory else None,
        )
        if result.trajectory:
            return result.trajectory[-1]
        return model.plan_of(result.state)
