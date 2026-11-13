from pathlib import Path

import pytest

from shopkeep.identity import (
    GitIdentity,
    read_git_config_value,
    render_git_config,
    resolve_git_identity,
    seed_git_identity,
)
from shopkeep.project_sdk import ConfigMount, GIT_CONFIG_MOUNT


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


def test_seed_git_identity_writes_the_rendered_config_through_the_git_mount() -> None:
    calls: list[tuple[str, ConfigMount, str]] = []

    def record(workshop: str, mount: ConfigMount, content: str) -> None:
        calls.append((workshop, mount, content))

    seed_git_identity(
        "dev", GitIdentity("Host User", "host@example.com"), writer=record
    )

    assert calls == [
        (
            "dev",
            GIT_CONFIG_MOUNT,
            "[user]\n"
            "\tname = Host User\n"
            "\temail = host@example.com\n"
            "[commit]\n"
            "\tgpgsign = false\n"
            "[tag]\n"
            "\tgpgsign = false\n",
        )
    ]
