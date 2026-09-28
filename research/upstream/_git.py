"""Local clones of the upstream repositories, and git commands that print themselves.

A clone starts as a partial clone that leaves out blobs over 1 MiB, then fetches each left-out
blob on its own. The result holds every commit, tree and blob reachable from any branch or tag,
as a full clone does, but a dropped connection costs one blob rather than the whole download,
and a rerun continues where the last one stopped. Git LFS objects are never downloaded.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

INITIAL_BLOB_LIMIT = "blob:limit=1m"
FETCH_ATTEMPTS = 5


class Repository:
    """A local clone that runs git commands and prints each one before its output."""

    def __init__(self, name: str, path: Path):
        """A clone at ``path``, called ``name`` in what the commands print."""
        self.name = name
        self.path = path

    def git(self, *args: str, show: bool = True, note: str = "", tolerate_failure: bool = False) -> str:
        """Run ``git args`` in the clone and return its standard output.

        With ``show`` the command is printed first, as ``$ git ...`` with the repository name,
        followed by ``note`` when there is one. When git fails, ``tolerate_failure`` returns a
        line stating the exit status and git's standard error; otherwise this raises
        ``subprocess.CalledProcessError``. Git never downloads a missing object here.
        """
        if show:
            suffix = f"   # {note}" if note else ""
            print(f"$ git {' '.join(quoted(a) for a in args)}   [in {self.name}]{suffix}")
        completed = subprocess.run(
            ["git", "-C", str(self.path), *args],
            capture_output=True,
            env=git_environment(lazy_fetch=False),
            check=False,
        )
        if completed.returncode != 0 and tolerate_failure:
            error = completed.stderr.decode("utf-8", errors="replace").strip()
            return f"  (git exited with status {completed.returncode}: {error})\n"
        if completed.returncode != 0:
            raise subprocess.CalledProcessError(
                completed.returncode, completed.args, completed.stdout, completed.stderr
            )
        return completed.stdout.decode("utf-8", errors="replace")

    def missing_blobs(self) -> dict[str, str]:
        """Every blob a tree of any commit names but the clone does not hold, with one of its paths.

        ``rev-list --missing=print`` names the missing objects without their paths, so the
        paths come from ``ls-tree`` of every commit, which reads trees only.
        """
        listing = self.git("rev-list", "--all", "--objects", "--missing=print", show=False)
        missing = {line[1:] for line in listing.split("\n") if line.startswith("?")}
        if not missing:
            return {}
        paths: dict[str, str] = {}
        for commit in self.git("rev-list", "--all", show=False).split():
            for entry in self.git("ls-tree", "-r", commit, show=False).split("\n"):
                meta, _, path = entry.partition("\t")
                fields = meta.split()
                if len(fields) == 3 and fields[2] in missing and fields[2] not in paths:
                    paths[fields[2]] = path
        return {oid: paths.get(oid, "?") for oid in sorted(missing)}


def quoted(argument: str) -> str:
    """``argument`` as it would be typed in a POSIX shell."""
    if re.fullmatch(r"[\w@%+=:,./^-]+", argument):
        return argument
    return "'" + argument.replace("'", "'\\''") + "'"


def git_environment(lazy_fetch: bool) -> dict[str, str]:
    """The environment git runs with: no LFS downloads, no pager, no prompts.

    ``lazy_fetch=False`` also stops a partial clone from downloading an object it lacks when a
    command reads it, so reading never touches the network by accident.
    """
    environment = {
        **os.environ,
        "GIT_LFS_SKIP_SMUDGE": "1",
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
    }
    if not lazy_fetch:
        environment["GIT_NO_LAZY_FETCH"] = "1"
    return environment


def ensure_clone(url: str, destination: Path, fetch: bool) -> None:
    """Make ``destination`` a clone of ``url`` holding every object of every branch and tag.

    A new clone is made with ``--filter=blob:limit=1m`` and ``--no-checkout``; an existing one
    is updated with ``git fetch`` when ``fetch`` is true. Either way every blob the clone still
    lacks is then fetched one at a time, as :func:`fetch_missing_blobs` does.
    """
    if destination.exists():
        if fetch:
            _run_printed(["git", "-C", str(destination), "fetch", "--prune", "--tags", "origin"])
        else:
            print(f"reusing {destination} without fetching")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        _run_printed(["git", "clone", "--no-checkout", f"--filter={INITIAL_BLOB_LIMIT}", url, str(destination)])
    fetch_missing_blobs(Repository(destination.name, destination))


def fetch_missing_blobs(repository: Repository) -> None:
    """Fetch every blob ``repository`` lacks, one blob per request, retrying each a few times.

    Reading a blob with ``git cat-file`` in a partial clone fetches it from the promisor remote.
    Raises ``RuntimeError`` naming the blobs still missing when a blob fails every attempt.
    """
    missing = repository.missing_blobs()
    print(f"{repository.name}: {len(missing)} blob(s) missing from the clone; fetching each one")
    for number, (oid, path) in enumerate(missing.items(), start=1):
        for attempt in range(1, FETCH_ATTEMPTS + 1):
            completed = subprocess.run(
                ["git", "-C", str(repository.path), "cat-file", "blob", oid],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                env=git_environment(lazy_fetch=True),
                check=False,
            )
            if completed.returncode == 0:
                print(f"  {number}/{len(missing)} {oid[:10]} {path}")
                break
            print(f"  {number}/{len(missing)} {oid[:10]} attempt {attempt} failed: "
                  f"{completed.stderr.decode('utf-8', errors='replace').strip()[:200]}")
    still_missing = repository.missing_blobs()
    if still_missing:
        raise RuntimeError(
            f"{repository.name} still lacks {len(still_missing)} blob(s) after {FETCH_ATTEMPTS} attempts "
            f"each; rerun to continue: {', '.join(f'{oid[:10]} {path}' for oid, path in still_missing.items())}"
        )


def _run_printed(command: list[str]) -> None:
    """Print ``command`` and run it, raising ``CalledProcessError`` when it fails."""
    print("$ GIT_LFS_SKIP_SMUDGE=1 " + " ".join(quoted(part) for part in command))
    subprocess.run(command, env=git_environment(lazy_fetch=True), check=True)
