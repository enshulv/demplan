"""A hand-built economy small enough to run without the dep1ex archives.

One source table drives two builders: :func:`build_economy` produces the ``Economy`` the
library works on, :func:`build_reference_inputs` produces the ``wc``/``cc`` dicts that the
numpy reference in ``research/bench/endowment.py`` expects. The two builders share the input
numbers only; every expected value in the tests comes from running the reference, never from
the table.

Three commodities per class keeps the reference usable: ``endowment.proposals`` indexes all
three of its output price vectors with the same ``product`` column, so the private, public and
intermediate sections have to be equally long.

``unit_group`` is deliberately not equal to ``output_commodity`` here. On dep1ex the two
coincide, so an implementation that aggregates supply by the wrong column still passes on the
real data; this economy separates them.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from demplan import CommodityKind, Economy, TechnologyKind

N_PER_CLASS = 3
N_CONSUMERS = 4

PRIV_BASE = 0
PUB_BASE = 3
INTER_BASE = 6
NATURE_BASE = 9
LABOR_BASE = 12
N_COMMODITIES = 15

ENDOWMENT = 5.0
"""Per-commodity endowment of every natural resource and every kind of labor."""

ENTITLEMENT = 10000.0
"""Consumption entitlement of every consumer unit."""

# (output commodity, unit group, [(input commodity, Cobb-Douglas exponent), ...])
UNITS = (
    (0, 0, ((6, 0.16), (7, 0.15), (9, 0.14), (12, 0.16), (13, 0.15))),
    (1, 0, ((6, 0.17), (10, 0.15), (12, 0.16), (14, 0.14))),
    (2, 0, ((7, 0.15), (9, 0.16), (11, 0.14), (13, 0.17))),
    (3, 1, ((6, 0.15), (8, 0.16), (9, 0.15), (12, 0.16))),
    (4, 1, ((7, 0.18), (10, 0.16), (13, 0.17))),
    (5, 1, ((8, 0.16), (11, 0.15), (14, 0.16), (12, 0.13))),
    (6, 2, ((9, 0.15), (10, 0.14), (12, 0.16), (13, 0.15))),
    (7, 2, ((10, 0.17), (13, 0.16), (14, 0.15))),
    (8, 2, ((11, 0.16), (9, 0.13), (14, 0.17), (12, 0.14))),
)

TECHNOLOGY_SCALE = (5.0, 4.6, 5.4, 4.8, 5.2, 5.0, 4.9, 5.1, 4.7)
EFFORT_C = (0.08, 0.07, 0.09, 0.075, 0.085, 0.08, 0.078, 0.082, 0.072)
EFFORT_S = (1.0, 1.5, 2.0, 1.0, 1.5, 2.0, 1.0, 1.5, 2.0)
"""Effort scale of each unit. The values differ so that the ``c * log(effort_s)`` term of the
worker-council closed form is exercised; at a uniform 1.0 the term is identically zero."""
EFFORT_K = (3.3, 3.1, 3.5, 3.2, 3.4, 3.3, 3.25, 3.35, 3.15)

# Cobb-Douglas utility exponents, three private goods then three public goods per consumer.
UTILITY_EXPONENT = (
    (0.20, 0.15, 0.10, 0.25, 0.30, 0.12),
    (0.12, 0.22, 0.14, 0.28, 0.24, 0.15),
    (0.18, 0.11, 0.19, 0.22, 0.30, 0.11),
    (0.14, 0.17, 0.13, 0.31, 0.25, 0.13),
)
CONSUMER_GROUP = (0, 0, 1, 1)


def build_economy() -> Economy:
    """The synthetic economy as the library sees it."""
    kind = np.empty(N_COMMODITIES, dtype=np.int8)
    kind[PRIV_BASE:PUB_BASE] = CommodityKind.PRIVATE_GOOD
    kind[PUB_BASE:INTER_BASE] = CommodityKind.PUBLIC_GOOD
    kind[INTER_BASE:NATURE_BASE] = CommodityKind.INTERMEDIATE
    kind[NATURE_BASE:LABOR_BASE] = CommodityKind.NATURAL_RESOURCE
    kind[LABOR_BASE:N_COMMODITIES] = CommodityKind.LABOR

    endowment = np.zeros(N_COMMODITIES, dtype=np.float64)
    endowment[NATURE_BASE:N_COMMODITIES] = ENDOWMENT

    counts = [len(inputs) for _, _, inputs in UNITS]
    offsets = np.zeros(len(UNITS) + 1, dtype=np.int64)
    np.cumsum(counts, out=offsets[1:])
    input_commodity = np.array(
        [commodity for _, _, inputs in UNITS for commodity, _ in inputs], dtype=np.int64
    )
    input_coefficient = np.array(
        [coefficient for _, _, inputs in UNITS for _, coefficient in inputs], dtype=np.float64
    )

    return Economy(
        period=0,
        commodity_id=np.arange(N_COMMODITIES, dtype=np.int64),
        commodity_kind=kind,
        endowment=endowment,
        unit_id=np.arange(len(UNITS), dtype=np.int64),
        unit_group=np.array([group for _, group, _ in UNITS], dtype=np.int64),
        output_commodity=np.array([output for output, _, _ in UNITS], dtype=np.int64),
        technology_kind=np.full(len(UNITS), TechnologyKind.COBB_DOUGLAS, dtype=np.int8),
        technology_scale=np.array(TECHNOLOGY_SCALE, dtype=np.float64),
        input_offsets=offsets,
        input_commodity=input_commodity,
        input_coefficient=input_coefficient,
        consumer_id=np.arange(N_CONSUMERS, dtype=np.int64),
        consumer_group=np.array(CONSUMER_GROUP, dtype=np.int64),
        unit_extra={
            "effort_c": np.array(EFFORT_C, dtype=np.float64),
            "effort_s": np.array(EFFORT_S, dtype=np.float64),
            "effort_k": np.array(EFFORT_K, dtype=np.float64),
        },
        consumer_extra={
            "entitlement": np.full(N_CONSUMERS, ENTITLEMENT, dtype=np.float64),
            "utility_exponent": np.array(UTILITY_EXPONENT, dtype=np.float64),
            "utility_exponent_commodity": np.arange(2 * N_PER_CLASS, dtype=np.int64),
        },
    )


NEW_COMMODITY_OF_OLD = np.array(
    [1, 3, 5, 0, 2, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14], dtype=np.int64
)
"""Commodity renumbering used by :func:`build_permuted_economy`.

