"""Print the repository evidence behind two points of the wiki page on the limitations of
existing implementations.

The first is the run log of ``msszczep/pequod-plus`` (``docs/notes.txt``) and the code its
timed runs used; the second is the timing records in ``msszczep/pequod-cljs``. The script clones
both repositories with every object of every branch and tag, without Git LFS objects. Then, for
every fact the page states, it prints the page's wording, the git or text command that bears on
it, and that command's output as it came. Where a fact can be compared mechanically, such as
whether a quoted line is the text at the cited line number, the two sides are printed next to
each other. The script draws no conclusion; a search that finds nothing is reported as finding
nothing for the patterns shown.

Usage:
  python research/upstream/check_history.py [--cache DIR] [--no-fetch]

``--cache`` is the directory the clones go into, under ``clones/`` (default
research/data/upstream). An existing clone is updated with ``git fetch`` unless ``--no-fetch``
is given. The pequod-cljs objects come to about 1 GB; blobs over 1 MiB are fetched one at a
time after the initial clone, so an interrupted run continues where it stopped. The search for
timing figures reads every text blob of every commit of pequod-cljs once, and the message of
every commit of both repositories.
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _git import Repository, ensure_clone, git_environment  # noqa: E402
from fetch import DEFAULT_CACHE  # noqa: E402

PLUS_URL = "https://github.com/msszczep/pequod-plus"
CLJS_URL = "https://github.com/msszczep/pequod-cljs"

NOTES = "docs/notes.txt"
NOTES_COMMIT = "44a6d08"
CSVGEN = "src/clj/pequod_plus/csvgen.clj"
UTIL = "src/cljc/pequod_plus/util.cljc"
TIMED_CODE_COMMIT = "10da5d2"
UNCHANGED_SINCE_COMMIT = "04b6caf"
MISSING_NAMESPACE = "src/clj/pequod_plus/ppex004.clj"
CLJS_EXPERIMENTS = "src/cljs/pequod_plus/ppex00*.cljs"
TIMING_SCRIPT = "bin/bigger_csv.sh"

CITED_COMMITS = {
    "pequod-plus": ["44a6d08", "10da5d2", "0d2506d", "04b6caf"],
    "pequod-cljs": ["71e44d3", "df6dc57", "0d24482"],
}
"""Every commit of the two repositories the Limitations page cites."""

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE_HEADING = re.compile(rf"^({MONTHS}) \d{{1,2}}, \d{{4}}:?\s*$")
TIME_OUTPUT_LINE = re.compile(r"^real\s")
RUN_COMMAND = "lein run"

TIMING_PATTERNS = {
    "a 'real' line of time(1) output": rb"^[ \t]*real\s",
    "the word 'real'": rb"\breal\b",
    "a duration like 12m3.4s": rb"\b\d+m\d+(?:\.\d+)?s\b",
    "a number and a time unit": rb"\b\d+(?:\.\d+)?\s*(?:m?secs?|seconds?|mins?|minutes?|hrs?|hours?)\b",
    "the word minutes, hours or seconds": rb"\b(?:minutes|hours|seconds)\b",
    "elapsed (as in Clojure's time macro)": rb"\belapsed\b",
}
"""What the full-history search of pequod-cljs looks for: Python bytes regexes, compiled with
IGNORECASE and MULTILINE. The singular words "second", "minute" and "hour" count only after a
number: on its own, "second" matches every call of Clojure's ``second`` function."""

SEARCH_FLAGS = re.IGNORECASE | re.MULTILINE

CONTROL_PATTERN = rb"\btime lein run\b"
"""A line every search must find: ``bin/bigger_csv.sh`` runs each experiment as ``time lein run``."""

BINARY_PROBE_BYTES = 8000
"""Git's own heuristic: a file with a NUL byte in its first 8000 bytes is binary."""


def heading(label: str, wiki: str) -> None:
    """The start of one fact: its label and the page's wording."""
    print()
    print("=" * 100)
    print(f"[{label}]")
    print(f'Wiki: "{wiki}"')
    print("-" * 100)


