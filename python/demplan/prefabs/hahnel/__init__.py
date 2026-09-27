"""The Hahnel participatory-planning prefab.

:mod:`~demplan.prefabs.hahnel.councils` is the half that does not depend on a source: the
councils, the facilitation board, the price-rule seam, its plan keys, and the relative
imbalance rebuilt from a plan.
:mod:`~demplan.prefabs.hahnel.book_2021` is the price rule and the procedure behind the
published tables of Hahnel (2021), and the pieces of its two-year experiments.
:mod:`~demplan.prefabs.hahnel.labels` is the technology label and the five commodity class
labels the prefab reads off an economy, and the helpers that turn the class labels into the
commodity indices the library's objectives and accessors take.
"""

from __future__ import annotations

from demplan.prefabs.hahnel.book_2021 import (
    Book2021Rule,
    HahnelBook2021,
    WarmStart,
    book_2021_rule,
    increasing_returns,
    perturb_exponents,
    real_gdp_growth,
)
from demplan.prefabs.hahnel.councils import (
    NEXT_INDICATIVE_PRICE,
    PRICE_RULE_STATE,
    CouncilModel,
    PriceRule,
    StatelessPriceRule,
    relative_imbalance,
    stateless,
)
from demplan.prefabs.hahnel.labels import (
    INTERMEDIATE,
    LABOR,
    NATURAL_RESOURCE,
    PRIVATE_GOOD,
    PUBLIC_GOOD,
    TECHNOLOGY,
    intermediate_goods,
    labor,
    natural_resources,
    private_goods,
    shared_goods,
)
from demplan.prefabs.hahnel.production import technology

__all__ = [
    "Book2021Rule",
    "CouncilModel",
    "HahnelBook2021",
    "INTERMEDIATE",
    "LABOR",
    "NATURAL_RESOURCE",
    "NEXT_INDICATIVE_PRICE",
    "PRICE_RULE_STATE",
    "PRIVATE_GOOD",
    "PUBLIC_GOOD",
    "PriceRule",
    "StatelessPriceRule",
    "TECHNOLOGY",
    "WarmStart",
    "book_2021_rule",
    "increasing_returns",
    "intermediate_goods",
    "labor",
    "natural_resources",
    "perturb_exponents",
    "private_goods",
    "real_gdp_growth",
    "relative_imbalance",
    "shared_goods",
    "stateless",
    "technology",
]
