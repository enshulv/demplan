"""Builds pequod-plus at each pinned commit in Docker, runs the probes, and checks the closed forms.

    python run_all.py [--cache DIR] [--data-dir DIR] [--no-build]

Steps:
1. `make_closed_form_cases.py` takes the dep1ex01 archive and pequod-cljs's dep1ex61.csv through
   `research/upstream/fetch.py` (downloaded when missing, checked against `manifest.tsv`) and
   writes the worker-council cases to `<cache>/pequod-plus-probes/`.
2. One image per target (see TARGETS), built from this directory's Dockerfile. An edited target
   starts from the image of its base target: its edit set in edits/ is applied to the file it
   names, taken from that image, after the sha256 of each edited line is checked, and
   edited.Dockerfile copies the result and its diff into a new image.
3. For each target: the source lines the checks refer to, which lines/ lists by line number and
   sha256 and which are printed after every hash is checked, then `probe.demand-by-commodity`,
   `probe.category-multiplier` and `probe.closed-forms` run inside the image with `lein -o run`
   (offline: every dependency is in the image).
4. `verify_closed_forms.py` compares every closed-form result with the first-order conditions and
   a numerical maximiser.

Standard library only, apart from numpy and scipy in step 4. Needs Docker and network access for
the first build and the first download.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import _source_edits  # noqa: E402
import _source_lines  # noqa: E402
import fetch  # noqa: E402

IMAGE = "demplan-upstream-pequod-plus"
CONTAINER_PREFIX = f"{IMAGE}-"
WORK_DIRECTORY = "pequod-plus-probes"
"""Subdirectory of the cache for the cases, the probes' results and nothing else."""
CASES = "closed-form-cases"
EDITS_DIR = HERE / "edits"
LINES_DIR = HERE / "lines"
"""One listing per commit target, ``<label>.json``: the source lines printed before the probes
(see ``_source_lines.py``)."""
EDITED_CONTEXTS = "edited-build-contexts"
"""Subdirectory of the work directory holding one build context per edited target."""
REPOSITORY_IN_IMAGE = "/opt/pequod-plus"

TARGETS = [
    {"label": "44a6d08", "commit": "44a6d08be631b57e1638d39555d1f6089f0ca68b",
     "probes": ("demand-by-commodity", "category-multiplier", "closed-forms"),
     "note": "the commit the wiki cites"},
    {"label": "44a6d08-log-p3", "base": "44a6d08", "edits": "solution-5-x1-log-p3.json",
     "probes": ("closed-forms",),
     "note": "44a6d08 with log-p2 replaced by log-p3 in one term of solution-5's x1"},
    {"label": "44d8c15", "commit": "44d8c150fdcd95e19903e26831b631f994404ef0",
     "probes": ("demand-by-commodity", "category-multiplier", "closed-forms"),
     "note": "head of branch db on 2026-09-28"},
    {"label": "10da5d2", "commit": "10da5d2587d515be1f6a547cd83cb6b6a49502b5",
     "probes": ("demand-by-commodity", "category-multiplier", "closed-forms"),
     "note": "the code of the author's timed runs (docs/notes.txt)"},
]
"""Images to build and the probes each runs. A target with a commit is built from Dockerfile at
that commit, and LINES_DIR holds the listing of its source lines; a target with a base and an
edit set in EDITS_DIR is the base target's image with the edits made, runs only the closed-form
probe and prints its base's listing. A base comes before the targets built on it."""


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Runs a command with UTF-8 text output, raising on a non-zero exit."""
    return subprocess.run(command, check=True, text=True, encoding="utf-8", errors="replace", **kwargs)


def tag(target: dict) -> str:
    """Image tag of a target."""
    return f"{IMAGE}:{target['label']}"


def build(target: dict, work: Path) -> float:
    """Builds the target's image and returns the wall-clock seconds the build took."""
    start = time.monotonic()
    if "edits" in target:
        base = base_of(target)
        context = work / EDITED_CONTEXTS / target["label"]
        write_edited_context(target, read_from_image(base, target), context)
        run(["docker", "build", "-f", str(HERE / "edited.Dockerfile"), "--build-arg", f"BASE={tag(base)}",
             "-t", tag(target), str(context)])
    else:
        run(["docker", "build", "--build-arg", f"PEQUOD_COMMIT={target['commit']}", "-t", tag(target), str(HERE)])
    return time.monotonic() - start


