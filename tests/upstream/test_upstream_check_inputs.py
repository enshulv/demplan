"""The LFS pointer reader and the renamed-input hashes of ``research/upstream/check_inputs.py``."""

from __future__ import annotations

import hashlib

import pytest

import upstream_paths  # noqa: F401  (puts the scripts on sys.path)

import check_inputs as ci  # noqa: E402


def test_pointer_parse_and_rename_hash():
    text = ("version https://git-lfs.github.com/spec/v1\n"
            "oid sha256:" + "a" * 64 + "\nsize 12\n")
    assert ci.read_pointer(text, "x") == ("a" * 64, 12)
    with pytest.raises(ValueError):
        ci.read_pointer("hello world\n", "x")
    body = b"(ns pequod-cljs.dep1ex01)\n(def x 1)\n"
    target = b"(ns pequod-cljs.dep1ex61)\n(def x 1)\n"
    pointers = {61: (hashlib.sha256(target).hexdigest(), len(target)), 62: ("b" * 64, len(target))}
    got = ci.renamed_digests(body, pointers)
    assert got[61] == pointers[61]
    assert got[62][0] != pointers[62][0] and got[62][1] == len(target)


def test_namespace_line():
    assert ci.namespace_line(1) == b"(ns pequod-cljs.dep1ex01)"
    assert ci.namespace_line(100) == b"(ns pequod-cljs.dep1ex100)"


# ---------------------------------------------------------------- the hit matrix

ARCHIVES = {n: f"(ns pequod-cljs.dep1ex{n:02d})\n(def councils {n:02d})\n".encode() for n in (1, 2, 3, 20)}
"""Four input files of equal length, as the archives of book experiments 1, 2, 3 and 20."""


def _pointer_of(n: int, m: int) -> tuple[str, int]:
    """The pointer that archive ``n`` renamed to ``dep1ex<m>`` would have."""
    renamed = ci.namespace_line(m) + ARCHIVES[n][ARCHIVES[n].index(b"\n"):]
    return hashlib.sha256(renamed).hexdigest(), len(renamed)


def _pointers() -> dict[int, tuple[str, int]]:
    """61 and 62 are archives 1 and 2 renamed; 63 has the size archive 3 renamed would have and
    another hash; there is no pointer 80."""
    size_63 = _pointer_of(3, 63)[1]
    return {61: _pointer_of(1, 61), 62: _pointer_of(2, 62), 63: ("c" * 64, size_63)}


def test_a_hit_needs_both_sha256_and_size():
    pointers = _pointers()
    digests = {n: ci.renamed_digests(ARCHIVES[n], pointers) for n in ARCHIVES}
    # every renamed file has the size of every pointer, so the sha256 alone tells them apart
    assert all(size == pointers[m][1] for n in ARCHIVES for m, (_, size) in digests[n].items())
    assert {n: ci.hits_of(digests[n], pointers) for n in ARCHIVES} == {1: [61], 2: [62], 3: [], 20: []}
    same_hash_other_size = {61: (pointers[61][0], pointers[61][1] + 1)}
    assert ci.hits_of({61: pointers[61]}, same_hash_other_size) == []


def test_expected_hits_are_60_plus_n_where_that_pointer_exists_and_none_otherwise():
    assert ci.expected_hits([1, 2, 3, 20], [61, 62, 63]) == {1: [61], 2: [62], 3: [63], 20: []}


def test_unexpected_hits_name_every_archive_whose_hits_are_not_the_expected_ones():
    expected = {1: [61], 2: [62], 3: [63], 20: []}
    hits = {1: [61], 2: [62], 3: [], 20: []}
    assert ci.unexpected_hits(hits, expected) == {3: []}
    assert ci.unexpected_hits({**hits, 3: [63]}, expected) == {}
    assert ci.unexpected_hits({**hits, 3: [63], 1: [61, 62]}, expected) == {1: [61, 62]}
    assert ci.unexpected_hits({**hits, 3: [63], 20: [63]}, expected) == {20: [63]}
    assert ci.unexpected_hits({**hits, 3: [63], 1: [62]}, expected) == {1: [62]}