def numbered(text: str) -> list[str]:
    """``text`` split into lines; index ``n - 1`` is line ``n``."""
    return text.split("\n")


def print_lines(lines: list[str], numbers) -> None:
    """Print the given 1-based line numbers of ``lines`` as ``   n: text``."""
    for number in numbers:
        print(f"{number:5d}: {lines[number - 1]}")


def side_by_side(label: str, wiki_value, found_value) -> None:
    """One mechanical comparison: the page's value, the value found, and whether they are equal."""
    print(f"  {label}: wiki={wiki_value!r}  found={found_value!r}  equal={wiki_value == found_value}")


def contains(label: str, line_number: int, lines: list[str], quotation: str) -> None:
    """Whether line ``line_number`` of ``lines`` contains ``quotation`` verbatim."""
    print(f"  line {line_number} contains {quotation!r}: {quotation in lines[line_number - 1]}   ({label})")


def minutes_seconds(duration: str) -> tuple[int, int]:
    """``'253m10.673s'`` as whole minutes and seconds rounded to the nearest second."""
    minutes, seconds = re.fullmatch(r"(\d+)m([\d.]+)s", duration).groups()
    total = int(minutes) * 60 + round(float(seconds))
    return divmod(total, 60)


# ---------------------------------------------------------------------------------------------
# The run log of pequod-plus
# ---------------------------------------------------------------------------------------------

def fact_round_count_tables(plus: Repository) -> None:
    """The log lines that hold the round-count tables and their headings."""
    heading(
        "run log: round-count tables",
        "The round-count tables in the author's log come from `ppex` experiments with 300 to 3000 "
        "worker councils and as many consumer councils (`docs/notes.txt`, lines 9–14 and 35–36).",
    )
    lines = numbered(plus.git("show", f"{NOTES_COMMIT}:{NOTES}",
                              note="lines 5, 7-14, 31, 33-36 shown; 7-8 and 33-34 are the table headers"))
    print_lines(lines, [5, *range(7, 15), 31, *range(33, 37)])


def timed_runs(lines: list[str]) -> list[dict]:
    """Every ``real`` line of the log with the date heading and ``lein run`` command before it."""
    runs = []
    for number, line in enumerate(lines, start=1):
        if not TIME_OUTPUT_LINE.match(line):
            continue
        runs.append({"real": number, "date": line_above(lines, number, is_date_heading),
                     "command": line_above(lines, number, is_run_command)})
    return runs


def line_above(lines: list[str], number: int, predicate) -> int | None:
    """The nearest line before line ``number`` (1-based) for which ``predicate`` holds, or ``None``."""
    return next((n for n in range(number - 1, 0, -1) if predicate(lines[n - 1])), None)


def is_date_heading(line: str) -> bool:
    """Whether ``line`` is a date heading of the log, such as ``January 24, 2026``."""
    return DATE_HEADING.match(line) is not None


def is_run_command(line: str) -> bool:
    """Whether ``line`` holds a ``lein run`` command."""
    return RUN_COMMAND in line


def command_text(line: str) -> str:
    """The command of a log line from ``lein run`` on, without the prompt and ``time`` before it."""
    return line[line.index(RUN_COMMAND):]


def fact_timed_runs(plus: Repository) -> list[dict]:
    """Every timed run of the log; returns them for the council-count fact."""
    heading(
        "run log: timed runs",
        "The eleven timed runs, 2026-01-24 to 2026-03-15, are `ppex` experiments; their wall-clock "
        "times are 159 min 56 s to 253 min 11 s (the `real` lines 81, 115, 138, 157, 178, 199, 219, "
        "238, 257, 276 and 291).",
    )
    lines = numbered(plus.git("show", f"{NOTES_COMMIT}:{NOTES}",
                              note="every line matching ^real, with the nearest date heading and "
                                   "'lein run' line above it"))
    runs = timed_runs(lines)
    for run in runs:
        print(f"  date heading {run['date']:4d}: {lines[run['date'] - 1]}")
        print(f"  command      {run['command']:4d}: {lines[run['command'] - 1]}")
        print(f"  real         {run['real']:4d}: {lines[run['real'] - 1]}")
        print()
    durations = [lines[run["real"] - 1].split()[1] for run in runs]
    rounded = sorted(minutes_seconds(d) for d in durations)
    side_by_side("number of ^real lines", 11, len(runs))
    side_by_side("line numbers", [81, 115, 138, 157, 178, 199, 219, 238, 257, 276, 291], [r["real"] for r in runs])
    side_by_side("shortest (min, s), rounded to the second", (159, 56), rounded[0])
    side_by_side("longest (min, s), rounded to the second", (253, 11), rounded[-1])
    commands = [lines[run["command"] - 1] for run in runs]
    print(f"  commands naming a ppex experiment: {sum('ppex' in c for c in commands)} of {len(commands)}")
    return runs


