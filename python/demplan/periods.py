"""Running a procedure over several periods.

:func:`run_periods` calls :func:`demplan.run` once per period and keeps every period's economy
and result together, so the library sees one trajectory instead of unrelated runs. Without an
evolution rule every period solves the same economy (static mode); with one, each period's
economy is what the rule made of the previous period's economy and plan (rolling mode).
"""

from __future__ import annotations

import dataclasses
import warnings
from typing import Collection, Protocol, runtime_checkable

import numpy as np

from demplan.differences import PeriodDifferences, _declared_constraints, period_differences
from demplan.economy import Economy
from demplan.plan import Plan, _commodity_declaration
from demplan.procedure import Procedure, RunResult, run
from demplan.seeds import split_seed

_WORDS_PER_PERIOD = 2
"""Sub-seeds reserved per period: word ``2i`` solves period ``i``, word ``2i + 1`` is passed to
the evolution rule that produces period ``i + 1``. The last period's second word is unused."""


@runtime_checkable
class Advance(Protocol):
    """An evolution rule: what the economy becomes after one period's plan.

    It belongs to the researcher. Capital accumulation, technical change, resource depletion
    and population change are theoretical claims, and the rule is where a study states them.
    :func:`run_periods` has no default rule: without one it runs in static mode.

    It receives a seed so that a random evolution rule is reproducible from the run's seed. It
    must draw all its randomness from that seed and keep no random state of its own between
    calls, because the same object is reused across runs and a second run would otherwise
    continue the first run's random stream.
    """

    def __call__(self, economy: Economy, plan: Plan, seed: int) -> Economy:
        ...


@runtime_checkable
class NextProcedure(Protocol):
    """Builds the procedure for the next period from the previous period's plan.

    This is how a period's procedure gets information from the plan before it, for example to
    start its iteration from where the previous period ended (a warm start). Returning a new
    procedure object for each period is the point: the information travels in the object, and
    the interface ``solve(economy, seed)`` stays unchanged.

    Without it, :func:`run_periods` reuses the same procedure object in every period.
    """

    def __call__(self, previous_plan: Plan) -> Procedure:
        ...


class PeriodWarning(UserWarning):
    """An evolution rule returned an economy whose ``period`` is not one more than the last."""


@dataclasses.dataclass(frozen=True)
class PeriodResult:
    """One period of a multi-period run."""

    index: int
    """Position of the period in the run, counting from 0."""
    economy: Economy
    """The economy this period's procedure solved."""
    result: RunResult
    """What :func:`demplan.run` returned for this period."""
    solve_seed: int
    """The seed passed to ``solve``."""
    advance_seed: int | None
    """The seed passed to the evolution rule that produced :attr:`economy`. ``None`` for the
    first period and for every period of a run without an evolution rule."""


@dataclasses.dataclass(frozen=True)
class PeriodsResult:
    """Every period of a multi-period run, in order."""

    periods: tuple[PeriodResult, ...]
    differences: PeriodDifferences | None = None
    """:func:`demplan.period_differences` over the run's economies and plans, or ``None`` when
    the run was asked not to compute it."""


