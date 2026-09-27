"""Runs the code blocks of README.md.

The blocks are read out of the file rather than restated here, so a README example that stops
working fails this file instead of quietly misleading a reader. Blocks are located by the
heading they sit under, which keeps the marker out of what the reader sees.

The block under "Write your own coordination method" opens on an ``economy`` that the reader
has from the block above it, which loads a dep1ex archive. The archives are not in the
repository, so this file supplies a Cobb-Douglas economy under that name instead; nothing else
about the block is changed.

The blocks that load ``dep1ex01.clj.gz`` run as written from the data directory, and the numbers
the README's prose quotes about them are checked against what they compute. Those tests read an
archive, so they are slow and skip without the data.
"""

from __future__ import annotations

import pathlib
import re

import numpy as np
import pytest

from demplan import technology_margins
from demplan.prefabs import hahnel
from reference import synthetic
from reference.paths import DATA_DIR, dep1ex_available

README = pathlib.Path(__file__).resolve().parents[1] / "README.md"

CODE_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)

HEADING_LINE = re.compile(r"^(#{1,6})\s")

FENCE_LINE = re.compile(r"^ {0,3}```")


def section_under(text: str, heading: str) -> str:
    """The lines under ``heading``, up to the next heading of the same or a higher level.

    A deeper heading stays inside the section, and a line opening with a ``#`` inside a fenced
    block is a comment rather than a heading, so fences are tracked while scanning.
    """
    parts = text.split(f"\n{heading}\n", 1)
    assert len(parts) == 2, f"heading {heading!r} is absent"
    level = len(heading) - len(heading.lstrip("#"))

    body = []
    fenced = False
    for line in parts[1].splitlines(keepends=True):
        if FENCE_LINE.match(line):
            fenced = not fenced
        elif not fenced:
            opened = HEADING_LINE.match(line)
            if opened is not None and len(opened.group(1)) <= level:
                break
        body.append(line)
    return "".join(body)


def code_block_in(text: str, heading: str, occurrence: int = 0) -> str:
    """The ``occurrence``-th python block of the section ``heading`` opens, verbatim.

    Blocks are taken from that section only. A section that carries no python block fails here
    instead of reaching for the next section's, which would test a block the reader is not
    looking at while the block under the heading goes unrun.
    """
    blocks = CODE_BLOCK.findall(section_under(text, heading))
    assert len(blocks) > occurrence, f"heading {heading!r} has {len(blocks)} python blocks"
    return blocks[occurrence]


def code_block_under(heading: str, occurrence: int = 0) -> str:
    """:func:`code_block_in` on README.md."""
    return code_block_in(README.read_text(encoding="utf-8"), heading, occurrence)


def test_the_hand_built_economy_runs():
    namespace: dict = {}
    exec(code_block_under("## `Economy`"), namespace)  # noqa: S102

    economy = namespace["economy"]
    assert economy.n_commodities == 7
    assert economy.n_units == 3
    assert economy.n_consumers == 2
    assert economy.n_inputs == 8


def test_the_price_rule_example_runs():
    namespace = {"economy": synthetic.build_economy()}
    # The first block under that heading is the one-line `solve` signature.
    exec(code_block_under("## Write your own coordination method", 1), namespace)  # noqa: S102

    assert callable(namespace["proportional_rule"])
    assert namespace["result"].summary.rounds is not None


def test_every_readme_python_block_parses():
    """A block nobody runs still has to be syntactically whole."""
    blocks = CODE_BLOCK.findall(README.read_text(encoding="utf-8"))
    assert blocks
    for block in blocks:
        compile(block, "README.md", "exec")


@pytest.mark.parametrize(
    "heading", ["## Ten lines", "## `Economy`", "## Write your own coordination method"]
)
def test_the_documented_headings_carry_a_python_block(heading):
    assert code_block_under(heading).strip()


SAMPLE_MARKDOWN = """# Title

## Prose only

A heading whose section holds no code at all.

## With a block

```python
value = 1
```

### A deeper heading

```python
value = 2
```

## After

```python
value = 3
```
"""

COMMENTED_MARKDOWN = """# Title

## Only section

```python
# a comment written at column zero
value = 4
```
"""


class TestSectionBoundary:
    """Which blocks a heading owns, on markdown written here rather than on README.md."""

    def test_a_section_without_a_block_fails_instead_of_taking_the_next_section(self):
        with pytest.raises(AssertionError, match="Prose only"):
            code_block_in(SAMPLE_MARKDOWN, "## Prose only")

    def test_a_section_returns_the_block_written_under_it(self):
        assert code_block_in(SAMPLE_MARKDOWN, "## With a block") == "value = 1\n"

    def test_a_deeper_heading_does_not_end_the_section(self):
        assert code_block_in(SAMPLE_MARKDOWN, "## With a block", 1) == "value = 2\n"

    def test_a_heading_of_the_same_level_ends_the_section(self):
        with pytest.raises(AssertionError, match="2 python blocks"):
            code_block_in(SAMPLE_MARKDOWN, "## With a block", 2)

    def test_a_comment_inside_a_block_is_not_read_as_a_heading(self):
        block = code_block_in(COMMENTED_MARKDOWN, "## Only section")
        assert block == "# a comment written at column zero\nvalue = 4\n"


