"""Where the column-mapping key is exempt from the row-count rule.

``utility_exponent_commodity`` maps the columns of ``consumer_extra["utility_exponent"]`` to
commodities, so in ``consumer_extra`` it is as long as there are exponent columns, not as long as
there are consumer units. It is registered for that bag alone: under the same name in
``commodity_extra`` or ``unit_extra`` an array is an ordinary extra array, one row per row of its
table.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from demplan import SchemaError

KEY = "utility_exponent_commodity"


def with_extra(economy, bag: str, value: np.ndarray):
    return dataclasses.replace(economy, **{bag: {**dict(getattr(economy, bag)), KEY: value}})


def test_the_key_is_exempt_in_the_consumer_table(synthetic_economy):
    columns = synthetic_economy.consumer_extra["utility_exponent"].shape[1]
    assert columns != synthetic_economy.n_consumers
    assert synthetic_economy.consumer_extra[KEY].shape == (columns,)


def test_the_key_follows_the_row_count_in_the_commodity_table(synthetic_economy):
    wrong = np.zeros(synthetic_economy.n_commodities + 3, dtype=np.int64)
    with pytest.raises(SchemaError, match=r"commodity_extra\['utility_exponent_commodity'\]"):
        with_extra(synthetic_economy, "commodity_extra", wrong)


def test_the_key_follows_the_row_count_in_the_unit_table(synthetic_economy):
    wrong = np.zeros(synthetic_economy.n_units + 3, dtype=np.int64)
    with pytest.raises(SchemaError, match=r"unit_extra\['utility_exponent_commodity'\]"):
        with_extra(synthetic_economy, "unit_extra", wrong)


def test_one_row_per_commodity_under_the_key_is_accepted_in_the_commodity_table(
    synthetic_economy,
):
    rows = np.arange(synthetic_economy.n_commodities, dtype=np.int64)
    economy = with_extra(synthetic_economy, "commodity_extra", rows)
    np.testing.assert_array_equal(economy.commodity_extra[KEY], rows)
