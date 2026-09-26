"""The procedure of Hahnel (2021), *Democratic Economic Planning*, ch. 9, as its program ran it.

The published round counts come from ``msszczep/pequod-cljs``, ``src/clj/pequod_cljs/csvgen.clj``
at commit ``71e44d3``. This module holds that program's price rule, :class:`Book2021Rule`,
and the procedure that runs the councils of :mod:`demplan.prefabs.hahnel.councils` under it,
:class:`HahnelBook2021`.

It also holds what the book's two-year experiments add, for :func:`demplan.run_periods`: the
change between the years, :func:`perturb_exponents`; the warm start of year two,
:class:`WarmStart`; the increasing returns of Table 9.6, :func:`increasing_returns`; and the
growth figure the book reports, :func:`real_gdp_growth`.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np

from demplan.economy import CommodityKind, Economy
from demplan.iterate import iterate
from demplan.plan import Plan
from demplan.prefabs.hahnel.councils import (
    NEXT_INDICATIVE_PRICE,
    PERCENT,
    PRICE_RULE_STATE,
    CouncilModel,
    PriceRule,
)
from demplan.seeds import rng
from demplan.tools import unit_of_input

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


INPUT_EXPONENT_STEPS = (0.0, 0.001, 0.002, 0.003, 0.004)
"""What ``augment-wc`` may add to one worker-council input, nature or labour exponent."""

UTILITY_EXPONENT_STEPS = (-0.002, -0.001, 0.0, 0.001, 0.002)
"""What ``augment-cc`` may add to one consumer-council utility exponent."""

UTILITY_EXPONENT = "utility_exponent"


def perturb_exponents(economy: Economy, plan: Plan, seed: int) -> Economy:
    """The book's change between two years: every input and utility exponent moves a little.

    An :class:`demplan.Advance` for :func:`demplan.run_periods`. Source: ``csvgen.clj`` at
    ``71e44d3``, ``augment-wc`` and ``augment-cc`` (lines 185-192), which ``augmented-reset``
    (lines 194-200) applies to every council between the two years. Each exponent gets its
    own draw, uniform over five values:

    * every entry of ``input_coefficient`` (the program's input, nature and labour exponents)
      gains one of :data:`INPUT_EXPONENT_STEPS`;
    * every entry of ``consumer_extra["utility_exponent"]`` (its private-good and public-good
      utility exponents) gains one of :data:`UTILITY_EXPONENT_STEPS`.

    The effort exponent ``unit_extra["effort_c"]`` is not changed; the program leaves it alone
    too. The draws come from ``demplan.seeds.rng(seed)``: the input steps first, in the order
    of ``input_coefficient``, then the utility steps, in row-major order.

    ``plan`` is not read. The book's technical and preference change is drawn at random and
    does not depend on what the year before planned; the argument is there because an
    evolution law receives the plan.

    Returns a new economy with ``period`` one higher and those two arrays replaced. Raises
    ``ValueError`` when ``consumer_extra`` has no ``"utility_exponent"``, and when a perturbed
    exponent is zero or below, naming each such array and how many of its entries are; no
    exponent is clipped, because a clipped exponent is a change the program does not make.
    """
    if UTILITY_EXPONENT not in economy.consumer_extra:
        raise ValueError(
            f"perturb_exponents needs consumer_extra[{UTILITY_EXPONENT!r}], the consumer "
            "councils' utility exponents"
        )
    generator = rng(seed)
    input_steps = generator.choice(np.array(INPUT_EXPONENT_STEPS), size=economy.n_inputs)
    utility_exponent = np.asarray(economy.consumer_extra[UTILITY_EXPONENT])
    utility_steps = generator.choice(
        np.array(UTILITY_EXPONENT_STEPS), size=utility_exponent.shape
    )

    perturbed_input = np.asarray(economy.input_coefficient) + input_steps
    perturbed_utility = utility_exponent + utility_steps
    _refuse_non_positive(
        {
            "input_coefficient": perturbed_input,
            f"consumer_extra[{UTILITY_EXPONENT!r}]": perturbed_utility,
        }
    )
    return dataclasses.replace(
        economy,
        period=economy.period + 1,
        input_coefficient=perturbed_input,
        consumer_extra={**economy.consumer_extra, UTILITY_EXPONENT: perturbed_utility},
    )


def _refuse_non_positive(arrays: dict[str, np.ndarray]) -> None:
    """Raise ``ValueError`` naming every array that holds an entry of zero or below."""
    problems = [
        f"{int(np.count_nonzero(values <= 0))} of {values.size} entries of {name}"
        for name, values in arrays.items()
        if np.any(values <= 0)
    ]
    if problems:
        raise ValueError(
            f"perturb_exponents left {' and '.join(problems)} at or below zero; "
            "an exponent has to stay above zero, and none is clipped"
        )


@dataclasses.dataclass(frozen=True)
class WarmStart:
    """Builds year two's :class:`HahnelBook2021` from year one's plan: a warm start.

    A :class:`demplan.NextProcedure` for :func:`demplan.run_periods`. In ``csvgen.clj`` at
    ``71e44d3``, ``augmented-reset`` (lines 194-200) sets the round counter back to zero and
    keeps the prices and the ``pdlist`` as the last round of year one left them, and ``-main``
    (lines 1028-1060) then runs year two to the threshold. Here that is a procedure whose
    ``initial_price`` is the previous plan's ``valuation["next_indicative_price"]`` and whose
    ``initial_rule_state`` is its ``extra["price_rule_state"]``: the price and the multiplier
    the last round's update returned. The four fields are passed on as they are.
    """

    threshold_pct: float = 3.0
    max_rounds: int = 250
    record_trajectory: bool = False
    price_rule: PriceRule | None = None

    def __call__(self, previous_plan: Plan) -> HahnelBook2021:
        """The procedure that continues from ``previous_plan``.

        The two arrays are handed on as the plan holds them; :class:`HahnelBook2021` copies
        them when it starts. Raises ``ValueError`` when the plan lacks either key.
        """
        missing = []
        if NEXT_INDICATIVE_PRICE not in previous_plan.valuation:
            missing.append(f"valuation[{NEXT_INDICATIVE_PRICE!r}]")
        if PRICE_RULE_STATE not in previous_plan.extra:
            missing.append(f"extra[{PRICE_RULE_STATE!r}]")
        if missing:
            raise ValueError(
                f"the previous plan has no {' and no '.join(missing)}, so it was not produced "
                "by HahnelBook2021 and a warm start has nothing to start from"
            )
        return HahnelBook2021(
            threshold_pct=self.threshold_pct,
            max_rounds=self.max_rounds,
            initial_price=previous_plan.valuation[NEXT_INDICATIVE_PRICE],
            initial_rule_state=previous_plan.extra[PRICE_RULE_STATE],
            record_trajectory=self.record_trajectory,
            price_rule=self.price_rule,
        )


def increasing_returns(
    economy: Economy, seed: int, share: float = 0.2, increment: float = 0.1
) -> Economy:
    """Give a share of the producing units increasing returns to scale.

    Source: ``csvgen.clj`` at ``71e44d3``, ``create-toothaches`` (lines 942-952), which the
    runs behind Table 9.6 of Hahnel (2021) apply once to the initial economy: a fifth of the
    worker councils, picked at random, get ``0.1`` added to every input, nature and labour
    exponent. Clojure's ``take`` with a fractional count takes the ceiling, so the number of
    units is ``ceil(share * n_units)``.

    The units are the first ``ceil(share * n_units)`` entries of
    ``demplan.seeds.rng(seed).permutation(n_units)``, and ``increment`` is added to every
    ``input_coefficient`` entry of those units. The effort exponent and ``period`` are not
    changed.

    Raises ``ValueError`` when ``share`` is not between 0 and 1 or ``increment`` is not finite.
    """
    if not 0.0 <= share <= 1.0:
        raise ValueError(f"share must be between 0 and 1, got {share!r}")
    if not math.isfinite(increment):
        raise ValueError(f"increment must be finite, got {increment!r}")
    n_chosen = math.ceil(share * economy.n_units)
    chosen = rng(seed).permutation(economy.n_units)[:n_chosen]
    raised = np.isin(unit_of_input(economy), chosen)
    coefficient = np.asarray(economy.input_coefficient)
    return dataclasses.replace(
        economy, input_coefficient=np.where(raised, coefficient + increment, coefficient)
    )


_FINAL_GOODS = (CommodityKind.PRIVATE_GOOD, CommodityKind.PUBLIC_GOOD)


def real_gdp_growth(
    economy_1: Economy, plan_1: Plan, economy_2: Economy, plan_2: Plan
) -> float:
    """Real GDP growth from year one to year two, in percent, as Hahnel (2021) reports it.

    Source: the book's note 15 (called on p. 182, text on p. 193) and the upstream
    ``bin/dep_data_process.py``, block "table 4, gdp". Only private and public goods count.
    A good's quantity is its supply, the worker councils' output
    ``plan.total_output(economy)``, and its price is the price after the year's last update,
    ``plan.valuation["next_indicative_price"]``. At one price vector ``p``::

        g(p) = 100 * (p . q_2 - p . q_1) / (p . q_1)

    and the growth reported is the mean of ``g(p_1)`` and ``g(p_2)``.

    The goods are the commodities whose ``commodity_kind`` is a private or a public good in
    ``economy_1``. Raises ``ValueError`` when the two economies differ in ``n_commodities``
    or in ``commodity_kind``, or when either plan has no ``"next_indicative_price"``.
    """
    if economy_1.n_commodities != economy_2.n_commodities:
        raise ValueError(
            f"the two economies differ in n_commodities: {economy_1.n_commodities} and "
            f"{economy_2.n_commodities}"
        )
    if not np.array_equal(economy_1.commodity_kind, economy_2.commodity_kind):
        raise ValueError("the two economies differ in commodity_kind")
    for label, plan in (("plan_1", plan_1), ("plan_2", plan_2)):
        if NEXT_INDICATIVE_PRICE not in plan.valuation:
            raise ValueError(f"{label} has no valuation[{NEXT_INDICATIVE_PRICE!r}]")

    goods = np.isin(economy_1.commodity_kind, [int(kind) for kind in _FINAL_GOODS])
    quantity_1 = plan_1.total_output(economy_1)[goods]
    quantity_2 = plan_2.total_output(economy_2)[goods]
    price_1 = np.asarray(plan_1.valuation[NEXT_INDICATIVE_PRICE])[goods]
    price_2 = np.asarray(plan_2.valuation[NEXT_INDICATIVE_PRICE])[goods]
    growth_1 = _growth_at(price_1, quantity_1, quantity_2)
    growth_2 = _growth_at(price_2, quantity_1, quantity_2)
    return float((growth_1 + growth_2) / 2.0)


def _growth_at(price: np.ndarray, quantity_1: np.ndarray, quantity_2: np.ndarray) -> float:
    """``100 * (p . q_2 - p . q_1) / (p . q_1)``: growth valued at one price vector."""
    value_1 = float(np.dot(price, quantity_1))
    value_2 = float(np.dot(price, quantity_2))
    return PERCENT * (value_2 - value_1) / value_1