def fact_no_dep1ex(plus: Repository) -> None:
    """How often the log names dep1ex, and every command line it records."""
    heading("run log: dep1ex data", "No run in the log uses the `dep1ex` data.")
    text = plus.git("show", f"{NOTES_COMMIT}:{NOTES}",
                    note="occurrences of 'dep1ex' (any case), then every line containing 'lein run'")
    print(f"  occurrences of 'dep1ex': {len(re.findall('dep1ex', text, flags=re.IGNORECASE))}")
    lines = numbered(text)
    print_lines(lines, [n for n, line in enumerate(lines, start=1) if RUN_COMMAND in line])


def form_end(lines: list[str], first: int) -> int:
    """The 1-based line on which the Clojure form opening on line ``first`` closes.

    Counts parentheses, brackets and braces outside strings and ``;`` comments.
    """
    depth = 0
    for number in range(first, len(lines) + 1):
        in_string = False
        previous = ""
        for character in lines[number - 1]:
            if in_string:
                in_string = not (character == '"' and previous != "\\")
            elif character == '"':
                in_string = True
            elif character == ";":
                break
            elif character in "([{":
                depth += 1
            elif character in ")]}":
                depth -= 1
                if depth == 0:
                    return number
            previous = character
    raise ValueError(f"the form opening on line {first} does not close")


def fact_setup_ignores_experiment(plus: Repository) -> None:
    """The namespace the timed code loads and where setup reads its experiment argument."""
    heading(
        "timed code: the experiment argument of setup",
        "In the code those runs used, the experiment argument is not read: `csvgen.clj` requires "
        "`pequod-plus.ppex004` on line 2, and `setup` (line 80) loads `ppex004` on lines 99–100",
    )
    lines = numbered(plus.git("show", f"{TIMED_CODE_COMMIT}:{CSVGEN}",
                              note="lines 1-3, and the setup form from line 80 to its closing parenthesis"))
    end = form_end(lines, 80)
    print_lines(lines, [1, 2, 3])
    print("  ...")
    print_lines(lines, range(80, end + 1))
    contains("require", 2, lines, "pequod-plus.ppex004")
    contains("setup", 80, lines, "(defn setup [t _ experiment]")
    contains("ccs", 99, lines, "ppex004/ccs")
    contains("wcs", 100, lines, "ppex004/wcs")
    word = re.compile(r"(?<![\w-])experiment(?![\w-])")
    in_parameters = len(word.findall(lines[79]))
    in_body = sum(len(word.findall(lines[n - 1])) for n in range(81, end + 1))
    print(f"  setup spans lines 80-{end}; the symbol 'experiment' appears {in_parameters} time(s) on "
          f"line 80 and {in_body} time(s) on lines 81-{end}")
    main_line = next(n for n, line in enumerate(lines, start=1) if line.startswith("(defn -main"))
    main_end = form_end(lines, main_line)
    calls = [n for n in range(main_line, main_end + 1) if "setup" in lines[n - 1]]
    print(f"  lines of -main (lines {main_line}-{main_end}) that mention setup:")
    print_lines(lines, [main_line, *calls])


