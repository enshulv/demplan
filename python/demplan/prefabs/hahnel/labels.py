"""The labels the Hahnel prefab reads off an economy, and the index arrays they translate into.

The Hahnel model sorts commodities into five classes, and its production function carries an
effort factor that plain Cobb-Douglas does not. Neither is part of the data model: the class
of each commodity is a text label in ``commodity_extra["hahnel_kind"]``, and the technology is
the label :data:`TECHNOLOGY` in ``technology_kind``. The dep1ex loader writes both.

The library's own tools take commodity indices rather than labels, so the five helpers here
turn the label column into the sorted index arrays those tools take: ``counted`` and ``shared``
on the objectives, ``resources`` on :meth:`demplan.Plan.endowment_use`.
"""

from __future__ import annotations

import numpy as np

from demplan.economy import Economy

TECHNOLOGY = "hahnel_cobb_douglas_effort"
"""The technology label of the Hahnel model: ``Q = a * e**c * prod(x_j ** b_j)``.

``a`` is ``technology_scale``, ``b_j`` the unit's ``input_coefficient``, ``e`` the effort the
worker council chooses and ``c`` its ``unit_extra["effort_c"]``.
"""

KIND_KEY = "hahnel_kind"
"""The ``commodity_extra`` key holding each commodity's class label."""

PRIVATE_GOOD = "private_good"
"""Class label: a good each consumer unit consumes on its own."""

PUBLIC_GOOD = "public_good"
"""Class label: a good the consumer units use in common, stated once for the whole society."""

INTERMEDIATE = "intermediate"
"""Class label: a good produced within the period and used as an input."""

NATURAL_RESOURCE = "natural_resource"
"""Class label: a resource drawn from the endowment rather than produced."""

LABOR = "labor"
"""Class label: a kind of labour, drawn from the endowment rather than produced."""

KIND_LABELS = (PRIVATE_GOOD, PUBLIC_GOOD, INTERMEDIATE, NATURAL_RESOURCE, LABOR)
"""The five class labels, in the order the dep1ex loader lays the sections out."""

_KIND_MEANINGS = (
    (PRIVATE_GOOD, "a good each consumer unit consumes on its own"),
    (PUBLIC_GOOD, "a good the consumer units use in common"),
    (INTERMEDIATE, "a good produced and used as an input"),
    (NATURAL_RESOURCE, "a resource drawn from the endowment"),
    (LABOR, "a kind of labour drawn from the endowment"),
)


def _what_the_labels_are() -> str:
    """The five labels and what each means, for the messages below."""
    return "; ".join(f"{label!r} for {meaning}" for label, meaning in _KIND_MEANINGS)


def kind_labels(economy: Economy, reader: str) -> np.ndarray:
    """The ``hahnel_kind`` column of ``economy``, checked. Raises ``ValueError``.

    ``reader`` names what needs the column, for the message. The column has to be there, hold
    text, and hold only the five labels: a misspelt label would drop its commodity out of
    every class without a word.
    """
    labels = economy.commodity_extra.get(KIND_KEY)
    if labels is None:
        raise ValueError(
            f"{reader} needs commodity_extra[{KIND_KEY!r}], which this economy does not carry. "
            "It is a text label per commodity naming which of the Hahnel model's five classes "
            f"the commodity belongs to: {_what_the_labels_are()}. demplan.load_dep1ex writes "
            f"it; for an economy built by hand, pass commodity_extra={{{KIND_KEY!r}: [...]}} "
            "with one of those labels per commodity."
        )
    if labels.dtype.kind != "U":
        raise ValueError(
            f"{reader} needs commodity_extra[{KIND_KEY!r}] to hold text labels, one per "
            f"commodity, and it holds dtype {labels.dtype}. The labels are "
            f"{_what_the_labels_are()}."
        )
    unknown = np.flatnonzero(~np.isin(labels, KIND_LABELS))
    if unknown.size:
        at = int(unknown[0])
        raise ValueError(
            f"{reader} reads commodity_extra[{KIND_KEY!r}], which holds {str(labels[at])!r} for "
            f"commodity {at}. That is not one of the five labels: {_what_the_labels_are()}."
        )
    return labels


def _commodities_labelled(economy: Economy, label: str, reader: str) -> np.ndarray:
    """Sorted int64 indices of the commodities carrying ``label``."""
    return np.flatnonzero(kind_labels(economy, reader) == label).astype(np.int64)


def private_goods(economy: Economy) -> np.ndarray:
    """Indices of the commodities labelled :data:`PRIVATE_GOOD`, ascending."""
    return _commodities_labelled(economy, PRIVATE_GOOD, "private_goods")


def shared_goods(economy: Economy) -> np.ndarray:
    """Indices of the commodities labelled :data:`PUBLIC_GOOD`, ascending.

    The name is the library's: the commodities the consumer units use in common, which is what
    the ``shared`` declaration of the objectives and ``Plan.shared_use`` are about.
    """
    return _commodities_labelled(economy, PUBLIC_GOOD, "shared_goods")


def intermediate_goods(economy: Economy) -> np.ndarray:
    """Indices of the commodities labelled :data:`INTERMEDIATE`, ascending."""
    return _commodities_labelled(economy, INTERMEDIATE, "intermediate_goods")


def natural_resources(economy: Economy) -> np.ndarray:
    """Indices of the commodities labelled :data:`NATURAL_RESOURCE`, ascending."""
    return _commodities_labelled(economy, NATURAL_RESOURCE, "natural_resources")


def labor(economy: Economy) -> np.ndarray:
    """Indices of the commodities labelled :data:`LABOR`, ascending."""
    return _commodities_labelled(economy, LABOR, "labor")


def resources(economy: Economy) -> np.ndarray:
    """Indices of the natural resources and the kinds of labour, ascending.

    The commodities whose input use draws on the endowment rather than on production within
    the period: the ``resources`` declaration :meth:`demplan.Plan.endowment_use` and
    :func:`demplan.period_differences` take.
    """
    return np.union1d(natural_resources(economy), labor(economy)).astype(np.int64)


def bads(economy: Economy) -> np.ndarray:
    """The commodities the model counts as bads: none, as an empty int64 array.

    The source model has no commodity with negative value. The economy is taken so that the
    call reads like the other declaration helpers.
    """
    return np.zeros(0, dtype=np.int64)
