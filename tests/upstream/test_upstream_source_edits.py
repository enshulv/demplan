"""``research/upstream/_source_edits.py``, the edit sets under ``docker/*/edits``, and the two
Docker drivers that apply them.

The applier is tested on small synthetic sources whose line hashes are computed here with
``hashlib``, not with the module. The real edit sets name lines of upstream files that are not
in the repository; their content is checked structurally here, and against the real file in
``test_real_pequod_cljs_file_changes_only_the_named_lines`` when the pinned csvgen.clj is in
the download cache.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

import upstream_paths

import _source_edits as se  # noqa: E402
import run as cljs_run  # noqa: E402  (docker/pequod-cljs/run.py)
import run_all as plus_run  # noqa: E402  (docker/pequod-plus/run_all.py)

CLJS_EDITS = upstream_paths.PEQUOD_CLJS_DOCKER_DIR / "edits"
PLUS_EDITS = upstream_paths.PEQUOD_PLUS_DOCKER_DIR / "edits"
EDIT_FILES = sorted(CLJS_EDITS.glob("*.json")) + sorted(PLUS_EDITS.glob("*.json"))

COMMIT = "0123456789abcdef0123456789abcdef01234567"


def sha(line: bytes) -> str:
    return hashlib.sha256(line).hexdigest()


def edit_set(edits, file="src/a.clj"):
    """A parsed edit set over ``file`` with the given edit dicts."""
    return se.parse({
        "description": "test",
        "repository": "someone/something",
        "commit": COMMIT,
        "file": file,
        "edits": edits,
    })


SOURCE = (
    b"(ns a)\n"
    b"  (let [x 1\n"
    b"\t\ty (+ x 2)]\n"
    b"    (+ (* x y) (* x y)))\n"
    b"(def lambda \xce\xbb)\n"
)
LINES = SOURCE.split(b"\n")[:-1]


# ---------------------------------------------------------------- parse / load


def valid_document():
    return {
        "description": "why",
        "repository": "someone/something",
        "commit": COMMIT,
        "file": "src/a.clj",
        "edits": [
            {"line": 2, "line_sha256": sha(LINES[1]), "replace_line": "(let [x 5"},
            {"line": 5, "line_sha256": sha(LINES[4]), "replace_once": {"old": "λ", "new": "mu"}},
        ],
    }


def test_parse_reads_every_field():
    parsed = se.parse(valid_document())
    assert parsed.description == "why"
    assert parsed.repository == "someone/something"
    assert parsed.commit == COMMIT
    assert parsed.file == "src/a.clj"
    assert [e.line for e in parsed.edits] == [2, 5]
    assert isinstance(parsed.edits[0], se.ReplaceLine)
    assert parsed.edits[0].text == "(let [x 5"
    assert parsed.edits[0].line_sha256 == sha(LINES[1])
    assert isinstance(parsed.edits[1], se.ReplaceOnce)
    assert (parsed.edits[1].old, parsed.edits[1].new) == ("λ", "mu")


def test_load_reads_a_json_file(tmp_path):
    path = tmp_path / "e.json"
    path.write_text(json.dumps(valid_document()), encoding="utf-8")
    assert se.load(path) == se.parse(valid_document())


def _broken(mutate):
    document = copy.deepcopy(valid_document())
    mutate(document)
    return document


@pytest.mark.parametrize("mutate", [
    pytest.param(lambda d: d.pop("commit"), id="missing top-level key"),
    pytest.param(lambda d: d.update(extra=1), id="unknown top-level key"),
    pytest.param(lambda d: d.update(commit="abc"), id="short commit"),
    pytest.param(lambda d: d.update(commit=COMMIT.upper()), id="upper-case commit"),
    pytest.param(lambda d: d.update(file=""), id="empty file"),
    pytest.param(lambda d: d.update(edits=[]), id="no edits"),
    pytest.param(lambda d: d["edits"][0].pop("line_sha256"), id="missing line_sha256"),
    pytest.param(lambda d: d["edits"][0].update(line_sha256="ab" * 31), id="short hash"),
    pytest.param(lambda d: d["edits"][0].update(line_sha256=d["edits"][0]["line_sha256"].upper()),
                 id="upper-case hash"),
    pytest.param(lambda d: d["edits"][0].update(line=0), id="line 0"),
    pytest.param(lambda d: d["edits"][0].update(line=-3), id="negative line"),
    pytest.param(lambda d: d["edits"][0].update(line=2.0), id="float line"),
    pytest.param(lambda d: d["edits"][0].update(line=True), id="bool line"),
    pytest.param(lambda d: d["edits"][0].update(line="2"), id="string line"),
    pytest.param(lambda d: d["edits"][1].update(line=2), id="two edits of one line"),
    pytest.param(lambda d: d["edits"][0].update(replace_once={"old": "x", "new": "y"}), id="both kinds"),
    pytest.param(lambda d: d["edits"][0].pop("replace_line"), id="neither kind"),
    pytest.param(lambda d: d["edits"][0].update(note="x"), id="unknown edit key"),
    pytest.param(lambda d: d["edits"][0].update(replace_line=""), id="empty replacement line"),
    pytest.param(lambda d: d["edits"][0].update(replace_line="  (let [x 5"), id="replacement with indentation"),
    pytest.param(lambda d: d["edits"][0].update(replace_line="(let\n[x 5"), id="newline in replacement line"),
    pytest.param(lambda d: d["edits"][0].update(replace_line="(let\r[x 5"), id="carriage return in replacement"),
    pytest.param(lambda d: d["edits"][1]["replace_once"].update(old=""), id="empty old text"),
    pytest.param(lambda d: d["edits"][1]["replace_once"].update(new="λ"), id="old equals new"),
    pytest.param(lambda d: d["edits"][1]["replace_once"].update(new="a\nb"), id="newline in new text"),
    pytest.param(lambda d: d["edits"][1]["replace_once"].update(extra="x"), id="unknown replace_once key"),
    pytest.param(lambda d: d["edits"][1]["replace_once"].pop("new"), id="replace_once without new"),
])
def test_parse_rejects_a_malformed_edit_set(mutate):
    with pytest.raises(se.SourceEditError):
        se.parse(_broken(mutate))


def test_line_sha256_is_the_sha256_of_the_bytes_without_terminator():
    assert se.line_sha256(b"  (let [x 1") == hashlib.sha256(b"  (let [x 1").hexdigest()


# ---------------------------------------------------------------- apply


def test_replace_line_keeps_the_indentation_and_every_other_byte():
    edits = edit_set([{"line": 2, "line_sha256": sha(LINES[1]), "replace_line": "(let [x 5"}])
    assert se.apply(edits, SOURCE) == SOURCE.replace(b"  (let [x 1\n", b"  (let [x 5\n")


def test_replace_line_keeps_tab_indentation():
    edits = edit_set([{"line": 3, "line_sha256": sha(LINES[2]), "replace_line": "z 0]"}])
    assert se.apply(edits, SOURCE).split(b"\n")[2] == b"\t\tz 0]"


def test_replace_once_changes_only_the_named_text_on_the_named_line():
    edits = edit_set([{"line": 3, "line_sha256": sha(LINES[2]), "replace_once": {"old": "(+ x 2)", "new": "(- x 2)"}}])
    after = se.apply(edits, SOURCE)
    assert after == SOURCE.replace(b"y (+ x 2)]", b"y (- x 2)]")


def test_replace_once_works_on_non_ascii_lines():
    edits = edit_set([{"line": 5, "line_sha256": sha(LINES[4]), "replace_once": {"old": "λ", "new": "mu"}}])
    assert se.apply(edits, SOURCE).split(b"\n")[4] == b"(def lambda mu)"


def test_several_edits_apply_together():
    edits = edit_set([
        {"line": 5, "line_sha256": sha(LINES[4]), "replace_line": "(def b 2)"},
        {"line": 1, "line_sha256": sha(LINES[0]), "replace_line": "(ns b)"},
    ])
    after = se.apply(edits, SOURCE).split(b"\n")
    assert after[0] == b"(ns b)"
    assert after[4] == b"(def b 2)"
    assert after[1:4] == LINES[1:4]


def test_a_file_without_final_newline_keeps_that():
    source = b"a\nb"
    edits = edit_set([{"line": 2, "line_sha256": sha(b"b"), "replace_line": "c"}])
    assert se.apply(edits, source) == b"a\nc"


def test_line_endings_other_than_the_edited_line_are_kept():
    source = b"a\r\nb\nc\r\n"
    edits = edit_set([{"line": 2, "line_sha256": sha(b"b"), "replace_line": "d"}])
    assert se.apply(edits, source) == b"a\r\nd\nc\r\n"


def test_hash_mismatch_is_an_error_naming_the_line_and_both_hashes():
    wrong = sha(b"something else")
    edits = edit_set([{"line": 2, "line_sha256": wrong, "replace_line": "(let [x 5"}], file="src/a.clj")
    with pytest.raises(se.SourceEditError) as info:
        se.apply(edits, SOURCE)
    message = str(info.value)
    assert "src/a.clj" in message and "line 2" in message
    assert wrong in message and sha(LINES[1]) in message


def test_the_hash_is_checked_against_the_named_line_not_a_neighbour():
    # The hash of line 2, given for line 3: an off-by-one reading of the line number fails.
    edits = edit_set([{"line": 3, "line_sha256": sha(LINES[1]), "replace_line": "z"}])
    with pytest.raises(se.SourceEditError):
        se.apply(edits, SOURCE)
    edits = edit_set([{"line": 1, "line_sha256": sha(LINES[1]), "replace_line": "z"}])
    with pytest.raises(se.SourceEditError):
        se.apply(edits, SOURCE)


def test_the_hash_covers_the_indentation():
    edits = edit_set([{"line": 2, "line_sha256": sha(LINES[1].lstrip()), "replace_line": "z"}])
    with pytest.raises(se.SourceEditError):
        se.apply(edits, SOURCE)


def test_a_later_mismatch_stops_the_whole_set():
    edits = edit_set([
        {"line": 1, "line_sha256": sha(LINES[0]), "replace_line": "(ns b)"},
        {"line": 2, "line_sha256": sha(b"x"), "replace_line": "z"},
    ])
    with pytest.raises(se.SourceEditError):
        se.apply(edits, SOURCE)


@pytest.mark.parametrize("line", [6, 7, 100])
def test_a_line_past_the_end_is_an_error(line):
    # SOURCE has five lines; the empty text after its final newline is not a sixth.
    edits = edit_set([{"line": line, "line_sha256": sha(b""), "replace_line": "z"}])
    with pytest.raises(se.SourceEditError, match="past the end"):
        se.apply(edits, SOURCE)


def test_replace_once_needs_exactly_one_occurrence():
    twice = edit_set([{"line": 4, "line_sha256": sha(LINES[3]), "replace_once": {"old": "(* x y)", "new": "(* y x)"}}])
    with pytest.raises(se.SourceEditError, match="2 times"):
        se.apply(twice, SOURCE)
    absent = edit_set([{"line": 4, "line_sha256": sha(LINES[3]), "replace_once": {"old": "(- x y)", "new": "(* y x)"}}])
    with pytest.raises(se.SourceEditError, match="0 times"):
        se.apply(absent, SOURCE)


def test_replace_once_counts_on_the_named_line_only():
    # "(ns a)" occurs once in the file, on line 1; it does not occur on line 4.
    edits = edit_set([{"line": 4, "line_sha256": sha(LINES[3]), "replace_once": {"old": "(ns a)", "new": "(ns b)"}}])
    with pytest.raises(se.SourceEditError):
        se.apply(edits, SOURCE)


def test_a_replacement_that_leaves_the_line_unchanged_is_an_error():
    edits = edit_set([{"line": 1, "line_sha256": sha(LINES[0]), "replace_line": "(ns a)"}])
    with pytest.raises(se.SourceEditError, match="unchanged"):
        se.apply(edits, SOURCE)


# ---------------------------------------------------------------- summary and unified_diff


def test_summary_names_file_commit_and_lines():
    one = edit_set([{"line": 2, "line_sha256": sha(LINES[1]), "replace_line": "z"}])
    assert se.summary(one) == "src/a.clj at 0123456, line 2: sha256 as recorded, edited"
    two = edit_set([
        {"line": 5, "line_sha256": sha(LINES[4]), "replace_line": "z"},
        {"line": 1, "line_sha256": sha(LINES[0]), "replace_line": "z"},
    ])
    assert se.summary(two) == "src/a.clj at 0123456, lines 5, 1: sha256 as recorded, edited"



def test_unified_diff_shows_only_the_changed_lines_with_their_numbers():
    edits = edit_set([
        {"line": 2, "line_sha256": sha(LINES[1]), "replace_line": "(let [x 5"},
        {"line": 5, "line_sha256": sha(LINES[4]), "replace_once": {"old": "λ", "new": "mu"}},
    ])
    after = se.apply(edits, SOURCE)
    assert se.unified_diff(edits, SOURCE, after).splitlines() == [
        "--- a/src/a.clj",
        "+++ b/src/a.clj",
        "@@ -2 +2 @@",
        "-  (let [x 1",
        "+  (let [x 5",
        "@@ -5 +5 @@",
        "-(def lambda λ)",
        "+(def lambda mu)",
    ]


def test_unified_diff_of_identical_sources_is_empty():
    edits = edit_set([{"line": 1, "line_sha256": sha(LINES[0]), "replace_line": "(ns b)"}])
    assert se.unified_diff(edits, SOURCE, SOURCE) == ""


# ---------------------------------------------------------------- the edit sets in the repository


def test_the_edit_sets_are_the_three_expected():
    assert [p.name for p in EDIT_FILES] == [
        "rule-book-p181.json", "rule-paper-p7.json", "solution-5-x1-log-p3.json",
    ]


@pytest.mark.parametrize("path", EDIT_FILES, ids=lambda p: p.name)
def test_every_edit_set_loads(path):
    assert se.load(path).edits


def test_no_patch_files_are_left_in_the_docker_directories():
    docker = upstream_paths.UPSTREAM_DIR / "docker"
    assert sorted(docker.rglob("*.patch")) == []
    assert sorted(docker.rglob("*.diff")) == []


def _replaced_line_hashes() -> set[str]:
    return {edit.line_sha256 for path in EDIT_FILES for edit in se.load(path).edits}


def test_no_file_holds_a_line_the_edits_replace():
    """No line of research/upstream or tests/upstream is one of the upstream lines the edits
    replace, whole or as a diff line (one leading character of `+`, `-` or space)."""
    hashes = _replaced_line_hashes()
    assert len(hashes) == 3
    offending = []
    for root in (upstream_paths.UPSTREAM_DIR, upstream_paths.REPO_ROOT / "tests" / "upstream"):
        for path in root.rglob("*"):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            for number, line in enumerate(path.read_bytes().split(b"\n"), start=1):
                line = line.rstrip(b"\r")
                if sha(line) in hashes or sha(line[1:]) in hashes:
                    offending.append(f"{path}:{number}")
    assert offending == []


def test_the_book_and_paper_edits_name_the_same_upstream_lines():
    book = se.load(CLJS_EDITS / "rule-book-p181.json")
    paper = se.load(CLJS_EDITS / "rule-paper-p7.json")
    assert (book.repository, book.commit, book.file) == (paper.repository, paper.commit, paper.file)
    assert [e.line for e in book.edits] == [719]
    assert [e.line for e in paper.edits] == [718, 719]
    assert book.edits[0].line_sha256 == paper.edits[1].line_sha256
    assert paper.edits[0].line_sha256 != paper.edits[1].line_sha256
    assert all(isinstance(e, se.ReplaceLine) for e in book.edits + paper.edits)


def _dockerfile_arg(path: Path, name: str) -> str:
    match = re.search(rf"^ARG {name}=(\S+)$", path.read_text(encoding="utf-8"), re.M)
    return match.group(1)


def test_the_pequod_cljs_edits_name_the_commit_and_file_the_image_checks_out():
    commit = _dockerfile_arg(upstream_paths.PEQUOD_CLJS_DOCKER_DIR / "Dockerfile", "PROGRAM_COMMIT")
    for name in ("rule-book-p181.json", "rule-paper-p7.json"):
        edits = se.load(CLJS_EDITS / name)
        assert edits.repository == "msszczep/pequod-cljs"
        assert edits.commit == commit
        assert edits.file == cljs_run.CSVGEN_PATH == "src/clj/pequod_cljs/csvgen.clj"


def test_run_py_maps_each_text_rule_to_its_edit_set():
    assert cljs_run.RULE_EDITS == {
        "program": None, "book-p181": "rule-book-p181.json", "paper-p7": "rule-paper-p7.json",
    }
    assert cljs_run.RULE_RUNS == ("program", "book-p181", "paper-p7")
    for name in filter(None, cljs_run.RULE_EDITS.values()):
        assert (cljs_run.EDITS_DIR / name).is_file()


def test_the_pequod_plus_edit_replaces_one_term_of_line_228():
    edits = se.load(PLUS_EDITS / "solution-5-x1-log-p3.json")
    assert edits.repository == "msszczep/pequod-plus"
    assert edits.file == "src/clj/pequod_plus/csvgen.clj"
    assert len(edits.edits) == 1
    edit = edits.edits[0]
    assert isinstance(edit, se.ReplaceOnce)
    assert edit.line == 228
    assert (edit.old, edit.new) == ("(* b3 k log-p2)", "(* b3 k log-p3)")


def test_the_edited_pequod_plus_target_builds_on_the_commit_its_edits_name():
    by_label = {t["label"]: t for t in plus_run.TARGETS}
    edited = [t for t in plus_run.TARGETS if "edits" in t]
    assert [t["label"] for t in edited] == ["44a6d08-log-p3"]
    target = edited[0]
    base = by_label[target["base"]]
    assert "edits" not in base
    assert plus_run.TARGETS.index(base) < plus_run.TARGETS.index(target)
    edits = se.load(plus_run.EDITS_DIR / target["edits"])
    assert edits.commit == base["commit"] == "44a6d08be631b57e1638d39555d1f6089f0ca68b"
    assert target["probes"] == ("closed-forms",)


def test_unedited_pequod_plus_targets_carry_no_edits():
    for target in plus_run.TARGETS:
        assert "patch" not in target
        if "edits" not in target:
            assert re.fullmatch(r"[0-9a-f]{40}", target["commit"])


# ---------------------------------------------------------------- the drivers write nothing on a mismatch


def test_run_py_writes_no_source_when_an_edit_does_not_apply(tmp_path):
    committed = b"(ns pequod-cljs.csvgen)\n" * 800
    with pytest.raises(SystemExit) as info:
        cljs_run.prepare_sources(["program", "book-p181", "paper-p7"],
                                 se.load(CLJS_EDITS / "rule-book-p181.json").commit, committed, tmp_path)
    assert "line 719" in str(info.value.code)
    assert list(tmp_path.rglob("*")) == []


def test_run_py_refuses_edits_for_another_commit(tmp_path):
    with pytest.raises(SystemExit) as info:
        cljs_run.prepare_sources(["book-p181"], "f" * 40, b"x\n" * 800, tmp_path)
    assert "commit" in str(info.value.code)
    assert list(tmp_path.rglob("*")) == []


def test_run_py_needs_no_source_for_the_program_rule(tmp_path):
    assert cljs_run.prepare_sources(["program"], "f" * 40, b"", tmp_path) == {}
    assert list(tmp_path.rglob("*")) == []


def _synthetic_edits(directory: Path, name: str, file: str) -> None:
    """An edit set over ``file`` that turns line 2 of SOURCE into ``(let [x 5``."""
    document = valid_document()
    document.update(file=file, edits=[document["edits"][0]])
    (directory / name).write_text(json.dumps(document), encoding="utf-8")


def test_run_py_writes_each_edited_source_under_its_rule(tmp_path, monkeypatch):
    edits_dir = tmp_path / "edits"
    edits_dir.mkdir()
    _synthetic_edits(edits_dir, "r.json", cljs_run.CSVGEN_PATH)
    monkeypatch.setattr(cljs_run, "EDITS_DIR", edits_dir)
    monkeypatch.setattr(cljs_run, "RULE_EDITS", {"program": None, "r": "r.json"})
    written = cljs_run.prepare_sources(["program", "r"], COMMIT, SOURCE, tmp_path / "out")
    assert written == {"r": tmp_path / "out" / "r" / "csvgen.clj"}
    assert written["r"].read_bytes() == SOURCE.replace(b"(let [x 1", b"(let [x 5")


def test_run_py_writes_nothing_when_a_later_rule_does_not_apply(tmp_path, monkeypatch):
    edits_dir = tmp_path / "edits"
    edits_dir.mkdir()
    _synthetic_edits(edits_dir, "good.json", cljs_run.CSVGEN_PATH)
    bad = valid_document()
    bad.update(file=cljs_run.CSVGEN_PATH, edits=[{"line": 2, "line_sha256": sha(b"x"), "replace_line": "z"}])
    (edits_dir / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    monkeypatch.setattr(cljs_run, "EDITS_DIR", edits_dir)
    monkeypatch.setattr(cljs_run, "RULE_EDITS", {"good": "good.json", "bad": "bad.json"})
    with pytest.raises(SystemExit):
        cljs_run.prepare_sources(["good", "bad"], COMMIT, SOURCE, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_run_py_refuses_edits_of_another_file(tmp_path, monkeypatch):
    edits_dir = tmp_path / "edits"
    edits_dir.mkdir()
    _synthetic_edits(edits_dir, "r.json", "src/clj/pequod_cljs/util.clj")
    monkeypatch.setattr(cljs_run, "EDITS_DIR", edits_dir)
    monkeypatch.setattr(cljs_run, "RULE_EDITS", {"program": None, "r": "r.json"})
    with pytest.raises(SystemExit):
        cljs_run.prepare_sources(["r"], COMMIT, SOURCE, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_run_all_writes_the_edited_file_and_its_diff_into_the_build_context(tmp_path, monkeypatch):
    edits_dir = tmp_path / "edits"
    edits_dir.mkdir()
    _synthetic_edits(edits_dir, "s.json", "src/clj/pequod_plus/csvgen.clj")
    monkeypatch.setattr(plus_run, "EDITS_DIR", edits_dir)
    base = {"label": "base", "commit": COMMIT, "probes": (), "note": ""}
    target = {"label": "edited", "base": "base", "edits": "s.json", "probes": (), "note": ""}
    monkeypatch.setattr(plus_run, "TARGETS", [base, target])
    context = tmp_path / "context"
    diff = plus_run.write_edited_context(target, SOURCE, context)
    assert (context / "source" / "src" / "clj" / "pequod_plus" / "csvgen.clj").read_bytes() == (
        SOURCE.replace(b"(let [x 1", b"(let [x 5"))
    assert (context / "changes.txt").read_text(encoding="utf-8") == diff
    assert "-  (let [x 1" in diff.splitlines() and "+  (let [x 5" in diff.splitlines()
    assert sorted(p.relative_to(context).as_posix() for p in context.rglob("*") if p.is_file()) == [
        "changes.txt", "source/src/clj/pequod_plus/csvgen.clj",
    ]


def test_run_all_refuses_edits_for_another_commit_than_the_base(tmp_path, monkeypatch):
    edits_dir = tmp_path / "edits"
    edits_dir.mkdir()
    _synthetic_edits(edits_dir, "s.json", "src/clj/pequod_plus/csvgen.clj")
    monkeypatch.setattr(plus_run, "EDITS_DIR", edits_dir)
    base = {"label": "base", "commit": "f" * 40, "probes": (), "note": ""}
    target = {"label": "edited", "base": "base", "edits": "s.json", "probes": (), "note": ""}
    monkeypatch.setattr(plus_run, "TARGETS", [base, target])
    with pytest.raises(SystemExit):
        plus_run.write_edited_context(target, SOURCE, tmp_path / "context")
    assert not (tmp_path / "context").exists()


def test_run_all_writes_no_build_context_when_the_edit_does_not_apply(tmp_path):
    target = next(t for t in plus_run.TARGETS if "edits" in t)
    with pytest.raises(SystemExit) as info:
        plus_run.write_edited_context(target, b"(ns pequod-plus.csvgen)\n" * 300, tmp_path / "context")
    assert "line 228" in str(info.value.code)
    assert not (tmp_path / "context").exists()


# ---------------------------------------------------------------- the real upstream file, when cached


CSVGEN_71E44D3 = "pequod-cljs@71e44d3/csvgen.clj"


def _cached_csvgen() -> Path | None:
    return upstream_paths.cached_upstream_file(CSVGEN_71E44D3)


@pytest.mark.skipif(_cached_csvgen() is None, reason="csvgen.clj at 71e44d3 not in research/data/upstream "
                    "(python research/upstream/fetch.py pequod-cljs@71e44d3/csvgen.clj)")
@pytest.mark.parametrize(("name", "lines"), [
    ("rule-book-p181.json", [719]),
    ("rule-paper-p7.json", [718, 719]),
])
def test_real_pequod_cljs_file_changes_only_the_named_lines(name, lines, tmp_path):
    before = _cached_csvgen().read_bytes()
    edits = se.load(CLJS_EDITS / name)
    after = se.apply(edits, before)
    old, new = before.split(b"\n"), after.split(b"\n")
    assert len(old) == len(new)
    changed = [i + 1 for i, (a, b) in enumerate(zip(old, new)) if a != b]
    assert changed == lines
    for number in lines:
        # the same let binding, at the same indentation, now bound to our expression
        old_line, new_line = old[number - 1].decode(), new[number - 1].decode()
        assert old_line.split()[0] == new_line.split()[0]
        assert len(old_line) - len(old_line.lstrip()) == len(new_line) - len(new_line.lstrip())

    written = cljs_run.prepare_sources(["book-p181", "paper-p7"], edits.commit, before, tmp_path)
    assert written[name.removeprefix("rule-").removesuffix(".json")].read_bytes() == (
        se.apply(se.load(CLJS_EDITS / name), before))