def fact_unchanged(plus: Repository) -> None:
    """The commits that touch csvgen.clj and util.cljc between 04b6caf and 10da5d2."""
    heading(
        "timed code: unchanged between commits",
        "... unchanged from `04b6caf` (2025-06-16) to `10da5d2`; that the timed runs used the committed "
        "code is an inference.",
    )
    print(plus.git("show", "-s", "--format=%h %ad %s", "--date=short", UNCHANGED_SINCE_COMMIT, TIMED_CODE_COMMIT), end="")
    for path in (CSVGEN, UTIL):
        output = plus.git("log", "--format=%h %ad %s", "--date=short",
                          f"{UNCHANGED_SINCE_COMMIT}..{TIMED_CODE_COMMIT}", "--", path)
        print(output if output else "  (no output)\n", end="")
    print(plus.git("rev-parse", f"{UNCHANGED_SINCE_COMMIT}:{CSVGEN}", f"{TIMED_CODE_COMMIT}:{CSVGEN}",
                   note="blob ids of csvgen.clj at both commits"), end="")
    print(plus.git("blame", "--date=short", "-L", "2,2", "-L", "99,100", TIMED_CODE_COMMIT, "--", CSVGEN,
                   note="the commit each of lines 2 and 99-100 comes from"), end="")


def fact_missing_namespace(plus: Repository) -> None:
    """Whether ppex004.clj was ever committed, and the ppex files that were."""
    heading(
        "timed code: the namespace ppex004",
        "The Clojure namespace it loads, `src/clj/pequod_plus/ppex004.clj`, is not in the repository's "
        "history; the repository has only the ClojureScript files `src/cljs/pequod_plus/ppex001.cljs` "
        "to `ppex005.cljs`.",
    )
    output = plus.git("log", "--all", "--oneline", "--", MISSING_NAMESPACE)
    print(output if output else "  (no output)\n", end="")
    names = plus.git("log", "--all", "--format=", "--name-only",
                     note="every path any commit on any branch touched, filtered to names containing 'ppex'")
    ppex_paths = sorted({name for name in names.split("\n") if "ppex" in name})
    for name in ppex_paths:
        print(f"  {name}")
    listing = plus.git("ls-tree", "-r", "--name-only", TIMED_CODE_COMMIT, "--", "src/",
                       note="filtered to names containing 'ppex'")
    for name in listing.split("\n"):
        if "ppex" in name:
            print(f"  {name}")
    print(plus.git("log", "--all", "--diff-filter=A", "--format=%h %ad %s", "--date=short", "--name-only",
                   "--", CLJS_EXPERIMENTS, note="the commit that added each file"), end="")


def fact_council_count(plus: Repository, runs: list[dict]) -> None:
    """Every line of the log that states a council count."""
    heading(
        "run log: council counts",
        "The log states a council count for one command only, the one the first timed run also used: "
        "\"An iteration with 60,000 councils\" (line 74, under 21 January 2026, about a run still in "
        "progress), and \"a full-sized experiment complete, with pollutants, in exactly four hours\" "
        "(line 86, under 24 January, the day of the first timed run). That the 60,000 councils "
        "describe the timed run is an inference.",
    )
    lines = numbered(plus.git("show", f"{NOTES_COMMIT}:{NOTES}",
                              note="lines 74 and 86, then every line of the file that mentions "
                                   "councils, WCs, CCs or a count like 12K"))
    print_lines(lines, [74, 86])
    contains("line 74", 74, lines, "An iteration with 60,000 councils")
    contains("line 86", 86, lines, "a full-sized experiment complete, with pollutants, in exactly four hours")
    for number in (74, 86):
        heading_line = line_above(lines, number, is_date_heading)
        print(f"  date heading above line {number}: line {heading_line}: {lines[heading_line - 1]}")
    first = runs[0]
    print(f"  first timed run: real line {first['real']}, under the date heading on line {first['date']}: "
          f"{lines[first['date'] - 1]}")
    before_74 = line_above(lines, 74, is_run_command)
    print(f"  'lein run' line above line 74: line {before_74}; command of the first timed run: line "
          f"{first['command']}; the same from 'lein run' on: "
          f"{command_text(lines[before_74 - 1]) == command_text(lines[first['command'] - 1])}")
    count_words = re.compile(r"(?i)council|\bWCs?\b|\bCCs?\b|\b\d+K\b")
    commands = [n for n, line in enumerate(lines, start=1) if RUN_COMMAND in line]
    print(f"  'lein run' lines: {commands}")
    print(f"  ^real lines:      {[run['real'] for run in runs]}")
    print("  every line mentioning a council count:")
    print_lines(lines, [n for n, line in enumerate(lines, start=1) if count_words.search(line)])


