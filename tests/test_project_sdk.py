from dataclasses import FrozenInstanceError
import subprocess

import pytest

from shopkeep.project_sdk import (
    CONFIG_MOUNTS,
    GIT_CONFIG_MOUNT,
    HERDR_CONFIG_MOUNT,
    ConfigMount,
    write_config,
)


def test_config_mounts_iterates_git_then_herdr() -> None:
    assert list(CONFIG_MOUNTS) == [GIT_CONFIG_MOUNT, HERDR_CONFIG_MOUNT]


def test_git_config_mount_derives_its_target_and_destination() -> None:
    assert GIT_CONFIG_MOUNT.workshop_target == "/home/workshop/.config/git"
    assert GIT_CONFIG_MOUNT.destination == "/home/workshop/.config/git/config"


def test_herdr_config_mount_derives_its_target_and_destination() -> None:
    assert HERDR_CONFIG_MOUNT.workshop_target == "/home/workshop/.config/herdr"
    assert HERDR_CONFIG_MOUNT.destination == (
        "/home/workshop/.config/herdr/config.toml"
    )


def test_config_mount_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(GIT_CONFIG_MOUNT, "filename", "other")


@pytest.mark.parametrize(
    ("directory", "filename"),
    [
        ("/home/workshop/.config/git", "config"),
        ("../git", "config"),
        (".config/../git", "config"),
        (".config//git", "config"),
        (".config/git/", "config"),
        ("", "config"),
        (".config\\git", "config"),
        (".config/git", "/config"),
        (".config/git", "nested/config"),
        (".config/git", ".."),
        (".config/git", ""),
        (".config/git", "config\\nested"),
    ],
)
def test_config_mount_rejects_unsafe_paths(directory: str, filename: str) -> None:
    with pytest.raises(ValueError):
        ConfigMount(plug="git-config", directory=directory, filename=filename)


def test_config_mount_rejects_an_unsafe_plug() -> None:
    with pytest.raises(ValueError, match="plug"):
        ConfigMount(plug="../git-config", directory=".config/git", filename="config")


def test_write_config_writes_the_mount_destination(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("shopkeep.project_sdk.subprocess.run", fake_run)

    write_config("dev", HERDR_CONFIG_MOUNT, "[terminal]\n")

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
                "mkdir -p /home/workshop/.config/herdr && "
                "cat > /home/workshop/.config/herdr/config.toml",
            ],
            {"input": "[terminal]\n", "text": True, "check": True},
        )
    ]
