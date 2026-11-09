from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess


GitRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]
LOG_FORMAT = "%H%x1f%G?%x1f%P%x1f%s"
SIGN_EXEC = "git commit --amend --no-edit -S"


@dataclass(frozen=True)
class GitCommit:
    sha: str
    status: str
    parents: tuple[str, ...]
    subject: str


@dataclass(frozen=True)
class SignPlan:
    boundary: str
    base: str
    commits: tuple[GitCommit, ...]
    stop: str | None


class SigningFailed(Exception):
    def __init__(
        self, command: list[str], result: subprocess.CompletedProcess[str]
    ) -> None:
        self.paused = command[0] == "rebase"
        detail = (result.stderr or result.stdout).strip()
        super().__init__(detail or f"git {command[0]} failed")


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )


def signing_commands(plan: SignPlan) -> list[list[str]]:
    if not plan.commits:
        return []
    if len(plan.commits) == 1:
        return [["commit", "--amend", "--no-edit", "-S"]]
    if plan.stop is not None:
        stop = plan.stop
        return [["rebase", "--exec", SIGN_EXEC, "--empty=keep", stop]]
    oldest = plan.commits[0]
    if oldest.parents:
        return [["rebase", "--exec", SIGN_EXEC, "--empty=keep", oldest.parents[0]]]
    return [["rebase", "--root", "--exec", SIGN_EXEC, "--empty=keep"]]


def format_signing_commands(commands: list[list[str]]) -> str:
    return "".join(
        f"would run: {shlex.join(['git', *command])}\n" for command in commands
    )


def execute_sign_plan(plan: SignPlan, cwd: Path, runner: GitRunner = run_git) -> None:
    for command in signing_commands(plan):
        result = runner(command, cwd)
        if result.returncode != 0:
            raise SigningFailed(command, result)


def head_revision(cwd: Path, runner: GitRunner = run_git) -> str:
    result = runner(["rev-parse", "HEAD"], cwd)
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError(f"cannot read HEAD: {result.stderr.strip()}")
    return result.stdout.strip()


def format_sign_plan(plan: SignPlan) -> str:
    lines = [
        f"boundary: {plan.boundary}",
        f"base: {plan.base}",
        f"range: {plan.base}..HEAD",
    ]
    if plan.commits:
        lines.append("unsigned commits:")
        lines.extend(f"  {commit.sha[:7]} {commit.subject}" for commit in plan.commits)
        if plan.stop is not None:
            lines.append(f"stopped at signed commit {plan.stop[:7]}")
    else:
        lines.append("no unsigned commits to sign")
    return "\n".join(lines) + "\n"


def plan_sign(
    cwd: Path, from_rev: str | None = None, runner: GitRunner = run_git
) -> SignPlan:
    ensure_branch(cwd, runner)
    ensure_no_rebase(cwd, runner)
    ensure_clean_tracked(cwd, runner)
    boundary, base = resolve_boundary(cwd, from_rev, runner)
    commits, stop = scan_unsigned_tail(cwd, base, runner)
    return SignPlan(boundary, base, commits, stop)


def ensure_branch(cwd: Path, runner: GitRunner) -> None:
    result = runner(["symbolic-ref", "--short", "-q", "HEAD"], cwd)
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError("cannot sign commits on a detached HEAD")


def ensure_no_rebase(cwd: Path, runner: GitRunner) -> None:
    result = runner(["rev-parse", "--verify", "--quiet", "REBASE_HEAD"], cwd)
    if result.returncode == 0:
        raise ValueError("a rebase is already in progress")


def ensure_clean_tracked(cwd: Path, runner: GitRunner) -> None:
    result = runner(["status", "--porcelain", "--untracked-files=no"], cwd)
    if result.returncode != 0:
        raise ValueError(f"cannot read git status: {result.stderr.strip()}")
    if result.stdout.strip():
        raise ValueError(
            "working tree has tracked changes; commit or stash them before signing"
        )


def resolve_boundary(
    cwd: Path, from_rev: str | None, runner: GitRunner
) -> tuple[str, str]:
    if from_rev is not None:
        resolved = runner(
            ["rev-parse", "--verify", "--quiet", f"{from_rev}^{{commit}}"], cwd
        )
        if resolved.returncode != 0 or not resolved.stdout.strip():
            raise ValueError(f"--from does not resolve to a commit: {from_rev}")
        base = resolved.stdout.strip()
        ancestor = runner(["merge-base", "--is-ancestor", base, "HEAD"], cwd)
        if ancestor.returncode != 0:
            raise ValueError(f"--from is not an ancestor of HEAD: {from_rev}")
        return f"--from {from_rev}", base

    upstream = runner(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd,
    )
    if upstream.returncode == 0 and upstream.stdout.strip():
        name = upstream.stdout.strip()
        return f"upstream ({name})", merge_base(cwd, name, runner)

    origin = runner(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd)
    if origin.returncode == 0 and origin.stdout.strip():
        name = origin.stdout.strip()
        return f"origin/HEAD ({name})", merge_base(cwd, name, runner)

    raise ValueError("no signing boundary: pass --from <rev>")


def merge_base(cwd: Path, ref: str, runner: GitRunner) -> str:
    result = runner(["merge-base", ref, "HEAD"], cwd)
    if result.returncode != 0 or not result.stdout.strip():
        raise ValueError(f"cannot find a merge-base between {ref} and HEAD")
    return result.stdout.strip()


def scan_unsigned_tail(
    cwd: Path, base: str, runner: GitRunner
) -> tuple[tuple[GitCommit, ...], str | None]:
    result = runner(
        ["log", "--first-parent", f"--format={LOG_FORMAT}", f"{base}..HEAD"],
        cwd,
    )
    if result.returncode != 0:
        raise ValueError(f"cannot read commits: {result.stderr.strip()}")

    newest_first: list[GitCommit] = []
    stop: str | None = None
    for line in result.stdout.splitlines():
        if not line:
            continue
        sha, status, parents, subject = line.split("\x1f", 3)
        commit = GitCommit(
            sha,
            status,
            tuple(parents.split()) if parents else (),
            subject,
        )
        if status == "N":
            newest_first.append(commit)
            continue
        if status in {"G", "U"}:
            stop = sha
            break
        raise ValueError(
            f"commit {sha[:7]} has signature status {status}; refusing to rewrite it"
        )

    commits = tuple(reversed(newest_first))
    for commit in commits:
        if len(commit.parents) > 1:
            raise ValueError(
                f"merge commit {commit.sha[:7]} is in the unsigned range; "
                "sign a linear range instead"
            )
    return commits, stop
