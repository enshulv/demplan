"""Technologies as checks: can a unit's planned inputs produce the unit's planned outputs.

``Economy.technology_kind`` is a text label per producing unit, and the data model says nothing
about what a label means. A :class:`Technology` is one reading of a label: given a plan, it
says for each output entry of a unit what the unit's planned inputs can deliver of that output
minus what the plan records. A negative number means the plan asks for more than the inputs
can produce.

The interface is per unit and takes the whole plan, because some technologies read plan fields
beyond ``input_use`` (one with an effort factor reads the effort the plan records). Per unit
also means a researcher writes a formula for one unit in plain Python, with no vectorised
numpy.

Most technologies separate into two halves: how much the unit can run on its inputs
(:class:`InputSide`), and what that much running delivers of each output (:class:`OutputSide`).
:class:`SeparableTechnology` joins one of each. The library ships two input sides,
:class:`Leontief` and :class:`CobbDouglas`, and two output sides, :class:`SingleOutput` and
:class:`FixedRatios`, and reads the labels :data:`demplan.LEONTIEF` and
:data:`demplan.COBB_DOUGLAS` as the matching input side with :class:`SingleOutput`. Reading a
unit with several outputs in fixed ratios is a statement about that unit's technology, so
:class:`FixedRatios` is never attached to a label unless the caller passes it.

:func:`technology_margins` runs the check over a whole plan. A unit whose label has no
implementation is reported as not computed and counted, never read under a guessed technology.
Every technology here is a theoretical claim about production, which is why this is a tool.
"""

from __future__ import annotations

import dataclasses
from types import MappingProxyType
from typing import Mapping, Protocol, runtime_checkable

import numpy as np

from demplan._wording import counted
from demplan.economy import COBB_DOUGLAS, LEONTIEF, Economy
from demplan.plan import Plan


@runtime_checkable
class Technology(Protocol):
    """One reading of a ``technology_kind`` label.

    ``label`` is the ``technology_kind`` value this technology reads.
    """

    label: str

    def margin(self, economy: Economy, plan: Plan, unit: int) -> np.ndarray:
        """One number per output entry of ``unit``, in storage order: what the unit's planned
        inputs can deliver of that output minus what the plan records. Negative means the plan
        asks for more than the inputs can produce."""
        ...


@runtime_checkable
class InputSide(Protocol):
    """The half of a separable technology that reads a unit's inputs."""

    def activity(self, economy: Economy, plan: Plan, unit: int) -> float:
        """How much the unit can run on its planned inputs."""
        ...


@runtime_checkable
class OutputSide(Protocol):
    """The half of a separable technology that turns activity into outputs."""

    def deliverable(self, economy: Economy, unit: int, activity: float) -> np.ndarray:
        """How much of each of the unit's output entries ``activity`` delivers, in storage
        order."""
        ...


def _outputs_of(economy: Economy, unit: int) -> slice:
    """Window of the flat output arrays that belongs to one producing unit."""
    return slice(int(economy.output_offsets[unit]), int(economy.output_offsets[unit + 1]))


class SeparableTechnology:
    """A technology that is an input side followed by an output side.

    The margin of a unit is ``outputs.deliverable(economy, unit, activity)`` minus the plan's
    output entries of the unit, where ``activity`` is ``inputs.activity(economy, plan, unit)``.
    A researcher who has one formula for how much a unit can run, or for what running delivers,
    writes that half and takes the other from the library.
    """

    def __init__(self, label: str, inputs: InputSide, outputs: OutputSide):
        self.label = label
        self.inputs = inputs
        self.outputs = outputs

    def margin(self, economy: Economy, plan: Plan, unit: int) -> np.ndarray:
        """Deliverable output of ``unit`` at the activity its planned inputs allow, minus the
        plan's output entries of ``unit``."""
        activity = self.inputs.activity(economy, plan, unit)
        deliverable = np.asarray(
            self.outputs.deliverable(economy, unit, activity), dtype=np.float64
        )
        return deliverable - plan.output[_outputs_of(economy, unit)]


class Leontief:
    """Fixed input proportions: the scarcest input, relative to its coefficient, sets activity.

    Activity is the smallest ``input_use / input_coefficient`` over the unit's inputs whose
    coefficient is above zero. An input with a coefficient of zero or below limits nothing, so
    a unit with no positive coefficient has infinite activity.
    """

    def activity(self, economy: Economy, plan: Plan, unit: int) -> float:
        """The binding ratio of planned input use to coefficient, or infinity if none binds."""
        window = economy.inputs_of(unit)
        coefficient = economy.input_coefficient[window]
        limiting = coefficient > 0.0
        if not limiting.any():
            return float("inf")
        return float(np.min(plan.input_use[window][limiting] / coefficient[limiting]))


