import importlib
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shopkeep import app


runner = CliRunner()


@pytest.fixture
def recorded_calls(monkeypatch) -> list[list[str]]:
    """Patch subprocess.run to record commands invoked with check=True."""
    calls: list[list[str]] = []

    def record_run(command: list[str], *, check: bool) -> None:
        assert check is True
        calls.append(command)

    monkeypatch.setattr(subprocess, "run", record_run)
    return calls


def test_remount_command_remounts_a_specified_plug(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    calls: list[tuple[list[str], bool]] = []

    def record_run(command: list[str], *, check: bool) -> None:
        calls.append((command, check))

    monkeypatch.setattr(subprocess, "run", record_run)

    result = runner.invoke(
        app,
        [
            "remount",
            "hotsos",
            "--sdk",
            "opencode:opencode-config",
            "--profile",
            "Work",
        ],
    )

    source = (
        tmp_path
        / "data"
        / "shopkeep"
        / "mounts"
        / "Work"
        / "opencode"
        / "opencode-config"
    )
    assert result.exit_code == 0
    assert result.stdout == f"remount hotsos/opencode:opencode-config {source}\n"
    assert source.is_dir()
    assert calls == [
        (
            [
                "workshop",
                "remount",
                "hotsos/opencode:opencode-config",
                str(source),
            ],
            True,
        )
    ]


def test_remount_command_remounts_all_known_sdk_plugs(
    tmp_path: Path, monkeypatch, recorded_calls: list[list[str]]
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    result = runner.invoke(app, ["remount", "hotsos", "--sdk", "opencode"])

    config = (
        tmp_path
        / "data"
        / "shopkeep"
        / "mounts"
        / "Work"
        / "opencode"
        / "opencode-config"
    )
    data = (
        tmp_path
        / "data"
        / "shopkeep"
        / "mounts"
        / "Work"
        / "opencode"
        / "opencode-data"
    )
    assert result.exit_code == 0
    assert config.is_dir()
    assert data.is_dir()
    assert recorded_calls == [
        ["workshop", "remount", "hotsos/opencode:opencode-config", str(config)],
        ["workshop", "remount", "hotsos/opencode:opencode-data", str(data)],
    ]


def test_remount_command_remounts_skills_sdk(
    tmp_path: Path, monkeypatch, recorded_calls: list[list[str]]
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    result = runner.invoke(app, ["remount", "hotsos", "--sdk", "skills"])

    source = tmp_path / "data" / "shopkeep" / "mounts" / "Work" / "skills" / "skills"
    assert result.exit_code == 0
    assert result.stdout == f"remount hotsos/skills:skills {source}\n"
    assert source.is_dir()
    assert recorded_calls == [
        ["workshop", "remount", "hotsos/skills:skills", str(source)]
    ]


def test_remount_command_preserves_repeated_sdk_order(
    tmp_path: Path, monkeypatch, recorded_calls: list[list[str]]
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    result = runner.invoke(
        app,
        [
            "remount",
            "hotsos",
            "--sdk",
            "skills",
            "--sdk",
            "opencode:opencode-data",
        ],
    )

    skills = tmp_path / "data" / "shopkeep" / "mounts" / "Work" / "skills" / "skills"
    opencode_data = (
        tmp_path
        / "data"
        / "shopkeep"
        / "mounts"
        / "Work"
        / "opencode"
        / "opencode-data"
    )
    assert result.exit_code == 0
    assert result.stdout == (
        f"remount hotsos/skills:skills {skills}\n"
        f"remount hotsos/opencode:opencode-data {opencode_data}\n"
    )
    assert recorded_calls == [
        ["workshop", "remount", "hotsos/skills:skills", str(skills)],
        ["workshop", "remount", "hotsos/opencode:opencode-data", str(opencode_data)],
    ]


def test_remount_command_remounts_explicit_plug_for_unknown_sdk(
    tmp_path: Path, monkeypatch, recorded_calls: list[list[str]]
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    result = runner.invoke(app, ["remount", "hotsos", "--sdk", "custom-sdk:cache"])

    source = tmp_path / "data" / "shopkeep" / "mounts" / "Work" / "custom-sdk" / "cache"
    assert result.exit_code == 0
    assert result.stdout == f"remount hotsos/custom-sdk:cache {source}\n"
    assert source.is_dir()
    assert recorded_calls == [
        ["workshop", "remount", "hotsos/custom-sdk:cache", str(source)]
    ]


def test_remount_command_uses_custom_profile(
    tmp_path: Path, monkeypatch, recorded_calls: list[list[str]]
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    result = runner.invoke(
        app,
        [
            "remount",
            "hotsos",
            "--sdk",
            "skills",
            "--profile",
            "Sandbox",
        ],
    )

    source = tmp_path / "data" / "shopkeep" / "mounts" / "Sandbox" / "skills" / "skills"
    assert result.exit_code == 0
    assert source.is_dir()
    assert recorded_calls == [
        ["workshop", "remount", "hotsos/skills:skills", str(source)]
    ]


def test_remount_command_stops_when_workshop_remount_fails(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    calls: list[list[str]] = []

    def fail_run(command: list[str], *, check: bool) -> None:
        assert check is True
        calls.append(command)
        raise subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(subprocess, "run", fail_run)

    result = runner.invoke(app, ["remount", "hotsos", "--sdk", "opencode"])

    config = (
        tmp_path
        / "data"
        / "shopkeep"
        / "mounts"
        / "Work"
        / "opencode"
        / "opencode-config"
    )
    data = (
        tmp_path
        / "data"
        / "shopkeep"
        / "mounts"
        / "Work"
        / "opencode"
        / "opencode-data"
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, subprocess.CalledProcessError)
    assert calls == [
        ["workshop", "remount", "hotsos/opencode:opencode-config", str(config)]
    ]
    assert config.is_dir()
    assert not data.exists()


def test_cli_help_lists_remount_command() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert (
        "Helpers to streamline the development workflow with Workshop." in result.stdout
    )
    assert "remount" in result.stdout


def test_main_invokes_typer_app(monkeypatch) -> None:
    app_module = importlib.import_module("shopkeep.app")
    calls: list[None] = []

    def invoke_app() -> None:
        calls.append(None)

    monkeypatch.setattr(app_module, "app", invoke_app)

    app_module.main()

    assert calls == [None]


def test_remount_command_rejects_an_unknown_sdk(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["remount", "hotsos", "--sdk", "unknown"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: unknown plugs for SDK 'unknown'; known SDKs: opencode, skills "
        "(or pass sdk:plug)\n"
    )
