"""The Hahnel participatory-planning prefab.

:mod:`~demplan.prefabs.hahnel.councils` is the half that does not depend on a source: the
councils, the facilitation board, the price-rule seam, its plan keys, and the relative
imbalance rebuilt from a plan.
:mod:`~demplan.prefabs.hahnel.book_2021` is the price rule and the procedure behind the
published tables of Hahnel (2021), and the pieces of its two-year experiments.
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

__all__ = [
    "Book2021Rule",
    "CouncilModel",
    "HahnelBook2021",
    "NEXT_INDICATIVE_PRICE",
    "PRICE_RULE_STATE",
    "PriceRule",
    "StatelessPriceRule",
    "WarmStart",
    "book_2021_rule",
    "increasing_returns",
    "perturb_exponents",
    "real_gdp_growth",
    "relative_imbalance",
    "stateless",
]
