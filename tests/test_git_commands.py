from pathlib import Path
import subprocess

from typer.testing import CliRunner

from shopkeep.app import create_app
from shopkeep.identity import GitIdentity
from shopkeep.sign import GitCommit, SignPlan, plan_sign, run_git


runner = CliRunner()


def resolve_test_identity(_: Path, name: str | None, email: str | None) -> GitIdentity:
    return GitIdentity(name or "Test User", email or "test@example.com")


def ignore_seed(_: str, __: GitIdentity) -> None:
    pass


def build_app(
    *,
    identity_resolver=resolve_test_identity,
    identity_seeder=ignore_seed,
    sign_planner=plan_sign,
    sign_runner=run_git,
):
    return create_app(
        lambda _operation, _source: None,
        lambda _: None,
        identity_resolver=identity_resolver,
        identity_seeder=identity_seeder,
        sign_planner=sign_planner,
        sign_runner=sign_runner,
    )


def test_git_identity_seeds_a_running_workshop() -> None:
    seeds: list[tuple[str, GitIdentity]] = []

    def record_seed(workshop: str, identity: GitIdentity) -> None:
        seeds.append((workshop, identity))

    result = runner.invoke(
        build_app(identity_seeder=record_seed),
        ["git", "identity", "--workshop", "dev"],
    )

    assert result.exit_code == 0
    assert seeds == [("dev", GitIdentity("Test User", "test@example.com"))]


def test_git_identity_passes_overrides() -> None:
    received: list[tuple[Path, str | None, str | None]] = []

    def resolve_identity(
        project_root: Path, name: str | None, email: str | None
    ) -> GitIdentity:
        received.append((project_root, name, email))
        return GitIdentity(name or "", email or "")

    result = runner.invoke(
        build_app(identity_resolver=resolve_identity),
        [
            "git",
            "identity",
            "--workshop",
            "dev",
            "--git-name",
            "Override User",
            "--git-email",
            "override@example.com",
        ],
    )

    assert result.exit_code == 0
    assert received == [(Path.cwd(), "Override User", "override@example.com")]


def test_git_identity_reports_missing_identity() -> None:
    def fail_resolution(_: Path, __: str | None, ___: str | None) -> GitIdentity:
        raise ValueError("git identity is not configured: user.name (pass --git-name)")

    result = runner.invoke(
        build_app(identity_resolver=fail_resolution),
        ["git", "identity", "--workshop", "dev"],
    )

    assert result.exit_code == 2
    assert "error: git identity is not configured" in result.stderr


def test_git_sign_explain_prints_the_plan_without_signing() -> None:
    plan = SignPlan(
        boundary="upstream (origin/main)",
        base="base-sha",
        commits=(GitCommit("old-sha", "N", ("base-sha",), "Oldest"),),
        stop=None,
    )
    received: list[tuple[Path, str | None]] = []

    def plan_signing(cwd: Path, from_rev: str | None) -> SignPlan:
        received.append((cwd, from_rev))
        return plan

    result = runner.invoke(
        build_app(sign_planner=plan_signing),
        ["git", "sign", "--explain"],
    )

    assert result.exit_code == 0
    assert received == [(Path.cwd(), None)]
    assert "boundary: upstream (origin/main)" in result.stdout
    assert "unsigned commits:\n  old-sha Oldest\n" in result.stdout


def test_git_sign_passes_the_from_revision() -> None:
    plan = SignPlan("--from base", "base-sha", (), None)
    received: list[str | None] = []

    def plan_signing(_: Path, from_rev: str | None) -> SignPlan:
        received.append(from_rev)
        return plan

    result = runner.invoke(
        build_app(sign_planner=plan_signing),
        ["git", "sign", "--explain", "--from", "base"],
    )

    assert result.exit_code == 0
    assert received == ["base"]


def test_git_sign_reports_a_planning_error() -> None:
    def fail_planning(_: Path, __: str | None) -> SignPlan:
        raise ValueError("no signing boundary: pass --from <rev>")

    result = runner.invoke(
        build_app(sign_planner=fail_planning),
        ["git", "sign", "--explain"],
    )

    assert result.exit_code == 2
    assert "error: no signing boundary" in result.stderr