class CobbDouglas:
    """Activity is ``technology_scale * prod(input_use ** input_coefficient)``."""

    def activity(self, economy: Economy, plan: Plan, unit: int) -> float:
        """The unit's scale times the product of its planned inputs raised to its exponents."""
        window = economy.inputs_of(unit)
        powers = plan.input_use[window] ** economy.input_coefficient[window]
        return float(economy.technology_scale[unit] * np.prod(powers))


class SingleOutput:
    """One output entry, delivering ``activity * output_coefficient``.

    A unit with any other number of output entries is refused: a technology read with one
    output has no reading of a second.
    """

    def deliverable(self, economy: Economy, unit: int, activity: float) -> np.ndarray:
        """``activity`` times the unit's one output coefficient. Raises ``ValueError`` naming
        the unit when it has more than one output entry."""
        window = _outputs_of(economy, unit)
        entries = window.stop - window.start
        if entries != 1:
            raise ValueError(
                f"unit {unit} has {entries} output entries, and its technology "
                f"{str(economy.technology_kind[unit])!r} is read with one output. A unit with "
                "joint products needs a technology that reads them: build a "
                "SeparableTechnology with an output side such as FixedRatios and pass it to "
                "technology_margins under the unit's label."
            )
        return activity * economy.output_coefficient[window]


class FixedRatios:
    """Every output entry delivers ``activity * output_coefficient``: outputs in fixed ratios."""

    def deliverable(self, economy: Economy, unit: int, activity: float) -> np.ndarray:
        """``activity`` times each of the unit's output coefficients."""
        return activity * economy.output_coefficient[_outputs_of(economy, unit)]


def _library_technologies() -> dict[str, Technology]:
    """The labels the library reads without being told how, each with its technology."""
    return {
        LEONTIEF: SeparableTechnology(LEONTIEF, Leontief(), SingleOutput()),
        COBB_DOUGLAS: SeparableTechnology(COBB_DOUGLAS, CobbDouglas(), SingleOutput()),
    }


@dataclasses.dataclass(frozen=True, eq=False)
class TechnologyReport:
    """What :func:`technology_margins` found, one entry per output entry of the economy.

    ``margin`` is ``f64[n_outputs]``: the technology's margin where it was computed and 0.0
    where it was not. ``computed`` is ``bool[n_outputs]`` and says which. ``missing`` maps each
    label that had no implementation to the number of producing units carrying it. Both arrays
    and the mapping are read-only.

    Equality is identity, since the fields are numpy arrays.
    """

    margin: np.ndarray
    computed: np.ndarray
    missing: Mapping[str, int]


def technology_margins(
    economy: Economy, plan: Plan, technologies: Mapping[str, Technology] | None = None
) -> TechnologyReport:
    """Each unit's margin under the technology its label names, over the whole plan.

    ``technologies`` maps a ``technology_kind`` label to the :class:`Technology` that reads it.
    It adds to the labels the library reads, :data:`demplan.LEONTIEF` and
    :data:`demplan.COBB_DOUGLAS`, and an entry under one of those replaces the library's
    reading for this call. A unit whose label nothing reads is left out: its entries are not
    computed, and the label is counted in ``missing``.

    Raises :class:`demplan.SchemaError` when the plan is not shaped for ``economy``, and
    ``ValueError`` when a technology answers with a number of entries other than the unit's
    output entries. A technology's own refusal, such as :class:`SingleOutput` meeting a unit
    with joint products, propagates.
    """
    plan._require_conformable(economy)
    readings = _library_technologies()
    if technologies is not None:
        readings.update(technologies)

    margin = np.zeros(economy.n_outputs, dtype=np.float64)
    computed = np.zeros(economy.n_outputs, dtype=bool)
    missing: dict[str, int] = {}
    for unit in range(economy.n_units):
        label = str(economy.technology_kind[unit])
        technology = readings.get(label)
        if technology is None:
            missing[label] = missing.get(label, 0) + 1
            continue
        window = _outputs_of(economy, unit)
        margin[window] = _margin_of_unit(technology, label, economy, plan, unit, window)
        computed[window] = True

    margin.flags.writeable = False
    computed.flags.writeable = False
    return TechnologyReport(
        margin=margin, computed=computed, missing=MappingProxyType(missing)
    )


def _margin_of_unit(
    technology: Technology, label: str, economy: Economy, plan: Plan, unit: int, window: slice
) -> np.ndarray:
    """``technology.margin`` for one unit, checked to hold one number per output entry."""
    unit_margin = np.asarray(technology.margin(economy, plan, unit), dtype=np.float64)
    entries = window.stop - window.start
    if unit_margin.shape != (entries,):
        raise ValueError(
            f"the technology for {label!r} returned a margin of shape {unit_margin.shape} for "
            f"unit {unit}, which has {counted(entries, 'output entry', 'output entries')}; a "
            "margin is one number per output entry"
        )
    return unit_margin
