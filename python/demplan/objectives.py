"""What a reference solution optimises, and how it hands the result to consumer units.

Every objective in this module is a theoretical commitment. The library has no default one:
a centralised optimum is only defined once somebody says what "optimal" means, and saying it
is the researcher's job, not the library's. What the library supplies is the interface, so
that a declared objective travels into the run manifest alongside the plan it produced.

An objective answers two questions. :meth:`Objective.weights` says what the linear program
maximises, one coefficient per commodity. :meth:`Objective.allocate` says who ends up with the
final consumption the program chose, which is a separate commitment from what to maximise:
the same weights can be shared out equally, by entitlement, or by any other rule.

Which commodities carry weight, which ones a labour count totals, and which ones consumer
units use in common are all declared here by commodity index. The economy says none of it.
"""

from __future__ import annotations

from typing import Mapping, Protocol, runtime_checkable

import numpy as np

from demplan.economy import Economy, _index_array, _require_indices_in_range

EQUAL_SPLIT = "equal"
"""The one split rule implemented here: every consumer unit receives the same quantity."""


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

        An objective that is not a weighted sum returns zeros and carries its own attributes
        instead; see :class:`MinimizeLabor`.
        """
        ...

    def allocate(
        self, economy: Economy, aggregate: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Turn total final consumption into the consumption side of a plan.

        ``aggregate`` is ``f64[n_commodities]``. The result is
        ``(consumption f64[n_consumers, k], consumption_commodity int64[k],
        shared_use f64[n_commodities])``, shaped for :class:`demplan.Plan`.
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


def _shared_commodities(shared) -> np.ndarray:
    """The ``shared`` declaration as an index array: empty for ``None``, checked otherwise."""
    if shared is None:
        return np.zeros(0, dtype=np.int64)
    return _index_array("shared", shared)


def _split_equally(
    economy: Economy, aggregate: np.ndarray, declared: np.ndarray, shared: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Give shared commodities to ``shared_use`` whole and split the rest evenly.

    ``declared`` is the objective's weight or floor vector over the commodity range. The
    consumption columns are every commodity it is non-zero on that is not in ``shared``, in
    ascending order, and each consumer unit receives the aggregate of each divided by the
    number of consumer units. A commodity in ``shared`` goes to ``shared_use`` at its whole
    aggregate, which is what used in common means: no consumer unit's use reduces another's.
    """
    aggregate = np.asarray(aggregate, dtype=np.float64)
    if aggregate.shape != (economy.n_commodities,):
        raise ValueError(
            f"aggregate: shape {aggregate.shape}, expected one entry per commodity "
            f"({economy.n_commodities},)"
        )
    _require_indices_in_range("shared", shared, economy.n_commodities)

    in_common = np.zeros(economy.n_commodities, dtype=bool)
    in_common[shared] = True
    columns = np.flatnonzero((declared != 0.0) & ~in_common).astype(np.int64)
    if economy.n_consumers == 0 and np.any(aggregate[columns] != 0.0):
        raise ValueError(
            "allocate: the economy has no consumer unit to split final consumption among"
        )

    share = np.zeros(columns.shape[0], dtype=np.float64)
    if economy.n_consumers:
        share = aggregate[columns] / economy.n_consumers
    consumption = np.tile(share, (economy.n_consumers, 1))
    shared_use = np.where(in_common, aggregate, 0.0)
    return consumption, columns, shared_use


