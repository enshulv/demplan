"""The worker councils of a public dep1ex archive, as the parameters of the council's problem.

An archive ``dep1exNN.clj.gz`` is a Clojure namespace holding ``(def ccs [...])`` and
``(def wcs [...])``. Each worker council is a map; the keys read here are the ones
``proposal`` in pequod-cljs's csvgen.clj at 71e44d3 (lines 734-770) reads:

  :industry           0 private goods, 1 intermediate goods, 2 public goods
  :product            the id of the good it makes, within that category
  :production-inputs  [[intermediate ids] [natural resource ids] [labour ids]]
  :input-exponents, :nature-exponents, :labor-exponents
                      one exponent per id, in the same order
  :a :s :c :du        total factor productivity, disutility coefficient, effort elasticity,
                      disutility exponent (``k`` in the program)

A council's inputs are ordered intermediate goods, natural resources, labour, which is the
order ``proposal`` concatenates the exponents and the prices in.
"""
from __future__ import annotations

import gzip
import re
from pathlib import Path

INPUT_CATEGORIES = ("intermediate-inputs", "nature", "labor")
"""Input categories in the order the program concatenates exponents and prices."""

PRODUCT_CATEGORY = {0: "private-goods", 1: "intermediate-inputs", 2: "public-goods"}
"""Price category of a council's product, by its ``:industry`` code (``get-lambda-o``, lines 739-744)."""

PRICE_CATEGORIES = ("private-goods", "intermediate-inputs", "nature", "labor", "public-goods")
"""The five price categories by the names used here, in the order of the price blocks of the
program's output files (``_program_output.CATEGORIES``)."""

_TOKEN = re.compile(r"[{}\[\]]|:[A-Za-z0-9?!*+<>=/_-]+|-?\d+\.\d*(?:[eE][-+]?\d+)?|-?\d+(?:[eE][-+]?\d+)?|true|false|nil")
"""The EDN tokens a dep1ex archive uses; commas and whitespace separate them and are skipped."""


def _parse_edn(tokens: list[str], pos: int):
    """One EDN value (map, vector, keyword, number, boolean, nil) starting at ``tokens[pos]``,
    and the position after it."""
    token = tokens[pos]
    if token in ("{", "["):
        close = "}" if token == "{" else "]"
        items = []
        pos += 1
        while tokens[pos] != close:
            item, pos = _parse_edn(tokens, pos)
            items.append(item)
        if token == "[":
            return items, pos + 1
        return dict(zip(items[0::2], items[1::2])), pos + 1
    if token.startswith(":"):
        return token[1:], pos + 1
    if token in ("true", "false", "nil"):
        return {"true": True, "false": False, "nil": None}[token], pos + 1
    return (float(token) if any(ch in token for ch in ".eE") else int(token)), pos + 1


def read_worker_councils(path: Path) -> list[dict]:
    """The ``wcs`` vector of a dep1ex archive, as dicts keyed by keyword name without the colon.

    Only the worker councils are parsed; the consumer councils before them are skipped.
    """
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        text = stream.read()
    start = text.index("(def wcs")
    tokens = _TOKEN.findall(text, start + len("(def wcs"))
    councils, _ = _parse_edn(tokens, 0)
    return councils


def council_from_dep1ex(wc: dict) -> dict:
    """A dep1ex worker council as ``{industry, product, a, s, c, k, inputs}``.

    ``inputs`` maps each input category to ``[[id, exponent], ...]``; ``k`` is ``:du``, as in
    ``proposal``. Raises ``ValueError`` when a category's exponents do not pair one to one with
    its ids.
    """
    exponents = (wc["input-exponents"], wc["nature-exponents"], wc["labor-exponents"])
    inputs = {
        category: [[int(i), float(b)] for i, b in zip(ids, bs, strict=True)]
        for category, ids, bs in zip(INPUT_CATEGORIES, wc["production-inputs"], exponents, strict=True)
    }
    return {"industry": int(wc["industry"]), "product": int(wc["product"]), "a": float(wc["a"]),
            "s": float(wc["s"]), "c": float(wc["c"]), "k": float(wc["du"]), "inputs": inputs}


def input_count(council: dict) -> int:
    """Number of inputs of a council, over all categories."""
    return sum(len(council["inputs"][c]) for c in INPUT_CATEGORIES)
