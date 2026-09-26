"""Seed derivation.

One run gets one seed. Everything inside it that needs randomness draws a sub-seed from
:func:`split_seed`, so the whole run is reproducible from that one number regardless of how
many components ask for randomness or in what order they are added.
"""

from __future__ import annotations

import numpy as np

_MASK_64 = (1 << 64) - 1
_TWO_64 = 1 << 64

# SplitMix64, as published by Steele, Lea and Flood and used as the seeding generator of the
# xoshiro family. Python integers are used rather than numpy words: numpy signals overflow on
# unsigned arithmetic, and the mixing steps here rely on wrapping.
_GOLDEN_GAMMA = 0x9E3779B97F4A7C15
_MIX_MULTIPLIER_1 = 0xBF58476D1CE4E5B9
_MIX_MULTIPLIER_2 = 0x94D049BB133111EB


def split_seed(seed: int, n: int) -> list[int]:
    """Derive ``n`` sub-seeds from ``seed`` with SplitMix64.

    The stream is a prefix chain: the first ``k`` words of ``split_seed(seed, n)`` are exactly
    ``split_seed(seed, k)``, so adding a component that needs a sub-seed does not renumber the
    ones already handed out.

    Raises ``ValueError`` when ``seed`` is outside ``[0, 2**64)`` or ``n`` is negative.
    """
    if not isinstance(seed, (int, np.integer)) or isinstance(seed, bool):
        raise ValueError(f"seed must be an integer, got {type(seed).__name__}")
    if not 0 <= int(seed) < _TWO_64:
        raise ValueError(f"seed must be in [0, 2**64), got {seed}")
    if n < 0:
        raise ValueError(f"n must not be negative, got {n}")

    state = int(seed)
    words = []
    for _ in range(n):
        state = (state + _GOLDEN_GAMMA) & _MASK_64
        word = state
        word = ((word ^ (word >> 30)) * _MIX_MULTIPLIER_1) & _MASK_64
        word = ((word ^ (word >> 27)) * _MIX_MULTIPLIER_2) & _MASK_64
        word ^= word >> 31
        words.append(word)
    return words


def rng(seed: int) -> np.random.Generator:
    """The library's random generator for one seed."""
    return np.random.default_rng(seed)
