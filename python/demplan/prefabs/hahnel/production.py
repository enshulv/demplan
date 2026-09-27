"""The Hahnel model's production function as a :class:`demplan.Technology`.

A unit labelled :data:`~demplan.prefabs.hahnel.TECHNOLOGY` produces
``Q = a * e**c * prod(x_j ** b_j)``: ``a`` is its ``technology_scale``, ``b_j`` its
``input_coefficient``, ``x_j`` the plan's ``input_use``, ``e`` the effort the plan records in
``extra["effort"]`` and ``c`` its ``unit_extra["effort_c"]``. The effort factor is why plain
Cobb-Douglas does not describe these units: a plan the councils made delivers more than the
input bundle alone accounts for, by the factor ``e**c``.

The library does not read this label on its own. Pass the technology to
:func:`demplan.technology_margins` under its label::

    technology_margins(economy, plan, {TECHNOLOGY: technology()})
"""

from __future__ import annotations

import numpy as np

from demplan.economy import Economy
from demplan.plan import EFFORT, Plan
from demplan.prefabs.hahnel.labels import TECHNOLOGY

_EFFORT_EXPONENT_KEY = "effort_c"
"""The ``unit_extra`` key holding each unit's effort exponent ``c``."""


class _EffortCobbDouglas:
    """``Q = a * e**c * prod(x_j ** b_j)`` for one unit, against the plan's one output entry."""

    label = TECHNOLOGY

    def margin(self, economy: Economy, plan: Plan, unit: int) -> np.ndarray:
        """What the unit's planned inputs and effort deliver, minus its planned output.

        Raises ``ValueError`` when the plan records no effort, when the economy carries no
        effort exponent, or when the unit has more than one output entry.
        """
        outputs = slice(int(economy.output_offsets[unit]), int(economy.output_offsets[unit + 1]))
        _require_one_output(unit, outputs)
        effort = _effort_of(plan)[unit]
        effort_exponent = _effort_exponent_of(economy)[unit]
        inputs = economy.inputs_of(unit)
        bundle = np.prod(plan.input_use[inputs] ** economy.input_coefficient[inputs])
        deliverable = economy.technology_scale[unit] * effort**effort_exponent * bundle
        return np.array([deliverable], dtype=np.float64) - plan.output[outputs]


def technology() -> _EffortCobbDouglas:
    """The Hahnel production function, labelled :data:`TECHNOLOGY`."""
    return _EffortCobbDouglas()


def _require_one_output(unit: int, outputs: slice) -> None:
    """Refuse a unit with more than one output entry, naming it."""
    entries = outputs.stop - outputs.start
    if entries != 1:
        raise ValueError(
            f"unit {unit} has {entries} output entries, and the Hahnel production function "
            f"{TECHNOLOGY!r} has one output per unit"
        )


def _effort_of(plan: Plan) -> np.ndarray:
    """The plan's effort per unit. Raises ``ValueError`` in plain words when it is absent."""
    effort = plan.extra.get(EFFORT)
    if effort is None:
        raise ValueError(
            f"the Hahnel production function needs plan.extra[{EFFORT!r}], which this plan "
            "does not carry. It is the effort each producing unit chose, one number per unit, "
            "and the factor e**c in Q = a * e**c * prod(x_j ** b_j). The Hahnel councils write "
            f"it on every plan they make; a plan made another way has to pass "
            f"extra={{{EFFORT!r}: ...}} with one effort per producing unit."
        )
    return effort


def _effort_exponent_of(economy: Economy) -> np.ndarray:
    """The economy's effort exponent per unit. Raises ``ValueError`` when it is absent."""
    exponent = economy.unit_extra.get(_EFFORT_EXPONENT_KEY)
    if exponent is None:
        raise ValueError(
            f"the Hahnel production function needs unit_extra[{_EFFORT_EXPONENT_KEY!r}], which "
            "this economy does not carry. It is each producing unit's effort exponent, the c "
            "in Q = a * e**c * prod(x_j ** b_j). demplan.load_dep1ex writes it; for an economy "
            f"built by hand, pass unit_extra={{{_EFFORT_EXPONENT_KEY!r}: ...}} with one exponent "
            "per producing unit."
        )
    return exponent