def test_git_sign_reports_nothing_to_sign() -> None:
    plan = SignPlan("upstream (origin/main)", "base-sha", (), "head-sha")

    result = runner.invoke(
        build_app(sign_planner=lambda _, __: plan),
        ["git", "sign", "--explain"],
    )

    assert result.exit_code == 0
    assert "no unsigned commits to sign" in result.stdout


def test_git_sign_dry_run_prints_commands_without_running() -> None:
    plan = SignPlan(
        boundary="upstream (origin/main)",
        base="base-sha",
        commits=(GitCommit("only-sha", "N", ("base-sha",), "Only"),),
        stop=None,
    )
    calls: list[list[str]] = []

    def fake_runner(args: list[str], _: Path) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(["git", *args], 0, "", "")

    result = runner.invoke(
        build_app(
            sign_planner=lambda _, __: plan,
            sign_runner=fake_runner,
        ),
        ["git", "sign", "--dry-run"],
    )

    assert result.exit_code == 0
    assert "would run: git commit --amend --no-edit -S" in result.stdout
    assert calls == []


def test_git_sign_executes_and_reports_the_new_head() -> None:
    plan = SignPlan(
        boundary="upstream (origin/main)",
        base="base-sha",
        commits=(GitCommit("only-sha", "N", ("base-sha",), "Only"),),
        stop=None,
    )
    calls: list[list[str]] = []

    def fake_runner(args: list[str], _: Path) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(["git", *args], 0, "new-head-sha\n", "")
        return subprocess.CompletedProcess(["git", *args], 0, "", "")

    result = runner.invoke(
        build_app(
            sign_planner=lambda _, __: plan,
            sign_runner=fake_runner,
        ),
        ["git", "sign"],
    )

    assert result.exit_code == 0
    assert calls == [
        ["commit", "--amend", "--no-edit", "-S"],
        ["rev-parse", "HEAD"],
    ]
    assert "signed 1 commit(s); HEAD is now new-hea" in result.stdout


def test_git_sign_reports_an_amend_failure() -> None:
    plan = SignPlan(
        boundary="upstream (origin/main)",
        base="base-sha",
        commits=(GitCommit("only-sha", "N", ("base-sha",), "Only"),),
        stop=None,
    )

    def fail(args: list[str], _: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["git", *args], 1, "", "gpg failed")

    result = runner.invoke(
        build_app(
            sign_planner=lambda _, __: plan,
            sign_runner=fail,
        ),
        ["git", "sign"],
    )

    assert result.exit_code == 1
    assert "error: signing failed: gpg failed" in result.stderr
    assert "HEAD is unchanged." in result.stderr


def test_git_sign_reports_a_paused_rebase() -> None:
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

    result = runner.invoke(
        build_app(
            sign_planner=lambda _, __: plan,
            sign_runner=fail,
        ),
        ["git", "sign"],
    )

    assert result.exit_code == 1
    assert "git rebase --continue" in result.stderr
    assert "git rebase --abort" in result.stderr


def test_git_sign_does_not_execute_without_commits() -> None:
    plan = SignPlan("upstream (origin/main)", "base-sha", (), "head-sha")
    calls: list[list[str]] = []

    def fake_runner(args: list[str], _: Path) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return subprocess.CompletedProcess(["git", *args], 0, "", "")

    result = runner.invoke(
        build_app(
            sign_planner=lambda _, __: plan,
            sign_runner=fake_runner,
        ),
        ["git", "sign"],
    )

    assert result.exit_code == 0
    assert "no unsigned commits to sign" in result.stdout
    assert calls == []


def test_git_help_lists_identity() -> None:
    result = runner.invoke(build_app(), ["git", "--help"])

    assert result.exit_code == 0
    assert "identity" in result.stdout


def test_git_identity_reports_seed_failure() -> None:
    def fail_seed(workshop: str, _: GitIdentity) -> None:
        raise subprocess.CalledProcessError(1, ["workshop", "exec", workshop])

    result = runner.invoke(
        build_app(identity_seeder=fail_seed),
        ["git", "identity", "--workshop", "dev"],
    )

    assert result.exit_code == 1
    assert "could not seed git identity for workshop 'dev'" in result.stderr
    assert "is it running?" in result.stderr
