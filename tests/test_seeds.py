"""Seed derivation.

The expected words below are the published SplitMix64 output stream. Vandermeersch's
reference C implementation, seeded with state 0, emits e220a8397b1dcdaf, 6e789e6aa1b965f4,
06c45d188009454f; the same three words appear in every SplitMix64 port that carries test
vectors. The second block is the stream for state 0xdeadbeef, recomputed here from the same
published algorithm with Python big integers.
"""

from __future__ import annotations

import numpy as np
import pytest

from cyberstride import rng, split_seed

TWO_64 = 1 << 64

SPLITMIX64_FROM_ZERO = [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F]
SPLITMIX64_FROM_DEADBEEF = [0x4ADFB90F68C9EB9B, 0xDE586A3141A10922, 0x021FBC2F8E1CFC1D]


class TestKnownVectors:
    def test_stream_from_zero(self):
        assert split_seed(0, 3) == SPLITMIX64_FROM_ZERO

    def test_stream_from_deadbeef(self):
        assert split_seed(0xDEADBEEF, 3) == SPLITMIX64_FROM_DEADBEEF

    def test_first_word_from_zero_is_not_the_seed(self):
        assert split_seed(0, 1) != [0]


class TestStreamShape:
    def test_zero_children(self):
        assert split_seed(12345, 0) == []

    def test_length(self):
        assert len(split_seed(7, 16)) == 16

    def test_a_longer_stream_extends_a_shorter_one(self):
        assert split_seed(99, 8)[:3] == split_seed(99, 3)

    def test_words_are_unsigned_64_bit(self):
        for word in split_seed(0xFFFFFFFFFFFFFFFF, 32):
            assert isinstance(word, int)
            assert 0 <= word < TWO_64

    def test_distinct_seeds_give_distinct_streams(self):
        assert split_seed(0, 4) != split_seed(1, 4)

    def test_repeated_calls_agree(self):
        assert split_seed(0xABCDEF, 10) == split_seed(0xABCDEF, 10)


class TestRejectedArguments:
    @pytest.mark.parametrize("seed", [-1, -(1 << 70), TWO_64, TWO_64 + 1])
    def test_seed_outside_the_64_bit_range(self, seed):
        with pytest.raises(ValueError, match="seed"):
            split_seed(seed, 1)

    def test_negative_child_count(self):
        with pytest.raises(ValueError, match="n"):
            split_seed(0, -1)

    def test_the_largest_valid_seed_is_accepted(self):
        assert len(split_seed(TWO_64 - 1, 2)) == 2


class TestGenerator:
    def test_returns_a_numpy_generator(self):
        assert isinstance(rng(0), np.random.Generator)

    def test_matches_numpy_default_rng(self):
        np.testing.assert_array_equal(
            rng(4242).random(16), np.random.default_rng(4242).random(16)
        )

    def test_same_seed_same_draws(self):
        np.testing.assert_array_equal(rng(11).standard_normal(8), rng(11).standard_normal(8))

    def test_different_seeds_differ(self):
        assert not np.array_equal(rng(11).random(8), rng(12).random(8))

    def test_accepts_a_derived_sub_seed(self):
        child = split_seed(0, 1)[0]
        assert isinstance(rng(child), np.random.Generator)
