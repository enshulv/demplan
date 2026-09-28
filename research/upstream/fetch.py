"""
Downloads the upstream files listed in manifest.tsv and checks each against its recorded sha256.

Every file is taken at a fixed commit:

  msszczep/pequod-cljs   https://raw.githubusercontent.com/<repository>/<commit>/<path>
  www.szcz.org           https://www.szcz.org/<path> (the public dep1ex archives; no commit)

A file already on disk is hashed and not downloaded again. A file whose size or sha256 differs
from the manifest stops the run with an error; the file is left in place for inspection, and
deleting it makes the next run download it again.

Where files go:

  --cache DIR     the pequod-cljs files, under <name> (default research/data/upstream)
  --data-dir DIR  the szcz.org archives dep1exNN.clj.gz (default $DEMPLAN_DATA_DIR, or
                  research/data), the directory research/bench reads them from, so one copy
                  serves both

The raw endpoint serves a Git LFS file as its pointer text, not the object it points to. The
dep1exMM.clj entries are those pointers: three lines giving the sha256 and size of the input
file the program read.

Usage:
  python research/upstream/fetch.py [--cache DIR] [--data-dir DIR] [NAME_PREFIX ...]

With no NAME_PREFIX, every file in the manifest; otherwise the entries whose name starts with
one of the prefixes, for example ``pequod-cljs@df6dc57/dep1ex61`` or ``dep1ex0``.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Callable, Iterable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = HERE / "manifest.tsv"
DEFAULT_CACHE = ROOT / "research" / "data" / "upstream"
DEFAULT_DATA = Path(os.environ.get("DEMPLAN_DATA_DIR", ROOT / "research" / "data"))

COLUMNS = ("name", "repository", "commit", "path", "sha256", "bytes")
GITHUB_REPOSITORIES = ("msszczep/pequod-cljs",)
SZCZ = "www.szcz.org"
NO_COMMIT = "-"

CHUNK_BYTES = 1 << 20
DOWNLOAD_ATTEMPTS = 3
RETRY_PAUSE_SECONDS = 5
TIMEOUT_SECONDS = 120

_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")


class FetchError(Exception):
    """A file could not be obtained, or does not match the manifest."""


@dataclasses.dataclass(frozen=True)
class Entry:
    """One manifest row: where a file comes from and what it must hash to."""

    name: str
    """Path of the local copy, relative to the directory its repository is stored under."""
    repository: str
    commit: str
    path: str
    sha256: str
    size: int

    @property
    def url(self) -> str:
        """The address the file is downloaded from, pinned to the commit where there is one."""
        if self.repository == SZCZ:
            return f"https://{SZCZ}/{self.path}"
        return f"https://raw.githubusercontent.com/{self.repository}/{self.commit}/{self.path}"

    @property
    def source(self) -> str:
        """Repository, commit and path, as printed next to a figure taken from the file."""
        if self.repository == SZCZ:
            return self.url
        return f"{self.repository}@{self.commit[:7]}:{self.path}"


@dataclasses.dataclass(frozen=True)
class Roots:
    """The two directories local copies live under."""

    cache: Path
    """pequod-cljs files."""
    data: Path
    """The szcz.org dep1ex archives."""

    def local_path(self, entry: Entry) -> Path:
        """Where the copy of ``entry`` is kept."""
        root = self.data if entry.repository == SZCZ else self.cache
        return root / entry.name


def load_manifest(path: Path = MANIFEST) -> list[Entry]:
    """Every row of the manifest, in file order.

    Raises ``ValueError`` naming the file and line when the header is not the expected one, a
    row does not have six tab-separated fields, a field is malformed (sha256 not 64 lower-case
    hex digits, commit not 40, byte count not an integer), the repository is not one this
    script knows, or a name repeats.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or tuple(lines[0].split("\t")) != COLUMNS:
        raise ValueError(f"{path.name}: header must be {' '.join(COLUMNS)} separated by tabs")
    entries, seen = [], set()
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        entry = _parse_row(line, f"{path.name}:{number}")
        if entry.name in seen:
            raise ValueError(f"{path.name}:{number}: duplicate name {entry.name}")
        seen.add(entry.name)
        entries.append(entry)
    return entries


def _parse_row(line: str, where: str) -> Entry:
    """One manifest line as an :class:`Entry`; ``where`` prefixes every error message."""
    fields = line.split("\t")
    if len(fields) != len(COLUMNS):
        raise ValueError(f"{where}: expected {len(COLUMNS)} tab-separated fields, got {len(fields)}")
    name, repository, commit, path, sha256, size = fields
    if repository == SZCZ:
        if commit != NO_COMMIT:
            raise ValueError(f"{where}: {SZCZ} files have no commit; write {NO_COMMIT}")
    elif repository in GITHUB_REPOSITORIES:
        if not _COMMIT.fullmatch(commit):
            raise ValueError(f"{where}: commit must be the full 40-digit hash, got {commit!r}")
    else:
        raise ValueError(f"{where}: unknown repository {repository!r}")
    if not _SHA256.fullmatch(sha256):
        raise ValueError(f"{where}: sha256 must be 64 lower-case hex digits, got {sha256!r}")
    if not size.isdigit():
        raise ValueError(f"{where}: bytes must be a non-negative integer, got {size!r}")
    return Entry(name, repository, commit, path, sha256, int(size))


