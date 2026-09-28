"""The price step of the Hahnel procedure under three readings, per commodity.

``v`` is a commodity's relative imbalance ``|2(s - d)| / (s + d)``; the step ``w`` moves the
price to ``p(1 - w)`` when supply exceeds demand and to ``p(1 + w)`` when it falls short.

  program   w_k = max(0.001, min(v_{k-1}, 0.25) * (1.05 - 0.5 ** v_k)),  v_{-1} = 0.25
            msszczep/pequod-cljs, csvgen.clj at 71e44d3, lines 164, 646-647, 718, 787-799,
            890-899 and 925
  book      w_k = min(v_k, 0.25) * (1.05 - 0.5 ** v_k)
            Hahnel (2021), p. 181: 0.25 substituted "for v where it first appears in the price
            adjustment formula, but not where it appears as an exponent"
  paper     w_k = min(v_k, 0.25) * (1.05 - 0.5 ** min(v_k, 0.25))
            Szczepanczyk (2023), p. 7, "except when v > 0.25 then v = 0.25", with the cap
            applied to both occurrences of v

The texts state no floor. ``step_book_floored`` and ``step_paper_floored`` add the program's
floor of 0.001 to the two text rules, as a check of how much the floor alone changes.

The same two text rules are written into pequod-cljs by the line edits in
``docker/pequod-cljs/edits``; a test evaluates their Clojure replacement lines against these
functions.
"""
from __future__ import annotations

import numpy as np

CAP = 0.25
FLOOR = 0.001
CEILING = 1.05
DECAY_BASE = 0.5
INITIAL_MULTIPLIER = 0.25
"""``v_{-1}``: the program starts every commodity's stored multiplier at 0.25 (line 164)."""
INITIAL_PRICE = 700.0
"""Every price starts at 700 (csvgen.clj at 71e44d3, lines 106-110)."""


def relative_imbalance(supply: np.ndarray, demand: np.ndarray) -> np.ndarray:
    """``|2(s - d)| / (s + d)`` elementwise."""
    return np.abs(2.0 * (supply - demand)) / (supply + demand)


def step_program(imbalance: np.ndarray, previous_multiplier: np.ndarray) -> np.ndarray:
    """The program's step: the previous round's capped imbalance times this round's base, floored."""
    base = CEILING - DECAY_BASE**imbalance
    return np.maximum(FLOOR, np.minimum(previous_multiplier, CAP) * base)


def step_book(imbalance: np.ndarray) -> np.ndarray:
    """The book's printed step: this round's imbalance, capped where it multiplies only."""
    return np.minimum(imbalance, CAP) * (CEILING - DECAY_BASE**imbalance)


def step_paper(imbalance: np.ndarray) -> np.ndarray:
    """The paper's printed step read literally: the cap applied to both occurrences."""
    capped = np.minimum(imbalance, CAP)
    return capped * (CEILING - DECAY_BASE**capped)


def step_book_floored(imbalance: np.ndarray) -> np.ndarray:
    """The book's printed step with the program's floor of 0.001 under it."""
    return np.maximum(FLOOR, step_book(imbalance))


def step_paper_floored(imbalance: np.ndarray) -> np.ndarray:
    """The paper's printed step, read literally, with the program's floor of 0.001 under it."""
    return np.maximum(FLOOR, step_paper(imbalance))


def next_price(price: np.ndarray, surplus: np.ndarray, step: np.ndarray) -> np.ndarray:
    """``p(1 - w)`` where the surplus is positive, ``p(1 + w)`` where negative, else ``p``."""
    factor = np.where(surplus > 0, 1.0 - step, np.where(surplus < 0, 1.0 + step, 1.0))
    return price * factor