# ---------------------------------------------------------------------------------------------
# Timing records in pequod-cljs
# ---------------------------------------------------------------------------------------------

def fact_timing_script(cljs: Repository) -> None:
    """The history of bin/bigger_csv.sh and its lines that use time."""
    heading(
        "pequod-cljs: the timing script",
        "Its script `bin/bigger_csv.sh` runs each experiment under `time`, but the output was not "
        "saved in the repository.",
    )
    print(cljs.git("log", "--all", "--format=%h %ad %s", "--date=short", "--", TIMING_SCRIPT), end="")
    text = cljs.git("show", f"origin/HEAD:{TIMING_SCRIPT}", note="lines containing 'time', and the line count")
    lines = numbered(text.rstrip("\n"))
    timed = [n for n, line in enumerate(lines, start=1) if re.search(r"\btime\b", line)]
    print_lines(lines, timed)
    print(f"  {len(timed)} of {len(lines)} lines contain the word 'time'")


@dataclasses.dataclass
class Hit:
    """One distinct (path, line) the full-history search matched."""

    patterns: set[str]
    blob: str
    line_number: int
    n_blobs: int = 1


def object_paths(cljs: Repository) -> dict[str, str]:
    """Every tree and blob the clone holds that any ref reaches, with the path it is first listed at.

    Commits and the root tree carry no path and are left out; objects the clone lacks are left
    out too, and :meth:`Repository.missing_blobs` names them.
    """
    listing = cljs.git("rev-list", "--all", "--objects", "--missing=print", show=False)
    paths: dict[str, str] = {}
    for entry in listing.split("\n"):
        name, _, path = entry.partition(" ")
        if path and not name.startswith("?") and name not in paths:
            paths[name] = path
    return paths


def search_history(cljs: Repository) -> None:
    """Every line of every text blob of pequod-cljs that looks like a timing figure."""
    heading(
        "pequod-cljs: timing figures in the history",
        "`pequod-cljs` contains no wall-clock figure for any run.",
    )
    print("$ git rev-list --all --objects --missing=print   [in pequod-cljs]   # every object any ref reaches")
    print("$ git cat-file --batch   [in pequod-cljs]   # the content of every blob among them")
    print("  Files stored in Git LFS are searched as their pointer files; the LFS objects are not")
    print("  downloaded. A blob with a NUL byte in its first 8000 bytes is skipped as binary; every other blob is")
    print("  searched line by line for these patterns (Python bytes regex, IGNORECASE):")
    for label, pattern in TIMING_PATTERNS.items():
        print(f"    {label:38} {pattern.decode()}")
    print(f"  and, as a control that must match, for {CONTROL_PATTERN.decode()}")

    missing = cljs.missing_blobs()
    scan = scan_blobs(cljs, object_paths(cljs))
    print(f"  blobs: {scan.counts['blobs']}, {scan.counts['bytes']:,} bytes; text blobs searched: "
          f"{scan.counts['text blobs searched']}; binary blobs skipped: {scan.counts['binary blobs skipped']}")
    print(f"  blobs a tree names but the clone lacks, and so not searched: {len(missing)}")
    for oid, path in missing.items():
        print(f"    {oid[:10]} {path}")
    print(f"  control: {sum(scan.control.values())} distinct (path, line) match {CONTROL_PATTERN.decode()}, in "
          f"{', '.join(f'{path} ({n})' for path, n in sorted(scan.control.items())) or 'no file'}")
    per_pattern = collections.Counter(label for hit in scan.hits.values() for label in hit.patterns)
    for label in TIMING_PATTERNS:
        print(f"  distinct (path, line) matching {label}: {per_pattern[label]}")
    print()
    print("  Every distinct (path, line) that matched, with one blob that holds it and the line number")
    print("  in that blob, and how many versions of the file hold the same line:")
    for (path, line), hit in sorted(scan.hits.items()):
        print(f"  {path} [blob {hit.blob[:10]}, line {hit.line_number}, in {hit.n_blobs} version(s)] "
              f"<{'; '.join(sorted(hit.patterns))}>")
        print(f"      {line.decode('utf-8', errors='replace')}")


