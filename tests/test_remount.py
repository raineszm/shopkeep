import importlib
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from shopkeep import app
from shopkeep.app import create_app
from shopkeep.remount import (
    RemountOperation,
    WorkshopLifecycle,
    execute_remount_operations,
    mount_source,
    plan_remount_operations,
    remount,
    resolve_sdk_plugs,
)


runner = CliRunner()


def noop_lifecycle_action(_: str) -> None:
    pass


class RecordingLifecycle:
    """A lifecycle stub that records calls into one event log.

    Status reads return each value in order and then keep repeating the last.
    Set ``status_error`` or ``start_error`` to exercise the failure paths.
    """

    def __init__(self, *statuses: str) -> None:
        self.events: list[tuple[str, ...]] = []
        self.statuses = list(statuses) or ["Ready"]
        self.status_error: Exception | None = None
        self.start_error: Exception | None = None

    @property
    def lifecycle(self) -> WorkshopLifecycle:
        return WorkshopLifecycle(self.read_status, self.stop, self.start)

    def read_status(self, workshop: str) -> str:
        self.events.append(("status", workshop))
        if self.status_error is not None:
            raise self.status_error
        if len(self.statuses) > 1:
            return self.statuses.pop(0)
        return self.statuses[0]

    def stop(self, workshop: str) -> None:
        self.events.append(("stop", workshop))

    def start(self, workshop: str) -> None:
        self.events.append(("start", workshop))
        if self.start_error is not None:
            raise self.start_error


def test_lifecycle_owns_status_parsing_for_running_states() -> None:
    lifecycle = WorkshopLifecycle(
        lambda _: "  READY  \n", noop_lifecycle_action, noop_lifecycle_action
    )

    assert lifecycle.is_running("hotsos") is True


def test_lifecycle_treats_an_unreadable_status_as_not_running() -> None:
    def fail_status(_: str) -> str:
        raise subprocess.CalledProcessError(1, ["workshop", "info"])

    lifecycle = WorkshopLifecycle(
        fail_status, noop_lifecycle_action, noop_lifecycle_action
    )

    assert lifecycle.is_running("hotsos") is False


def test_resolve_sdk_plugs_expands_a_managed_sdk_in_configured_order() -> None:
    assert resolve_sdk_plugs("opencode") == (
        "opencode",
        ["opencode-config", "opencode-data"],
    )


def test_resolve_sdk_plugs_does_not_expose_registry_plugs_for_mutation() -> None:
    _, plugs = resolve_sdk_plugs("skills")
    plugs.append("extra")

    assert resolve_sdk_plugs("skills") == ("skills", ["skills"])


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


