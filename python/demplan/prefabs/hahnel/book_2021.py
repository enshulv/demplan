"""The procedure of Hahnel (2021), *Democratic Economic Planning*, ch. 9, as its program ran it.

The published round counts come from ``msszczep/pequod-cljs``, ``src/clj/pequod_cljs/csvgen.clj``
at commit ``71e44d3``. This module holds that program's price rule, :class:`Book2021Rule`,
and the procedure that runs the councils of :mod:`demplan.prefabs.hahnel.councils` under it,
:class:`HahnelBook2021`.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from demplan.economy import Economy
from demplan.iterate import iterate
from demplan.plan import Plan
from demplan.prefabs.hahnel.councils import CouncilModel, PriceRule

IMBALANCE_CAP = 0.25
"""Cap on the imbalance a round hands the next as its step multiplier, and the starting value.

csvgen.clj starts every commodity's ``pdlist`` entry at 0.25 and caps it at 0.25 afterwards.
"""

PRICE_STEP_CEILING = 1.05
PRICE_STEP_DECAY_BASE = 0.5

PRICE_STEP_FLOOR = 0.001
"""The smallest step the rule takes on a commodity out of balance."""


@dataclasses.dataclass(frozen=True)
class Book2021Rule:
    """The price rule of the program that produced the published tables of Hahnel (2021).

    Source: ``msszczep/pequod-cljs``, ``src/clj/pequod_cljs/csvgen.clj`` at commit ``71e44d3``,
    functions ``get-deltas``, ``update-pdlist`` and ``iterate-plan``. Per commodity, in round
    ``k``, with ``v_k`` the round's relative imbalance measured at the round's price::

        base_k = 1.05 - 0.5 ** v_k
        w_k    = max(0.001, min(base_k, |base_k * m_{k-1}|))
        m_k    = min(v_k, 0.25),  m_{-1} = 0.25

    The price falls by ``w_k`` of itself where supply exceeds demand, rises by ``w_k`` where it
    falls short, and stays where they are equal. ``m`` is the rule's state: ``iterate-plan``
    hands the price update the ``pdlist`` of the previous round and computes the new one
    afterwards. Since ``m`` never exceeds 0.25, the ``min`` always picks ``base_k * m``; it is
    kept so that the code reads like the source.

    The book's text, p. 181, gives the step as ``w = v(1.05 - 0.5^v)``, with ``v`` capped at
    0.25 where it first appears, the ``v`` that multiplies, and not where it appears as an
    exponent. The program differs from that text in two ways: the ``v`` that multiplies is the previous round's capped imbalance rather than
    this round's, and the step has a floor of 0.001. This rule follows the program, because
    the published round counts come from the program.

    The rule has no fields and keeps nothing between calls; the board carries ``m``.
    """

    def initial_state(self, n_commodities: int) -> np.ndarray:
        """``m_{-1}``: 0.25 for every commodity."""
        return np.full(n_commodities, IMBALANCE_CAP, dtype=np.float64)

    def __call__(self, price, surplus, imbalance, state):
        """One round's price update, and the multiplier the next round takes.

        Returns ``(next_price, next_state)``: the price moved against the surplus by this
        round's step, and this round's imbalance capped at 0.25.
        """
        base = PRICE_STEP_CEILING - PRICE_STEP_DECAY_BASE**imbalance
        step = np.maximum(PRICE_STEP_FLOOR, np.minimum(base, np.abs(base * state)))
        next_price = price * np.where(surplus > 0, 1 - step, np.where(surplus < 0, 1 + step, 1.0))
        return next_price, np.minimum(imbalance, IMBALANCE_CAP)


book_2021_rule = Book2021Rule()
"""The instance :class:`HahnelBook2021` runs when it is given no rule."""


@dataclasses.dataclass(frozen=True)
class HahnelBook2021:
    """The Hahnel (2021) procedure as a :class:`demplan.Procedure`.

    ``threshold_pct`` is the worst relative imbalance, in percent, at which the board declares
    the plan feasible; the book reports runs at 5 and at 3. ``initial_price`` is the price
    round one's proposals are made at: a scalar is the same price for every commodity, a cold
    start, and a float64 vector of one price per commodity is a warm start. Every price must be
    finite and above zero.

    ``initial_rule_state`` is the state the price rule receives in round one; ``None`` takes
    the rule's own initial state. A run that continues from an earlier plan passes that plan's
    ``valuation["next_indicative_price"]`` and ``extra["price_rule_state"]`` here.

    ``price_rule`` replaces the board's rule while leaving the councils alone; ``None`` is
    :data:`book_2021_rule`, the rule the published round counts come from.

    The rule is deterministic, so ``seed`` is accepted and ignored. Set
    ``record_trajectory`` to keep one plan per round, at the cost of holding all of them.
    Divergence is watched for either way.

    ``solve`` raises ``ValueError`` when the initial price or the initial rule state is
    refused, naming the problem.
    """

    threshold_pct: float = 5.0
    max_rounds: int = 250
    initial_price: float | np.ndarray = 700.0
    initial_rule_state: np.ndarray | None = None
    record_trajectory: bool = False
    price_rule: PriceRule | None = None

    def solve(self, economy: Economy, seed: int) -> Plan:
        """Run the councils under the price rule until the threshold or the round cap."""
        rule = book_2021_rule if self.price_rule is None else self.price_rule
        model = CouncilModel(economy, self.threshold_pct, rule)
        result = iterate(
            lambda: model.initial_state(self.initial_price, self.initial_rule_state),
            model.step,
            model.converged,
            self.max_rounds,
            plan_of=model.plan_of,
            keep_trajectory=self.record_trajectory,
        )
        if result.trajectory:
            return result.trajectory[-1]
        return model.plan_of(result.state)