@dataclasses.dataclass
class Scan:
    """What :func:`scan_blobs` found."""

    hits: dict[tuple[str, bytes], Hit]
    """Every distinct (path, line) a timing pattern matched."""
    control: collections.Counter
    """Per path, how many distinct lines the control pattern matched."""
    counts: collections.Counter
    """Blobs read, bytes read, text blobs searched and binary blobs skipped."""


def scan_blobs(cljs: Repository, candidates: dict[str, str]) -> Scan:
    """Read every object in ``candidates`` through one ``git cat-file --batch`` and search its blobs.

    Trees among the candidates are read and passed over. A blob whose first 8000 bytes hold a
    NUL byte is counted as binary and not searched. A line that several versions of a file share
    is reported once, with the first blob it was found in.
    """
    compiled = {label: re.compile(pattern, SEARCH_FLAGS) for label, pattern in TIMING_PATTERNS.items()}
    control = re.compile(CONTROL_PATTERN, SEARCH_FLAGS)
    # One pass of the union over a blob decides whether its lines need testing one by one.
    union = re.compile(
        b"|".join(b"(?:" + pattern + b")" for pattern in (*TIMING_PATTERNS.values(), CONTROL_PATTERN)),
        SEARCH_FLAGS,
    )
    scan = Scan({}, collections.Counter(), collections.Counter())
    control_lines: set[tuple[str, bytes]] = set()
    process = subprocess.Popen(
        ["git", "-C", str(cljs.path), "cat-file", "--batch"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=git_environment(lazy_fetch=False),
    )
    for name, path in candidates.items():
        kind, content = _read_object(process, name)
        if kind != b"blob":
            continue
        scan.counts["blobs"] += 1
        scan.counts["bytes"] += len(content)
        if b"\0" in content[:BINARY_PROBE_BYTES]:
            scan.counts["binary blobs skipped"] += 1
            continue
        scan.counts["text blobs searched"] += 1
        if not union.search(content):
            continue
        for line_number, raw_line in enumerate(content.split(b"\n"), start=1):
            line = raw_line.rstrip(b"\r")
            if control.search(line) and (path, line) not in control_lines:
                control_lines.add((path, line))
                scan.control[path] += 1
            matched = {label for label, pattern in compiled.items() if pattern.search(line)}
            if not matched:
                continue
            if (path, line) in scan.hits:
                scan.hits[(path, line)].n_blobs += 1
            else:
                scan.hits[(path, line)] = Hit(matched, name, line_number)
    process.stdin.close()
    process.wait()
    return scan


def _read_object(process: subprocess.Popen, name: str) -> tuple[bytes, bytes]:
    """Ask a running ``git cat-file --batch`` for ``name``; return its type and content."""
    process.stdin.write(name.encode() + b"\n")
    process.stdin.flush()
    header = process.stdout.readline().split()
    if header[-1] == b"missing":
        return b"missing", b""
    content = process.stdout.read(int(header[2]))
    process.stdout.read(1)
    return header[1], content


@dataclasses.dataclass(frozen=True)
class MessageHit:
    """One line of one commit message that a timing pattern matched."""

    commit: str
    line_number: int
    """Line within the message, counted from 1; line 1 is the subject."""
    line: str
    patterns: frozenset[str]


@dataclasses.dataclass(frozen=True)
class MessageScan:
    """What :func:`scan_messages` found in one repository."""

    commits: list[str]
    """Every commit whose message was searched, newest first."""
    hits: list[MessageHit]


def scan_messages(repository: Repository) -> MessageScan:
    """Search the full message of every commit any ref reaches, line by line, with TIMING_PATTERNS."""
    compiled = {label: re.compile(pattern, SEARCH_FLAGS) for label, pattern in TIMING_PATTERNS.items()}
    log = repository.git("log", "--all", "-z", "--format=%H%n%B",
                         note="the full message of every commit any ref reaches")
    commits, hits = [], []
    for record in log.split("\0"):
        commit, _, message = record.strip("\n").partition("\n")
        if not commit:
            continue
        commits.append(commit)
        for line_number, line in enumerate(message.split("\n"), start=1):
            matched = frozenset(label for label, pattern in compiled.items()
                                if pattern.search(line.encode("utf-8")))
            if matched:
                hits.append(MessageHit(commit, line_number, line, matched))
    return MessageScan(commits, hits)


def search_messages(repositories: list[Repository]) -> None:
    """Every line of every commit message of both repositories that looks like a timing figure."""
    heading(
        "both repositories: timing figures in the commit messages",
        "`pequod-cljs` contains no wall-clock figure for any run.",
    )
    print("  Every line of every message is searched for the patterns of the file search above.")
    print("  Control: every commit the page cites has to be among the commits searched.")
    for repository in repositories:
        scan = scan_messages(repository)
        cited = CITED_COMMITS[repository.name]
        found = [short for short in cited if any(commit.startswith(short) for commit in scan.commits)]
        print(f"  commit messages searched: {len(scan.commits)}")
        print(f"  control: cited commits among them: {len(found)} of {len(cited)} ({', '.join(found) or 'none'})")
        print(f"  lines matching a timing pattern: {len(scan.hits)}")
        for hit in scan.hits:
            print(f"    {hit.commit[:7]} message line {hit.line_number} <{'; '.join(sorted(hit.patterns))}>")
            print(f"        {hit.line}")


# ---------------------------------------------------------------------------------------------
# Repository state
# ---------------------------------------------------------------------------------------------

def print_repository_state(repository: Repository) -> None:
    """The remote branches and whether each cited commit is on one of them."""
    heading(
        f"state of {repository.name}",
        "Line numbers refer to the stated commit. They go stale as the repositories change; the commit "
        "does not.",
    )
    print(repository.git("for-each-ref", "--format=%(refname:short) %(objectname:short) %(committerdate:iso8601)",
                         "refs/remotes/"), end="")
    for commit in CITED_COMMITS[repository.name]:
        print(repository.git("show", "-s", "--format=%H %ad %s", "--date=iso8601", commit,
                             tolerate_failure=True), end="")
        print(repository.git("branch", "-r", "--contains", commit, tolerate_failure=True), end="")


def main() -> None:
    """Clone or update both repositories and print every fact."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="directory for the clones")
    parser.add_argument("--no-fetch", action="store_true", help="reuse existing clones as they are")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    clones = args.cache / "clones"
    ensure_clone(PLUS_URL, clones / "pequod-plus", fetch=not args.no_fetch)
    ensure_clone(CLJS_URL, clones / "pequod-cljs", fetch=not args.no_fetch)
    plus = Repository("pequod-plus", clones / "pequod-plus")
    cljs = Repository("pequod-cljs", clones / "pequod-cljs")

    print_repository_state(plus)
    print_repository_state(cljs)

    print("\n\nThe run log of `pequod-plus` and the code its timed runs used")
    fact_round_count_tables(plus)
    runs = fact_timed_runs(plus)
    fact_no_dep1ex(plus)
    fact_setup_ignores_experiment(plus)
    fact_unchanged(plus)
    fact_missing_namespace(plus)
    fact_council_count(plus, runs)

    print("\n\nTiming records of the runs behind the book in `pequod-cljs`")
    fact_timing_script(cljs)
    search_history(cljs)
    search_messages([plus, cljs])


if __name__ == "__main__":
    main()