def base_of(target: dict) -> dict:
    """The target an edited target is built on."""
    return next(t for t in TARGETS if t["label"] == target["base"])


def read_from_image(base: dict, target: dict) -> bytes:
    """The file the target's edit set names, as it is in the base target's image."""
    edit_set = _source_edits.load(EDITS_DIR / target["edits"])
    return file_in_image(base, edit_set.file)


def file_in_image(target: dict, path: str) -> bytes:
    """The bytes of ``path``, a path within the repository, in the target's image."""
    return subprocess.run(["docker", "run", "--rm", tag(target), "cat", f"{REPOSITORY_IN_IMAGE}/{path}"],
                          check=True, capture_output=True).stdout


def listing_of(target: dict) -> _source_lines.Listing:
    """The listing of source lines a target prints: its own, or its base's for an edited target."""
    source = base_of(target) if "edits" in target else target
    return _source_lines.load(LINES_DIR / f"{source['label']}.json")


def write_edited_context(target: dict, original: bytes, context: Path) -> str:
    """Writes the build context of edited.Dockerfile for an edited target and returns the diff.

    ``original`` is the file the target's edit set names, from the base target's image. The
    context gets the edited file under ``source/`` at its path within the repository, and
    ``changes.txt``, its diff against ``original``. Stops the script, with nothing written, when
    the edit set is for another commit than the base target's or one of its edits does not
    apply (see ``_source_edits.apply``). A context left by an earlier run is replaced.
    """
    name = target["edits"]
    edit_set = _source_edits.load(EDITS_DIR / name)
    base = base_of(target)
    if edit_set.commit != base["commit"]:
        sys.exit(f"{name} is written for commit {edit_set.commit}, the base image has {base['commit']}; stopping")
    try:
        edited = _source_edits.apply(edit_set, original)
    except _source_edits.SourceEditError as error:
        sys.exit(f"{name}: {error}; nothing was changed, stopping")
    diff = _source_edits.unified_diff(edit_set, original, edited)
    # The directory is this script's own output; clearing it keeps a file that an earlier edit
    # set named out of the image.
    shutil.rmtree(context, ignore_errors=True)
    edited_path = context / "source" / edit_set.file
    edited_path.parent.mkdir(parents=True)
    edited_path.write_bytes(edited)
    (context / "changes.txt").write_bytes(diff.encode("utf-8"))
    print(f"{target['label']}: {name}: {_source_edits.summary(edit_set)}")
    return diff


PLUGIN_WARNING = re.compile(r"^WARNING: update-(vals|keys) already refers to: ")
"""Warnings that the development-profile plugins of project.clj print on Clojure 1.11 at start-up."""


def without_plugin_warnings(text: str) -> str:
    """`text` without PLUGIN_WARNING lines, followed by a note of how many were left out."""
    lines = text.splitlines()
    kept = [line for line in lines if not PLUGIN_WARNING.match(line)]
    omitted = len(lines) - len(kept)
    note = [f"({omitted} Leiningen plugin warnings 'update-vals/update-keys already refers to' omitted)"] if omitted else []
    return "\n".join(note + kept)


