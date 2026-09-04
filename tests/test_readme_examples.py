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