COMPARISON = "## A first comparison between two mechanisms, and why it is not citable yet"

LEAVES_OVER = "## What the plan leaves over or short"

TEXT_BLOCK = re.compile(r"```text\n(.*?)```", re.DOTALL)


def run_on_dep1ex01(*headings: str) -> dict:
    """The first python block under each heading, run in turn in one namespace, from the data
    directory, so ``load_dep1ex("dep1ex01.clj.gz")`` reads the archive as the reader would."""
    if not dep1ex_available(1):
        pytest.skip(f"dep1ex01 archive not found in {DATA_DIR}")
    namespace: dict = {}
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(DATA_DIR)
        for heading in headings:
            exec(code_block_under(heading), namespace)  # noqa: S102
    return namespace


def prose_of(heading: str) -> str:
    """The section under ``heading`` with every run of whitespace made one space."""
    return " ".join(section_under(README.read_text(encoding="utf-8"), heading).split())


@pytest.fixture(scope="module")
def comparison_namespace():
    return run_on_dep1ex01(COMPARISON)


@pytest.fixture(scope="module")
def leaves_over_namespace():
    return run_on_dep1ex01("## Ten lines", LEAVES_OVER)


@pytest.mark.slow
class TestTheReferenceComparisonOnDep1ex01:
    """The recipe under the comparison heading gives the numbers its prose quotes."""

    def test_the_iterative_procedure_converges_in_12_rounds(self, comparison_namespace):
        assert comparison_namespace["result"].summary.rounds == 12
        assert comparison_namespace["result"].summary.converged is True
        assert "converges in 12 rounds" in prose_of(COMPARISON)

    def test_the_iterative_plan_spends_96539_3_units_of_labour(self, comparison_namespace):
        assert comparison_namespace["labor_spent"] == pytest.approx(96_539.3, abs=0.05)
        assert "96,539.3 units of labour" in prose_of(COMPARISON)

    def test_the_reference_solution_needs_53493_7(self, comparison_namespace):
        reference = comparison_namespace["reference"]
        assert reference.status == "optimal"
        assert reference.objective_value == pytest.approx(53_493.7, abs=0.05)
        assert "needs 53,493.7" in prose_of(COMPARISON)

    def test_the_ratio_the_prose_quotes(self, comparison_namespace):
        ratio = comparison_namespace["labor_spent"] / comparison_namespace["reference"].objective_value
        assert round(ratio, 2) == 1.80
        assert "The ratio is 1.80" in prose_of(COMPARISON)

    def test_the_floor_is_private_consumption_plus_public_good_output(self, comparison_namespace):
        """Rebuilt here entry by entry, so a recipe that changed its floor fails this test."""
        economy = comparison_namespace["economy"]
        plan = comparison_namespace["plan"]
        public = set(hahnel.shared_goods(economy).tolist())
        expected = np.zeros(economy.n_commodities)
        for column, commodity in enumerate(plan.consumption_commodity):
            expected[commodity] += plan.consumption[:, column].sum()
        for entry, commodity in enumerate(economy.output_commodity):
            if int(commodity) in public:
                expected[commodity] += plan.output[entry]
        floor = comparison_namespace["objective"].final_demand_lower_bound
        np.testing.assert_allclose(floor, expected, rtol=1e-12, atol=0.0)
        np.testing.assert_array_equal(
            comparison_namespace["objective"].counted_commodities, hahnel.labor(economy)
        )


@pytest.mark.slow
class TestTheDifferenceReportOnDep1ex01:
    """The block under the difference heading gives the numbers its prose quotes."""

    def test_supply_minus_use_lies_between_14_9_and_45_9(self, leaves_over_namespace):
        difference = leaves_over_namespace["balance"].difference
        assert round(float(difference.min()), 1) == 14.9
        assert round(float(difference.max()), 1) == 45.9
        assert "lies between 14.9 and 45.9" in prose_of(LEAVES_OVER)

    def test_the_budget_reason_is_the_one_the_prose_prints(self, leaves_over_namespace):
        printed = TEXT_BLOCK.findall(section_under(README.read_text(encoding="utf-8"), LEAVES_OVER))
        assert len(printed) == 1
        reason = leaves_over_namespace["result"].differences.budget.why_not_computed
        assert " ".join(printed[0].split()) == reason

    def test_the_budget_difference_at_the_named_price_is_below_3e_12(self, leaves_over_namespace):
        budget = leaves_over_namespace["budget"]
        assert budget.why_not_computed is None
        assert float(np.abs(budget.difference).max()) < 3e-12
        assert "income minus expenditure is below 3e-12 for every council" in prose_of(
            LEAVES_OVER
        )

    def test_the_largest_technology_margin_is_below_1e_12(self, leaves_over_namespace):
        margins = leaves_over_namespace["margins"]
        assert dict(margins.missing) == {}
        assert bool(margins.computed.all())
        assert float(np.abs(margins.margin).max()) < 1e-12

    def test_without_the_prefab_technology_every_unit_is_missing(self, leaves_over_namespace):
        economy = leaves_over_namespace["economy"]
        report = technology_margins(economy, leaves_over_namespace["plan"])
        assert dict(report.missing) == {hahnel.TECHNOLOGY: 30_000}
        assert economy.n_units == 30_000
        assert "lists all 30,000 units under `missing`" in prose_of(LEAVES_OVER)
