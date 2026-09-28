"""The helpers of ``research/upstream/check_history.py`` and ``_git.py``, on throw-away
repositories built in a temporary directory."""
import pytest

import upstream_paths  # noqa: F401  (puts the scripts on sys.path)

import _git  # noqa: E402
import check_history  # noqa: E402


def test_form_end_skips_strings_and_comments():
    lines = [
        "(defn f [x]",
        "  (str \")\" x) ; ) ) )",
        "  {:a [1 2]})",
        "(defn g [])",
    ]
    assert check_history.form_end(lines, 1) == 3
    assert check_history.form_end(lines, 4) == 4


def test_form_end_refuses_unclosed_form():
    with pytest.raises(ValueError):
        check_history.form_end(["(defn f [x]", "  x"], 1)


def test_timed_runs_link_each_real_line_to_date_and_command():
    lines = [
        "January 3, 2026",
        "text",
        "$ time lein run -m x ppex001 > a.csv",
        "real\t10m1.5s",
        "February 15, 2026:",
        "user$ time lein run -m x ppex002 > b.csv",
        "",
        "real\t20m0.2s",
        "not real\t1m1s",
    ]
    runs = check_history.timed_runs(lines)
    assert runs == [
        {"real": 4, "date": 1, "command": 3},
        {"real": 8, "date": 5, "command": 6},
    ]


def test_line_above_finds_the_nearest_earlier_line_only():
    lines = ["January 21, 2026", "$ time lein run -m a ppex004 > x.csv", "An iteration with 6 councils",
             "January 24, 2026", "me:~$ time lein run -m a ppex004 > x.csv", "real\t1m1s"]
    assert check_history.line_above(lines, 3, check_history.is_date_heading) == 1
    assert check_history.line_above(lines, 6, check_history.is_date_heading) == 4
    assert check_history.line_above(lines, 4, check_history.is_run_command) == 2
    assert check_history.line_above(lines, 1, check_history.is_date_heading) is None
    assert check_history.line_above(lines, 2, check_history.is_run_command) is None
    assert check_history.command_text(lines[1]) == check_history.command_text(lines[4]) == "lein run -m a ppex004 > x.csv"


def test_minutes_seconds_rounds_to_nearest_second():
    assert check_history.minutes_seconds("253m10.673s") == (253, 11)
    assert check_history.minutes_seconds("159m56.236s") == (159, 56)
    assert check_history.minutes_seconds("1m59.6s") == (2, 0)


def make_repo(tmp_path):
    import subprocess
    repo = tmp_path / "r"
    repo.mkdir()
    def git(*a):
        subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)
    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (repo / "run.sh").write_text("time lein run -m x ex1 > a.csv\n")
    (repo / "log.txt").write_text("header\nreal\t12m3.45s\nuser 1m\n")
    (repo / "pic.bin").write_bytes(b"\x00\x01real\t9m9s\n")
    git("add", ".")
    git("commit", "-q", "-m", "one")
    (repo / "log.txt").write_text("header\n")
    git("commit", "-q", "-am", "two")
    git("checkout", "-q", "-b", "side")
    (repo / "side.txt").write_text("took 3 hours\n")
    git("add", ".")
    git("commit", "-q", "-m", "side")
    git("checkout", "-q", "-")
    return _git.Repository("r", repo)


def test_scan_finds_lines_only_in_history_and_skips_binary(tmp_path):
    repo = make_repo(tmp_path)
    scan = check_history.scan_blobs(repo, check_history.object_paths(repo))
    lines = {(p, l) for p, l in scan.hits}
    assert ("log.txt", b"real\t12m3.45s") in lines
    assert ("side.txt", b"took 3 hours") in lines
    assert not any(p == "pic.bin" for p, _ in lines)
    assert scan.counts["binary blobs skipped"] == 1
    assert scan.control == {"run.sh": 1}
    hit = scan.hits[("log.txt", b"real\t12m3.45s")]
    assert hit.line_number == 2
    assert "a 'real' line of time(1) output" in hit.patterns
    assert "a duration like 12m3.4s" in hit.patterns


def test_missing_blobs_empty_for_full_repo(tmp_path):
    repo = make_repo(tmp_path)
    assert repo.missing_blobs() == {}


def make_message_repo(tmp_path):
    import subprocess
    repo = tmp_path / "m"
    repo.mkdir()

    def git(*a):
        subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    git("commit", "-q", "--allow-empty", "-m", "Initial commit")
    git("commit", "-q", "--allow-empty", "-m", "Faster pricing\n\nThe run took 12m3.4s on the laptop.")
    git("checkout", "-q", "-b", "side")
    git("commit", "-q", "--allow-empty", "-m", "First real commit.")
    git("checkout", "-q", "-")
    return _git.Repository("m", repo)


def test_scan_messages_reads_the_message_of_every_commit_of_every_branch(tmp_path):
    repo = make_message_repo(tmp_path)
    scan = check_history.scan_messages(repo)
    every = set(repo.git("rev-list", "--all", show=False).split())
    assert len(scan.commits) == 3 and set(scan.commits) == every
    found = {(hit.line_number, hit.line): hit.patterns for hit in scan.hits}
    assert found == {
        (3, "The run took 12m3.4s on the laptop."): {"a duration like 12m3.4s"},
        (1, "First real commit."): {"the word 'real'"},
    }
    side = repo.git("rev-parse", "side", show=False).strip()
    assert [hit.commit for hit in scan.hits if hit.line_number == 1] == [side]
