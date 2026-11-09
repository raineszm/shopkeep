from pathlib import Path
import subprocess

import pytest

from shopkeep.sign import (
    GitCommit,
    SignPlan,
    SigningFailed,
    execute_sign_plan,
    format_sign_plan,
    format_signing_commands,
    plan_sign,
    signing_commands,
)


class FakeGit:
    def __init__(self) -> None:
        self.responses: dict[tuple[str, ...], tuple[int, str, str]] = {
            ("symbolic-ref", "--short", "-q", "HEAD"): (0, "feature\n", ""),
            ("rev-parse", "--verify", "--quiet", "REBASE_HEAD"): (1, "", ""),
            ("status", "--porcelain", "--untracked-files=no"): (0, "", ""),
        }

    def __call__(self, args: list[str], _: Path) -> subprocess.CompletedProcess[str]:
        returncode, stdout, stderr = self.responses.get(
            tuple(args), (1, "", "not found")
        )
        return subprocess.CompletedProcess(["git", *args], returncode, stdout, stderr)


def log_line(sha: str, status: str, parents: str, subject: str) -> str:
    return f"{sha}\x1f{status}\x1f{parents}\x1f{subject}\n"


def test_plan_sign_uses_the_from_boundary() -> None:
    git = FakeGit()
    git.responses[("rev-parse", "--verify", "--quiet", "base^{commit}")] = (
        0,
        "base-sha\n",
        "",
    )
    git.responses[("merge-base", "--is-ancestor", "base-sha", "HEAD")] = (
        0,
        "",
        "",
    )
    git.responses[
        (
            "log",
            "--first-parent",
            "--format=%H%x1f%G?%x1f%P%x1f%s",
            "base-sha..HEAD",
        )
    ] = (
        0,
        log_line("new-sha", "N", "old-sha", "Newest")
        + log_line("old-sha", "N", "base-sha", "Oldest"),
        "",
    )

    plan = plan_sign(Path("/repo"), from_rev="base", runner=git)

    assert plan.boundary == "--from base"
    assert plan.base == "base-sha"
    assert [commit.sha for commit in plan.commits] == ["old-sha", "new-sha"]


def test_plan_sign_uses_the_upstream_boundary() -> None:
    git = FakeGit()
    git.responses[
        ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    ] = (0, "origin/feature\n", "")
    git.responses[("merge-base", "origin/feature", "HEAD")] = (
        0,
        "merge-sha\n",
        "",
    )
    git.responses[
        (
            "log",
            "--first-parent",
            "--format=%H%x1f%G?%x1f%P%x1f%s",
            "merge-sha..HEAD",
        )
    ] = (0, log_line("new-sha", "N", "merge-sha", "Newest"), "")

    plan = plan_sign(Path("/repo"), runner=git)

    assert plan.boundary == "upstream (origin/feature)"
    assert plan.base == "merge-sha"
    assert [commit.sha for commit in plan.commits] == ["new-sha"]


def test_plan_sign_falls_back_to_origin_head() -> None:
    git = FakeGit()
    git.responses[
        ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    ] = (1, "", "no upstream")
    git.responses[("symbolic-ref", "--short", "refs/remotes/origin/HEAD")] = (
        0,
        "origin/main\n",
        "",
    )
    git.responses[("merge-base", "origin/main", "HEAD")] = (
        0,
        "main-sha\n",
        "",
    )
    git.responses[
        (
            "log",
            "--first-parent",
            "--format=%H%x1f%G?%x1f%P%x1f%s",
            "main-sha..HEAD",
        )
    ] = (0, log_line("new-sha", "N", "main-sha", "Newest"), "")

    plan = plan_sign(Path("/repo"), runner=git)

    assert plan.boundary == "origin/HEAD (origin/main)"
    assert plan.base == "main-sha"