It interleaves the public goods with the private ones at the low identifiers, so that neither
the private commodities nor the private utility-exponent columns come first.
"""


def build_permuted_economy() -> Economy:
    """:func:`build_economy` with the commodities renumbered.

    Same economy, different identifiers. On dep1ex, and on :func:`build_economy`, the private
    goods hold the lowest commodity identifiers and the first utility-exponent columns, so
    code that picks the private goods by position rather than by ``commodity_kind`` passes
    there. Here it does not.
    """
    base = build_economy()
    new_of_old = NEW_COMMODITY_OF_OLD
    order = np.argsort(new_of_old[np.arange(2 * N_PER_CLASS)])

    kind = np.empty(N_COMMODITIES, dtype=np.int8)
    kind[new_of_old] = np.asarray(base.commodity_kind)
    endowment = np.empty(N_COMMODITIES, dtype=np.float64)
    endowment[new_of_old] = np.asarray(base.endowment)

    exponents = np.asarray(base.consumer_extra["utility_exponent"])[:, order]
    return dataclasses.replace(
        base,
        commodity_kind=kind,
        endowment=endowment,
        output_commodity=new_of_old[np.asarray(base.output_commodity)],
        input_commodity=new_of_old[np.asarray(base.input_commodity)],
        consumer_extra={
            "entitlement": np.asarray(base.consumer_extra["entitlement"]),
            "utility_exponent": exponents,
            "utility_exponent_commodity": new_of_old[
                np.asarray(base.consumer_extra["utility_exponent_commodity"])[order]
            ],
        },
    )


_INDUSTRY_OF_SECTION = {PRIV_BASE: 0, INTER_BASE: 1, PUB_BASE: 2}
_CAT_OF_SECTION = {INTER_BASE: 0, NATURE_BASE: 1, LABOR_BASE: 2}


def _section_base(commodity: int) -> int:
    for base in (LABOR_BASE, NATURE_BASE, INTER_BASE, PUB_BASE, PRIV_BASE):
        if commodity >= base:
            return base
    raise ValueError(f"commodity {commodity} is below the first section base")


def build_reference_inputs() -> tuple[dict, dict, tuple[int, int, int], float]:
    """The same economy in the shape ``endowment.run`` expects: ``(wc, cc, dims, S)``."""
    width = max(len(inputs) for _, _, inputs in UNITS)
    n_units = len(UNITS)
    coef = np.zeros((n_units, width), dtype=np.int64)
    b = np.zeros((n_units, width), dtype=np.float64)
    cat = np.full((n_units, width), -1, dtype=np.int8)
    industry = np.empty(n_units, dtype=np.int64)
    product = np.empty(n_units, dtype=np.int64)

    for row, (output, _, inputs) in enumerate(UNITS):
        out_base = _section_base(output)
        industry[row] = _INDUSTRY_OF_SECTION[out_base]
        product[row] = output - out_base
        for column, (commodity, coefficient) in enumerate(inputs):
            in_base = _section_base(commodity)
            cat[row, column] = _CAT_OF_SECTION[in_base]
            coef[row, column] = commodity - in_base
            b[row, column] = coefficient

    wc = {
        "a": np.array(TECHNOLOGY_SCALE, dtype=np.float64),
        "c": np.array(EFFORT_C, dtype=np.float64),
        "s": np.array(EFFORT_S, dtype=np.float64),
        "k": np.array(EFFORT_K, dtype=np.float64),
        "industry": industry,
        "product": product,
        "coef": coef,
        "b": b,
        "cat": cat,
        "mask": cat >= 0,
    }
    exponents = np.array(UTILITY_EXPONENT, dtype=np.float64)
    cc = {
        "priv_exp": exponents[:, :N_PER_CLASS].copy(),
        "pub_exp": exponents[:, N_PER_CLASS:].copy(),
        "income": np.full(N_CONSUMERS, ENTITLEMENT, dtype=np.float64),
    }
    return wc, cc, (N_PER_CLASS, N_PER_CLASS, N_PER_CLASS), ENDOWMENT


THIRD_KIND_COMMODITY = INTER_BASE
"""Commodity that :func:`build_economy_with_a_third_kind_column` puts a utility exponent on.

