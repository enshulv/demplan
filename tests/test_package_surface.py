"""What the top-level package exports, and in what order.

``__all__`` is the list a reader scans to find out what the library offers. In ASCII order the
position of a name is derivable, so a reader looking for one name reads a few entries instead
of the whole list, and two people adding an export land it in the same place.
"""

from __future__ import annotations

import cyberstride


class TestExportList:
    def test_every_exported_name_resolves_to_an_attribute(self):
        missing = [name for name in cyberstride.__all__ if not hasattr(cyberstride, name)]
        assert missing == []

    def test_the_list_is_in_ascii_order(self):
        assert list(cyberstride.__all__) == sorted(cyberstride.__all__)

    def test_no_name_is_listed_twice(self):
        duplicated = sorted(
            {name for name in cyberstride.__all__ if cyberstride.__all__.count(name) > 1}
        )
        assert duplicated == []


class TestPlanKeyConstants:
    """The convention keys a reader needs to take a plan apart carry a constant.

    ``valuation`` had all four of its keys exported; the two ``extra`` keys a plan's
    documentation names carry the same weight, because a reader who guesses either string
    wrong gets a ``KeyError`` rather than a wrong number.
    """

    def test_the_valuation_keys_are_exported(self):
        for name in ("INCOME", "INDICATIVE_PRICE", "LABOR_VALUE", "SHADOW_PRICE"):
            assert name in cyberstride.__all__

    def test_the_two_plan_extra_keys_are_exported(self):
        for name in ("CONSUMER_DEMAND", "EFFORT"):
            assert name in cyberstride.__all__

    def test_the_economy_extra_keys_are_not_exported(self):
        """They are a mechanism's input parameters, not vocabulary for reading a plan back."""
        for name in ("ENTITLEMENT", "EFFORT_C", "UTILITY_EXPONENT"):
            assert name not in cyberstride.__all__