def test_plan_sign_requires_a_boundary() -> None:
    git = FakeGit()
    git.responses[("symbolic-ref", "--short", "refs/remotes/origin/HEAD")] = (
        1,
        "",
        "not found",
    )

    with pytest.raises(ValueError, match="pass --from"):
        plan_sign(Path("/repo"), runner=git)


def test_plan_sign_rejects_an_unresolvable_from_revision() -> None:
    git = FakeGit()

    with pytest.raises(ValueError, match="does not resolve"):
        plan_sign(Path("/repo"), from_rev="missing", runner=git)


def test_plan_sign_rejects_a_non_ancestor_from_revision() -> None:
    git = FakeGit()
    git.responses[("rev-parse", "--verify", "--quiet", "other^{commit}")] = (
        0,
        "other-sha\n",
        "",
    )
    git.responses[("merge-base", "--is-ancestor", "other-sha", "HEAD")] = (
        1,
        "",
        "",
    )

    with pytest.raises(ValueError, match="not an ancestor"):
        plan_sign(Path("/repo"), from_rev="other", runner=git)


def test_plan_sign_stops_at_a_signed_commit() -> None:
    git = FakeGit()
    git.responses[("rev-parse", "--verify", "--quiet", "base^{commit}")] = (
        0,
        "base-sha\n",
        "",
    )
    git.responses[("merge-base", "--is-ancestor", "base-sha", "HEAD")] = (
        0,
        "",
        "",
    )
    git.responses[
        (
            "log",
            "--first-parent",
            "--format=%H%x1f%G?%x1f%P%x1f%s",
            "base-sha..HEAD",
        )
    ] = (
        0,
        log_line("new-sha", "N", "signed-sha", "Newest")
        + log_line("signed-sha", "G", "old-sha", "Signed")
        + log_line("old-sha", "N", "base-sha", "Older unsigned"),
        "",
    )

    plan = plan_sign(Path("/repo"), from_rev="base", runner=git)

    assert [commit.sha for commit in plan.commits] == ["new-sha"]
    assert plan.stop == "signed-sha"


@pytest.mark.parametrize("status", ["G", "U"])
def test_plan_sign_reports_nothing_when_head_is_signed(status: str) -> None:
    git = FakeGit()
    git.responses[("rev-parse", "--verify", "--quiet", "base^{commit}")] = (
        0,
        "base-sha\n",
        "",
    )
    git.responses[("merge-base", "--is-ancestor", "base-sha", "HEAD")] = (
        0,
        "",
        "",
    )
    git.responses[
        (
            "log",
            "--first-parent",
            "--format=%H%x1f%G?%x1f%P%x1f%s",
            "base-sha..HEAD",
        )
    ] = (0, log_line("head-sha", status, "base-sha", "Already signed"), "")

    plan = plan_sign(Path("/repo"), from_rev="base", runner=git)

    assert plan.commits == ()
    assert plan.stop == "head-sha"


@pytest.mark.parametrize("status", ["B", "E", "X", "Y", "R"])
def test_plan_sign_refuses_a_broken_signature_in_the_tail(status: str) -> None:
    git = FakeGit()
    git.responses[("rev-parse", "--verify", "--quiet", "base^{commit}")] = (
        0,
        "base-sha\n",
        "",
    )
    git.responses[("merge-base", "--is-ancestor", "base-sha", "HEAD")] = (
        0,
        "",
        "",
    )
    git.responses[
        (
            "log",
            "--first-parent",
            "--format=%H%x1f%G?%x1f%P%x1f%s",
            "base-sha..HEAD",
        )
    ] = (
        0,
        log_line("new-sha", "N", "bad-sha", "Newest")
        + log_line("bad-sha", status, "base-sha", "Broken"),
        "",
    )

    with pytest.raises(ValueError, match=f"bad-sha has signature status {status}"):
        plan_sign(Path("/repo"), from_rev="base", runner=git)


