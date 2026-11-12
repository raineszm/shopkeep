from pathlib import Path
import subprocess

import pytest

from shopkeep.identity import (
    GitIdentity,
    read_git_config_value,
    render_git_config,
    resolve_git_identity,
    run_workshop_exec,
    seed_git_identity,
)


def test_read_git_config_value_reports_missing_git(monkeypatch) -> None:
    def missing(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr("shopkeep.identity.subprocess.run", missing)

    with pytest.raises(ValueError, match="git is not installed"):
        read_git_config_value(Path("/repo"), "user.name")


def test_resolve_git_identity_uses_the_host_config() -> None:
    values = {"user.name": "Host User", "user.email": "host@example.com"}

    def read_config(_: Path, key: str) -> str | None:
        return values.get(key)

    identity = resolve_git_identity(Path("/project"), reader=read_config)

    assert identity == GitIdentity("Host User", "host@example.com")


def test_resolve_git_identity_prefers_overrides() -> None:
    values = {"user.name": "Host User", "user.email": "host@example.com"}

    def read_config(_: Path, key: str) -> str | None:
        return values.get(key)

    identity = resolve_git_identity(
        Path("/project"),
        name="Override User",
        email="override@example.com",
        reader=read_config,
    )

    assert identity == GitIdentity("Override User", "override@example.com")


def test_resolve_git_identity_rejects_a_missing_name() -> None:
    def read_config(_: Path, key: str) -> str | None:
        return {"user.email": "host@example.com"}.get(key)

    with pytest.raises(ValueError, match=r"user\.name.*--git-name"):
        resolve_git_identity(Path("/project"), reader=read_config)


def test_resolve_git_identity_rejects_a_missing_email() -> None:
    def read_config(_: Path, key: str) -> str | None:
        return {"user.name": "Host User"}.get(key)

    with pytest.raises(ValueError, match=r"user\.email.*--git-email"):
        resolve_git_identity(Path("/project"), reader=read_config)


def test_resolve_git_identity_rejects_a_blank_override() -> None:
    def read_config(_: Path, key: str) -> str | None:
        return {"user.name": "Host User", "user.email": "host@example.com"}.get(key)

    with pytest.raises(ValueError, match=r"user\.name.*--git-name"):
        resolve_git_identity(Path("/project"), name="  ", reader=read_config)


def test_render_git_config_includes_identity_and_disables_signing() -> None:
    assert render_git_config(GitIdentity("Host User", "host@example.com")) == (
        "[user]\n"
        "\tname = Host User\n"
        "\temail = host@example.com\n"
        "[commit]\n"
        "\tgpgsign = false\n"
        "[tag]\n"
        "\tgpgsign = false\n"
    )


def test_seed_git_identity_writes_the_rendered_config() -> None:
    calls: list[tuple[str, str]] = []

    def record(workshop: str, config: str) -> None:
        calls.append((workshop, config))

    seed_git_identity(
        "dev", GitIdentity("Host User", "host@example.com"), runner=record
    )

    assert calls == [
        (
            "dev",
            "[user]\n"
            "\tname = Host User\n"
            "\temail = host@example.com\n"
            "[commit]\n"
            "\tgpgsign = false\n"
            "[tag]\n"
            "\tgpgsign = false\n",
        )
    ]


def test_run_workshop_exec_writes_the_config_through_bash(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("shopkeep.workshop.subprocess.run", fake_run)

    run_workshop_exec("dev", "[user]\n")

    assert calls == [
        (
            [
                "workshop",
                "exec",
                "--non-interactive",
                "--uid",
                "1000",
                "--gid",
                "1000",
                "dev",
                "--",
                "bash",
                "-c",
                "mkdir -p ~/.config/git && cat > ~/.config/git/config",
            ],
            {"input": "[user]\n", "text": True, "check": True},
        )
    ]