def test_remount_command_stops_a_running_workshop_for_populated_sources(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    data_root = tmp_path / "data" / "shopkeep"
    skills_source = mount_source(data_root, "Work", "skills", "skills")
    skills_source.mkdir(parents=True)
    (skills_source / "state.json").write_text("{}", encoding="utf-8")
    recorded = RecordingLifecycle("Ready")

    def record_execution(operation: RemountOperation, _: Path) -> None:
        recorded.events.append(("remount", operation.sdk, operation.plug))

    result = runner.invoke(
        create_app(record_execution, lifecycle=recorded.lifecycle),
        ["remount", "hotsos", "--sdk", "opencode", "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert recorded.events == [
        ("status", "hotsos"),
        ("stop", "hotsos"),
        ("remount", "opencode", "opencode-config"),
        ("remount", "opencode", "opencode-data"),
        ("remount", "skills", "skills"),
        ("start", "hotsos"),
        ("status", "hotsos"),
    ]


@pytest.mark.parametrize("status", ["Failed", "Error"])
def test_remount_command_treats_failed_and_error_statuses_as_not_running(
    tmp_path: Path, monkeypatch, status: str
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    skills_source = mount_source(
        tmp_path / "data" / "shopkeep", "Work", "skills", "skills"
    )
    skills_source.mkdir(parents=True)
    (skills_source / "state.json").write_text("{}", encoding="utf-8")
    recorded = RecordingLifecycle(status)

    def record_execution(operation: RemountOperation, _: Path) -> None:
        recorded.events.append(("remount", operation.sdk, operation.plug))

    result = runner.invoke(
        create_app(record_execution, lifecycle=recorded.lifecycle),
        ["remount", "hotsos", "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert recorded.events == [
        ("status", "hotsos"),
        ("remount", "skills", "skills"),
    ]


def test_remount_command_keeps_the_atomic_path_when_status_cannot_be_read(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    skills_source = mount_source(
        tmp_path / "data" / "shopkeep", "Work", "skills", "skills"
    )
    skills_source.mkdir(parents=True)
    (skills_source / "state.json").write_text("{}", encoding="utf-8")
    recorded = RecordingLifecycle()
    recorded.status_error = subprocess.CalledProcessError(1, ["workshop", "info"])

    def record_execution(operation: RemountOperation, _: Path) -> None:
        recorded.events.append(("remount", operation.sdk, operation.plug))

    result = runner.invoke(
        create_app(record_execution, lifecycle=recorded.lifecycle),
        ["remount", "hotsos", "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert recorded.events == [
        ("status", "hotsos"),
        ("remount", "skills", "skills"),
    ]


def test_remount_command_keeps_the_atomic_path_when_status_is_unparseable(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    skills_source = mount_source(
        tmp_path / "data" / "shopkeep", "Work", "skills", "skills"
    )
    skills_source.mkdir(parents=True)
    (skills_source / "state.json").write_text("{}", encoding="utf-8")
    recorded = RecordingLifecycle("")

    def record_execution(operation: RemountOperation, _: Path) -> None:
        recorded.events.append(("remount", operation.sdk, operation.plug))

    result = runner.invoke(
        create_app(record_execution, lifecycle=recorded.lifecycle),
        ["remount", "hotsos", "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert recorded.events == [
        ("status", "hotsos"),
        ("remount", "skills", "skills"),
    ]


def test_remount_command_keeps_the_atomic_path_when_sources_are_empty(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    recorded = RecordingLifecycle("Ready")

    def record_execution(operation: RemountOperation, _: Path) -> None:
        recorded.events.append(("remount", operation.sdk, operation.plug))

    result = runner.invoke(
        create_app(record_execution, lifecycle=recorded.lifecycle),
        ["remount", "hotsos", "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert recorded.events == [("remount", "skills", "skills")]


@pytest.mark.parametrize("status", ["Stopped", "off"])
def test_remount_command_remounts_a_stopped_workshop_without_starting_it(
    tmp_path: Path, monkeypatch, status: str
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    data_root = tmp_path / "data" / "shopkeep"
    skills_source = mount_source(data_root, "Work", "skills", "skills")
    skills_source.mkdir(parents=True)
    (skills_source / "state.json").write_text("{}", encoding="utf-8")
    recorded = RecordingLifecycle(status)

    def record_execution(operation: RemountOperation, _: Path) -> None:
        recorded.events.append(("remount", operation.sdk, operation.plug))

    result = runner.invoke(
        create_app(record_execution, lifecycle=recorded.lifecycle),
        ["remount", "hotsos", "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert recorded.events == [
        ("status", "hotsos"),
        ("remount", "skills", "skills"),
    ]


def test_remount_command_starts_the_workshop_after_a_failed_remount(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    data_root = tmp_path / "data" / "shopkeep"
    skills_source = mount_source(data_root, "Work", "skills", "skills")
    skills_source.mkdir(parents=True)
    (skills_source / "state.json").write_text("{}", encoding="utf-8")
    recorded = RecordingLifecycle("Ready")

    def fail_execution(operation: RemountOperation, _: Path) -> None:
        recorded.events.append(("remount", operation.sdk, operation.plug))
        raise subprocess.CalledProcessError(returncode=1, cmd=["workshop"])

    result = runner.invoke(
        create_app(fail_execution, lifecycle=recorded.lifecycle),
        ["remount", "hotsos", "--sdk", "skills"],
    )

    assert result.exit_code == 1
    assert result.stderr == "error: workshop remount failed\n"
    assert recorded.events == [
        ("status", "hotsos"),
        ("stop", "hotsos"),
        ("remount", "skills", "skills"),
        ("start", "hotsos"),
        ("status", "hotsos"),
    ]


def test_remount_starts_the_workshop_when_the_remount_is_interrupted(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    source = mount_source(tmp_path / "data" / "shopkeep", "Work", "skills", "skills")
    source.mkdir(parents=True)
    (source / "state.json").write_text("{}", encoding="utf-8")
    recorded = RecordingLifecycle("Ready")

    def interrupt(_operation: RemountOperation, _source: Path) -> None:
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        remount(
            "hotsos",
            ["skills"],
            executor=interrupt,
            lifecycle=recorded.lifecycle,
        )

    assert recorded.events == [
        ("status", "hotsos"),
        ("stop", "hotsos"),
        ("start", "hotsos"),
        ("status", "hotsos"),
    ]


def test_remount_command_reports_a_restart_command_failure(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    skills_source = mount_source(
        tmp_path / "data" / "shopkeep", "Work", "skills", "skills"
    )
    skills_source.mkdir(parents=True)
    (skills_source / "state.json").write_text("{}", encoding="utf-8")
    recorded = RecordingLifecycle("Ready")
    recorded.start_error = subprocess.CalledProcessError(1, ["workshop", "start"])

    result = runner.invoke(
        create_app(lambda _operation, _source: None, lifecycle=recorded.lifecycle),
        ["remount", "hotsos", "--sdk", "skills"],
    )

    assert result.exit_code == 1
    assert result.stderr == (
        "error: workshop 'hotsos' did not restart after remounting; "
        "run `workshop start hotsos`\n"
    )


def test_remount_command_reports_the_remount_failure_when_restart_also_fails(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    skills_source = mount_source(
        tmp_path / "data" / "shopkeep", "Work", "skills", "skills"
    )
    skills_source.mkdir(parents=True)
    (skills_source / "state.json").write_text("{}", encoding="utf-8")
    recorded = RecordingLifecycle("Ready")
    recorded.start_error = ValueError("the workshop could not be started")

    def fail_execution(operation: RemountOperation, _: Path) -> None:
        recorded.events.append(("remount", operation.sdk, operation.plug))
        raise subprocess.CalledProcessError(1, ["workshop", "remount"])

    result = runner.invoke(
        create_app(fail_execution, lifecycle=recorded.lifecycle),
        ["remount", "hotsos", "--sdk", "skills"],
    )

    assert result.exit_code == 1
    assert result.stderr == "error: workshop remount failed\n"
    assert recorded.events == [
        ("status", "hotsos"),
        ("stop", "hotsos"),
        ("remount", "skills", "skills"),
        ("start", "hotsos"),
    ]


def test_remount_command_fails_when_the_workshop_does_not_come_back_up(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    skills_source = mount_source(
        tmp_path / "data" / "shopkeep", "Work", "skills", "skills"
    )
    skills_source.mkdir(parents=True)
    (skills_source / "state.json").write_text("{}", encoding="utf-8")
    recorded = RecordingLifecycle("Ready", "Stopped")

    def record_execution(operation: RemountOperation, _: Path) -> None:
        recorded.events.append(("remount", operation.sdk, operation.plug))

    result = runner.invoke(
        create_app(record_execution, lifecycle=recorded.lifecycle),
        ["remount", "hotsos", "--sdk", "skills"],
    )

    assert result.exit_code == 1
    assert result.stderr == (
        "error: workshop 'hotsos' did not restart after remounting; "
        "run `workshop start hotsos`\n"
    )
    assert recorded.events == [
        ("status", "hotsos"),
        ("stop", "hotsos"),
        ("remount", "skills", "skills"),
        ("start", "hotsos"),
        ("status", "hotsos"),
    ]


def test_remount_command_reports_a_workshop_that_is_not_ready_after_start(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    skills_source = mount_source(
        tmp_path / "data" / "shopkeep", "Work", "skills", "skills"
    )
    skills_source.mkdir(parents=True)
    (skills_source / "state.json").write_text("{}", encoding="utf-8")
    recorded = RecordingLifecycle("Ready", "Failed")

    def record_execution(operation: RemountOperation, _: Path) -> None:
        recorded.events.append(("remount", operation.sdk, operation.plug))

    result = runner.invoke(
        create_app(record_execution, lifecycle=recorded.lifecycle),
        ["remount", "hotsos", "--sdk", "skills"],
    )

    assert result.exit_code == 1
    assert result.stderr == (
        "error: workshop 'hotsos' did not restart after remounting; "
        "run `workshop start hotsos`\n"
    )
    assert recorded.events == [
        ("status", "hotsos"),
        ("stop", "hotsos"),
        ("remount", "skills", "skills"),
        ("start", "hotsos"),
        ("status", "hotsos"),
    ]


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


def test_remount_command_rejects_unknown_sdk_before_executing_any(
    tmp_path: Path, monkeypatch, recorded_calls: list[list[str]]
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    result = runner.invoke(
        app, ["remount", "hotsos", "--sdk", "skills", "--sdk", "unknown"]
    )

    skills = tmp_path / "data" / "shopkeep" / "mounts" / "Work" / "skills" / "skills"
    assert result.exit_code == 2
    assert recorded_calls == []
    assert not skills.exists()
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
    assert "setup" in result.stdout
    assert "upgrade" in result.stdout


def test_cli_without_a_command_prints_help() -> None:
    result = runner.invoke(app, [])

    assert (
        "Helpers to streamline the development workflow with Workshop." in result.stdout
    )
    assert "remount" in result.stdout
    assert "setup" in result.stdout


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