def test_plan_sign_refuses_a_detached_head() -> None:
    git = FakeGit()
    git.responses[("symbolic-ref", "--short", "-q", "HEAD")] = (1, "", "")

    with pytest.raises(ValueError, match="detached HEAD"):
        plan_sign(Path("/repo"), from_rev="base", runner=git)


def test_plan_sign_refuses_an_in_progress_rebase() -> None:
    git = FakeGit()
    git.responses[("rev-parse", "--verify", "--quiet", "REBASE_HEAD")] = (
        0,
        "rebase-sha\n",
        "",
    )

    with pytest.raises(ValueError, match="rebase is already in progress"):
        plan_sign(Path("/repo"), from_rev="base", runner=git)


def test_plan_sign_refuses_tracked_changes() -> None:
    git = FakeGit()
    git.responses[("status", "--porcelain", "--untracked-files=no")] = (
        0,
        " M changed.py\n",
        "",
    )

    with pytest.raises(ValueError, match="tracked changes"):
        plan_sign(Path("/repo"), from_rev="base", runner=git)


def test_plan_sign_refuses_a_merge_commit_in_the_tail() -> None:
    git = FakeGit()
    git.responses[("rev-parse", "--verify", "--quiet", "base^{commit}")] = (
        0,
        "base-sha\n",
        "",
    )
    git.responses[("merge-base", "--is-ancestor", "base-sha", "HEAD")] = (
        0,
        "",
        "",
    )
    git.responses[
        (
            "log",
            "--first-parent",
            "--format=%H%x1f%G?%x1f%P%x1f%s",
            "base-sha..HEAD",
        )
    ] = (
        0,
        log_line("merge-sha", "N", "parent-a parent-b", "Merge feature"),
        "",
    )

    with pytest.raises(ValueError, match="merge commit merge-s"):
        plan_sign(Path("/repo"), from_rev="base", runner=git)


def test_format_sign_plan_lists_the_boundary_range_and_commits() -> None:
    plan = SignPlan(
        boundary="upstream (origin/main)",
        base="base-sha",
        commits=(
            GitCommit("old-sha", "N", ("base-sha",), "Oldest"),
            GitCommit("new-sha", "N", ("old-sha",), "Newest"),
        ),
        stop=None,
    )

    assert format_sign_plan(plan) == (
        "boundary: upstream (origin/main)\n"
        "base: base-sha\n"
        "range: base-sha..HEAD\n"
        "unsigned commits:\n"
        "  old-sha Oldest\n"
        "  new-sha Newest\n"
    )


def test_signing_commands_amends_a_single_commit() -> None:
    plan = SignPlan(
        boundary="upstream (origin/main)",
        base="base-sha",
        commits=(GitCommit("only-sha", "N", ("base-sha",), "Only"),),
        stop=None,
    )

    assert signing_commands(plan) == [["commit", "--amend", "--no-edit", "-S"]]


def test_signing_commands_rebases_after_a_signed_boundary() -> None:
    plan = SignPlan(
        boundary="upstream (origin/main)",
        base="base-sha",
        commits=(
            GitCommit("old-sha", "N", ("signed-sha",), "Oldest"),
            GitCommit("new-sha", "N", ("old-sha",), "Newest"),
        ),
        stop="signed-sha",
    )

    assert signing_commands(plan) == [
        [
            "rebase",
            "--exec",
            "git commit --amend --no-edit -S",
            "--empty=keep",
            "signed-sha",
        ]
    ]


def test_signing_commands_rebases_from_the_oldest_parent_without_a_stop() -> None:
    plan = SignPlan(
        boundary="--from base",
        base="base-sha",
        commits=(
            GitCommit("old-sha", "N", ("base-sha",), "Oldest"),
            GitCommit("new-sha", "N", ("old-sha",), "Newest"),
        ),
        stop=None,
    )

    assert signing_commands(plan) == [
        [
            "rebase",
            "--exec",
            "git commit --amend --no-edit -S",
            "--empty=keep",
            "base-sha",
        ]
    ]


