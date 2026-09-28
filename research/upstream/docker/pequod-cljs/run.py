"""Run pequod-cljs's csvgen.clj in Docker for the first rounds of one experiment, under the
program's own price rule and under the rules as printed in the book and in the paper, and compare
every run with the output file the authors committed.

    python research/upstream/docker/pequod-cljs/run.py [--cache DIR] [--data-dir DIR] [--rounds 3] [--program-rounds 12]

`--data-dir` holds the public input `dep1ex01.clj.gz` (https://www.szcz.org/depexperiments/);
`--cache` is where the committed output is kept and where this script puts the prepared input
and the runs' CSVs, under `pequod-cljs-runs/`. Both files are taken through `fetch.py` and
checked against `manifest.tsv`; a missing one is downloaded. Needs Docker and network access to
Docker Hub, GitHub, Clojars and Maven Central for the build. Standard library only, apart from
numpy in the comparisons.

What it does, in order:
1. Builds the image from ./Dockerfile: pequod-cljs at 71e44d3, Java 11, Leiningen 2.9.
2. For the book's and the paper's rule, takes csvgen.clj from the image and replaces the lines
   that edits/rule-book-p181.json and edits/rule-paper-p7.json name, after checking the sha256
   of each line; stops when a check fails. The edited files go to the cache; the run prints
   their diff against the commit.
3. Decompresses the public input, sets its first-line namespace to the repository's name for it,
   and checks the result against the repository's Git LFS pointer (sha256 and size).
4. Checks the Git blob id of the committed output dep1ex61.csv at df6dc57 against that commit's
   tree, as the image recorded it.
5. Checks every year-one row of the committed output against three step rules.
6. Runs csvgen.clj once per rule and stops it after `--rounds` rounds (`--program-rounds` for
   the run under the program's own rule).
7. Compares each run with the committed output, and the rule runs with the program run.
8. Reports load time, time per round and peak memory, and extrapolates the time of year one.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import csvcompare as cc

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import _experiments  # noqa: E402
import _source_edits  # noqa: E402
import fetch  # noqa: E402
from _program_output import YEAR_END, read_year_one  # noqa: E402

IMAGE = "demplan-upstream-pequod-cljs"
CONTAINER_PREFIX = f"{IMAGE}-"
RUNS_DIRECTORY = "pequod-cljs-runs"
"""Subdirectory of the cache for the prepared input, the edited csvgen.clj files and the runs'
CSVs and GC logs."""
CSVGEN_PATH = "src/clj/pequod_cljs/csvgen.clj"
"""csvgen.clj within the repository; the image checks the repository out at /pequod-cljs."""
EDITS_DIR = HERE / "edits"
RULE_EDITS = {"program": None, "book-p181": "rule-book-p181.json", "paper-p7": "rule-paper-p7.json"}
"""Each rule and the edit set in EDITS_DIR that puts it into csvgen.clj; None runs csvgen.clj as
committed."""
RULE_RUNS = tuple(RULE_EDITS)
_MEMORY = re.compile(r"^([\d.]+)\s*([KMGT]?i?B)")
_GC_HEAP = re.compile(r"(\d+)M->(\d+)M\((\d+)M\)")
_UNITS = {"B": 1, "KiB": 2**10, "MiB": 2**20, "GiB": 2**30, "TiB": 2**40, "kB": 10**3, "MB": 10**6, "GB": 10**9}


@dataclass
class RunRecord:
    """What one csvgen.clj run printed and how long and how much memory it took."""

    rule: str
    csv_path: Path
    rows: int = 0
    #: seconds from `lein run` starting to each row being printed
    row_times: list[float] = field(default_factory=list)
    peak_memory_bytes: int = 0
    max_heap_before_gc_mb: int = 0
    max_heap_after_gc_mb: int = 0
    heap_capacity_mb: int = 0
    stopped_by: str = ""
    wall_seconds: float = 0.0


def main() -> int:
    """Build, prepare, run every rule, compare, and report; exit status 0."""
    args = parse_args()
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    number = _experiments.output_number(args.experiment)
    store = fetch.Store(fetch.roots_from(args))
    work = (args.cache / RUNS_DIRECTORY).resolve()
    work.mkdir(parents=True, exist_ok=True)

    section(f"pequod-cljs csvgen.clj, book experiment {args.experiment} = dep1ex{number}, price rules: {', '.join(args.rules)}")
    build_image(args.skip_build)
    evidence = read_evidence(number)
    sources = {}
    if any(RULE_EDITS[rule] for rule in args.rules):
        section("Line edits")
        sources = prepare_sources(args.rules, evidence["program_commit"], read_committed_csvgen(), work / "sources")

    section("Input")
    input_dir = work / "input"
    prepare_input(store.path(_experiments.archive_name(args.experiment)), number, evidence["pointer"], input_dir)

    section("Committed output")
    published_path = check_published(store, number, evidence["output_blob"])
    published = read_year_one(published_path, worker_councils=True)
    columns = 2 + published.price.shape[1] * 7 + 2 * len(published.wc_ids)
    print(f"year one: {len(published.iteration)} rows, {columns} columns")
    report_rule_check("committed output", published)

    records = {}
    for rule in args.rules:
        section(f"Run: {rule}")
        rounds = args.program_rounds if rule == "program" else args.rounds
        records[rule] = run_rule(rule, number, rounds, args, input_dir, work / "runs", sources.get(rule))

    runs = {rule: read_year_one(rec.csv_path, worker_councils=True) for rule, rec in records.items()}
    for rule, run in runs.items():
        section(f"Run {rule} against the committed output, rounds 1-{len(run.iteration)}")
        same = cc.identical_lines(records[rule].csv_path, published_path, len(run.iteration) + 1)
        print(f"lines byte for byte identical (header, round 1, ...): {same}")
        report_diff(run, published, len(run.iteration))
        report_rule_check(f"run {rule}", run)
    if "program" in runs:
        for rule in (r for r in runs if r != "program"):
            section(f"Run {rule} against run program, per round")
            report_step_comparison(runs["program"], runs[rule], rule)
    section("Time and memory")
    report_resources(records, len(published.iteration))
    return 0


def parse_args() -> argparse.Namespace:
    """The command-line options."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    fetch.add_location_arguments(parser)
    parser.add_argument("--experiment", type=int, default=1, choices=range(1, 6),
                        help="book experiment number; inputs 1-5 have LFS pointers in the repository")
    parser.add_argument("--rounds", type=int, default=3, help="rounds to run before stopping csvgen.clj")
    parser.add_argument("--program-rounds", type=int, default=12,
                        help="rounds for the run under the program's own rule; 12 is the first round the "
                        "committed outputs for dep1ex61 to dep1ex65 colour green (every imbalance below 5%%)")
    parser.add_argument("--rules", nargs="+", default=list(RULE_RUNS), choices=RULE_RUNS)
    parser.add_argument("--heap", default="6g", help="maximum JVM heap (-Xmx)")
    parser.add_argument("--timeout-minutes", type=float, default=20.0, help="stop a run after this long")
    parser.add_argument("--skip-build", action="store_true", help="use the image already built")
    return parser.parse_args()


