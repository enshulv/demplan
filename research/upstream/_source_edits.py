"""Line edits to an upstream source file, described without the file's text.

An edit set is a JSON file naming a repository, a commit, one file and the lines to change:

    {
      "description": "why the lines change",
      "repository": "owner/name",
      "commit": "<40 hex digits>",
      "file": "path/in/the/repository",
      "edits": [
        {"line": 719, "line_sha256": "<64 hex digits>", "replace_line": "new text"},
        {"line": 228, "line_sha256": "<64 hex digits>", "replace_once": {"old": "a", "new": "b"}}
      ]
    }

``line`` counts from 1. ``line_sha256`` is the sha256 of the line as it is before the edit: its
bytes, indentation included, without the line feed that ends it. The upstream text itself is
never stored.

- ``replace_line`` replaces the whole line with the given text, after the original line's
  indentation (its leading spaces and tabs).
- ``replace_once`` replaces ``old`` with ``new`` within the line; ``old`` must occur on it
  exactly once.

`apply` checks every line's hash before it changes anything, and raises `SourceEditError` on the
first check that fails. Every byte outside the edited lines, line endings included, is kept.
"""
from __future__ import annotations

import dataclasses
import difflib
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Union

_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_INDENTATION = re.compile(rb"[ \t]*")
_TOP_KEYS = {"description", "repository", "commit", "file", "edits"}
_EDIT_KINDS = ("replace_line", "replace_once")
_LINE_BREAKS = ("\n", "\r")


class SourceEditError(Exception):
    """An edit set is malformed, or does not fit the source it is applied to."""


@dataclasses.dataclass(frozen=True)
class ReplaceLine:
    """Replace a whole line, keeping its indentation."""

    line: int
    line_sha256: str
    text: str
    """The new line without indentation."""


@dataclasses.dataclass(frozen=True)
class ReplaceOnce:
    """Replace the one occurrence of ``old`` on a line with ``new``."""

    line: int
    line_sha256: str
    old: str
    new: str


LineEdit = Union[ReplaceLine, ReplaceOnce]


@dataclasses.dataclass(frozen=True)
class EditSet:
    """The edits to one file of one repository at one commit."""

    description: str
    repository: str
    commit: str
    file: str
    """Path of the file within the repository, with forward slashes."""
    edits: tuple[LineEdit, ...]


def load(path: Path) -> EditSet:
    """Read and validate the edit set in the JSON file ``path``."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SourceEditError(f"{path}: not valid JSON: {error}") from error
    return parse(document)


def parse(document: Any) -> EditSet:
    """Validate a decoded edit set and return it; raise `SourceEditError` naming the first fault."""
    require_keys(document, _TOP_KEYS, _TOP_KEYS, "edit set")
    for key in ("description", "repository", "file"):
        require_text(document[key], key)
    if not _COMMIT.fullmatch(require_text(document["commit"], "commit")):
        raise SourceEditError(f"commit must be 40 lower-case hex digits, got {document['commit']!r}")
    raw_edits = document["edits"]
    if not isinstance(raw_edits, list) or not raw_edits:
        raise SourceEditError("edits must be a non-empty list")
    edits = tuple(_parse_edit(raw, i) for i, raw in enumerate(raw_edits))
    lines = [edit.line for edit in edits]
    if len(set(lines)) != len(lines):
        raise SourceEditError(f"a line is edited more than once: {lines}")
    return EditSet(document["description"], document["repository"], document["commit"], document["file"], edits)


def _parse_edit(raw: Any, index: int) -> LineEdit:
    """One entry of ``edits``: a line number, the line's hash and exactly one kind of edit."""
    where = f"edits[{index}]"
    require_keys(raw, {"line", "line_sha256"}, {"line", "line_sha256", *_EDIT_KINDS}, where)
    line = raw["line"]
    # bool is a subclass of int; true would otherwise read as line 1
    if type(line) is not int or line < 1:
        raise SourceEditError(f"{where}.line must be an integer of at least 1, got {line!r}")
    line_sha256 = raw["line_sha256"]
    if not isinstance(line_sha256, str) or not _SHA256.fullmatch(line_sha256):
        raise SourceEditError(f"{where}.line_sha256 must be 64 lower-case hex digits, got {line_sha256!r}")
    kinds = [kind for kind in _EDIT_KINDS if kind in raw]
    if len(kinds) != 1:
        raise SourceEditError(f"{where} needs exactly one of {', '.join(_EDIT_KINDS)}, has {kinds}")
    if kinds[0] == "replace_line":
        text = _require_single_line(raw["replace_line"], f"{where}.replace_line")
        if text != text.lstrip(" \t"):
            raise SourceEditError(f"{where}.replace_line starts with indentation; the original line's is kept")
        return ReplaceLine(line, line_sha256, text)
    pair = raw["replace_once"]
    require_keys(pair, {"old", "new"}, {"old", "new"}, f"{where}.replace_once")
    old = _require_single_line(pair["old"], f"{where}.replace_once.old")
    new = _require_single_line(pair["new"], f"{where}.replace_once.new", allow_empty=True)
    if old == new:
        raise SourceEditError(f"{where}.replace_once replaces {old!r} with itself")
    return ReplaceOnce(line, line_sha256, old, new)


