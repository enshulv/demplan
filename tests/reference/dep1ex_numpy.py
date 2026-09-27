"""Turn the numpy reference parse of a dep1ex archive into an :class:`Economy`.

``repro.parse`` returns two dicts of padded matrices that keep the five commodity classes in
separate numbering spaces. ``Economy`` uses one commodity table, so every class gets a
contiguous section of commodity ids in the order private good, public good, intermediate,
natural resource, labor. :class:`Dep1exLayout` records the section base addresses, which the
differential tests need to slice a unified price vector back into the reference's five
per-class vectors.

The economy carries the labels the dep1ex loader writes, spelled out here as literals rather
than taken from the library: ``commodity_extra["hahnel_kind"]`` names each commodity's section,
and every unit's ``technology_kind`` is ``"hahnel_cobb_douglas_effort"``. Both are handed to
:class:`Economy` as Python lists of ``str``, the form the Rust binding hands them over in.
"""

from __future__ import annotations

import dataclasses

import numpy as np

from demplan import Economy

from .paths import import_reference

# Input class markers used by ``repro.parse`` in its ``cat`` matrix.
_CAT_INTERMEDIATE = 0
_CAT_NATURAL = 1
_CAT_LABOR = 2

# ``repro.parse`` encodes the class of a producing unit's output in its ``industry`` column.
_INDUSTRY_PRIVATE = 0
_INDUSTRY_INTERMEDIATE = 1
_INDUSTRY_PUBLIC = 2

KIND_KEY = "hahnel_kind"

SECTION_LABELS = {
    "priv": "private_good",
    "pub": "public_good",
    "inter": "intermediate",
    "nature": "natural_resource",
    "labor": "labor",
}
"""The ``hahnel_kind`` label the dep1ex loader writes on each of ``repro``'s five sections."""

TECHNOLOGY_LABEL = "hahnel_cobb_douglas_effort"
"""The ``technology_kind`` the dep1ex loader writes on every producing unit."""


@dataclasses.dataclass(frozen=True)
class Dep1exLayout:
    """Sizes and commodity-id base addresses of the five sections."""

    n_priv: int
    n_pub: int
    n_goods: int

    @property
    def priv_base(self) -> int:
        return 0

    @property
    def pub_base(self) -> int:
        return self.n_priv

    @property
    def inter_base(self) -> int:
        return self.n_priv + self.n_pub

    @property
    def nature_base(self) -> int:
        return self.inter_base + self.n_goods

    @property
    def labor_base(self) -> int:
        return self.inter_base + 2 * self.n_goods

    @property
    def n_commodities(self) -> int:
        return self.inter_base + 3 * self.n_goods

    def section(self, name: str) -> slice:
        """Slice of commodity ids covered by one section of ``repro``'s five."""
        base, size = {
            "priv": (self.priv_base, self.n_priv),
            "pub": (self.pub_base, self.n_pub),
            "inter": (self.inter_base, self.n_goods),
            "nature": (self.nature_base, self.n_goods),
            "labor": (self.labor_base, self.n_goods),
        }[name]
        return slice(base, base + size)


def parse_dep1ex(path) -> tuple[dict, dict, Dep1exLayout]:
    """Parse one dep1ex archive with the numpy reference and derive its layout."""
    repro, _ = import_reference()
    wc, cc = repro.parse(str(path))
    layout = Dep1exLayout(
        n_priv=int(cc["priv_exp"].shape[1]),
        n_pub=int(cc["pub_exp"].shape[1]),
        n_goods=int(wc["coef"].max()) + 1,
    )
    return wc, cc, layout


def reference_dims(layout: Dep1exLayout) -> tuple[int, int, int]:
    """The ``dims`` triple that ``endowment.run`` expects."""
    return (layout.n_priv, layout.n_pub, layout.n_goods)


def _commodity_table(layout: Dep1exLayout, endowment: float):
    kind = [""] * layout.n_commodities
    for name, label in SECTION_LABELS.items():
        section = layout.section(name)
        kind[section] = [label] * (section.stop - section.start)

    supply = np.zeros(layout.n_commodities, dtype=np.float64)
    supply[layout.section("nature")] = endowment
    supply[layout.section("labor")] = endowment
    return kind, supply


def _output_commodity(wc: dict, layout: Dep1exLayout) -> np.ndarray:
    industry, product = wc["industry"], wc["product"]
    base = np.select(
        [industry == _INDUSTRY_PRIVATE, industry == _INDUSTRY_INTERMEDIATE, industry == _INDUSTRY_PUBLIC],
        [layout.priv_base, layout.inter_base, layout.pub_base],
        default=-1,
    )
    if (base < 0).any():
        raise ValueError("dep1ex carries an industry marker outside {0, 1, 2}")
    return (base + product).astype(np.int64)


