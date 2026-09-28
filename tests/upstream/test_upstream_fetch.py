"""The manifest reader and the pinned download of ``research/upstream/fetch.py``.

Every download here goes through a stand-in opener that serves bytes from memory; no test
touches the network.
"""

from __future__ import annotations

import hashlib
import io
import subprocess

import pytest

import upstream_paths  # noqa: F401  (puts the scripts on sys.path)

import fetch  # noqa: E402

HEADER = "name\trepository\tcommit\tpath\tsha256\tbytes\n"
GH = "msszczep/pequod-cljs"
C40 = "df6dc57743d2ebb4eb2f9e255472cc87e1f22a23"


def _manifest(tmp_path, rows):
    p = tmp_path / "manifest.tsv"
    p.write_text(HEADER + "".join("\t".join(map(str, r)) + "\n" for r in rows), encoding="utf-8")
    return p


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def test_manifest_github_url(tmp_path):
    body = b"hello"
    m = _manifest(tmp_path, [("pequod-cljs@df6dc57/a.csv", GH, C40, "src/a.csv", _sha(body), 5)])
    (entry,) = fetch.load_manifest(m)
    assert entry.url == f"https://raw.githubusercontent.com/{GH}/{C40}/src/a.csv"
    assert entry.size == 5 and entry.sha256 == _sha(body)


def test_manifest_szcz_url(tmp_path):
    m = _manifest(tmp_path, [("dep1ex01.clj.gz", "www.szcz.org", "-", "depexperiments/dep1ex01.clj.gz", "a" * 64, 1)])
    (entry,) = fetch.load_manifest(m)
    assert entry.url == "https://www.szcz.org/depexperiments/dep1ex01.clj.gz"


@pytest.mark.parametrize("row", [
    ("x", GH, C40, "p", "abc", 5),                 # sha256 not 64 hex
    ("x", GH, C40, "p", "a" * 64, "five"),         # bytes not int
    ("x", GH, "df6dc57", "p", "a" * 64, 5),        # commit not full 40-hex
    ("x", "example.com", "-", "p", "a" * 64, 5),   # unknown repository
    ("x", GH, C40, "p", "a" * 64),                 # missing column
])
def test_manifest_rejects_bad_rows(tmp_path, row):
    m = _manifest(tmp_path, [row])
    with pytest.raises(ValueError, match="manifest.tsv:2"):
        fetch.load_manifest(m)


def test_manifest_rejects_duplicate_names(tmp_path):
    r = ("x", GH, C40, "p", "a" * 64, 5)
    with pytest.raises(ValueError, match="duplicate"):
        fetch.load_manifest(_manifest(tmp_path, [r, r]))


def test_manifest_rejects_wrong_header(tmp_path):
    p = tmp_path / "manifest.tsv"
    p.write_text("name\trepo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header"):
        fetch.load_manifest(p)


def _entry(tmp_path, body, name="pequod-cljs@df6dc57/a.csv", repo=GH, commit=C40):
    m = _manifest(tmp_path, [(name, repo, commit, "src/a.csv", _sha(body), len(body))])
    return fetch.load_manifest(m)[0]


class _Opener:
    def __init__(self, body):
        self.body, self.calls = body, []

    def __call__(self, url, timeout=None):
        self.calls.append(url)
        return io.BytesIO(self.body)


def test_ensure_downloads_missing_file_into_cache(tmp_path):
    body = b"x" * 1000
    entry = _entry(tmp_path, body)
    roots = fetch.Roots(cache=tmp_path / "cache", data=tmp_path / "data")
    opener = _Opener(body)
    path = fetch.ensure(entry, roots, opener=opener)
    assert path == tmp_path / "cache" / "pequod-cljs@df6dc57" / "a.csv"
    assert path.read_bytes() == body
    assert opener.calls == [entry.url]


def test_ensure_szcz_file_lives_in_data_dir(tmp_path):
    body = b"gz"
    entry = _entry(tmp_path, body, name="dep1ex01.clj.gz", repo="www.szcz.org", commit="-")
    roots = fetch.Roots(cache=tmp_path / "cache", data=tmp_path / "data")
    path = fetch.ensure(entry, roots, opener=_Opener(body))
    assert path == tmp_path / "data" / "dep1ex01.clj.gz"


def test_ensure_existing_good_file_is_not_downloaded(tmp_path):
    body = b"abc"
    entry = _entry(tmp_path, body)
    roots = fetch.Roots(cache=tmp_path / "cache", data=tmp_path / "data")
    target = tmp_path / "cache" / "pequod-cljs@df6dc57" / "a.csv"
    target.parent.mkdir(parents=True)
    target.write_bytes(body)
    opener = _Opener(b"other")
    assert fetch.ensure(entry, roots, opener=opener) == target
    assert opener.calls == []


def test_ensure_existing_bad_file_raises_and_is_kept(tmp_path):
    entry = _entry(tmp_path, b"abc")
    roots = fetch.Roots(cache=tmp_path / "cache", data=tmp_path / "data")
    target = tmp_path / "cache" / "pequod-cljs@df6dc57" / "a.csv"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"abd")
    with pytest.raises(fetch.FetchError, match="sha256"):
        fetch.ensure(entry, roots, opener=_Opener(b"abc"))
    assert target.read_bytes() == b"abd"


def test_ensure_bad_download_leaves_no_file(tmp_path):
    entry = _entry(tmp_path, b"abc")
    roots = fetch.Roots(cache=tmp_path / "cache", data=tmp_path / "data")
    with pytest.raises(fetch.FetchError):
        fetch.ensure(entry, roots, opener=_Opener(b"abcd"))
    folder = tmp_path / "cache" / "pequod-cljs@df6dc57"
    assert not any(folder.iterdir()) if folder.exists() else True


def test_ensure_same_size_wrong_content_is_rejected(tmp_path):
    entry = _entry(tmp_path, b"abc")
    roots = fetch.Roots(cache=tmp_path / "cache", data=tmp_path / "data")
    with pytest.raises(fetch.FetchError, match="sha256") as info:
        fetch.ensure(entry, roots, opener=_Opener(b"abd"))
    assert _sha(b"abd") in str(info.value)
    assert not (tmp_path / "cache" / "pequod-cljs@df6dc57" / "a.csv").exists()


def test_real_manifest_parses_and_names_are_unique():
    entries = fetch.load_manifest(fetch.MANIFEST)
    names = {e.name for e in entries}
    for m in range(51, 101):
        assert f"pequod-cljs@df6dc57/dep1ex{m}.csv" in names
    for n in range(1, 41):
        assert f"dep1ex{n:02d}.clj.gz" in names
    assert {f"pequod-cljs@dbcc1f1/dep1ex{m}.clj" for m in [51, *range(60, 79)]} <= names
    assert "pequod-cljs@71e44d3/csvgen.clj" in names


def test_default_cache_is_the_upstream_directory_under_research_data():
    assert fetch.DEFAULT_CACHE == upstream_paths.REPO_ROOT / "research" / "data" / "upstream"


def test_git_blob_id_matches_git_hash_object(tmp_path):
    path = tmp_path / "f.csv"
    path.write_bytes(b"a,b\r\n1,2\n")
    expected = subprocess.run(["git", "hash-object", "--no-filters", str(path)],
                              capture_output=True, text=True, check=True).stdout.strip()
    assert fetch.git_blob_id(path) == expected
