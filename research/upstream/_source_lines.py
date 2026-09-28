"""Lines of upstream source files to print, described without the files' text.

A listing is a JSON file naming a repository, a commit and, per file, the lines a script prints
from it:

    {
      "description": "what the lines are printed for",
      "repository": "owner/name",
      "commit": "<40 hex digits>",
      "files": {
        "path/in/the/repository": [
          {"line": 110, "line_sha256": "<64 hex digits>"},
          {"line": 175, "line_sha256": "<64 hex digits>", "columns": [361, 394]}
        ]
      }
    }

``line`` counts from 1, and the lines of a file are listed in increasing order.
``line_sha256`` is the sha256 of the line as committed, computed as ``_source_edits`` computes
it: the line's bytes, indentation included, without the line feed that ends it. ``columns``,
when given, prints only the characters ``first`` to ``last`` of the line, counted from 1, for a
line too long to print whole. The upstream text itself is never stored.

:func:`render` checks every listed line against its hash before it prints any, and raises
:class:`SourceLineError` naming the commit, the file and each line that differs.
"""
from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path
from typing import Any, Mapping

from _source_edits import line_sha256

_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_TOP_KEYS = {"description", "repository", "commit", "files"}
_LINE_KEYS = {"line", "line_sha256", "columns"}
LINE_WIDTH = 160
"""Printed lines longer than this many characters are cut and end in `` ...``."""


class SourceLineError(Exception):
    """A listing is malformed, or does not fit the files it is checked against."""


@dataclasses.dataclass(frozen=True)
class ListedLine:
    """One line to print and the hash it must have."""

    line: int
    line_sha256: str
    columns: tuple[int, int] | None
    """First and last character to print, counted from 1; ``None`` prints the whole line."""


@dataclasses.dataclass(frozen=True)
class ListedFile:
    """The listed lines of one file, in increasing order."""

    file: str
    """Path of the file within the repository, with forward slashes."""
    lines: tuple[ListedLine, ...]


@dataclasses.dataclass(frozen=True)
class Listing:
    """The lines to print from the files of one repository at one commit."""

    description: str
    repository: str
    commit: str
    files: tuple[ListedFile, ...]


