import subprocess
from pathlib import Path

from typer.testing import CliRunner

from shopkeep.app import create_app


runner = CliRunner()


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def commit(cwd: Path, name: str, message: str) -> str:
    (cwd / name).write_text(message, encoding="utf-8")
    git(cwd, "add", name)
    git(cwd, "commit", "-qm", message)
    return git(cwd, "rev-parse", "HEAD")


def make_repository(tmp_path: Path) -> tuple[Path, str]:
    project = tmp_path / "project"
    project.mkdir()
    git(project, "init", "-q")
    git(project, "config", "user.name", "Test User")
    git(project, "config", "user.email", "test@example.com")
    git(project, "config", "commit.gpgsign", "false")
    base = commit(project, "first.txt", "First")
    commit(project, "second.txt", "Second")
    return project, base


def test_sign_explain_reads_a_real_repository(tmp_path: Path, monkeypatch) -> None:
    project, base = make_repository(tmp_path)
    monkeypatch.chdir(project)

    result = runner.invoke(create_app(), ["git", "sign", "--explain", "--from", base])

    assert result.exit_code == 0, result.output
    assert "unsigned commits:\n" in result.stdout
    assert "Second" in result.stdout
    assert "First" not in result.stdout


def test_sign_dry_run_prints_a_real_repository_command(
    tmp_path: Path, monkeypatch
) -> None:
    project, base = make_repository(tmp_path)
    monkeypatch.chdir(project)

    result = runner.invoke(create_app(), ["git", "sign", "--dry-run", "--from", base])

    assert result.exit_code == 0, result.output
    assert "would run: git commit --amend --no-edit -S" in result.stdout


def configure_ssh_signing(project: Path, tmp_path: Path) -> None:
    key = tmp_path / "signing_key"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)],
        check=True,
    )
    git(project, "config", "gpg.format", "ssh")
    git(project, "config", "user.signingkey", f"{key}.pub")


def test_sign_signs_a_single_commit_in_a_real_repository(
    tmp_path: Path, monkeypatch
) -> None:
    project, base = make_repository(tmp_path)
    configure_ssh_signing(project, tmp_path)
    monkeypatch.chdir(project)

    result = runner.invoke(create_app(), ["git", "sign", "--from", base])

    assert result.exit_code == 0, result.output
    assert "signed 1 commit(s)" in result.stdout
    assert "gpgsig" in git(project, "cat-file", "-p", "HEAD")


def test_sign_rebases_and_signs_multiple_commits(tmp_path: Path, monkeypatch) -> None:
    project, base = make_repository(tmp_path)
    commit(project, "third.txt", "Third")
    configure_ssh_signing(project, tmp_path)
    monkeypatch.chdir(project)

    result = runner.invoke(create_app(), ["git", "sign", "--from", base])

    assert result.exit_code == 0, result.output
    assert "signed 2 commit(s)" in result.stdout
    assert git(project, "log", "--format=%s", f"{base}..HEAD") == "Third\nSecond"
    for sha in git(project, "rev-list", f"{base}..HEAD").splitlines():
        assert "gpgsig" in git(project, "cat-file", "-p", sha)


def configure_broken_signing(project: Path, tmp_path: Path) -> None:
    git(project, "config", "gpg.format", "ssh")
    git(project, "config", "user.signingkey", str(tmp_path / "missing.pub"))


def test_sign_reports_a_failed_amend_and_leaves_head_unchanged(
    tmp_path: Path, monkeypatch
) -> None:
    project, base = make_repository(tmp_path)
    configure_broken_signing(project, tmp_path)
    before = git(project, "rev-parse", "HEAD")
    monkeypatch.chdir(project)

    result = runner.invoke(create_app(), ["git", "sign", "--from", base])

    assert result.exit_code == 1
    assert "HEAD is unchanged." in result.stderr
    assert git(project, "rev-parse", "HEAD") == before


def test_sign_leaves_a_failed_rebase_paused(tmp_path: Path, monkeypatch) -> None:
    project, base = make_repository(tmp_path)
    commit(project, "third.txt", "Third")
    configure_broken_signing(project, tmp_path)
    monkeypatch.chdir(project)

    result = runner.invoke(create_app(), ["git", "sign", "--from", base])

    assert result.exit_code == 1
    assert "git rebase --continue" in result.stderr
    assert "git rebase --abort" in result.stderr
    assert "rebase in progress" in git(project, "status")
