"""Line listings of upstream files, ``research/upstream/_source_lines.py``, and the listings
``docker/pequod-plus/run_all.py`` prints for each image.

The sources here are made-up text; no upstream file is read.
"""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

import upstream_paths  # noqa: F401  (puts the scripts on sys.path)

import _source_edits  # noqa: E402
import _source_lines as sl  # noqa: E402
import run_all  # noqa: E402

COMMIT = "0123456789abcdef0123456789abcdef01234567"
UTIL = b"(ns demo.util)\n\n(defn step [x]\n  (max 0.001 x))\n\n(defn solve [a b]\n  (+ (* a b) (* 3 a) (* 4 b)))\n"
CORE = "(ns demo.core)\n(def price-of-λ 1)\n".encode("utf-8")


def sha(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


def line_of(source: bytes, number: int) -> bytes:
    return source.split(b"\n")[number - 1]


def document(**changes):
    """A valid listing of UTIL lines 3, 4 and 7 (columns 6-14 of 7) and CORE line 2."""
    doc = {
        "description": "lines printed before the probes",
        "repository": "someone/demo",
        "commit": COMMIT,
        "files": {
            "src/demo/util.clj": [
                {"line": 3, "line_sha256": sha(line_of(UTIL, 3))},
                {"line": 4, "line_sha256": sha(line_of(UTIL, 4))},
                {"line": 7, "line_sha256": sha(line_of(UTIL, 7)), "columns": [6, 14]},
            ],
            "src/demo/core.clj": [
                {"line": 2, "line_sha256": sha(line_of(CORE, 2))},
            ],
        },
    }
    doc.update(changes)
    return doc


SOURCES = {"src/demo/util.clj": UTIL, "src/demo/core.clj": CORE}


# ---------------------------------------------------------------- parse


def test_parse_reads_every_field():
    listing = sl.parse(document())
    assert listing.repository == "someone/demo" and listing.commit == COMMIT
    assert [f.file for f in listing.files] == ["src/demo/util.clj", "src/demo/core.clj"]
    first = listing.files[0]
    assert [(entry.line, entry.columns) for entry in first.lines] == [(3, None), (4, None), (7, (6, 14))]
    assert first.lines[0].line_sha256 == sha(b"(defn step [x]")


def _broken(mutate):
    doc = copy.deepcopy(document())
    mutate(doc)
    return doc


@pytest.mark.parametrize(("mutate", "message"), [
    (lambda d: d.pop("files"), "missing keys"),
    (lambda d: d.update(extra=1), "unknown keys"),
    (lambda d: d.update(commit="44a6d08"), "commit"),
    (lambda d: d.update(files={}), "files"),
    (lambda d: d.update(files=[]), "files"),
    (lambda d: d["files"].update({"src/demo/core.clj": []}), "src/demo/core.clj"),
    (lambda d: d["files"]["src/demo/core.clj"][0].update(line=0), "line"),
    (lambda d: d["files"]["src/demo/core.clj"][0].update(line=True), "line"),
    (lambda d: d["files"]["src/demo/core.clj"][0].update(line="2"), "line"),
    (lambda d: d["files"]["src/demo/core.clj"][0].update(line_sha256="ABC"), "line_sha256"),
    (lambda d: d["files"]["src/demo/core.clj"][0].update(text="(def x 1)"), "unknown keys"),
    (lambda d: d["files"]["src/demo/util.clj"][2].update(columns=[14, 6]), "columns"),
    (lambda d: d["files"]["src/demo/util.clj"][2].update(columns=[0, 6]), "columns"),
    (lambda d: d["files"]["src/demo/util.clj"][2].update(columns=[6]), "columns"),
    (lambda d: d["files"]["src/demo/util.clj"][2].update(columns=[6, True]), "columns"),
    (lambda d: d["files"]["src/demo/util.clj"].reverse(), "increasing"),
    (lambda d: d["files"]["src/demo/util.clj"].append(dict(d["files"]["src/demo/util.clj"][2])), "increasing"),
])
def test_parse_rejects_a_malformed_listing(mutate, message):
    with pytest.raises(sl.SourceLineError, match=message):
        sl.parse(_broken(mutate))


def test_load_reads_a_json_file(tmp_path):
    path = tmp_path / "listing.json"
    path.write_text(json.dumps(document()), encoding="utf-8")
    assert sl.load(path) == sl.parse(document())
    path.write_text("{", encoding="utf-8")
    with pytest.raises(sl.SourceLineError, match="JSON"):
        sl.load(path)


# ---------------------------------------------------------------- render


def test_render_prints_each_line_with_its_file_and_number():
    assert sl.render(sl.parse(document()), SOURCES) == [
        "src/demo/util.clj:3:(defn step [x]",
        "src/demo/util.clj:4:  (max 0.001 x))",
        "src/demo/util.clj:7: columns 6-14: (* a b) (",
        "src/demo/core.clj:2:(def price-of-λ 1)",
    ]


def test_render_cuts_a_long_line_and_says_so():
    shown = sl.render(sl.parse(document()), SOURCES, width=24)
    assert shown[0] == "src/demo/util.clj:3:(def ..."
    assert shown[3] == "src/demo/core.clj:2:(def ..."
    assert sl.render(sl.parse(document()), SOURCES, width=36)[1] == "src/demo/util.clj:4:  (max 0.001 x))"


def test_render_names_every_line_whose_hash_differs_and_prints_nothing():
    changed = {**SOURCES, "src/demo/util.clj": UTIL.replace(b"0.001", b"0.01").replace(b"(* 4 b)", b"(* 5 b)")}
    with pytest.raises(sl.SourceLineError) as error:
        sl.render(sl.parse(document()), changed)
    text = str(error.value)
    assert COMMIT in text
    assert "src/demo/util.clj line 4" in text and "src/demo/util.clj line 7" in text
    assert "line 3" not in text
    assert sha(b"  (max 0.001 x))") in text and sha(b"  (max 0.01 x))") in text


def test_render_refuses_a_line_past_the_end_or_a_file_it_was_not_given():
    short = {**SOURCES, "src/demo/util.clj": b"(ns demo.util)\n\n(defn step [x]\n  (max 0.001 x))\n"}
    with pytest.raises(sl.SourceLineError, match=r"src/demo/util.clj line 7 is past the end of the file \(4 lines\)"):
        sl.render(sl.parse(document()), short)
    with pytest.raises(sl.SourceLineError, match="src/demo/core.clj"):
        sl.render(sl.parse(document()), {"src/demo/util.clj": UTIL})


def test_render_refuses_columns_past_the_end_of_the_line():
    doc = _broken(lambda d: d["files"]["src/demo/util.clj"][2].update(columns=[6, 400]))
    with pytest.raises(sl.SourceLineError, match="line 7.*columns 6-400"):
        sl.render(sl.parse(doc), SOURCES)


def test_render_checks_the_committed_file_and_prints_the_shown_one():
    edit_set = _source_edits.parse({
        "description": "demo", "repository": "someone/demo", "commit": COMMIT, "file": "src/demo/util.clj",
        "edits": [{"line": 7, "line_sha256": sha(line_of(UTIL, 7)), "replace_once": {"old": "(* a b)", "new": "(* b a)"}}],
    })
    edited = {**SOURCES, "src/demo/util.clj": _source_edits.apply(edit_set, UTIL)}
    shown = sl.render(sl.parse(document()), SOURCES, shown=edited)
    assert shown[2] == "src/demo/util.clj:7: columns 6-14: (* b a) ("
    assert shown[:2] + shown[3:] == [line for i, line in enumerate(sl.render(sl.parse(document()), SOURCES)) if i != 2]
    with pytest.raises(sl.SourceLineError, match="line 7"):
        sl.render(sl.parse(document()), edited)


def test_render_refuses_a_shown_file_shorter_than_a_listed_line():
    with pytest.raises(sl.SourceLineError, match="line 7"):
        sl.render(sl.parse(document()), SOURCES, shown={**SOURCES, "src/demo/util.clj": b"(ns demo.util)\n"})


# ---------------------------------------------------------------- the listings of run_all.py


def test_every_commit_target_has_a_listing_for_its_commit():
    for target in run_all.TARGETS:
        listing = run_all.listing_of(target)
        commit = target["commit"] if "commit" in target else run_all.base_of(target)["commit"]
        assert listing.commit == commit, target["label"]
        assert listing.repository == "msszczep/pequod-plus"
        assert {f.file for f in listing.files} <= {"src/cljc/pequod_plus/util.cljc", "src/clj/pequod_plus/csvgen.clj"}


def test_an_edited_target_prints_the_listing_of_its_base():
    edited = next(t for t in run_all.TARGETS if "edits" in t)
    assert run_all.listing_of(edited) == run_all.listing_of(run_all.base_of(edited))


def test_the_listings_hold_line_numbers_and_hashes_only():
    for path in sorted(run_all.LINES_DIR.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert set(document) == {"description", "repository", "commit", "files"}, path.name
        for entries in document["files"].values():
            for entry in entries:
                assert set(entry) <= {"line", "line_sha256", "columns"}, path.name
