"""Numbers read off one plan or compared between two.

:func:`compare_plans` reports how far two plans lie apart, field by field, as the largest
relative difference between matching entries. :func:`input_use_on` totals a plan's input use
over commodities the caller names. Neither carries a tolerance or a verdict: what gap counts
as small is the researcher's statement.
"""

from __future__ import annotations

import dataclasses
from types import MappingProxyType
from typing import Mapping

import numpy as np

from demplan.economy import Economy
from demplan.plan import Plan, _commodity_declaration, require_comparable

_COMPARED_FIELDS = ("output", "input_use", "consumption", "shared_use")

_DIFFERENT_COLUMNS = "the two plans' consumption columns name different commodities"


@dataclasses.dataclass(frozen=True)
class PlanComparison:
    """How far two plans lie apart on each physical field.

    ``max_relative_difference`` maps each compared field to the largest
    ``|a - b| / max(|a|, |b|)`` over its entries, counting an entry where both are zero as 0.
    A NaN in either plan makes the field's value NaN. ``not_compared`` maps every other field
    to the reason it was left out. Fields appear in the order ``output``, ``input_use``,
    ``consumption``, ``shared_use``.
    """

    max_relative_difference: Mapping[str, float]
    not_compared: Mapping[str, str]


def compare_plans(plan: Plan, other: Plan) -> PlanComparison:
    """Compare two plans field by field. The result does not depend on the argument order.

    A field is not compared when either plan declares it absent. ``consumption`` is also not
    compared when the two plans read it differently (a stated plan against an allocated one,
    with :func:`demplan.require_comparable`'s message as the reason) or when their
    ``consumption_commodity`` columns differ. A field with no entries compares at 0.0.

    Raises ``ValueError`` naming the field when a field both plans carry has a different
    shape in each.
    """
    compared: dict[str, float] = {}
    not_compared: dict[str, str] = {}
    for name in _COMPARED_FIELDS:
        reason = _why_not_compared(name, plan, other)
        if reason is not None:
            not_compared[name] = reason
            continue
        first, second = getattr(plan, name), getattr(other, name)
        if first.shape != second.shape:
            raise ValueError(
                f"Plan.{name} has shape {first.shape} in one plan and {second.shape} in the "
                "other, so its entries cannot be matched"
            )
        compared[name] = _max_relative_difference(first, second)
    return PlanComparison(MappingProxyType(compared), MappingProxyType(not_compared))


def _why_not_compared(name: str, plan: Plan, other: Plan) -> str | None:
    """Why field ``name`` is left out of the comparison, or ``None`` when it is compared."""
    first, second = getattr(plan, name), getattr(other, name)
    if first is None and second is None:
        return "absent from both plans"
    if first is None or second is None:
        return "absent from one plan"
    if name != "consumption":
        return None
    try:
        require_comparable(plan, other)
    except ValueError as incomparable:
        return str(incomparable)
    if not np.array_equal(plan.consumption_commodity, other.consumption_commodity):
        return _DIFFERENT_COLUMNS
    return None


def _max_relative_difference(first: np.ndarray, second: np.ndarray) -> float:
    """``max |a - b| / max(|a|, |b|)`` over matching entries, 0 for an entry where both are 0.

    The maximum of no entries is 0.0: there is no entry on which the two plans differ.
    """
    if first.size == 0:
        return 0.0
    gap = np.abs(first - second)
    magnitude = np.maximum(np.abs(first), np.abs(second))
    both_zero = magnitude == 0.0
    with np.errstate(invalid="ignore", divide="ignore"):
        relative = np.where(both_zero, 0.0, gap / np.where(both_zero, 1.0, magnitude))
    return float(np.max(relative))


def input_use_on(economy: Economy, plan: Plan, commodities: np.ndarray) -> float:
    """The plan's input use summed over every input entry whose commodity is in ``commodities``.

    ``commodities`` is a one-dimensional int64 array of distinct commodity indices, checked as
    :meth:`demplan.Plan.endowment_use` checks its argument; the total is
    ``plan.endowment_use(economy, commodities).sum()``. The labour total of a Hahnel plan, for
    instance, is ``input_use_on(economy, plan, hahnel.labor(economy))``.

    Raises ``ValueError`` when ``commodities`` is not such an array or names a commodity
    outside the table, and :class:`demplan.SchemaError` when the plan is not shaped for
    ``economy``.
    """
    listed = _commodity_declaration("commodities", commodities, economy.n_commodities)
    return float(plan.endowment_use(economy, listed).sum())