def section(title: str) -> None:
    """Print a section heading."""
    print(f"\n== {title} ==", flush=True)


def docker(*args: str) -> str:
    """Run a docker command and return its standard output; raise when it fails."""
    return subprocess.run(["docker", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def build_image(skip: bool) -> None:
    """Build the image, or with `skip` check that it exists; print its id and base image."""
    if not skip:
        started = time.monotonic()
        subprocess.run(["docker", "build", "-t", IMAGE, str(HERE)], check=True)
        print(f"build: {time.monotonic() - started:.0f} s")
    print(f"image {IMAGE}: {docker('image', 'inspect', '--format', '{{.Id}}', IMAGE).strip()}")
    base = next(line for line in (HERE / "Dockerfile").read_text(encoding="utf-8").splitlines() if line.startswith("FROM "))
    print(f"base: {base[5:]}")


def read_evidence(number: int) -> dict[str, str]:
    """The facts the image recorded from the repository at build time."""
    def cat(name: str) -> str:
        """The content of one evidence file in the image."""
        return docker("run", "--rm", IMAGE, "cat", f"/evidence/{name}")

    program_commit = cat("program-commit").strip()
    print(f"checked out: {program_commit}")
    for line in cat("csvgen-blobs").splitlines():
        commit, blob = line.split()
        print(f"csvgen.clj at {commit}: git blob {blob}")
    output_line = next(l for l in cat("output-csv-blobs").splitlines() if l.endswith(f"dep1ex{number}.csv"))
    pointer_commit = cat(f"dep1ex{number}.clj.pointer-commit").strip()
    pointer = cat(f"dep1ex{number}.clj.pointer")
    print(f"LFS pointer of dep1ex{number}.clj at {pointer_commit}:")
    print("  " + pointer.strip().replace("\n", "\n  "))
    return {"pointer": pointer, "output_blob": output_line.split()[2], "program_commit": program_commit}


def read_committed_csvgen() -> bytes:
    """csvgen.clj as the image checked it out."""
    return subprocess.run(["docker", "run", "--rm", IMAGE, "cat", f"/pequod-cljs/{CSVGEN_PATH}"],
                          check=True, capture_output=True).stdout


def prepare_sources(rules: list[str], program_commit: str, committed: bytes, out_dir: Path) -> dict[str, Path]:
    """Write, for each rule with an edit set, ``committed`` with its edits made to
    ``out_dir/<rule>/csvgen.clj``, and return those paths by rule.

    Stops the script before writing any file when an edit set names another file or another
    commit than ``program_commit``, or when one of its edits does not apply (see
    ``_source_edits.apply``).
    """
    edited = {}
    for rule in rules:
        name = RULE_EDITS[rule]
        if name is None:
            continue
        edit_set = _source_edits.load(EDITS_DIR / name)
        if edit_set.file != CSVGEN_PATH:
            sys.exit(f"{name} edits {edit_set.file}, not {CSVGEN_PATH}; stopping")
        if edit_set.commit != program_commit:
            sys.exit(f"{name} is written for commit {edit_set.commit}, the image has {program_commit}; stopping")
        try:
            edited[rule] = _source_edits.apply(edit_set, committed)
        except _source_edits.SourceEditError as error:
            sys.exit(f"{name}: {error}; nothing was changed, stopping")
        print(f"{rule}: {name}: {_source_edits.summary(edit_set)}")
    paths = {}
    for rule, content in edited.items():
        path = out_dir / rule / "csvgen.clj"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        paths[rule] = path
    return paths


def prepare_input(gz_path: Path, number: int, pointer: str, out_dir: Path) -> Path:
    """Decompress the public input, rename its namespace and check it against the LFS pointer.

    The public file's first line is `(ns pequod-cljs.dep1exNN)` with NN the book's number; the
    repository's file names the namespace `pequod-cljs.dep1ex(60+NN)`. Nothing else changes.
    Stops the script when the first line is not the expected one or the result does not match
    the pointer's sha256 and size.
    """
    want_oid = re.search(r"^oid sha256:([0-9a-f]{64})$", pointer, re.M).group(1)
    want_size = int(re.search(r"^size (\d+)$", pointer, re.M).group(1))
    book_number = number - _experiments.OUTPUT_OFFSET
    old_first = f"(ns pequod-cljs.dep1ex{book_number:02d})\n".encode()
    new_first = f"(ns pequod-cljs.dep1ex{number})\n".encode()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"dep1ex{number}.clj"

    original, renamed = hashlib.sha256(), hashlib.sha256()
    original_size = renamed_size = 0
    with gzip.open(gz_path, "rb") as src, open(out_path, "wb") as dst:
        first = src.readline()
        if first != old_first:
            sys.exit(f"{gz_path}: first line is {first[:80]!r}, expected {old_first!r}")
        original.update(first)
        renamed.update(new_first)
        dst.write(new_first)
        original_size, renamed_size = len(first), len(new_first)
        while chunk := src.read(1 << 20):
            original.update(chunk)
            renamed.update(chunk)
            dst.write(chunk)
            original_size += len(chunk)
            renamed_size += len(chunk)
    print(f"{gz_path.name} decompressed: sha256 {original.hexdigest()} size {original_size}")
    print(f"first line {old_first.decode().strip()} -> {new_first.decode().strip()}")
    print(f"{out_path.name}:            sha256 {renamed.hexdigest()} size {renamed_size}")
    print(f"LFS pointer:                sha256 {want_oid} size {want_size}")
    match = renamed.hexdigest() == want_oid and renamed_size == want_size
    print(f"match: {match}")
    if not match:
        sys.exit("the prepared input does not match the repository's LFS pointer; stopping")
    return out_path


def check_published(store: fetch.Store, number: int, want_blob: str) -> Path:
    """The committed output, checked against the manifest and against the blob in df6dc57's tree."""
    name = _experiments.output_name(number)
    path = store.path(name)
    entry = store.entry(name)
    blob = fetch.git_blob_id(path)
    print(f"{entry.url}")
    print(f"sha256 {fetch.sha256_of(path)} size {path.stat().st_size}")
    print(f"git blob {blob}; tree of {entry.commit[:7]}: {want_blob}; match: {blob == want_blob}")
    if blob != want_blob:
        sys.exit("the downloaded output is not the committed file; stopping")
    return path


def run_rule(rule: str, number: int, rounds: int, args: argparse.Namespace, input_dir: Path, runs_dir: Path,
             source: Path | None) -> RunRecord:
    """Run csvgen.clj under one rule, save what it prints, and stop it after `rounds` rows.

    ``source`` is the edited csvgen.clj that replaces the committed one, or None to run the
    committed one.

    The run is also stopped at the first `exponent-sum` line (the end of year one) and after
    `args.timeout_minutes`. Memory is sampled from `docker stats` every few seconds; the JVM
    writes a GC log that gives the heap in use before and after each collection.
    """
    out_dir = runs_dir / rule
    out_dir.mkdir(parents=True, exist_ok=True)
    record = RunRecord(rule, out_dir / f"dep1ex{number}.csv")
    gc_log = out_dir / "gc.log"
    gc_log.unlink(missing_ok=True)
    name = f"{CONTAINER_PREFIX}{rule}-ex{number}"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    edited = ["-v", f"{source.parent}:/edited:ro"] if source else []
    command = [
        "docker", "run", "--rm", "--name", name,
        "-v", f"{HERE}:/work:ro", "-v", f"{input_dir}:/data:ro", "-v", f"{out_dir}:/logs", *edited,
        "-e", f"JVM_OPTS=-Xmx{args.heap} -Xlog:gc:file=/logs/gc.log",
        IMAGE, "bash", "/work/run_csvgen.sh", str(number), *([f"/edited/{source.name}"] if source else []),
    ]
    started = time.monotonic()
    lein_started = [started]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stop = threading.Event()
    threading.Thread(target=echo_stderr, args=(process, lein_started), daemon=True).start()
    sampler = threading.Thread(target=sample_memory, args=(name, record, stop), daemon=True)
    sampler.start()
    timer = threading.Timer(args.timeout_minutes * 60, lambda: stop_container(name, record, "timeout"))
    timer.start()

    with open(record.csv_path, "wb") as out:
        header_seen = False
        for line in process.stdout:
            out.write(line)
            out.flush()
            if not header_seen:
                header_seen = True
                continue
            if line.startswith(YEAR_END.encode()):
                stop_container(name, record, "end of year one")
                break
            record.rows += 1
            record.row_times.append(time.monotonic() - lein_started[0])
            print(f"round {record.rows}: {record.row_times[-1]:.1f} s after lein started", flush=True)
            if record.rows >= rounds:
                stop_container(name, record, f"{rounds} rounds read")
                break
    timer.cancel()
    process.wait()
    stop.set()
    sampler.join()
    record.wall_seconds = time.monotonic() - started
    if not record.stopped_by:
        record.stopped_by = f"exited with status {process.returncode}"
    if gc_log.exists():
        read_gc_log(gc_log, record)
    print(f"stopped: {record.stopped_by}; {record.rows} rounds; {record.wall_seconds:.0f} s in the container")
    return record


def echo_stderr(process: subprocess.Popen, lein_started: list[float]) -> None:
    """Print the container's diagnostics and note when `lein run` starts."""
    for raw in process.stderr:
        line = raw.decode("utf-8", errors="replace").rstrip()
        if line.startswith("starting: lein run"):
            lein_started[0] = time.monotonic()
        print(f"  | {line}", flush=True)


def stop_container(name: str, record: RunRecord, reason: str) -> None:
    """Kill the container, recording the first reason it was stopped for."""
    if not record.stopped_by:
        record.stopped_by = reason
    subprocess.run(["docker", "kill", name], capture_output=True)


def sample_memory(name: str, record: RunRecord, stop: threading.Event) -> None:
    """Keep the largest memory use `docker stats` reports for the container."""
    while not stop.is_set():
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", name],
            capture_output=True, text=True,
        )
        match = _MEMORY.match(result.stdout.strip())
        if match:
            used = int(float(match.group(1)) * _UNITS.get(match.group(2), 1))
            record.peak_memory_bytes = max(record.peak_memory_bytes, used)
        stop.wait(3)


def read_gc_log(path: Path, record: RunRecord) -> None:
    """The largest heap in use before and after a collection, and the largest heap size, in MB."""
    for match in _GC_HEAP.finditer(path.read_text(encoding="utf-8", errors="replace")):
        before, after, capacity = (int(g) for g in match.groups())
        record.max_heap_before_gc_mb = max(record.max_heap_before_gc_mb, before)
        record.max_heap_after_gc_mb = max(record.max_heap_after_gc_mb, after)
        record.heap_capacity_mb = max(record.heap_capacity_mb, capacity)


def print_table(header: list[str], rows: list[list[object]]) -> None:
    """Print rows under header in right-aligned columns."""
    cells = [header] + [[str(c) for c in row] for row in rows]
    widths = [max(len(row[i]) for row in cells) for i in range(len(header))]
    for row in cells:
        print("  ".join(cell.rjust(width) for cell, width in zip(row, widths)).rstrip())


def fmt(x: float) -> str:
    """A number in scientific notation with four significant digits."""
    return f"{x:.3e}"


def report_rule_check(label: str, run) -> None:
    """Per round, how far each rule's predicted step is from the recorded one."""
    errors = cc.rule_errors(run)
    prices = cc.price_update_errors(run)
    print(f"\n{label}: largest relative error of each rule's step against the recorded new-deltas,")
    print("with v = threshold-report / 100 and, for the program rule, the previous row's pdlist")
    print("(0.25 before round 1); last column: recorded price against p_(k-1)(1 -/+ w_k)")
    rows = [[r + 1] + [fmt(errors[rule][r]) for rule in cc.RULES] + [fmt(prices[r])] for r in range(len(run.iteration))]
    print_table(["round", "program rule", "book p.181", "paper p.7", "price update"], rows)


def report_diff(ours, theirs, rounds: int) -> None:
    """Per column kind, how the first ``rounds`` rows of two runs differ."""
    diff = cc.diff_runs(ours, theirs, rounds)
    rows = []
    for g in diff.groups:
        rows.append([
            g.kind, g.cells, g.identical_cells, fmt(g.max_abs), where(g.max_abs_at), fmt(g.max_rel), where(g.max_rel_at),
        ])
    print_table(["columns", "cells", "equal", "max abs diff", "at (round, column)", "max rel diff", "at (round, column)"], rows)
    print(f"iteration column: {len(diff.iteration_mismatches)} rows differ {diff.iteration_mismatches}")
    print(f"color column: {len(diff.color_mismatches)} rows differ {diff.color_mismatches}")
    ours_color = list(ours.color[:rounds])
    theirs_color = list(theirs.color[:rounds])
    print(f"color, this run: {ours_color}; committed: {theirs_color}")


def where(at: tuple[int, str] | None) -> str:
    """A (round, column) location, or ``-``."""
    return "-" if at is None else f"{at[0]}, {at[1]}"


def report_step_comparison(program, other, rule: str) -> None:
    """Per round, where the steps of a rule's run differ from the program run's."""
    rows = []
    for s in cc.compare_steps(program, other):
        rows.append([s.iteration, s.differing, fmt(s.max_abs_step_diff), f"{s.worst_imbalance_a:.6f}", f"{s.worst_imbalance_b:.6f}"])
    print_table(["round", "commodities with a different step (of 500)", "max |step difference|",
                 "worst imbalance %, program", f"worst imbalance %, {rule}"], rows)
    summary = {s.iteration: s for s in cc.round_summary(other)}
    base = {s.iteration: s for s in cc.round_summary(program)}
    rows = [[k, f"{base[k].min_step:.6f}", f"{base[k].max_step:.6f}", f"{summary[k].min_step:.6f}", f"{summary[k].max_step:.6f}"]
            for k in sorted(summary) if k in base]
    print_table(["round", "min step, program", "max step, program", f"min step, {rule}", f"max step, {rule}"], rows)


def report_resources(records: dict[str, RunRecord], year_one_rounds: int) -> None:
    """Measured times and memory per run, and the extrapolated time of a whole year one."""
    rows = []
    for rule, rec in records.items():
        if not rec.row_times:
            rows.append([rule, "-", "-", "-", f"{rec.peak_memory_bytes / 2**30:.2f}", "-", "-"])
            continue
        per_round = [b - a for a, b in zip(rec.row_times, rec.row_times[1:])]
        mean_round = sum(per_round) / len(per_round) if per_round else float("nan")
        extrapolated = rec.row_times[0] + (year_one_rounds - 1) * mean_round
        rows.append([
            rule, f"{rec.row_times[0]:.0f}", " ".join(f"{t:.0f}" for t in per_round) or "-",
            f"{extrapolated / 60:.0f}" if per_round else "- (needs 2 rounds)", f"{rec.peak_memory_bytes / 2**30:.2f}",
            f"{rec.max_heap_before_gc_mb}/{rec.max_heap_after_gc_mb}/{rec.heap_capacity_mb}", f"{rec.wall_seconds:.0f}",
        ])
    print_table([
        "run", "s to round 1 (load + round 1)", "s per later round", f"min for {year_one_rounds} rounds (extrapolated)",
        "peak container memory GiB", "heap MB before/after GC/size", "s in container",
    ], rows)


if __name__ == "__main__":
    sys.exit(main())
