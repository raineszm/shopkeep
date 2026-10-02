from pathlib import Path
import subprocess

import pytest
from typer.testing import CliRunner

from shopkeep.app import create_app
from shopkeep.remount import RemountOperation
from shopkeep.setup import setup_definition


runner = CliRunner()


def test_setup_definition_uses_the_default_template_without_a_source(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", None, [])

    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks: []\n"
    )
    assert (tmp_path / ".git" / "info" / "exclude").read_text(encoding="utf-8") == (
        ".workshop/dev.yaml\n.workshop.lock\n"
    )


def test_setup_definition_copies_adds_sdk_and_excludes_local_artifacts(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\nsdks:\n  - name: uv\n", encoding="utf-8")
    exclude = tmp_path / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True)
    exclude.write_text(".DS_Store\n", encoding="utf-8")

    setup_definition(tmp_path, "dev", source, ["skills"])

    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nsdks:\n  - name: uv\n  - name: skills\n    channel: latest/edge\n"
    )
    assert exclude.read_text(encoding="utf-8") == (
        ".DS_Store\n.workshop/dev.yaml\n.workshop.lock\n"
    )


def test_setup_definition_adds_a_pass_through_sdk_with_its_requested_channel(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", source, ["custom/latest/edge/candidate"])

    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nsdks:\n  - name: custom\n    channel: latest/edge/candidate\n"
    )


def test_setup_definition_quotes_yaml_significant_pass_through_channels(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", source, ["custom/latest #comment"])

    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        'name: dev\nsdks:\n  - name: custom\n    channel: "latest #comment"\n'
    )


def test_setup_definition_rejects_a_pass_through_sdk_without_a_channel(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)

    with pytest.raises(
        ValueError, match="SDK channel is required for pass-through SDK: custom"
    ):
        setup_definition(tmp_path, "dev", None, ["custom"])

    assert not (tmp_path / ".workshop" / "dev.yaml").exists()


def test_setup_definition_rejects_an_empty_pass_through_channel_from_a_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")
    (tmp_path / ".git" / "info").mkdir(parents=True)

    with pytest.raises(ValueError, match="SDK channel must not be empty"):
        setup_definition(tmp_path, "dev", source, ["custom/"])

    assert not (tmp_path / ".workshop" / "dev.yaml").exists()


def test_setup_definition_preserves_an_existing_requested_sdk(tmp_path: Path) -> None:
    source = tmp_path / "source.yaml"
    source.write_text(
        "name: base\nsdks:\n  - name: skills\n    channel: candidate\n",
        encoding="utf-8",
    )
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", source, ["skills"])

    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nsdks:\n  - name: skills\n    channel: candidate\n"
    )


def test_setup_definition_adds_sdk_before_a_later_top_level_section(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text(
        "name: base\nsdks:\n  - name: uv\nactions:\n  test: uv run pytest\n",
        encoding="utf-8",
    )
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", source, ["skills"])

    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nsdks:\n  - name: uv\n  - name: skills\n    channel: latest/edge\n"
        "actions:\n  test: uv run pytest\n"
    )


def test_setup_definition_rejects_an_existing_target(tmp_path: Path) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")
    target = tmp_path / ".workshop" / "dev.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("name: existing\n", encoding="utf-8")

    try:
        setup_definition(tmp_path, "dev", source, ["skills"])
    except ValueError as error:
        assert str(error) == "workshop definition already exists: .workshop/dev.yaml"
    else:
        raise AssertionError("expected existing workshop definition to be rejected")

    assert target.read_text(encoding="utf-8") == "name: existing\n"


def test_setup_definition_ignores_sdk_names_outside_the_sdks_section(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text(
        "name: base\nsdks:\n  - name: uv\nactions:\n  task:\n    - name: opencode\n",
        encoding="utf-8",
    )
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", source, ["opencode"])

    assert "  - name: opencode\n    channel: latest/stable\nactions:" in (
        tmp_path / ".workshop" / "dev.yaml"
    ).read_text(encoding="utf-8")


def test_setup_definition_deduplicates_requested_sdks(tmp_path: Path) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", source, ["skills", "skills"])

    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8").count(
        "  - name: skills\n"
    ) == 1


def test_setup_definition_uses_linked_worktree_exclude_file(tmp_path: Path) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")
    git_dir = tmp_path / "git-common"
    (git_dir / "info").mkdir(parents=True)
    (tmp_path / ".git").write_text("gitdir: git-common\n", encoding="utf-8")

    setup_definition(tmp_path, "dev", source, ["skills"])

    assert (git_dir / "info" / "exclude").read_text(encoding="utf-8") == (
        ".workshop/dev.yaml\n.workshop.lock\n"
    )


def test_setup_definition_rejects_a_traversing_workshop_name(tmp_path: Path) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")

    try:
        setup_definition(tmp_path, "../outside", source, ["skills"])
    except ValueError as error:
        assert str(error) == "workshop name must not contain path separators"
    else:
        raise AssertionError("expected an invalid workshop name to be rejected")

    assert not (tmp_path / "outside.yaml").exists()