An intermediate good, so it is neither a private good nor a public good. Other producing units
already take it as an input, which is what makes the consumer councils' share of its demand
visible next to a producer's share.
"""

THIRD_KIND_COLUMN = 1
"""Where that exponent sits among the utility-exponent columns.

Between two private-good columns, so that neither the private-good columns nor the rest form a
contiguous run. Code that splits the columns by position rather than by ``commodity_kind``
fails here.
"""

THIRD_KIND_EXPONENT = (0.16, 0.13, 0.17, 0.14)
"""Cobb-Douglas utility exponent each consumer unit places on :data:`THIRD_KIND_COMMODITY`."""


def build_economy_with_a_third_kind_column() -> Economy:
    """:func:`build_economy` with one more utility-exponent column, on an intermediate good.

    A utility-exponent column names a commodity of any kind, and the commodity table has five.
    This economy holds three of them at once: private-good columns, public-good columns, and
    one column whose commodity is neither. That third column is priced like a private-good
    column and reported like neither, so code that reads the columns as two cases drops it.
    """
    base = build_economy()
    exponent = np.insert(
        np.asarray(base.consumer_extra["utility_exponent"]),
        THIRD_KIND_COLUMN,
        np.array(THIRD_KIND_EXPONENT, dtype=np.float64),
        axis=1,
    )
    commodity = np.insert(
        np.asarray(base.consumer_extra["utility_exponent_commodity"]),
        THIRD_KIND_COLUMN,
        THIRD_KIND_COMMODITY,
    ).astype(np.int64)
    return dataclasses.replace(
        base,
        consumer_extra={
            "entitlement": np.asarray(base.consumer_extra["entitlement"]),
            "utility_exponent": exponent,
            "utility_exponent_commodity": commodity,
        },
    )


UNORDERED_COLUMN_COMMODITY = np.array([4, 2, 0, 5, 1, 3], dtype=np.int64)
"""Commodity each utility-exponent column names in
:func:`build_economy_with_unordered_private_columns`.

The private-good columns sit at positions 1, 2 and 4 and name commodities 2, 0 and 1 in that
order. The plan's ``consumption_commodity`` is therefore neither ascending nor equal to
``commodities_of_kind(PRIVATE_GOOD)``, so code that sorts the labels without reordering the
consumption block alongside them pairs every column with the wrong commodity.
"""

UNEVEN_ENTITLEMENT = (9000.0, 10500.0, 11750.0, 8250.0)
"""Consumption entitlement of each consumer unit in
:func:`build_economy_with_unordered_private_columns`.

The values differ from one unit to the next, and their mean is not one of them. Every other
economy here gives every unit the same entitlement, so a stated bundle built from the mean
entitlement instead of each unit's own comes out identical there.
"""


def build_economy_with_unordered_private_columns() -> Economy:
    """:func:`build_economy` with the utility-exponent columns permuted and uneven entitlements.

    Two assumptions hold in every other economy here and hold in dep1ex as well: the private
    utility-exponent columns name their commodities in ascending order, and every consumer unit
    is entitled to the same amount. Both are properties of the inputs rather than of the
    mechanism, and code that leans on either passes everywhere else.

    The commodities, the producing units and the utility exponent each unit places on each
    commodity are the ones :func:`build_economy` sets. Only the column order and the
    entitlements differ, so this economy states the same preferences as that one.
    """
    base = build_economy()
    columns = UNORDERED_COLUMN_COMMODITY
    exponent = np.asarray(base.consumer_extra["utility_exponent"])[:, columns]
    return dataclasses.replace(
        base,
        consumer_extra={
            "entitlement": np.array(UNEVEN_ENTITLEMENT, dtype=np.float64),
            "utility_exponent": exponent,
            "utility_exponent_commodity": columns.copy(),
        },
    )
