"""What a reference solution optimises, and how it hands the result to consumer units.

Every objective in this module is a theoretical commitment. The library has no default one:
a centralised optimum is only defined once somebody says what "optimal" means, and saying it
is the researcher's job, not the library's. What the library supplies is the interface, so
that a declared objective travels into the run manifest alongside the plan it produced.

An objective answers two questions. :meth:`Objective.weights` says what the linear program
maximises, one coefficient per commodity. :meth:`Objective.allocate` says who ends up with the
final consumption the program chose, which is a separate commitment from what to maximise:
the same weights can be shared out equally, by entitlement, or by any other rule.
"""

from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable

import numpy as np

from demplan.economy import CommodityKind, Economy

EQUAL_SPLIT = "equal"
"""The one split rule implemented here: every consumer unit receives the same quantity."""

_CONSUMABLE_KINDS = (CommodityKind.PRIVATE_GOOD, CommodityKind.PUBLIC_GOOD)


@runtime_checkable
class Objective(Protocol):
    """What a reference solution maximises and how it shares the result out.

    ``name`` identifies the objective in a run manifest, so it stays stable across releases.

    :meth:`weights` is also where an objective checks itself against the economy it is about
    to be used on: the reference solution calls it before assembling the program, and an
    objective that cannot apply to this economy raises ``ValueError`` there.
    """

    name: str

    def weights(self, economy: Economy) -> np.ndarray:
        """Coefficient on final consumption of each commodity, ``f64[n_commodities]``.

        Zero for every commodity that cannot be consumed. An objective that is not a weighted
        sum returns zeros and carries its own attributes instead; see :class:`MinimizeLabor`.
        """
        ...

    def allocate(
        self, economy: Economy, aggregate: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Turn total final consumption into the consumption side of a plan.

        ``aggregate`` is ``f64[n_commodities]``. The result is
        ``(consumption f64[n_consumers, k], consumption_commodity int64[k],
        provision f64[n_commodities])``, shaped for :class:`demplan.Plan`.
        """
        ...


def _as_weight_vector(
    values: np.ndarray | Mapping[int, float], n_commodities: int, label: str
) -> np.ndarray:
    """Materialise a weight or target declaration over the commodity range."""
    if isinstance(values, Mapping):
        vector = np.zeros(n_commodities, dtype=np.float64)
        for commodity, value in values.items():
            index = int(commodity)
            if index < 0 or index >= n_commodities:
                raise ValueError(
                    f"{label}: commodity {index} is outside the range [0, {n_commodities})"
                )
            vector[index] = float(value)
        return vector

    vector = np.asarray(values, dtype=np.float64)
    if vector.ndim != 1 or vector.shape[0] != n_commodities:
        raise ValueError(
            f"{label}: shape {vector.shape}, expected one entry per commodity "
            f"({n_commodities},)"
        )
    return vector


def _require_finite_declaration(values, label: str) -> None:
    if isinstance(values, Mapping):
        offending = [key for key, value in values.items() if not np.isfinite(float(value))]
        if offending:
            raise ValueError(f"{label}: commodity {offending[0]} carries a non-finite value")
        return
    array = np.asarray(values, dtype=np.float64)
    if array.size and not np.isfinite(array).all():
        raise ValueError(f"{label}: every entry must be finite")


def _require_non_negative(values: np.ndarray, label: str) -> None:
    """Refuse a negative entry in a floor on final consumption.

    The floor becomes the variable's lower bound in the reference program, and a negative bound
    lets that commodity carry negative final consumption: the plan covers part of its own input
    use out of the floor and reports less cost than any plan that meets the floor as read.
    """
    offending = np.flatnonzero(values < 0.0)
    if offending.size:
        commodity = int(offending[0])
        raise ValueError(
            f"{label}: commodity {commodity} carries {float(values[commodity])}, and a floor on "
            "final consumption cannot be negative"
        )


def _require_consumable_support(values: np.ndarray, economy: Economy, label: str) -> None:
    """Refuse a non-zero entry on a commodity no consumer unit can end up holding.

    A weight on an intermediate good, a natural resource or labour has no reading in a plan:
    the physical layer records who consumes private goods and how much of each public good is
    provided, and nothing else. Dropping such an entry silently would let a program optimise a
    quantity that never appears in its own output.
    """
    consumable = np.isin(
        np.asarray(economy.commodity_kind), [int(kind) for kind in _CONSUMABLE_KINDS]
    )
    offending = np.flatnonzero((values != 0.0) & ~consumable)
    if offending.size:
        commodity = int(offending[0])
        kind = CommodityKind(int(economy.commodity_kind[commodity])).name.lower()
        raise ValueError(
            f"{label}: commodity {commodity} is {kind}, which is neither a private good nor a "
            "public good, so it cannot carry final consumption"
        )


def _split_equally(
    economy: Economy, aggregate: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Divide private goods evenly across consumer units and provide public goods in common.

    The columns are every private good in the economy, in commodity order, whether or not the
    objective put weight on it. A stable column set means two plans of the same economy line up
    without either of them having to know what the other optimised.
    """
    aggregate = np.asarray(aggregate, dtype=np.float64)
    if aggregate.shape != (economy.n_commodities,):
        raise ValueError(
            f"aggregate: shape {aggregate.shape}, expected one entry per commodity "
            f"({economy.n_commodities},)"
        )

    kinds = np.asarray(economy.commodity_kind)
    columns = np.flatnonzero(kinds == int(CommodityKind.PRIVATE_GOOD)).astype(np.int64)
    if economy.n_consumers == 0 and np.any(aggregate[columns] != 0.0):
        raise ValueError(
            "allocate: the economy has no consumer unit to split private-good consumption among"
        )

    share = np.zeros(columns.shape[0], dtype=np.float64)
    if economy.n_consumers:
        share = aggregate[columns] / economy.n_consumers
    consumption = np.tile(share, (economy.n_consumers, 1))
    provision = np.where(kinds == int(CommodityKind.PUBLIC_GOOD), aggregate, 0.0)
    return consumption, columns, provision


class MaximizeWeightedConsumption:
    """Maximise a declared weighted sum of final consumption, then split it equally.

    Two commitments ride along with this objective, and a run that uses it is claiming both.
    The first is the weights themselves: they are a statement that one more unit of this
    commodity is worth exactly this much relative to that one, which is the whole content of a
    social welfare function. The second is the split: private goods are divided evenly between
    consumer units, so the plan carries no claim about differing needs, effort or entitlement.

    ``weights`` may be a full ``f64[n_commodities]`` vector or a mapping from commodity to
    weight, and may be non-zero only on private goods and public goods. ``split`` accepts
    ``"equal"``; the parameter exists because the split is a separate commitment from the
    weights, not because other rules are implemented here.
    """

    name = "maximize_weighted_consumption"

    def __init__(
        self, weights: np.ndarray | Mapping[int, float], split: str = EQUAL_SPLIT
    ) -> None:
        if split != EQUAL_SPLIT:
            raise ValueError(f"split: {split!r} is not implemented, only {EQUAL_SPLIT!r} is")
        _require_finite_declaration(weights, "weights")
        self.declared_weights = weights
        self.split = split

    def weights(self, economy: Economy) -> np.ndarray:
        vector = _as_weight_vector(self.declared_weights, economy.n_commodities, "weights")
        _require_consumable_support(vector, economy, "weights")
        return vector

    def allocate(
        self, economy: Economy, aggregate: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return _split_equally(economy, aggregate)


class MinimizeLabor:
    """Meet a declared floor on final consumption while spending the least labour.

    The commitment here is that labour is the only cost worth counting. Natural resources,
    intermediate goods and the plan's own timing are all free in this objective; what limits
    them is the material balance, not the thing being minimised. A run that adopts this
    objective is taking the labour theory's side of a live argument, which is why it is one
    option among several rather than the library's default.

    ``targets`` is a floor on final consumption, one entry per commodity, non-zero only on
    private goods and public goods, and never negative. Consumption above the floor is neither
    rewarded nor penalised, so the solution meets the floor and stops.

    :func:`demplan.reference.reference_solution` recognises this objective by two
    attributes rather than by its type, so a researcher's own labour-minimising objective is
    handled the same way: ``final_demand_lower_bound`` carries the floor and ``minimize_kind``
    says which commodity class the objective totals up. An objective carrying one of the two
    without the other is refused there.
    """

    name = "minimize_labor"
    minimize_kind = CommodityKind.LABOR

    def __init__(self, targets: np.ndarray) -> None:
        _require_finite_declaration(targets, "targets")
        self.final_demand_lower_bound = np.asarray(targets, dtype=np.float64)
        _require_non_negative(self.final_demand_lower_bound, "targets")

    def weights(self, economy: Economy) -> np.ndarray:
        """Zeros: the objective is total labour use, which no weight on consumption expresses.

        The targets are validated here because this is the call the reference solution makes
        before it assembles the program.
        """
        targets = _as_weight_vector(
            self.final_demand_lower_bound, economy.n_commodities, "targets"
        )
        _require_consumable_support(targets, economy, "targets")
        return np.zeros(economy.n_commodities, dtype=np.float64)

    def allocate(
        self, economy: Economy, aggregate: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return _split_equally(economy, aggregate)
