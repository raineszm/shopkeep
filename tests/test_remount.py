import subprocess
from pathlib import Path

from typer.testing import CliRunner

from shopkeep import app


runner = CliRunner()


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
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    calls: list[list[str]] = []

    def record_run(command: list[str], *, check: bool) -> None:
        assert check is True
        calls.append(command)

    monkeypatch.setattr(subprocess, "run", record_run)

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
    assert calls == [
        ["workshop", "remount", "hotsos/opencode:opencode-config", str(config)],
        ["workshop", "remount", "hotsos/opencode:opencode-data", str(data)],
    ]


def test_remount_command_rejects_an_unknown_sdk(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["remount", "hotsos", "--sdk", "unknown"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr == (
        "error: unknown plugs for SDK 'unknown'; known SDKs: opencode, skills "
        "(or pass sdk:plug)\n"
    )