def _flat_inputs(wc: dict, layout: Dep1exLayout):
    mask = wc["mask"]
    cat_flat = wc["cat"][mask]
    coef_flat = wc["coef"][mask]
    base = np.select(
        [cat_flat == _CAT_INTERMEDIATE, cat_flat == _CAT_NATURAL, cat_flat == _CAT_LABOR],
        [layout.inter_base, layout.nature_base, layout.labor_base],
        default=-1,
    )
    if (base < 0).any():
        raise ValueError("dep1ex carries an input class marker outside {0, 1, 2}")
    input_commodity = (base + coef_flat).astype(np.int64)
    input_coefficient = wc["b"][mask].astype(np.float64)

    offsets = np.zeros(mask.shape[0] + 1, dtype=np.int64)
    np.cumsum(mask.sum(axis=1), out=offsets[1:])
    return offsets, input_commodity, input_coefficient


def economy_from_repro(wc: dict, cc: dict, layout: Dep1exLayout, endowment: float = 1000.0) -> Economy:
    """Build the :class:`Economy` that the numpy reference is implicitly solving."""
    kind, supply = _commodity_table(layout, endowment)
    output_commodity = _output_commodity(wc, layout)
    offsets, input_commodity, input_coefficient = _flat_inputs(wc, layout)

    n_units = output_commodity.shape[0]
    n_consumers = cc["income"].shape[0]
    utility_exponent = np.hstack([cc["priv_exp"], cc["pub_exp"]]).astype(np.float64)
    utility_exponent_commodity = np.concatenate(
        [layout.priv_base + np.arange(layout.n_priv), layout.pub_base + np.arange(layout.n_pub)]
    ).astype(np.int64)

    return Economy(
        period=0,
        commodity_id=np.arange(layout.n_commodities, dtype=np.int64),
        endowment=supply,
        commodity_extra={KIND_KEY: kind},
        unit_id=np.arange(n_units, dtype=np.int64),
        technology_kind=[TECHNOLOGY_LABEL] * n_units,
        technology_scale=wc["a"].astype(np.float64),
        input_offsets=offsets,
        input_commodity=input_commodity,
        input_coefficient=input_coefficient,
        output_offsets=np.arange(n_units + 1, dtype=np.int64),
        output_commodity=output_commodity,
        output_coefficient=np.ones(n_units, dtype=np.float64),
        consumer_id=np.arange(n_consumers, dtype=np.int64),
        unit_extra={
            "effort_c": wc["c"].astype(np.float64),
            "effort_s": wc["s"].astype(np.float64),
            "effort_k": wc["k"].astype(np.float64),
        },
        consumer_extra={
            "entitlement": cc["income"].astype(np.float64),
            "utility_exponent": utility_exponent,
            "utility_exponent_commodity": utility_exponent_commodity,
        },
    )


def unified_price(reference_prices: dict, layout: Dep1exLayout) -> np.ndarray:
    """Concatenate the reference's five per-class price vectors into one commodity vector."""
    price = np.empty(layout.n_commodities, dtype=np.float64)
    for name in ("priv", "pub", "inter", "nature", "labor"):
        price[layout.section(name)] = reference_prices[name]
    return price


def _reference_precomp(wc: dict):
    """Rebuild the tuple ``endowment.run`` hands to ``endowment.proposals``."""
    b, mask = wc["b"], wc["mask"]
    b_sum = b.sum(axis=1)
    return (
        wc["a"], wc["c"], wc["s"], wc["k"], b, mask, wc["cat"], wc["coef"],
        wc["industry"], wc["product"], b_sum, wc["c"] - wc["k"] + wc["k"] * b_sum,
        np.where(mask, np.log(np.where(mask, b, 1.0)), 0.0),
    )


def reference_first_round(wc: dict, cc: dict, layout: Dep1exLayout, price: float = 700.0):
    """One round of the reference proposals at a flat price, as ``(output, input_use)``.

    ``input_use`` comes back flattened by the padding mask, in the same order as
    ``Economy.input_commodity``.
    """
    _, endowment = import_reference()
    per_class = {
        "priv": np.full(layout.n_priv, price),
        "pub": np.full(layout.n_pub, price),
        "inter": np.full(layout.n_goods, price),
        "nature": np.full(layout.n_goods, price),
        "labor": np.full(layout.n_goods, price),
    }
    tot_exp = cc["priv_exp"].sum(axis=1) + cc["pub_exp"].sum(axis=1)
    output, x, _, _ = endowment.proposals(
        wc, cc, per_class, cc["income"].shape[0], tot_exp, _reference_precomp(wc)
    )
    return output, x[wc["mask"]]


def reference_run(wc: dict, cc: dict, layout: Dep1exLayout, threshold: float = 5.0,
                  endowment_per_commodity: float = 1000.0):
    """``endowment.run`` under the pequod-cljs price rule: ``(rounds, prices, worst_percent)``.

    The mode is ``cljs_lagged``, the rule of ``csvgen.clj`` at ``71e44d3`` that
    :class:`demplan.prefabs.hahnel.Book2021Rule` implements. ``prices`` are the prices of the
    round that met the threshold, the ones its proposals were made at.
    """
    _, endowment = import_reference()
    return endowment.run(
        wc, cc, reference_dims(layout), endowment_per_commodity, "cljs_lagged", threshold
    )