def in_image(target: dict, name: str, command: list[str]) -> str:
    """Runs `command` in a fresh container of the target's image and returns stdout and stderr."""
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    result = run(["docker", "run", "--rm", "--name", name, tag(target), *command],
                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return without_plugin_warnings(result.stdout)


def show_source(target: dict) -> None:
    """Prints the checked-out commit, any change to it, and the lines of its listing.

    The files are read from the target's image and every listed line is checked against its
    hash before any is printed. For an edited target the hashes are checked on its base's
    files, the target's files must equal them with the edit set made, and the lines are printed
    as edited. Stops the script, naming the commit and each line, when a check fails.
    """
    print(in_image(target, f"{CONTAINER_PREFIX}{target['label']}-source",
                   ["sh", "-c", "cat /opt/source-info/commit.txt; "
                    "echo 'changes to pequod-plus against the commit:'; "
                    "cat /opt/source-info/changes.txt"]))
    listing = listing_of(target)
    paths = [listed.file for listed in listing.files]
    shown = {path: file_in_image(target, path) for path in paths}
    committed = shown
    if "edits" in target:
        committed = {path: file_in_image(base_of(target), path) for path in paths}
        check_edited_files(target, committed, shown)
    try:
        lines = _source_lines.render(listing, committed, shown)
    except _source_lines.SourceLineError as error:
        sys.exit(f"{target['label']}: {error}; stopping")
    source = base_of(target)["label"] if "edits" in target else target["label"]
    print(f"lines listed in lines/{source}.json, sha256 as recorded"
          f"{' (edited lines as edited)' if 'edits' in target else ''}:")
    print("\n".join(lines))


def check_edited_files(target: dict, committed: dict[str, bytes], shown: dict[str, bytes]) -> None:
    """Stops the script unless each file of an edited target's image equals its base's file with
    the target's edit set made; the file the set does not name must be unchanged."""
    edit_set = _source_edits.load(EDITS_DIR / target["edits"])
    expected = dict(committed)
    if edit_set.file in expected:
        expected[edit_set.file] = _source_edits.apply(edit_set, committed[edit_set.file])
    for path in expected:
        if shown[path] != expected[path]:
            sys.exit(f"{target['label']}: {path} in the image differs from {base_of(target)['label']} "
                     f"with {target['edits']} applied; stopping")


def run_closed_forms(target: dict, work: Path) -> Path:
    """Runs probe.closed-forms on the cases file and copies its results out of the container."""
    name = f"{CONTAINER_PREFIX}{target['label']}-closed-forms"
    out = work / f"closed-form-results-{target['label']}.tsv"
    subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    run(["docker", "create", "--name", name, tag(target), "lein", "-o", "run", "-m", "probe.closed-forms",
         f"/tmp/{CASES}.edn", "/tmp/closed-form-results.tsv"], stdout=subprocess.DEVNULL)
    try:
        run(["docker", "cp", str(work / f"{CASES}.edn"), f"{name}:/tmp/{CASES}.edn"])
        print(without_plugin_warnings(
            run(["docker", "start", "-a", name], stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout))
        run(["docker", "cp", f"{name}:/tmp/closed-form-results.tsv", str(out)])
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
    return out


def main() -> int:
    """Build the images, run every probe and the verification, and print the wall-clock seconds."""
    # Line buffering keeps this script's lines in order with the output of the child processes.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    fetch.add_location_arguments(parser)
    parser.add_argument("--no-build", action="store_true", help="use the images already built")
    args = parser.parse_args()
    work = args.cache / WORK_DIRECTORY
    work.mkdir(parents=True, exist_ok=True)
    timings = []

    start = time.monotonic()
    run([sys.executable, str(HERE / "make_closed_form_cases.py"), str(work),
         "--cache", str(args.cache), "--data-dir", str(args.data_dir)])
    timings.append(("cases", time.monotonic() - start))

    if not args.no_build:
        for target in TARGETS:
            timings.append((f"build {target['label']}", build(target, work)))

    results = []
    for target in TARGETS:
        print(f"\n######## {target['label']}: {target['note']}\n")
        show_source(target)
        for probe in target["probes"]:
            start = time.monotonic()
            if probe == "closed-forms":
                results.append(f"{target['label']}={run_closed_forms(target, work)}")
            else:
                print(in_image(target, f"{CONTAINER_PREFIX}{target['label']}-{probe}",
                               ["lein", "-o", "run", "-m", f"probe.{probe}"]))
            timings.append((f"{probe} {target['label']}", time.monotonic() - start))

    print("\n######## closed-form verification\n")
    start = time.monotonic()
    run([sys.executable, str(HERE / "verify_closed_forms.py"), str(work / f"{CASES}.json"), *results])
    timings.append(("verify closed forms", time.monotonic() - start))

    print("\nWall-clock seconds:")
    for step, seconds in timings:
        print(f"  {step:<28} {seconds:8.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
