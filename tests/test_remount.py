import importlib
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shopkeep import app
from shopkeep.app import create_app
from shopkeep.remount import (
    RemountOperation,
    SDKKnowledge,
    execute_remount_operations,
    mount_source,
    plan_remount_operations,
    resolve_sdk_plugs,
)


runner = CliRunner()


def test_sdk_knowledge_resolves_a_known_sdk_in_configured_order() -> None:
    knowledge = SDKKnowledge({"editor": ["settings", "state"]})

    assert knowledge.resolve("editor") == ("editor", ["settings", "state"])


def test_sdk_knowledge_does_not_expose_its_configured_plugs_for_mutation() -> None:
    knowledge = SDKKnowledge({"editor": ["settings"]})
    _, plugs = knowledge.resolve("editor")
    plugs.append("state")

    assert knowledge.resolve("editor") == ("editor", ["settings"])


def test_sdk_knowledge_resolves_an_explicit_custom_plug() -> None:
    knowledge = SDKKnowledge({"editor": ["settings"]})

    assert knowledge.resolve("custom-sdk:cache") == ("custom-sdk", ["cache"])


def test_sdk_knowledge_lists_its_known_sdks_for_an_unknown_sdk() -> None:
    knowledge = SDKKnowledge({"editor": ["settings"], "skills": ["skills"]})

    with pytest.raises(
        ValueError,
        match="unknown plugs for SDK 'unknown'; known SDKs: editor, skills",
    ):
        knowledge.resolve("unknown")


def test_remount_command_uses_injected_executor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    calls: list[tuple[RemountOperation, Path]] = []

    def record_execution(operation: RemountOperation, source: Path) -> None:
        calls.append((operation, source))

    result = runner.invoke(
        create_app(record_execution), ["remount", "hotsos", "--sdk", "skills"]
    )

    source = tmp_path / "data" / "shopkeep" / "mounts" / "Work" / "skills" / "skills"
    assert result.exit_code == 0
    assert result.stdout == f"remount hotsos/skills:skills {source}\n"
    assert calls == [(RemountOperation("hotsos", "skills", "skills"), source)]


def test_plan_remount_operations_expands_known_sdk_in_configured_order() -> None:
    assert plan_remount_operations("hotsos", ["opencode"]) == [
        RemountOperation("hotsos", "opencode", "opencode-config"),
        RemountOperation("hotsos", "opencode", "opencode-data"),
    ]


def test_resolve_sdk_plugs_preserves_explicit_custom_plug() -> None:
    assert resolve_sdk_plugs("custom-sdk:cache") == ("custom-sdk", ["cache"])


def test_resolve_sdk_plugs_describes_unknown_sdk() -> None:
    with pytest.raises(
        ValueError,
        match="unknown plugs for SDK 'unknown'; known SDKs: opencode, skills",
    ):
        resolve_sdk_plugs("unknown")


def test_mount_source_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not contain path separators"):
        mount_source(tmp_path, "Work", "../opencode", "opencode-config")


@pytest.mark.parametrize(
    ("profile", "sdk", "plug"),
    [
        ("", "opencode", "opencode-config"),
        ("Work", "", "opencode-config"),
        ("Work", "opencode", ""),
        ("Work", "/tmp", "opencode-config"),
        ("Work", "opencode", "."),
        ("Work", "..", "opencode-config"),
    ],
)
def test_mount_source_rejects_invalid_components(
    tmp_path: Path, profile: str, sdk: str, plug: str
) -> None:
    with pytest.raises(ValueError):
        mount_source(tmp_path, profile, sdk, plug)


def test_execute_remount_operations_stops_after_executor_failure(
    tmp_path: Path,
) -> None:
    operations = plan_remount_operations("hotsos", ["opencode"])
    calls: list[tuple[RemountOperation, Path]] = []

    def fail_after_first(operation: RemountOperation, source: Path) -> None:
        calls.append((operation, source))
        raise subprocess.CalledProcessError(1, ["workshop"])

    with pytest.raises(subprocess.CalledProcessError):
        execute_remount_operations(operations, tmp_path, "Work", fail_after_first)

    assert calls == [
        (operations[0], tmp_path / "mounts" / "Work" / "opencode" / "opencode-config")
    ]


def test_execute_remount_operations_uses_planned_order(tmp_path: Path) -> None:
    operations = plan_remount_operations("hotsos", ["skills", "opencode:opencode-data"])
    calls: list[tuple[RemountOperation, Path]] = []

    def record(operation: RemountOperation, source: Path) -> None:
        calls.append((operation, source))

    execute_remount_operations(operations, tmp_path, "Work", record)

    assert calls == [
        (operations[0], tmp_path / "mounts" / "Work" / "skills" / "skills"),
        (
            operations[1],
            tmp_path / "mounts" / "Work" / "opencode" / "opencode-data",
        ),
    ]


def test_remount_command_rejects_traversing_profile(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    result = runner.invoke(
        app, ["remount", "hotsos", "--sdk", "skills", "--profile", "../outside"]
    )

    assert result.exit_code == 2
    assert (
        result.stderr
        == "error: profile, SDK, and plug must not contain path separators\n"
    )
    assert not (tmp_path / "outside").exists()


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
    calls: list[tuple[RemountOperation, Path]] = []

    def fail_execution(operation: RemountOperation, source: Path) -> None:
        calls.append((operation, source))
        raise subprocess.CalledProcessError(returncode=1, cmd=["workshop"])

    result = runner.invoke(
        create_app(fail_execution), ["remount", "hotsos", "--sdk", "opencode"]
    )

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
    assert result.stderr == "error: workshop remount failed\n"
    assert calls == [
        (RemountOperation("hotsos", "opencode", "opencode-config"), config)
    ]
    assert config.is_dir()
    assert not data.exists()


def test_remount_command_executes_prior_sdk_before_rejecting_later_unknown_sdk(
    tmp_path: Path, monkeypatch, recorded_calls: list[list[str]]
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    result = runner.invoke(
        app, ["remount", "hotsos", "--sdk", "skills", "--sdk", "unknown"]
    )

    skills = tmp_path / "data" / "shopkeep" / "mounts" / "Work" / "skills" / "skills"
    assert result.exit_code == 2
    assert recorded_calls == [
        ["workshop", "remount", "hotsos/skills:skills", str(skills)]
    ]
    assert result.stderr == (
        "error: unknown plugs for SDK 'unknown'; known SDKs: opencode, skills "
        "(or pass sdk:plug)\n"
    )


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