def run_periods(
    economy: Economy,
    procedure: Procedure,
    periods: int,
    seed: int,
    advance: Advance | None = None,
    next_procedure: NextProcedure | None = None,
    check_period: bool = True,
    bads: np.ndarray | None = None,
    price: str | None = None,
    resources: np.ndarray | None = None,
    constraints: Collection[str] = (),
    differences: bool = True,
) -> PeriodsResult:
    """Run ``procedure`` for ``periods`` periods, starting from ``economy``.

    Seeds come from ``split_seed(seed, 2 * periods)``: period ``i`` solves with word ``2i``,
    and the evolution rule that produces period ``i + 1`` gets word ``2i + 1``. The layout is
    fixed, so a longer run repeats a shorter one's periods exactly.

    Between two periods, ``advance`` (when given) turns the economy and the plan just produced
    into the next economy, and ``next_procedure`` (when given) builds the next procedure from
    that plan. Without ``advance`` every period solves the same economy object; without
    ``next_procedure`` every period uses the same procedure object. Neither is called after the
    last period.

    With ``advance`` given and ``check_period`` true, an economy whose ``period`` is not one
    more than the previous economy's emits a :class:`PeriodWarning`; the run continues with the
    economy as returned.

    Every period's economy is kept in the result as the object the run used, without copying.

    ``bads``, ``price`` and ``differences`` are passed to every period's :func:`demplan.run`.
    With ``differences`` true, the result also carries :func:`demplan.period_differences` over
    the periods' economies and plans, given ``resources`` and ``constraints``, computed after
    the last period; with it false, neither report is computed.

    Raises ``ValueError`` when ``periods`` is not an integer of at least 1, or when ``seed`` is
    outside ``[0, 2**64)``; the errors :func:`demplan.run` and :func:`demplan.period_differences`
    raise for the declarations passed on to them; ``TypeError`` when ``advance`` returns
    something other than an ``Economy`` or ``next_procedure`` returns something without a
    callable ``solve``. ``resources`` and ``constraints`` are checked against ``economy`` before
    the first period runs, with ``differences`` on or off, so a malformed one costs no solve.
    Exceptions from ``solve``, ``advance`` and ``next_procedure`` propagate unchanged, and no
    partial result is returned.
    """
    periods = _period_count(periods)
    _require_period_declarations(economy, resources, constraints)
    words = split_seed(seed, _WORDS_PER_PERIOD * periods)

    recorded: list[PeriodResult] = []
    advance_seed: int | None = None
    for index in range(periods):
        solve_seed = words[_WORDS_PER_PERIOD * index]
        result = run(procedure, economy, solve_seed, bads, price, differences)
        recorded.append(PeriodResult(index, economy, result, solve_seed, advance_seed))
        if index == periods - 1:
            break

        if advance is not None:
            advance_seed = words[_WORDS_PER_PERIOD * index + 1]
            following = _advanced_economy(advance, economy, result.plan, advance_seed, index)
            gap = _period_gap_message(economy, following) if check_period else None
            if gap is not None:
                warnings.warn(PeriodWarning(gap), stacklevel=2)
            economy = following
        if next_procedure is not None:
            procedure = _next_procedure(next_procedure, result.plan, index)

    report = None
    if differences:
        report = period_differences(
            [period.economy for period in recorded],
            [period.result.plan for period in recorded],
            resources,
            constraints,
        )
    return PeriodsResult(tuple(recorded), report)


def _period_count(periods: object) -> int:
    """Return ``periods`` as a Python ``int``, refusing anything but an integer of at least 1.

    Python and numpy integers are accepted, as :func:`demplan.split_seed` accepts them for a
    seed. ``bool`` is an ``int`` subclass and is refused explicitly; ``numpy.bool_`` is not a
    ``numpy.integer`` and is refused by the type test. The conversion matters: numpy integer
    arithmetic wraps, so ``2 * numpy.uint8(130)`` is 4, and the seed count would come out short.
    """
    is_integer = isinstance(periods, (int, np.integer)) and not isinstance(periods, bool)
    if not is_integer or periods < 1:
        raise ValueError(f"periods must be an integer of at least 1, got {periods!r}")
    return int(periods)


def _require_period_declarations(
    economy: Economy, resources: np.ndarray | None, constraints: Collection[str]
) -> None:
    """Refuse ``resources`` or ``constraints`` that :func:`demplan.period_differences` would.

    ``resources`` is checked against the first period's commodities, as
    :func:`demplan.period_differences` checks it. Raises ``ValueError``.
    """
    if resources is not None:
        _commodity_declaration("resources", resources, economy.n_commodities)
    _declared_constraints(constraints)


def _advanced_economy(
    advance: Advance, economy: Economy, plan: Plan, seed: int, index: int
) -> Economy:
    """Call the evolution rule after period ``index``. Raises ``TypeError`` on a non-``Economy``."""
    following = advance(economy, plan, seed)
    if not isinstance(following, Economy):
        raise TypeError(
            f"advance returned {type(following).__name__} after period {index}, "
            "expected an Economy"
        )
    return following


def _next_procedure(next_procedure: NextProcedure, plan: Plan, index: int) -> Procedure:
    """Build the procedure for the period after ``index``.

    Raises ``TypeError`` when the returned object has no callable ``solve``.
    """
    built = next_procedure(plan)
    if not callable(getattr(built, "solve", None)):
        raise TypeError(
            f"next_procedure returned {type(built).__name__} after period {index}, "
            "expected an object with a callable solve method"
        )
    return built


def _period_gap_message(previous: Economy, following: Economy) -> str | None:
    """The :class:`PeriodWarning` text when ``following.period`` is not ``previous.period + 1``.

    Returns ``None`` when the period moved on by exactly one.
    """
    expected = previous.period + 1
    if following.period == expected:
        return None
    return (
        f"advance returned an economy with period {following.period}, expected "
        f"{expected}; pass check_period=False to silence this warning"
    )