def ensure(
    entry: Entry,
    roots: Roots,
    opener: Callable = urllib.request.urlopen,
    report: Callable[[str], None] | None = None,
) -> Path:
    """The local copy of ``entry``, downloaded first if it is not there, checked either way.

    A download goes to ``<name>.part`` and is renamed only after its size and sha256 match;
    a download that does not match is removed. ``opener(url, timeout=...)`` returns a
    readable binary stream (``urllib.request.urlopen`` by default). ``report`` receives one
    line per file saying what was done.

    Raises :class:`FetchError` when an existing copy does not match (the copy is kept), or
    when every download attempt fails or does not match.
    """
    target = roots.local_path(entry)
    if target.exists():
        problem = _mismatch(entry, target)
        if problem:
            raise FetchError(f"{target}: {problem} ({entry.source}); "
                             "delete the file to download it again")
        if report:
            report(f"verified    {entry.name}  {entry.size} bytes  sha256 {entry.sha256[:16]}")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    problem = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            _download(entry.url, partial, opener)
        except OSError as error:
            partial.unlink(missing_ok=True)
            problem = error
            if attempt < DOWNLOAD_ATTEMPTS:
                time.sleep(RETRY_PAUSE_SECONDS)
            continue
        mismatch = _mismatch(entry, partial)
        if mismatch:
            partial.unlink()
            raise FetchError(f"{entry.name}: the file served at {entry.url} does not match "
                             f"the manifest: {mismatch}")
        partial.replace(target)
        if report:
            report(f"downloaded  {entry.name}  {entry.size} bytes  sha256 {entry.sha256[:16]}"
                   f"  from {entry.url}")
        return target
    raise FetchError(f"{entry.name}: download from {entry.url} failed "
                     f"{DOWNLOAD_ATTEMPTS} times: {problem}")


def _download(url: str, destination: Path, opener: Callable) -> None:
    """Stream ``url`` into ``destination``."""
    with opener(url, timeout=TIMEOUT_SECONDS) as response, open(destination, "wb") as out:
        while chunk := response.read(CHUNK_BYTES):
            out.write(chunk)


def _mismatch(entry: Entry, path: Path) -> str | None:
    """How ``path`` differs from the manifest's size and sha256, or ``None`` if it does not."""
    size = path.stat().st_size
    if size != entry.size:
        return f"{size} bytes, manifest says {entry.size}"
    digest = sha256_of(path)
    if digest != entry.sha256:
        return f"sha256 {digest}, manifest says {entry.sha256}"
    return None


def sha256_of(path: Path) -> str:
    """The sha256 of a file, read in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def git_blob_id(path: Path) -> str:
    """The id git gives the file's content as a blob: sha1 of ``blob <size>\\0`` and the bytes.

    ``git ls-tree <commit> <path>`` prints the same id for the file as committed, so a copy
    can be matched with a repository's tree without downloading the repository.
    """
    digest = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
    with open(path, "rb") as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def select(entries: list[Entry], prefixes: Iterable[str]) -> list[Entry]:
    """The entries whose name starts with one of ``prefixes``; all of them when there is none."""
    prefixes = tuple(prefixes)
    if not prefixes:
        return list(entries)
    return [e for e in entries if e.name.startswith(prefixes)]


class Store:
    """The manifest together with the two directories, for the check scripts.

    ``path(name)`` returns the verified local copy of one manifest entry, downloading it when
    it is missing, and prints what it did.
    """

    def __init__(self, roots: Roots, manifest: Path = MANIFEST):
        """Read the manifest; no file is touched until :meth:`path` asks for it."""
        self.roots = roots
        self.entries = {e.name: e for e in load_manifest(manifest)}

    def entry(self, name: str) -> Entry:
        """The manifest entry called ``name``; ``KeyError`` names it when there is none."""
        if name not in self.entries:
            raise KeyError(f"{name} is not in {MANIFEST.name}")
        return self.entries[name]

    def path(self, name: str) -> Path:
        """The checked local copy of the entry called ``name``."""
        return ensure(self.entry(name), self.roots, report=lambda line: print(f"  {line}", flush=True))


def add_location_arguments(parser: argparse.ArgumentParser) -> None:
    """The ``--cache`` and ``--data-dir`` options every script in this directory takes."""
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE,
                        help=f"directory for the pequod-cljs files (default {DEFAULT_CACHE})")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA,
                        help="directory holding dep1exNN.clj.gz (default $DEMPLAN_DATA_DIR, "
                             f"or {ROOT / 'research' / 'data'})")


def roots_from(args: argparse.Namespace) -> Roots:
    """The :class:`Roots` the parsed ``--cache`` and ``--data-dir`` name."""
    return Roots(cache=args.cache, data=args.data_dir)


def main(argv: list[str]) -> int:
    """Ensure the selected files; exit status 1 if any does not match the manifest."""
    # Paths may hold non-ASCII characters; a Windows console or pipe defaults to a legacy code page.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=__doc__.strip().split("\n\n")[0],
        epilog="See the module docstring for where each file comes from.")
    add_location_arguments(parser)
    parser.add_argument("prefixes", nargs="*", metavar="NAME_PREFIX",
                        help="only the manifest entries whose name starts with this")
    args = parser.parse_args(argv)
    roots = roots_from(args)
    chosen = select(load_manifest(), args.prefixes)
    if not chosen:
        print(f"no manifest entry starts with {' or '.join(args.prefixes)}", file=sys.stderr)
        return 1
    print(f"manifest {MANIFEST.name}: {len(chosen)} files; cache {roots.cache}; data {roots.data}")
    failures = []
    for entry in chosen:
        try:
            ensure(entry, roots, report=lambda line: print(line, flush=True))
        except FetchError as error:
            failures.append(str(error))
            print(f"FAILED      {error}", flush=True)
    total = sum(e.size for e in chosen)
    print(f"{len(chosen) - len(failures)} of {len(chosen)} files match the manifest "
          f"({total / 1e6:.0f} MB in all)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