def load(path: Path) -> Listing:
    """Read and validate the listing in the JSON file ``path``."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SourceLineError(f"{path}: not valid JSON: {error}") from error
    return parse(document)


def parse(document: Any) -> Listing:
    """Validate a decoded listing and return it; raise :class:`SourceLineError` naming the first fault."""
    _require_keys(document, _TOP_KEYS, _TOP_KEYS, "listing")
    for key in ("description", "repository"):
        _require_text(document[key], key)
    if not _COMMIT.fullmatch(_require_text(document["commit"], "commit")):
        raise SourceLineError(f"commit must be 40 lower-case hex digits, got {document['commit']!r}")
    files = document["files"]
    if not isinstance(files, dict) or not files:
        raise SourceLineError("files must be a non-empty object from file paths to lists of lines")
    return Listing(document["description"], document["repository"], document["commit"],
                   tuple(_parse_file(path, entries) for path, entries in files.items()))


def _parse_file(path: str, entries: Any) -> ListedFile:
    """The listed lines of one file; they must be a non-empty list in increasing line order."""
    if not isinstance(entries, list) or not entries:
        raise SourceLineError(f"files[{path!r}] must be a non-empty list of lines")
    lines = tuple(_parse_line(entry, f"files[{path!r}][{index}]") for index, entry in enumerate(entries))
    numbers = [entry.line for entry in lines]
    if any(later <= earlier for earlier, later in zip(numbers, numbers[1:])):
        raise SourceLineError(f"files[{path!r}]: line numbers must be strictly increasing, got {numbers}")
    return ListedFile(path, lines)


def _parse_line(entry: Any, where: str) -> ListedLine:
    """One entry of a file's list: a line number, the line's hash and optionally a column range."""
    _require_keys(entry, {"line", "line_sha256"}, _LINE_KEYS, where)
    line = entry["line"]
    if not _is_count(line):
        raise SourceLineError(f"{where}.line must be an integer of at least 1, got {line!r}")
    digest = entry["line_sha256"]
    if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
        raise SourceLineError(f"{where}.line_sha256 must be 64 lower-case hex digits, got {digest!r}")
    columns = entry.get("columns")
    if columns is not None:
        if (not isinstance(columns, list) or len(columns) != 2 or not all(map(_is_count, columns))
                or columns[0] > columns[1]):
            raise SourceLineError(f"{where}.columns must be [first, last] with 1 <= first <= last, got {columns!r}")
        columns = (columns[0], columns[1])
    return ListedLine(line, digest, columns)


def _is_count(value: Any) -> bool:
    """Whether ``value`` is an integer of at least 1; ``True`` and ``False`` are not."""
    # bool is a subclass of int; true would otherwise read as 1
    return type(value) is int and value >= 1


def _require_keys(value: Any, required: set[str], allowed: set[str], where: str) -> None:
    """Raise unless ``value`` is an object holding every key of ``required`` and no key outside ``allowed``."""
    if not isinstance(value, dict):
        raise SourceLineError(f"{where} must be a JSON object")
    missing = required - value.keys()
    unknown = value.keys() - allowed
    if missing or unknown:
        raise SourceLineError(f"{where}: missing keys {sorted(missing)}, unknown keys {sorted(unknown)}")


def _require_text(value: Any, where: str) -> str:
    """``value`` when it is a non-empty string; raise otherwise."""
    if not isinstance(value, str) or not value:
        raise SourceLineError(f"{where} must be a non-empty string")
    return value


def render(listing: Listing, committed: Mapping[str, bytes], shown: Mapping[str, bytes] | None = None,
           width: int = LINE_WIDTH) -> list[str]:
    """The listed lines as ``path:number:text``, after every one of them has been checked.

    ``committed`` maps each listed path to the file's bytes at the listing's commit; every
    listed line of it must exist and have the recorded hash. ``shown`` maps the same paths to
    the bytes the lines are printed from, and defaults to ``committed``; it differs for a file
    edited after checkout, whose edited lines are printed as edited while the hashes are
    checked on the committed file. A line with ``columns`` prints only those characters. A
    printed line longer than ``width`` characters is cut there and ends in `` ...``.

    Raises :class:`SourceLineError` naming the commit and every line that is missing or whose
    hash differs, before printing anything.
    """
    shown = committed if shown is None else shown
    faults, printed = [], []
    for listed in listing.files:
        if listed.file not in committed or listed.file not in shown:
            faults.append(f"{listed.file} was not given")
            continue
        committed_lines = _split_lines(committed[listed.file])
        shown_lines = _split_lines(shown[listed.file])
        for entry in listed.lines:
            fault = _fault(listed.file, entry, committed_lines, shown_lines)
            if fault:
                faults.append(fault)
                continue
            printed.append(_cut(_printed_line(listed.file, entry, shown_lines[entry.line - 1]), width))
    if faults:
        raise SourceLineError(f"{listing.repository} at {listing.commit}: " + "; ".join(faults))
    return printed


def _split_lines(source: bytes) -> list[bytes]:
    """The lines of ``source`` without their line feeds; text after the final line feed is a
    line only when it is not empty."""
    lines = source.split(b"\n")
    return lines[:-1] if lines[-1] == b"" else lines


def _fault(file: str, entry: ListedLine, committed: list[bytes], shown: list[bytes]) -> str | None:
    """Why ``entry`` cannot be printed, or ``None`` when it can."""
    if entry.line > len(committed):
        return f"{file} line {entry.line} is past the end of the file ({len(committed)} lines)"
    found = line_sha256(committed[entry.line - 1])
    if found != entry.line_sha256:
        return f"{file} line {entry.line}: sha256 {found}, the listing expects {entry.line_sha256}"
    if entry.line > len(shown):
        return f"{file} line {entry.line} is past the end of the file printed ({len(shown)} lines)"
    if entry.columns and entry.columns[1] > len(shown[entry.line - 1].decode("utf-8")):
        first, last = entry.columns
        return (f"{file} line {entry.line}: columns {first}-{last} run past the end of the line "
                f"({len(shown[entry.line - 1].decode('utf-8'))} characters)")
    return None


def _printed_line(file: str, entry: ListedLine, line: bytes) -> str:
    """``path:number:text``, or ``path:number: columns first-last: text`` for a column range."""
    text = line.decode("utf-8")
    if entry.columns is None:
        return f"{file}:{entry.line}:{text}"
    first, last = entry.columns
    return f"{file}:{entry.line}: columns {first}-{last}: {text[first - 1:last]}"


def _cut(text: str, width: int) -> str:
    """``text``, or its first ``width`` characters followed by `` ...`` when it is longer."""
    return text if len(text) <= width else text[:width] + " ..."
