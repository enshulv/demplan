"""The run configuration document: the settings of one run, in a file it can be read back from.

A configuration document is an input, not a record. A run writes one, and whoever wants to
repeat that run feeds the same file back rather than working through a paper's methods section
by hand. The run manifest is the other half of the pair and holds provenance, which is read
rather than loaded; the two are separate files so that loading one cannot feed the last run's
results back in as settings.

What the library owns, it fills in: the economy's content digest, the seed, the version of the
library and of its core, and, for a coordination procedure the library ships, the module that
defines it together with the digest of that module's source. A procedure the researcher wrote
gets no source digest, because his version control is a better record of his code than a
digest taken here would be; his block carries ``"declared_origin": null`` instead. The key is
present and the value is null, because a document that simply left the key out would read as a
document that had nothing to say rather than as one saying nobody declared an origin.

Parameters are recorded either way, under the same rules. They are data rather than code, so
the argument that keeps the library out of the researcher's code does not reach them, and his
procedure is the common case: a document that dropped his parameters would leave the person
repeating his run with nothing to repeat it from. The loader block and
``plan_fields_absent``, read off ``plan.absent_fields`` by duck typing, take the same "not
declared" form. This module never runs the procedure and never inspects the plan beyond that
one attribute.

Writing a document costs an economy-wide sha256 -- 0.064 seconds on the 53.3 MB dep1ex01
economy -- so it is a function the researcher calls rather than something ``run`` does on
every call. A parameter scan runs thousands of times and should pay once.

The economy digest is byte for byte, at full precision, and is stored per column as well as
whole. A digest at reduced precision would swallow differences that move the round count,
since convergence is judged against a 3 to 5 percent threshold and a last-place difference can
cross it. The price of full precision is that the same economy loaded on two platforms can
differ in the last place and be reported as a different economy; the per-column digests are
what make that report diagnosable, because they say which column moved.

``algorithm`` names the normalisation, and any change to any step of it takes a new version
string, so that a document written under an older one can still be read for what it meant.
Under ``sha256-columns-v1`` each column is made contiguous, cast to little-endian, and fed to
sha256 behind a header of its name, its dtype string and its shape; the whole-economy digest
is sha256 over the column digests concatenated in name order. The columns are the fields of
the economy: every field that is not a mapping is one column, and every key of a field that is
a mapping is one column named ``<field>.<key>``. Nothing here holds a list of column names --
a list would go on producing a digest that looked right while leaving a newly added column out
of it.

What a matching digest proves is that the arrays are identical, and nothing else. It says
nothing about the library version, numpy, the platform or the solver.
:func:`compare_economy_digests` is what turns a mismatch into a diagnosis: it names the
columns that differ, which is the difference between "your data drifted in
``input_coefficient``" and "these are not the same economy".
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import importlib.metadata as metadata
import inspect
import json
import math
import os
import sys
from typing import Any, Mapping

import numpy as np

from cyberstride._core import core_version

CONFIGURATION_VERSION = 1
"""Version of the document layout. A new layout takes a new number."""

ECONOMY_DIGEST_ALGORITHM = "sha256-columns-v1"
"""Name of the economy normalisation, stored in every document beside the digest."""

LIBRARY_MODULE_PREFIX = "cyberstride."
"""A procedure defined under this module prefix is one the library ships and can digest."""

UNKNOWN_VERSION = "unknown"
"""What the document carries when the library is not installed as a distribution."""

_TWO_64 = 1 << 64
_JSON_SCALARS = (bool, int, float, str)


class ConfigurationError(ValueError):
    """A run cannot be described, or a configuration document cannot be read.

    It derives from ``ValueError`` for the same reason :class:`cyberstride.SchemaError` does:
    a caller who catches ``ValueError`` around the library's data handling catches this too.
    """


@dataclasses.dataclass(frozen=True)
class RetiredKey:
    """A key the library once wrote and has since removed."""

    removed_in: str
    """Library version that removed it."""

    reason: str
    """Why it went, in a form a reader of the error message can act on."""


RETIRED_KEYS: dict[str, RetiredKey] = {}
"""Keys removed from the document, by name.

