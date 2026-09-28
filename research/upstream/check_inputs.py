"""
Compares the public dep1ex input archives with the input files the pequod-cljs repository records.

The repository keeps its large input files dep1exMM.clj in Git LFS: what is committed is a
pointer giving the sha256 and size of the file. Each public archive dep1exNN.clj.gz from
www.szcz.org decompresses to a Clojure file whose first line is its namespace,
``(ns pequod-cljs.dep1exNN)``. For every archive N and every pointer M, the first line is
replaced by ``(ns pequod-cljs.dep1exMM)`` and the sha256 and size of the result are compared
with pointer M. Every pair is computed, so each archive is checked against the pointer it
should match and against all the others.

The pointers are those present at commit dbcc1f1 (2020-06-25), the last of the commits that
added them; they are unchanged at 8bd46b5, the latest commit when this script was written.
The script also asks the raw endpoint for the file names dep1ex52.clj to dep1ex59.clj and
dep1ex79.clj to dep1ex100.clj at both commits and prints the HTTP status, after asking for
dep1ex61.clj, which exists.

Usage:
  python research/upstream/check_inputs.py [--experiments 1-40] [--no-probe]
                                           [--cache DIR] [--data-dir DIR]

Missing files are downloaded and every file is checked against manifest.tsv (see fetch.py).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import sys
import time
import urllib.error
import urllib.request

import _experiments
import fetch

POINTER_COMMIT = "dbcc1f191fa6da3ba4f3a15968c7ee7bfe49e856"
LATEST_COMMIT = "8bd46b5c233f0e48c767ad6d5069b9437a67c38b"
POINTERS = (51, *range(60, 79))
ABSENT = (*range(52, 60), *range(79, 101))
PRESENT_PROBE = 61
"""A pointer name that exists, probed first so that a 404 below is not a network failure."""
REPOSITORY = "msszczep/pequod-cljs"
POINTER_PATH = "src/clj/pequod_cljs/dep1ex{m}.clj"
LFS_VERSION = "version https://git-lfs.github.com/spec/v1"
PROBE_TIMEOUT_SECONDS = 30


def namespace_line(number: int) -> bytes:
    """The first line of input file ``dep1ex<number>``, as the program's generator writes it."""
    return f"(ns pequod-cljs.dep1ex{number:02d})".encode()


def read_pointer(text: str, where: str) -> tuple[str, int]:
    """``(sha256, size)`` from the text of a Git LFS pointer; ``ValueError`` if it is not one."""
    fields = dict(line.split(" ", 1) for line in text.strip().splitlines())
    if f"version {fields.get('version')}" != LFS_VERSION or not fields.get("oid", "").startswith("sha256:"):
        raise ValueError(f"{where} is not a Git LFS pointer")
    return fields["oid"].removeprefix("sha256:"), int(fields["size"])


def renamed_digests(body: bytes, pointers: dict[int, tuple[str, int]]) -> dict[int, tuple[str, int]]:
    """For each pointer number M, sha256 and size of ``body`` with its first line set to M's namespace."""
    rest = memoryview(body)[body.index(b"\n"):]
    out = {}
    for m in pointers:
        digest = hashlib.sha256(namespace_line(m))
        digest.update(rest)
        out[m] = (digest.hexdigest(), len(namespace_line(m)) + len(rest))
    return out


def hits_of(digests: dict[int, tuple[str, int]], pointers: dict[int, tuple[str, int]]) -> list[int]:
    """The pointer numbers whose sha256 and size both equal the renamed file's (``digests``, as
    :func:`renamed_digests` returns them)."""
    return [m for m, pair in digests.items() if pair == pointers[m]]


def expected_hits(experiments, pointer_numbers) -> dict[int, list[int]]:
    """Per book experiment N, the hits the numbering N -> 60 + N predicts: ``[60 + N]`` where
    that pointer exists, none otherwise."""
    present = set(pointer_numbers)
    return {n: [_experiments.output_number(n)] if _experiments.output_number(n) in present else []
            for n in experiments}


def unexpected_hits(hits: dict[int, list[int]], expected: dict[int, list[int]]) -> dict[int, list[int]]:
    """The experiments whose hits are not exactly the expected ones, with the hits found."""
    return {n: found for n, found in hits.items() if found != expected[n]}