class MaximizeWeightedConsumption:
    """Maximise a declared weighted sum of final consumption, then split it equally.

    Two commitments ride along with this objective, and a run that uses it is claiming both.
    The first is the weights themselves: they are a statement that one more unit of this
    commodity is worth exactly this much relative to that one, which is the whole content of a
    social welfare function. The second is the split: what is not used in common is divided
    evenly between consumer units, so the plan carries no claim about differing needs, effort
    or entitlement.

    ``weights`` may be a full ``f64[n_commodities]`` vector or a mapping from commodity to
    weight, on any commodity the researcher chooses. ``shared`` is a one-dimensional int64
    array of the commodities consumer units use in common, which :meth:`allocate` hands to
    ``shared_use`` whole; ``None`` says no commodity is used in common. ``split`` accepts
    ``"equal"``; the parameter exists because the split is a separate commitment from the
    weights, not because other rules are implemented here.
    """

    name = "maximize_weighted_consumption"

    def __init__(
        self,
        weights: np.ndarray | Mapping[int, float],
        split: str = EQUAL_SPLIT,
        shared: np.ndarray | None = None,
    ) -> None:
        if split != EQUAL_SPLIT:
            raise ValueError(f"split: {split!r} is not implemented, only {EQUAL_SPLIT!r} is")
        _require_finite_declaration(weights, "weights")
        self.declared_weights = weights
        self.split = split
        self.shared_commodities = _shared_commodities(shared)

    def weights(self, economy: Economy) -> np.ndarray:
        """The declared weights over the commodity range; the declaration checked against it."""
        _require_indices_in_range("shared", self.shared_commodities, economy.n_commodities)
        return _as_weight_vector(self.declared_weights, economy.n_commodities, "weights")

    def allocate(
        self, economy: Economy, aggregate: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Shared commodities to ``shared_use``, every other weighted one split evenly."""
        declared = _as_weight_vector(self.declared_weights, economy.n_commodities, "weights")
        return _split_equally(economy, aggregate, declared, self.shared_commodities)


class MinimizeLabor:
    """Meet a declared floor on final consumption while spending the least labour.

    The commitment here is that labour is the only cost worth counting. Every commodity not in
    ``counted`` is free in this objective; what limits it is the material balance, not the
    thing being minimised. A run that adopts this objective is taking the labour theory's side
    of a live argument, which is why it is one option among several rather than the library's
    default.

    ``targets`` is a floor on final consumption, one entry per commodity, never negative.
    Consumption above the floor is neither rewarded nor penalised, so the solution meets the
    floor and stops. ``counted`` is a one-dimensional int64 array of the commodities whose
    input use the objective totals, at least one of them: which commodities are labour is the
    researcher's statement. ``shared`` is as on :class:`MaximizeWeightedConsumption`, and the
    floor decides the consumption columns the way the weights do there.

    :func:`demplan.reference.reference_solution` recognises this objective by two
    attributes rather than by its type, so a researcher's own labour-minimising objective is
    handled the same way: ``final_demand_lower_bound`` carries the floor and
    ``counted_commodities`` the commodities the objective totals. An objective carrying one of
    the two without the other is refused there.
    """

    name = "minimize_labor"

    def __init__(
        self, targets: np.ndarray, counted: np.ndarray, shared: np.ndarray | None = None
    ) -> None:
        _require_finite_declaration(targets, "targets")
        self.final_demand_lower_bound = np.asarray(targets, dtype=np.float64)
        _require_non_negative(self.final_demand_lower_bound, "targets")
        self.counted_commodities = _index_array("counted", counted)
        if self.counted_commodities.size == 0:
            raise ValueError(
                "counted: lists no commodity, so the labour the objective minimises is zero "
                "for every plan; name the commodities whose input use it totals"
            )
        self.shared_commodities = _shared_commodities(shared)

    def weights(self, economy: Economy) -> np.ndarray:
        """Zeros: the objective is total labour use, which no weight on consumption expresses.

        The targets and both index declarations are checked against the economy here, because
        this is the call the reference solution makes before it assembles the program.
        """
        _as_weight_vector(self.final_demand_lower_bound, economy.n_commodities, "targets")
        _require_indices_in_range("counted", self.counted_commodities, economy.n_commodities)
        _require_indices_in_range("shared", self.shared_commodities, economy.n_commodities)
        return np.zeros(economy.n_commodities, dtype=np.float64)

    def allocate(
        self, economy: Economy, aggregate: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Shared commodities to ``shared_use``, every other targeted one split evenly."""
        declared = _as_weight_vector(
            self.final_demand_lower_bound, economy.n_commodities, "targets"
        )
        return _split_equally(economy, aggregate, declared, self.shared_commodities)