def test_signing_commands_uses_root_for_a_root_commit() -> None:
    plan = SignPlan(
        boundary="--from base",
        base="base-sha",
        commits=(
            GitCommit("root-sha", "N", (), "Root"),
            GitCommit("new-sha", "N", ("root-sha",), "Newest"),
        ),
        stop=None,
    )

    assert signing_commands(plan) == [
        [
            "rebase",
            "--root",
            "--exec",
            "git commit --amend --no-edit -S",
            "--empty=keep",
        ]
    ]


def test_format_signing_commands_quotes_the_rebase_exec_string() -> None:
    commands = [
        [
            "rebase",
            "--exec",
            "git commit --amend --no-edit -S",
            "--empty=keep",
            "base-sha",
        ]
    ]

    assert format_signing_commands(commands) == (
        "would run: git rebase --exec 'git commit --amend --no-edit -S' "
        "--empty=keep base-sha\n"
    )


def test_execute_sign_plan_runs_the_signing_command() -> None:
    plan = SignPlan(
        boundary="upstream (origin/main)",
        base="base-sha",
        commits=(GitCommit("only-sha", "N", ("base-sha",), "Only"),),
        stop=None,
    )
    calls: list[tuple[list[str], Path]] = []

    def record(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        calls.append((args, cwd))
        return subprocess.CompletedProcess(["git", *args], 0, "", "")

    execute_sign_plan(plan, Path("/repo"), runner=record)

    assert calls == [(["commit", "--amend", "--no-edit", "-S"], Path("/repo"))]


def test_execute_sign_plan_reports_a_failed_amend() -> None:
    plan = SignPlan(
        boundary="upstream (origin/main)",
        base="base-sha",
        commits=(GitCommit("only-sha", "N", ("base-sha",), "Only"),),
        stop=None,
    )

    def fail(args: list[str], _: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["git", *args], 1, "", "gpg failed")

    with pytest.raises(SigningFailed) as error:
        execute_sign_plan(plan, Path("/repo"), runner=fail)

    assert error.value.paused is False
    assert "gpg failed" in str(error.value)


def test_execute_sign_plan_reports_a_paused_rebase() -> None:
    plan = SignPlan(
        boundary="--from base",
        base="base-sha",
        commits=(
            GitCommit("old-sha", "N", ("base-sha",), "Oldest"),
            GitCommit("new-sha", "N", ("old-sha",), "Newest"),
        ),
        stop=None,
    )

    def fail(args: list[str], _: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["git", *args], 1, "", "gpg failed")

    with pytest.raises(SigningFailed) as error:
        execute_sign_plan(plan, Path("/repo"), runner=fail)

    assert error.value.paused is True
    assert "gpg failed" in str(error.value)


def test_signing_commands_returns_nothing_without_commits() -> None:
    plan = SignPlan("upstream (origin/main)", "base-sha", (), "head-sha")

    assert signing_commands(plan) == []


def test_format_sign_plan_reports_the_signed_boundary() -> None:
    plan = SignPlan(
        boundary="--from base",
        base="base-sha",
        commits=(GitCommit("new-sha", "N", ("signed-sha",), "Newest"),),
        stop="signed-sha",
    )

    assert format_sign_plan(plan) == (
        "boundary: --from base\n"
        "base: base-sha\n"
        "range: base-sha..HEAD\n"
        "unsigned commits:\n"
        "  new-sha Newest\n"
        "stopped at signed commit signed-\n"
    )


def test_format_sign_plan_reports_nothing_to_sign() -> None:
    plan = SignPlan(
        boundary="upstream (origin/main)",
        base="base-sha",
        commits=(),
        stop="head-sha",
    )

    assert format_sign_plan(plan) == (
        "boundary: upstream (origin/main)\n"
        "base: base-sha\n"
        "range: base-sha..HEAD\n"
        "no unsigned commits to sign\n"
    )
