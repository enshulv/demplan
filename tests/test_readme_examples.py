"""Runs the code blocks of README.md.

The blocks are read out of the file rather than restated here, so a README example that stops
working fails this file instead of quietly misleading a reader. Blocks are located by the
heading they sit under, which keeps the marker out of what the reader sees.

The block under "Write your own coordination method" opens on an ``economy`` that the reader
has from the block above it, which loads a dep1ex archive. The archives are not in the
repository, so this file supplies a Cobb-Douglas economy under that name instead; nothing else
about the block is changed.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from reference import synthetic

README = pathlib.Path(__file__).resolve().parents[1] / "README.md"

CODE_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)


def code_block_under(heading: str, occurrence: int = 0) -> str:
    """The ``occurrence``-th python block after ``heading``, verbatim."""
    text = README.read_text(encoding="utf-8")
    parts = text.split(f"\n{heading}\n", 1)
    assert len(parts) == 2, f"README has no heading {heading!r}"
    blocks = CODE_BLOCK.findall(parts[1])
    assert len(blocks) > occurrence, f"heading {heading!r} has {len(blocks)} python blocks"
    return blocks[occurrence]


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