def require_keys(value: Any, required: set[str], allowed: set[str], where: str,
                 error: type[Exception] = SourceEditError) -> None:
    """Raise ``error`` unless ``value`` is an object holding every key of ``required`` and no key
    outside ``allowed``."""
    if not isinstance(value, dict):
        raise error(f"{where} must be a JSON object")
    missing = required - value.keys()
    unknown = value.keys() - allowed
    if missing or unknown:
        raise error(f"{where}: missing keys {sorted(missing)}, unknown keys {sorted(unknown)}")


def require_text(value: Any, where: str, error: type[Exception] = SourceEditError) -> str:
    """``value`` when it is a non-empty string; raise ``error`` otherwise."""
    if not isinstance(value, str) or not value:
        raise error(f"{where} must be a non-empty string")
    return value


def _require_single_line(value: Any, where: str, allow_empty: bool = False) -> str:
    """``value`` when it is a string without line breaks, non-empty unless ``allow_empty``."""
    if not isinstance(value, str) or not (value or allow_empty):
        raise SourceEditError(f"{where} must be a {'string' if allow_empty else 'non-empty string'}")
    if any(mark in value for mark in _LINE_BREAKS):
        raise SourceEditError(f"{where} must not contain a line break")
    return value


def line_sha256(line: bytes) -> str:
    """The hash an edit records for ``line``, given without its line feed."""
    return hashlib.sha256(line).hexdigest()


def apply(edit_set: EditSet, source: bytes) -> bytes:
    """``source`` with every edit of ``edit_set`` made.

    Raises `SourceEditError`, naming the file and line, when a line does not exist, its hash
    differs from the recorded one, ``replace_once`` finds its text other than exactly once, or
    an edit would leave its line unchanged.
    """
    lines = source.split(b"\n")
    # The text after the final line feed is not a line when it is empty.
    line_count = len(lines) - 1 if lines[-1] == b"" else len(lines)
    for edit in edit_set.edits:
        _check_line(edit_set.file, edit, lines, line_count)
    for edit in edit_set.edits:
        lines[edit.line - 1] = _edited_line(edit_set.file, edit, lines[edit.line - 1])
    return b"\n".join(lines)


def _check_line(file: str, edit: LineEdit, lines: list[bytes], line_count: int) -> None:
    """Raise unless the edited line exists and hashes to the recorded value."""
    if edit.line > line_count:
        raise SourceEditError(f"{file} line {edit.line} is past the end of the file ({line_count} lines)")
    found = line_sha256(lines[edit.line - 1])
    if found != edit.line_sha256:
        raise SourceEditError(
            f"{file} line {edit.line}: sha256 {found}, the edit expects {edit.line_sha256}; "
            "the file is not the version the edit was written for"
        )


def _edited_line(file: str, edit: LineEdit, line: bytes) -> bytes:
    """The new content of ``line`` under ``edit``."""
    if isinstance(edit, ReplaceLine):
        indentation = _INDENTATION.match(line).group()
        edited = indentation + edit.text.encode("utf-8")
    else:
        old = edit.old.encode("utf-8")
        occurrences = line.count(old)
        if occurrences != 1:
            raise SourceEditError(f"{file} line {edit.line}: {edit.old!r} occurs {occurrences} times, not once")
        edited = line.replace(old, edit.new.encode("utf-8"))
    if edited == line:
        raise SourceEditError(f"{file} line {edit.line}: the edit leaves the line unchanged")
    return edited


def summary(edit_set: EditSet) -> str:
    """One line naming the file, the commit and the edited lines, for a script to print once
    `apply` has succeeded."""
    numbers = ", ".join(str(edit.line) for edit in edit_set.edits)
    noun = "line" if len(edit_set.edits) == 1 else "lines"
    return f"{edit_set.file} at {edit_set.commit[:7]}, {noun} {numbers}: sha256 as recorded, edited"


def unified_diff(edit_set: EditSet, before: bytes, after: bytes) -> str:
    """The changes from ``before`` to ``after`` as a unified diff without context lines, headed
    ``a/<file>`` and ``b/<file>``; empty when the two are equal. Both are decoded as UTF-8."""
    old = before.decode("utf-8").split("\n")
    new = after.decode("utf-8").split("\n")
    lines = difflib.unified_diff(old, new, f"a/{edit_set.file}", f"b/{edit_set.file}", n=0, lineterm="")
    return "".join(f"{line}\n" for line in lines)