def probe(commit: str, number: int) -> str:
    """HTTP status of the raw endpoint for ``dep1ex<number>.clj`` at ``commit``."""
    url = f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}/{POINTER_PATH.format(m=number)}"
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=PROBE_TIMEOUT_SECONDS) as response:
            return str(response.status)
    except urllib.error.HTTPError as error:
        return str(error.code)
    except OSError as error:
        return f"error: {error}"


def main(argv: list[str]) -> int:
    """Print the pointers, each archive's hashes, the hit matrix and the probes; exit status 0."""
    # Paths may hold non-ASCII characters; a Windows console or pipe defaults to a legacy code page.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.strip().split("\n\n")[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="\n\n".join(__doc__.strip().split("\n\n")[1:]))
    _experiments.add_experiments_argument(parser)
    parser.add_argument("--no-probe", action="store_true",
                        help="skip asking the raw endpoint for the pointer names not in the manifest")
    fetch.add_location_arguments(parser)
    args = parser.parse_args(argv)
    started = time.perf_counter()
    store = fetch.Store(fetch.roots_from(args))

    print(f"LFS pointers of {REPOSITORY} at {POINTER_COMMIT[:7]} (pinned in manifest.tsv):")
    pointers = {}
    for m in POINTERS:
        name = f"pequod-cljs@dbcc1f1/dep1ex{m}.clj"
        pointers[m] = read_pointer(store.path(name).read_text(encoding="ascii"), name)
    print(f"  {'M':>3}  {'size':>10}  sha256")
    for m, (oid, size) in pointers.items():
        print(f"  {m:>3}  {size:>10}  {oid}")

    print("\nPublic archives: first line, size and sha256 as published (decompressed), then the")
    print("pointers M whose sha256 and size equal the file with its first line set to M's namespace.")
    hits: dict[int, list[int]] = {}
    size_hits: dict[int, list[int]] = {}
    for n in args.experiments:
        entry = store.entry(_experiments.archive_name(n))
        body = gzip.decompress(store.path(entry.name).read_bytes())
        first = body[:body.index(b"\n")]
        if first != namespace_line(n):
            print(f"  dep1ex{n:02d}: first line is {first!r}, expected {namespace_line(n)!r}")
            return 1
        digests = renamed_digests(body, pointers)
        hits[n] = hits_of(digests, pointers)
        size_hits[n] = [m for m, (_, size) in digests.items() if size == pointers[m][1]]
        published = hashlib.sha256(body).hexdigest()
        unchanged = [m for m, (oid, size) in pointers.items() if (published, len(body)) == (oid, size)]
        print(f"  dep1ex{n:02d}  {first.decode()}  {len(body):>10} bytes  {published}")
        print(f"           renamed: sha256 and size equal for M = {hits[n] or 'none'}; "
              f"size alone equal for M = {size_hits[n] or 'none'}; "
              f"as published (not renamed): {unchanged or 'none'}", flush=True)

    print("\nHit matrix: row N = archive dep1exNN, column M = pointer dep1exMM.clj; "
          "# = sha256 and size equal, . = not equal")
    print("       " + " ".join(f"{m:>2}" for m in POINTERS))
    for n in args.experiments:
        print(f"  {n:>3}  " + " ".join(f"{'#' if m in hits[n] else '.':>2}" for m in POINTERS))

    expected = expected_hits(args.experiments, POINTERS)
    unexpected = unexpected_hits(hits, expected)
    print(f"\nArchives whose hits are exactly [60 + N] where that pointer exists and none otherwise: "
          f"{len(args.experiments) - len(unexpected)} of {len(args.experiments)}")
    for n, found in unexpected.items():
        print(f"  dep1ex{n:02d}: hits {found}, expected {expected[n]}")

    if not args.no_probe:
        print(f"\nRaw endpoint, HTTP status for the pointer names not in the manifest "
              f"({POINTER_PATH.format(m='MM')}), after pointer {PRESENT_PROBE}, which is there:")
        print(f"  {'M':>3}  {POINTER_COMMIT[:7]:>8}  {LATEST_COMMIT[:7]:>8}")
        for m in (PRESENT_PROBE, *ABSENT):
            print(f"  {m:>3}  {probe(POINTER_COMMIT, m):>8}  {probe(LATEST_COMMIT, m):>8}", flush=True)

    print(f"\nwall seconds: {time.perf_counter() - started:.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