Empty in this version, and the machinery around it is not. Without a register, removing a key
degrades into the same error a key from a newer library raises, and the two have opposite
answers: one is fixed by upgrading, the other by editing the document.
"""


def economy_digest(economy) -> dict[str, Any]:
    """Content digest of one economy: the whole thing, and each column on its own.

    The result is the ``economy`` block of a configuration document:
    ``{"algorithm": ..., "digest": hex, "columns": {name: hex}}``. Column names come from the
    dataclass fields of ``economy``, so a field added to :class:`cyberstride.Economy` is
    covered without anything here being edited.
    """
    columns = {name: _column_digest(name, value) for name, value in _columns(economy)}
    joined = "".join(columns[name] for name in sorted(columns))
    return {
        "algorithm": ECONOMY_DIGEST_ALGORITHM,
        "digest": hashlib.sha256(joined.encode("ascii")).hexdigest(),
        "columns": columns,
    }


def _columns(economy):
    """Every column of ``economy`` as ``(name, value)``, bags expanded under their own name."""
    for field in dataclasses.fields(economy):
        value = getattr(economy, field.name)
        if isinstance(value, Mapping):
            for key in sorted(value):
                yield f"{field.name}.{key}", value[key]
        else:
            yield field.name, value


def _column_digest(name: str, value) -> str:
    """sha256 over one column's name, dtype, shape and bytes, normalised to little-endian.

    The header is part of the preimage because the bytes alone do not identify a column: the
    same bytes are a different column under a different name, a different dtype or a different
    shape, and a digest that read the bytes alone would report two of those as the same
    economy. ``period`` is not an array; ``np.ascontiguousarray`` makes it one, and its dtype
    string travels in the header like any other column's.
    """
    array = np.ascontiguousarray(value)
    array = array.astype(array.dtype.newbyteorder("<"), copy=False)
    shape = ",".join(str(length) for length in array.shape)
    header = f"{name}\n{array.dtype.str}\n{shape}\n".encode("utf-8")
    return hashlib.sha256(header + array.tobytes()).hexdigest()


@dataclasses.dataclass(frozen=True)
class EconomyDigestReport:
    """Whether two economy digests agree, and where they do not."""

    identical: bool
    """True when the two describe the same economy: no column parts, nothing one-sided."""

    differing_columns: list[str]
    """Columns both blocks carry under different digests, in name order."""

    matching_columns: list[str]
    """Columns both blocks carry under the same digest, in name order."""

    only_in_recorded: list[str]
    """Columns the recorded block carries and the block at hand does not."""

    only_in_current: list[str]
    """Columns the block at hand carries and the recorded block does not."""

    digest_contradicts_columns: bool
    """Every column agrees and the whole digests do not: one block has been edited."""


def compare_economy_digests(
    recorded: Mapping[str, Any], current: Mapping[str, Any]
) -> EconomyDigestReport:
    """Compare two economy digest blocks. Returns a report; raises only on incomparability.

    ``recorded`` is the block a configuration document carries, ``current`` the block of the
    economy at hand. The report names every column the two disagree on, which is what the
    per-column digests are for: full precision reports a last-place difference between two
    platforms as a different economy, and the researcher needs the column names to tell that
    apart from data that really is different.

    Whether the difference matters is his call, so the result comes back as a report on the
    pattern of :func:`cyberstride.check_determinism` rather than as an exception. The one
    thing that is not his call is two blocks taken under different algorithms: their digests
    were built by different normalisations, so neither agreement nor disagreement between them
    would mean anything, and that raises :class:`ConfigurationError`.
    """
    if recorded.get("algorithm") != current.get("algorithm"):
        raise ConfigurationError(
            f"these digests were taken under different algorithms, "
            f"{recorded.get('algorithm')!r} and {current.get('algorithm')!r}, so they cannot "
            "be compared"
        )

    recorded_columns = dict(recorded.get("columns") or {})
    current_columns = dict(current.get("columns") or {})
    shared = sorted(set(recorded_columns) & set(current_columns))
    differing = [name for name in shared if recorded_columns[name] != current_columns[name]]
    matching = [name for name in shared if recorded_columns[name] == current_columns[name]]
    only_recorded = sorted(set(recorded_columns) - set(current_columns))
    only_current = sorted(set(current_columns) - set(recorded_columns))
    edited = not differing and not only_recorded and not only_current and (
        recorded.get("digest") != current.get("digest")
    )
    return EconomyDigestReport(
        identical=not (differing or only_recorded or only_current or edited),
        differing_columns=differing,
        matching_columns=matching,
        only_in_recorded=only_recorded,
        only_in_current=only_current,
        digest_contradicts_columns=edited,
    )


@dataclasses.dataclass(frozen=True)
class RunConfiguration:
    """The settings of one run, as they go into and come out of a JSON file.

    Every field has a default, because a document written by an older library is missing the
    keys that library did not have and still has to load. That puts a standing condition on
    any key added here: its default has to leave behaviour as it was, or an old document loads
    without complaint and runs a setting its author never chose. A new key that cannot do that
    is a version change, not an addition.
    """

    configuration_version: int = CONFIGURATION_VERSION
    library_version: str | None = None
    core_version: str | None = None
    seed: int | None = None
    economy: Mapping[str, Any] | None = None
    procedure: Mapping[str, Any] | None = None
    loader: Mapping[str, Any] | None = None
    plan_fields_absent: tuple[str, ...] | None = None

    def to_json(self, path: str | os.PathLike[str]) -> None:
        """Write the document to ``path`` as UTF-8 JSON, keys sorted, indented by two.

        Line endings are written as ``\\n`` on every platform, so that the same settings give
        the same file and a document can be compared as bytes.

        The whole document is serialised before the file is opened, so a document that cannot
        be written leaves no half-written file behind. ``NaN`` and ``Infinity`` are refused:
        Python reads them back, no other language does, and being readable elsewhere is the
        reason this is JSON.
        """
        document = {
            field.name: getattr(self, field.name) for field in dataclasses.fields(self)
        }
        if self.plan_fields_absent is not None:
            document["plan_fields_absent"] = list(self.plan_fields_absent)
        try:
            text = json.dumps(
                document, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
            )
        except (TypeError, ValueError) as error:
            raise ConfigurationError(
                f"this configuration cannot be written as JSON: {error}"
            ) from error
        with open(path, "w", encoding="utf-8", newline="\n") as file:
            file.write(text + "\n")

    @classmethod
    def from_json(cls, path: str | os.PathLike[str]) -> "RunConfiguration":
        """Read a document back.

        A key this library does not know raises :class:`ConfigurationError`, and the message
        separates the two ways that happens: the document may come from a newer library, or it
        may name a setting this library has removed. A key the document does not carry takes
        its default.

        A ``configuration_version`` above the one this library writes is refused before any of
        that. A newer layout can reuse every key name and still mean something else by them,
        and the key rules alone would load such a document without a word.
        """
        with open(path, encoding="utf-8") as file:
            document = json.load(file)
        if not isinstance(document, dict):
            raise ConfigurationError(
                f"a configuration document is a JSON object, this one is a "
                f"{type(document).__name__}"
            )

        _require_readable_version(document.get("configuration_version", CONFIGURATION_VERSION))
        known = {field.name for field in dataclasses.fields(cls)}
        unknown = sorted(set(document) - known)
        if unknown:
            raise ConfigurationError(_unknown_key_message(unknown[0]))

        values = dict(document)
        absent = values.get("plan_fields_absent")
        if absent is not None:
            values["plan_fields_absent"] = tuple(absent)
        return cls(**values)


def run_configuration(
    procedure, economy, seed: int, loader: Mapping[str, Any] | None = None, plan=None
) -> RunConfiguration:
    """Describe one run: what it ran on, what ran it, and what it was seeded with.

    ``loader`` is the researcher's own declaration of where the economy came from, as a
    JSON-serialisable mapping, and is null when he declares nothing. The economy's identity is
    carried by its content digest, so the loader block is a convenience rather than the thing
    that pins the data down.

    ``plan`` is read by duck typing: the one attribute wanted is ``absent_fields``, a tuple of
    field names the mechanism did not fill in. Pass nothing and the document records null,
    which is the same "not declared" form the loader block uses.

    The procedure is described, never run.
    """
    return RunConfiguration(
        configuration_version=CONFIGURATION_VERSION,
        library_version=_library_version(),
        core_version=core_version(),
        seed=_seed_value(seed),
        economy=economy_digest(economy),
        procedure=_origin_block(procedure),
        loader=_loader_block(loader),
        plan_fields_absent=_absent_fields(plan),
    )


def _require_readable_version(version) -> None:
    if not isinstance(version, int) or isinstance(version, bool):
        raise ConfigurationError(
            f"configuration_version: expected an integer, got {type(version).__name__}"
        )
    if version > CONFIGURATION_VERSION:
        raise ConfigurationError(
            f"configuration_version {version}: this library writes and reads version "
            f"{CONFIGURATION_VERSION}, so the document was written by a newer cyberstride "
            f"than {_library_version()}. Upgrade cyberstride to read it."
        )


def _unknown_key_message(key: str) -> str:
    """Why ``key`` is unknown, told apart by cause because the two have opposite answers."""
    retired = RETIRED_KEYS.get(key)
    if retired is not None:
        return (
            f"{key!r}: this setting no longer exists in cyberstride. It was removed in "
            f"{retired.removed_in} because {retired.reason}. Drop the key from the document."
        )
    return (
        f"{key!r}: this version of cyberstride has no such setting and never had one, so the "
        f"document was written by a newer library than {_library_version()}. Upgrade "
        f"cyberstride to read it."
    )


def _library_version() -> str:
    try:
        return metadata.version("cyberstride")
    except metadata.PackageNotFoundError:
        return UNKNOWN_VERSION


def _seed_value(seed) -> int:
    if not isinstance(seed, (int, np.integer)) or isinstance(seed, bool):
        raise ConfigurationError(f"seed must be an integer, got {type(seed).__name__}")
    if not 0 <= int(seed) < _TWO_64:
        raise ConfigurationError(f"seed must be in [0, 2**64), got {seed}")
    return int(seed)


def _origin_block(value, label: str = "parameters") -> dict[str, Any]:
    """Where ``value`` came from, under the one split the library can honestly make.

    Anything defined under :data:`LIBRARY_MODULE_PREFIX` is the library's own, and the library
    can pin it down: the module, the qualified name, and the digest of the module's source.
    Anything else belongs to the researcher, whose version control is a better record of his
    code than a digest taken by this library would be, so his block says that no origin was
    declared and stops there. The split is about code. Parameters are recorded either way,
    under the same rules, since they are data the library reads off a dataclass.

    ``label`` is where the block sits in the document, used to say which parameter an error
    is about.
    """
    holder = value if isinstance(value, type) or inspect.isroutine(value) else type(value)
    module = getattr(holder, "__module__", "")
    parameters = _parameters(value, label)
    if not module.startswith(LIBRARY_MODULE_PREFIX):
        return {"kind": "researcher", "declared_origin": None, "parameters": parameters}
    return {
        "kind": "library",
        "module": module,
        "qualname": holder.__qualname__,
        "source_digest": _module_source_digest(module),
        "parameters": parameters,
    }


def _module_source_digest(module_name: str) -> str:
    """sha256 of the source file of ``module_name``, read as bytes.

    The whole file rather than the source of the class: a module-level constant decides
    behaviour as surely as the class body does, and a digest over the class alone would go on
    matching after one of them moved.
    """
    module = sys.modules.get(module_name) or importlib.import_module(module_name)
    path = getattr(module, "__file__", None)
    if path is None:
        raise ConfigurationError(
            f"{module_name}: has no source file, so its content digest cannot be taken"
        )
    with open(path, "rb") as source:
        return hashlib.sha256(source.read()).hexdigest()


def _parameters(value, label: str) -> dict[str, Any] | None:
    """The dataclass fields of ``value``, or null when it is not a dataclass."""
    if isinstance(value, type) or not dataclasses.is_dataclass(value):
        return None
    return {
        field.name: _parameter_value(getattr(value, field.name), f"{label}.{field.name}")
        for field in dataclasses.fields(value)
    }


def _parameter_value(value, label: str):
    """A parameter as the document holds it: a JSON scalar as it stands, the rest by origin.

    A numpy scalar is unwrapped into the Python scalar it holds before either rule applies.
    ``np.float64`` subclasses ``float`` and ``np.int64`` subclasses nothing, so without this
    the same procedure would record one parameter as a number and drop the next into the
    undeclared form, taking its value with it.
    """
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or isinstance(value, _JSON_SCALARS):
        _require_finite_number(label, value)
        return value
    return _origin_block(value, f"{label}.parameters")


def _require_finite_number(label: str, value) -> None:
    """Refuse ``NaN`` and ``Infinity``, naming the parameter they sit on.

    ``json`` writes both, and reads both back, but they are not JSON and no other language
    will take them. The message names the parameter because the message ``json`` raises does
    not, and a document with fifty parameters gives no way to find the one.
    """
    if isinstance(value, float) and not math.isfinite(value):
        raise ConfigurationError(
            f"{label}: {value} is not a number JSON can carry, so this run cannot be written "
            "as a configuration document"
        )


def _loader_block(loader) -> dict[str, Any] | None:
    if loader is None:
        return None
    if not isinstance(loader, Mapping):
        raise ConfigurationError(
            "loader: expected a mapping declaring where the economy came from, or None to "
            f"record that nothing was declared, got {type(loader).__name__}"
        )
    block = dict(loader)
    try:
        json.dumps(block, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"loader: is not JSON serialisable: {error}") from error
    return block


def _absent_fields(plan) -> tuple[str, ...] | None:
    if plan is None:
        return None
    fields = getattr(plan, "absent_fields", None)
    if fields is None:
        raise ConfigurationError(
            "plan: expected an object carrying absent_fields, which is the one attribute of a "
            f"plan this document records, and a {type(plan).__name__} has none"
        )
    names = tuple(fields)
    wrong = [name for name in names if not isinstance(name, str)]
    if wrong:
        raise ConfigurationError(
            f"plan.absent_fields: expected field names, got {wrong[0]!r}"
        )
    return names