def test_setup_command_remounts_requested_sdk_after_writing_definition(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    calls: list[RemountOperation] = []
    launches: list[str] = []

    def record_remount(operation: RemountOperation, _: Path) -> None:
        calls.append(operation)

    def record_launch(workshop: str) -> None:
        launches.append(workshop)

    result = runner.invoke(
        create_app(record_remount, record_launch),
        ["setup", "--workshop", "dev", "--from", str(source), "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert launches == ["dev"]
    assert calls == [RemountOperation("dev", "skills", "skills")]
    assert (tmp_path / ".workshop" / "dev.yaml").exists()


def test_setup_command_uses_the_default_template_without_from(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    calls: list[RemountOperation] = []
    launches: list[str] = []

    def record_remount(operation: RemountOperation, _: Path) -> None:
        calls.append(operation)

    def record_launch(workshop: str) -> None:
        launches.append(workshop)

    result = runner.invoke(
        create_app(record_remount, record_launch),
        ["setup", "--workshop", "dev", "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert launches == ["dev"]
    assert calls == [RemountOperation("dev", "skills", "skills")]
    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks:\n  - name: skills\n"
        "    channel: latest/edge\n"
    )


def test_setup_command_skips_remounting_a_pass_through_sdk(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    calls: list[RemountOperation] = []

    def record_remount(operation: RemountOperation, _: Path) -> None:
        calls.append(operation)

    result = runner.invoke(
        create_app(record_remount, lambda _: None),
        [
            "setup",
            "--workshop",
            "dev",
            "--sdk",
            "custom/latest/edge/candidate",
            "--sdk",
            "skills",
        ],
    )

    assert result.exit_code == 0
    assert calls == [RemountOperation("dev", "skills", "skills")]
    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks:\n  - name: custom\n"
        "    channel: latest/edge/candidate\n  - name: skills\n"
        "    channel: latest/edge\n"
    )
    assert not (tmp_path / "data" / "shopkeep" / "mounts" / "Work" / "custom").exists()


def test_setup_command_preserves_a_pass_through_channel_in_the_default_template(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        create_app(lambda _operation, _source: None, lambda _: None),
        ["setup", "--workshop", "dev", "--sdk", "custom/latest/edge/candidate"],
    )

    assert result.exit_code == 0
    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks:\n  - name: custom\n"
        "    channel: latest/edge/candidate\n"
    )


def test_setup_command_skips_remounting_a_source_selected_pass_through_sdk(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    calls: list[RemountOperation] = []

    result = runner.invoke(
        create_app(lambda operation, _: calls.append(operation), lambda _: None),
        [
            "setup",
            "--workshop",
            "dev",
            "--from",
            str(source),
            "--sdk",
            "custom/latest/edge",
        ],
    )

    assert result.exit_code == 0
    assert calls == []
    assert not (tmp_path / "data" / "shopkeep" / "mounts" / "Work" / "custom").exists()


def test_setup_command_remounts_managed_sdk_with_a_source_selected_pass_through_sdk(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    calls: list[RemountOperation] = []

    result = runner.invoke(
        create_app(lambda operation, _: calls.append(operation), lambda _: None),
        [
            "setup",
            "--workshop",
            "dev",
            "--from",
            str(source),
            "--sdk",
            "custom/latest/edge",
            "--sdk",
            "skills/candidate",
        ],
    )

    assert result.exit_code == 0
    assert calls == [RemountOperation("dev", "skills", "skills")]
    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nsdks:\n  - name: custom\n    channel: latest/edge\n"
        "  - name: skills\n    channel: latest/edge\n"
    )


@pytest.mark.parametrize("with_source", [False, True])
def test_setup_command_rejects_invalid_sdk_before_writing_definition(
    tmp_path: Path, monkeypatch, with_source: bool
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    args = ["setup", "--workshop", "dev", "--sdk", "custom/"]
    if with_source:
        source = tmp_path / "source.yaml"
        source.write_text("name: base\n", encoding="utf-8")
        args.extend(["--from", str(source)])

    result = runner.invoke(create_app(), args)

    assert result.exit_code == 2
    assert result.stderr == "error: SDK channel must not be empty\n"
    assert not (tmp_path / ".workshop" / "dev.yaml").exists()


def test_setup_command_uses_a_managed_sdks_canonical_channel(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        create_app(lambda _operation, _source: None, lambda _: None),
        ["setup", "--workshop", "dev", "--sdk", "skills/candidate"],
    )

    assert result.exit_code == 0
    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks:\n  - name: skills\n"
        "    channel: latest/edge\n"
    )


def test_setup_command_remounts_a_managed_sdk_once_for_equivalent_specifications(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    calls: list[RemountOperation] = []

    result = runner.invoke(
        create_app(lambda operation, _: calls.append(operation), lambda _: None),
        [
            "setup",
            "--workshop",
            "dev",
            "--sdk",
            "skills",
            "--sdk",
            "skills/candidate",
        ],
    )

    assert result.exit_code == 0
    assert calls == [RemountOperation("dev", "skills", "skills")]


def test_setup_command_skips_remount_with_no_remount(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    calls: list[RemountOperation] = []
    launches: list[str] = []

    def record_remount(operation: RemountOperation, _: Path) -> None:
        calls.append(operation)

    def record_launch(workshop: str) -> None:
        launches.append(workshop)

    result = runner.invoke(
        create_app(record_remount, record_launch),
        [
            "setup",
            "--workshop",
            "dev",
            "--from",
            str(source),
            "--sdk",
            "skills",
            "--no-remount",
        ],
    )

    assert result.exit_code == 0
    assert launches == ["dev"]
    assert calls == []


def test_setup_command_stops_when_workshop_launch_fails(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    calls: list[RemountOperation] = []

    def record_remount(operation: RemountOperation, _: Path) -> None:
        calls.append(operation)

    def fail_launch(_: str) -> None:
        raise subprocess.CalledProcessError(1, ["workshop", "launch"])

    result = runner.invoke(
        create_app(record_remount, fail_launch),
        ["setup", "--workshop", "dev", "--from", str(source), "--sdk", "skills"],
    )

    assert result.exit_code == 1
    assert result.stderr == "error: workshop setup failed\n"
    assert calls == []
