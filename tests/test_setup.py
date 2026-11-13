from collections.abc import Callable
from pathlib import Path
import subprocess

import pytest
from typer.testing import CliRunner

from shopkeep.app import create_app
from shopkeep.identity import GitIdentity
from shopkeep.remount import (
    DEFAULT_LIFECYCLE,
    RemountOperation,
    WorkshopLifecycle,
    mount_source,
    run_workshop_remount,
)
from shopkeep.setup import (
    git_exclude_path,
    is_git_work_tree,
    run_workshop_launch,
    setup_definition,
    upgrade_project_shopkeep_sdk,
    validate_project_shopkeep_sdk,
)


runner = CliRunner()


def resolve_test_identity(_: Path, __: str | None, ___: str | None) -> GitIdentity:
    return GitIdentity("Test User", "test@example.com")


def ignore_identity_seed(_: str, __: GitIdentity) -> None:
    pass


def ignore_config_seed(_: str) -> None:
    pass


def build_test_app(
    executor: Callable[[RemountOperation, Path], None] = run_workshop_remount,
    launcher: Callable[[str], None] = run_workshop_launch,
    *,
    lifecycle: WorkshopLifecycle = DEFAULT_LIFECYCLE,
    identity_resolver: Callable[
        [Path, str | None, str | None], GitIdentity
    ] = resolve_test_identity,
    identity_seeder: Callable[[str, GitIdentity], None] = ignore_identity_seed,
    config_seeder: Callable[[str], None] = ignore_config_seed,
):
    return create_app(
        executor=executor,
        launcher=launcher,
        lifecycle=lifecycle,
        identity_resolver=identity_resolver,
        identity_seeder=identity_seeder,
        config_seeder=config_seeder,
    )


def test_setup_definition_uses_the_default_template_without_a_source(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", None, [])

    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks:\n  - name: project-shopkeep\n"
    )
    assert (tmp_path / ".git" / "info" / "exclude").read_text(encoding="utf-8") == (
        ".workshop/dev.yaml\n.workshop.lock\n.workshop/shopkeep/\n"
    )


def test_setup_definition_writes_the_project_shopkeep_sdk_manifest(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", None, [])

    assert (tmp_path / ".workshop" / "shopkeep" / "sdk.yaml").read_text(
        encoding="utf-8"
    ) == (
        "name: shopkeep\n"
        "plugs:\n"
        "  git-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/git\n"
        "  herdr-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/herdr\n"
    )


def test_setup_definition_adds_the_project_shopkeep_sdk(tmp_path: Path) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", None, [])

    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks:\n  - name: project-shopkeep\n"
    )


def test_setup_definition_excludes_the_project_shopkeep_sdk(tmp_path: Path) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", None, [])

    assert (tmp_path / ".git" / "info" / "exclude").read_text(encoding="utf-8") == (
        ".workshop/dev.yaml\n.workshop.lock\n.workshop/shopkeep/\n"
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
        "  - name: project-shopkeep\n"
    )
    assert exclude.read_text(encoding="utf-8") == (
        ".DS_Store\n.workshop/dev.yaml\n.workshop.lock\n.workshop/shopkeep/\n"
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
        "  - name: project-shopkeep\n"
    )


def test_setup_definition_adds_a_channel_less_pass_through_sdk(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", None, ["custom"])

    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks:\n  - name: custom\n"
        "  - name: project-shopkeep\n"
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
        "  - name: project-shopkeep\n"
    )


def test_setup_definition_adds_a_channel_less_pass_through_sdk_from_a_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", source, ["custom"])

    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nsdks:\n  - name: custom\n  - name: project-shopkeep\n"
    )


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
        "  - name: project-shopkeep\n"
    )


def test_setup_definition_preserves_an_existing_project_shopkeep_sdk(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text(
        "name: base\nsdks:\n  - name: project-shopkeep\n",
        encoding="utf-8",
    )
    (tmp_path / ".git" / "info").mkdir(parents=True)

    setup_definition(tmp_path, "dev", source, [])

    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8").count(
        "  - name: project-shopkeep\n"
    ) == 1


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
        "  - name: project-shopkeep\nactions:\n  test: uv run pytest\n"
    )


def test_validate_project_shopkeep_sdk_accepts_a_legacy_manifest_without_writing(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / ".workshop" / "shopkeep" / "sdk.yaml"
    manifest.parent.mkdir(parents=True)
    legacy = (
        "name: shopkeep\n"
        "plugs:\n"
        "  git-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/git\n"
    )
    manifest.write_text(legacy, encoding="utf-8")

    validate_project_shopkeep_sdk(tmp_path)

    assert manifest.read_text(encoding="utf-8") == legacy


def test_setup_definition_upgrades_a_legacy_project_shopkeep_sdk_manifest(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    manifest = tmp_path / ".workshop" / "shopkeep" / "sdk.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "name: shopkeep\n"
        "plugs:\n"
        "  git-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/git\n",
        encoding="utf-8",
    )

    setup_definition(tmp_path, "dev", None, [])

    assert manifest.read_text(encoding="utf-8") == (
        "name: shopkeep\n"
        "plugs:\n"
        "  git-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/git\n"
        "  herdr-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/herdr\n"
    )
    assert (tmp_path / ".workshop" / "dev.yaml").exists()


def test_setup_definition_refuses_to_overwrite_a_different_shopkeep_sdk(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    manifest = tmp_path / ".workshop" / "shopkeep" / "sdk.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("name: custom\n", encoding="utf-8")

    with pytest.raises(
        ValueError,
        match=(
            "workshop SDK already exists with different content: "
            ".workshop/shopkeep/sdk.yaml"
        ),
    ):
        setup_definition(tmp_path, "dev", None, [])

    assert manifest.read_text(encoding="utf-8") == "name: custom\n"
    assert not (tmp_path / ".workshop" / "dev.yaml").exists()


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
    assert not (tmp_path / ".workshop" / "shopkeep" / "sdk.yaml").exists()


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

    assert (
        "  - name: opencode\n    channel: 2/stable\n"
        "  - name: project-shopkeep\nactions:"
    ) in (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8")


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
        ".workshop/dev.yaml\n.workshop.lock\n.workshop/shopkeep/\n"
    )


def test_setup_definition_reports_the_git_work_tree_it_used_for_excludes(
    tmp_path: Path,
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)

    result = setup_definition(tmp_path, "dev", None, [])

    assert result.definition == tmp_path / ".workshop" / "dev.yaml"
    assert result.excludes.git_work_tree is True


def test_setup_definition_reports_a_project_root_without_a_git_work_tree(
    tmp_path: Path,
) -> None:
    result = setup_definition(tmp_path, "dev", None, [])

    assert result.excludes.git_work_tree is False


def test_upgrade_project_shopkeep_sdk_reports_a_project_root_without_a_work_tree(
    tmp_path: Path,
) -> None:
    result = upgrade_project_shopkeep_sdk(tmp_path)

    assert result.manifest == tmp_path / ".workshop" / "shopkeep" / "sdk.yaml"
    assert result.excludes.git_work_tree is False


def test_setup_command_rejects_a_malformed_dot_git_file(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git").write_text("this is not a gitdir pointer\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        build_test_app(lambda _operation, _source: None, lambda _: None),
        ["setup", "--workshop", "dev"],
    )

    assert result.exit_code == 0
    assert "local excludes were skipped: no git work tree at the project root" in (
        result.stdout
    )
    assert not (tmp_path / "this is not a gitdir pointer").exists()


def test_is_git_work_tree_rejects_a_malformed_dot_git_file(tmp_path: Path) -> None:
    (tmp_path / ".git").write_text("garbage\n", encoding="utf-8")

    assert is_git_work_tree(tmp_path) is False
    assert git_exclude_path(tmp_path) is None


def test_is_git_work_tree_accepts_a_gitdir_pointer(tmp_path: Path) -> None:
    git_dir = tmp_path / "git-common"
    git_dir.mkdir()
    (tmp_path / ".git").write_text("gitdir: git-common\n", encoding="utf-8")

    assert is_git_work_tree(tmp_path) is True
    assert git_exclude_path(tmp_path) == (git_dir / "info" / "exclude").resolve()


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


def test_upgrade_command_rewrites_a_legacy_manifest_and_preserves_the_definition(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    definition = tmp_path / ".workshop" / "dev.yaml"
    definition.parent.mkdir(parents=True)
    definition.write_text("name: dev\nbase: ubuntu@26.04\nsdks: []\n", encoding="utf-8")
    manifest = tmp_path / ".workshop" / "shopkeep" / "sdk.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "name: shopkeep\n"
        "plugs:\n"
        "  git-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/git\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(build_test_app(), ["upgrade"])

    assert result.exit_code == 0
    assert manifest.read_text(encoding="utf-8") == (
        "name: shopkeep\n"
        "plugs:\n"
        "  git-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/git\n"
        "  herdr-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/herdr\n"
    )
    assert definition.read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks: []\n"
    )


def test_upgrade_command_leaves_the_current_manifest_unchanged(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    manifest = tmp_path / ".workshop" / "shopkeep" / "sdk.yaml"
    manifest.parent.mkdir(parents=True)
    current = (
        "name: shopkeep\n"
        "plugs:\n"
        "  git-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/git\n"
        "  herdr-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/herdr\n"
    )
    manifest.write_text(current, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(build_test_app(), ["upgrade"])

    assert result.exit_code == 0
    assert manifest.read_text(encoding="utf-8") == current


def test_upgrade_command_creates_a_missing_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(build_test_app(), ["upgrade"])

    assert result.exit_code == 0
    assert (tmp_path / ".workshop" / "shopkeep" / "sdk.yaml").read_text(
        encoding="utf-8"
    ) == (
        "name: shopkeep\n"
        "plugs:\n"
        "  git-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/git\n"
        "  herdr-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/herdr\n"
    )
    assert (tmp_path / ".git" / "info" / "exclude").read_text(encoding="utf-8") == (
        ".workshop/shopkeep/\n.workshop.lock\n"
    )


def test_upgrade_command_skips_local_excludes_outside_a_git_work_tree(
    tmp_path: Path, monkeypatch
) -> None:
    manifest = tmp_path / ".workshop" / "shopkeep" / "sdk.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        "name: shopkeep\n"
        "plugs:\n"
        "  git-config:\n"
        "    interface: mount\n"
        "    workshop-target: /home/workshop/.config/git\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(build_test_app(), ["upgrade"])

    assert result.exit_code == 0
    assert "herdr-config:" in manifest.read_text(encoding="utf-8")
    assert "local excludes were skipped: no git work tree at the project root" in (
        result.stdout
    )
    assert not (tmp_path / ".git").exists()


def test_setup_command_writes_local_excludes_without_a_skip_message_in_a_repository(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    result = runner.invoke(
        build_test_app(lambda _operation, _source: None, lambda _: None),
        ["setup", "--workshop", "dev", "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert "local excludes were skipped" not in result.output
    assert (tmp_path / ".git" / "info" / "exclude").read_text(encoding="utf-8") == (
        ".workshop/dev.yaml\n.workshop.lock\n.workshop/shopkeep/\n"
    )


def test_upgrade_command_rejects_foreign_manifest_content(
    tmp_path: Path, monkeypatch
) -> None:
    manifest = tmp_path / ".workshop" / "shopkeep" / "sdk.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("name: custom\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(build_test_app(), ["upgrade"])

    assert result.exit_code == 2
    assert result.stderr == (
        "error: workshop SDK already exists with different content: "
        ".workshop/shopkeep/sdk.yaml\n"
    )
    assert manifest.read_text(encoding="utf-8") == "name: custom\n"


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
        build_test_app(record_remount, record_launch),
        ["setup", "--workshop", "dev", "--from", str(source), "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert launches == ["dev"]
    assert calls == [RemountOperation("dev", "skills", "skills")]
    assert (tmp_path / ".workshop" / "dev.yaml").exists()


def test_setup_command_restarts_a_running_workshop_with_populated_sources(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source.yaml"
    source.write_text("name: base\n", encoding="utf-8")
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    skills_source = mount_source(
        tmp_path / "data" / "shopkeep", "Work", "skills", "skills"
    )
    skills_source.mkdir(parents=True)
    (skills_source / "marker").write_text("seeded", encoding="utf-8")
    events: list[tuple[str, ...]] = []

    def record_launch(workshop: str) -> None:
        events.append(("launch", workshop))

    def record_identity(workshop: str, _: GitIdentity) -> None:
        events.append(("identity", workshop))

    def record_config(workshop: str) -> None:
        events.append(("config", workshop))

    def record_status(_: str) -> str:
        return "Ready"

    def record_stop(workshop: str) -> None:
        events.append(("stop", workshop))

    def record_start(workshop: str) -> None:
        events.append(("start", workshop))

    def record_remount(operation: RemountOperation, _: Path) -> None:
        events.append(("remount", operation.sdk, operation.plug))

    result = runner.invoke(
        build_test_app(
            record_remount,
            record_launch,
            lifecycle=WorkshopLifecycle(record_status, record_stop, record_start),
            identity_seeder=record_identity,
            config_seeder=record_config,
        ),
        ["setup", "--workshop", "dev", "--from", str(source), "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert events == [
        ("launch", "dev"),
        ("identity", "dev"),
        ("config", "dev"),
        ("stop", "dev"),
        ("remount", "skills", "skills"),
        ("start", "dev"),
    ]
    assert (skills_source / "marker").read_text(encoding="utf-8") == "seeded"


def test_setup_command_restarts_once_for_multiple_populated_sdks(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    data_root = tmp_path / "data" / "shopkeep"
    for sdk, plug in (
        ("opencode", "opencode-config"),
        ("opencode", "opencode-data"),
        ("skills", "skills"),
    ):
        source = mount_source(data_root, "Work", sdk, plug)
        source.mkdir(parents=True)
        (source / "state.json").write_text("{}", encoding="utf-8")
    events: list[tuple[str, ...]] = []

    def record_remount(operation: RemountOperation, _: Path) -> None:
        events.append(("remount", operation.sdk, operation.plug))

    def record_status(_: str) -> str:
        return "Ready"

    def record_stop(workshop: str) -> None:
        events.append(("stop", workshop))

    def record_start(workshop: str) -> None:
        events.append(("start", workshop))

    result = runner.invoke(
        build_test_app(
            record_remount,
            lambda _: None,
            lifecycle=WorkshopLifecycle(record_status, record_stop, record_start),
        ),
        ["setup", "--workshop", "dev", "--sdk", "opencode", "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert events == [
        ("stop", "dev"),
        ("remount", "opencode", "opencode-config"),
        ("remount", "opencode", "opencode-data"),
        ("remount", "skills", "skills"),
        ("start", "dev"),
    ]


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
        build_test_app(record_remount, record_launch),
        ["setup", "--workshop", "dev", "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert launches == ["dev"]
    assert calls == [RemountOperation("dev", "skills", "skills")]
    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks:\n  - name: skills\n"
        "    channel: latest/edge\n  - name: project-shopkeep\n"
    )


def test_setup_command_skips_local_excludes_outside_a_git_work_tree(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        build_test_app(lambda _operation, _source: None, lambda _: None),
        ["setup", "--workshop", "dev"],
    )

    assert result.exit_code == 0
    assert (tmp_path / ".workshop" / "dev.yaml").exists()
    assert (tmp_path / ".workshop" / "shopkeep" / "sdk.yaml").exists()
    assert "local excludes were skipped: no git work tree at the project root" in (
        result.stdout
    )
    assert not (tmp_path / ".git").exists()


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
        build_test_app(record_remount, lambda _: None),
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
        "    channel: latest/edge\n  - name: project-shopkeep\n"
    )
    assert not (tmp_path / "data" / "shopkeep" / "mounts" / "Work" / "custom").exists()


def test_setup_command_skips_a_channel_less_pass_through_sdk(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    calls: list[RemountOperation] = []

    result = runner.invoke(
        build_test_app(lambda operation, _: calls.append(operation), lambda _: None),
        ["setup", "--workshop", "dev", "--sdk", "custom", "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert calls == [RemountOperation("dev", "skills", "skills")]
    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks:\n  - name: custom\n"
        "  - name: skills\n    channel: latest/edge\n  - name: project-shopkeep\n"
    )
    assert not (tmp_path / "data" / "shopkeep" / "mounts" / "Work" / "custom").exists()


def test_setup_command_preserves_a_pass_through_channel_in_the_default_template(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        build_test_app(lambda _operation, _source: None, lambda _: None),
        ["setup", "--workshop", "dev", "--sdk", "custom/latest/edge/candidate"],
    )

    assert result.exit_code == 0
    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks:\n  - name: custom\n"
        "    channel: latest/edge/candidate\n  - name: project-shopkeep\n"
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
        build_test_app(lambda operation, _: calls.append(operation), lambda _: None),
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
        build_test_app(lambda operation, _: calls.append(operation), lambda _: None),
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
        "  - name: skills\n    channel: candidate\n  - name: project-shopkeep\n"
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

    result = runner.invoke(build_test_app(), args)

    assert result.exit_code == 2
    assert result.stderr == "error: SDK channel must not be empty\n"
    assert not (tmp_path / ".workshop" / "dev.yaml").exists()


def test_setup_command_rejects_conflicting_managed_sdk_channels_before_side_effects(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    resolved: list[Path] = []

    def record_resolution(
        project_root: Path, name: str | None, email: str | None
    ) -> GitIdentity:
        resolved.append(project_root)
        return GitIdentity("Test User", "test@example.com")

    result = runner.invoke(
        build_test_app(identity_resolver=record_resolution),
        [
            "setup",
            "--workshop",
            "dev",
            "--sdk",
            "skills/candidate",
            "--sdk",
            "skills/other",
        ],
    )

    assert result.exit_code == 2
    assert result.stderr == (
        "error: SDK 'skills' has conflicting channels: candidate, other\n"
    )
    assert resolved == []
    assert not (tmp_path / ".workshop" / "dev.yaml").exists()


@pytest.mark.parametrize("with_source", [False, True])
def test_setup_command_rejects_an_empty_sdk_name_before_writing_definition(
    tmp_path: Path, monkeypatch, with_source: bool
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    args = ["setup", "--workshop", "dev", "--sdk", "/latest/edge"]
    if with_source:
        source = tmp_path / "source.yaml"
        source.write_text("name: base\n", encoding="utf-8")
        args.extend(["--from", str(source)])

    result = runner.invoke(build_test_app(), args)

    assert result.exit_code == 2
    assert result.stderr == "error: SDK name must not be empty\n"
    assert not (tmp_path / ".workshop" / "dev.yaml").exists()


def test_setup_command_uses_an_explicit_channel_for_a_managed_sdk(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        build_test_app(lambda _operation, _source: None, lambda _: None),
        ["setup", "--workshop", "dev", "--sdk", "skills/candidate"],
    )

    assert result.exit_code == 0
    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks:\n  - name: skills\n"
        "    channel: candidate\n  - name: project-shopkeep\n"
    )


def test_setup_command_collapses_bare_and_explicit_managed_specs(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    calls: list[RemountOperation] = []

    result = runner.invoke(
        build_test_app(lambda operation, _: calls.append(operation), lambda _: None),
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
    assert (tmp_path / ".workshop" / "dev.yaml").read_text(encoding="utf-8") == (
        "name: dev\nbase: ubuntu@26.04\nsdks:\n  - name: skills\n"
        "    channel: candidate\n  - name: project-shopkeep\n"
    )


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
        build_test_app(record_remount, record_launch),
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


def test_setup_command_seeds_git_identity_after_launch(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    seeds: list[tuple[str, GitIdentity]] = []

    def resolve_identity(
        project_root: Path, name: str | None, email: str | None
    ) -> GitIdentity:
        assert project_root == tmp_path
        return GitIdentity("Test User", "test@example.com")

    def record_seed(workshop: str, identity: GitIdentity) -> None:
        seeds.append((workshop, identity))

    result = runner.invoke(
        build_test_app(
            lambda _operation, _source: None,
            lambda _: None,
            identity_resolver=resolve_identity,
            identity_seeder=record_seed,
        ),
        ["setup", "--workshop", "dev", "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert seeds == [("dev", GitIdentity("Test User", "test@example.com"))]


def test_setup_command_passes_git_identity_overrides(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    received: list[tuple[Path, str | None, str | None]] = []

    def resolve_identity(
        project_root: Path, name: str | None, email: str | None
    ) -> GitIdentity:
        received.append((project_root, name, email))
        return GitIdentity(name or "", email or "")

    result = runner.invoke(
        build_test_app(
            lambda _operation, _source: None,
            lambda _: None,
            identity_resolver=resolve_identity,
        ),
        [
            "setup",
            "--workshop",
            "dev",
            "--sdk",
            "skills",
            "--git-name",
            "Override User",
            "--git-email",
            "override@example.com",
        ],
    )

    assert result.exit_code == 0
    assert received == [(tmp_path, "Override User", "override@example.com")]


def test_setup_command_seeds_identity_with_no_remount(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    seeds: list[tuple[str, GitIdentity]] = []

    def record_seed(workshop: str, identity: GitIdentity) -> None:
        seeds.append((workshop, identity))

    result = runner.invoke(
        build_test_app(
            lambda _operation, _source: None,
            lambda _: None,
            identity_seeder=record_seed,
        ),
        ["setup", "--workshop", "dev", "--sdk", "skills", "--no-remount"],
    )

    assert result.exit_code == 0
    assert seeds == [("dev", GitIdentity("Test User", "test@example.com"))]


def test_setup_command_seeds_herdr_config_after_identity(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    events: list[tuple[str, str]] = []

    def record_identity(workshop: str, _: GitIdentity) -> None:
        events.append(("identity", workshop))

    def record_config(workshop: str) -> None:
        events.append(("config", workshop))

    def record_remount(operation: RemountOperation, _: Path) -> None:
        events.append(("remount", operation.workshop))

    result = runner.invoke(
        build_test_app(
            record_remount,
            lambda _: None,
            identity_seeder=record_identity,
            config_seeder=record_config,
        ),
        ["setup", "--workshop", "dev", "--sdk", "skills"],
    )

    assert result.exit_code == 0
    assert events == [
        ("identity", "dev"),
        ("config", "dev"),
        ("remount", "dev"),
    ]


def test_setup_command_seeds_herdr_config_with_no_remount(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    seeds: list[str] = []
    remounts: list[RemountOperation] = []

    def record_config(workshop: str) -> None:
        seeds.append(workshop)

    def record_remount(operation: RemountOperation, _: Path) -> None:
        remounts.append(operation)

    result = runner.invoke(
        build_test_app(
            record_remount,
            lambda _: None,
            config_seeder=record_config,
        ),
        ["setup", "--workshop", "dev", "--sdk", "skills", "--no-remount"],
    )

    assert result.exit_code == 0
    assert seeds == ["dev"]
    assert remounts == []


def test_setup_command_reports_herdr_config_seed_failure(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    def fail_seed(workshop: str) -> None:
        raise subprocess.CalledProcessError(1, ["workshop", "exec", workshop])

    result = runner.invoke(
        build_test_app(
            lambda _operation, _source: None,
            lambda _: None,
            config_seeder=fail_seed,
        ),
        ["setup", "--workshop", "dev", "--sdk", "skills"],
    )

    assert result.exit_code == 1
    assert result.stderr == (
        "error: workshop launched but herdr config was not applied; "
        "run `shopkeep herdr connect --workshop dev`\n"
    )
    assert (tmp_path / ".workshop" / "dev.yaml").exists()


def test_setup_command_rejects_missing_identity_before_writing(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    def fail_resolution(_: Path, __: str | None, ___: str | None) -> GitIdentity:
        raise ValueError("git identity is not configured: user.name (pass --git-name)")

    result = runner.invoke(
        build_test_app(identity_resolver=fail_resolution),
        ["setup", "--workshop", "dev", "--sdk", "skills"],
    )

    assert result.exit_code == 2
    assert "error: git identity is not configured" in result.stderr
    assert not (tmp_path / ".workshop" / "dev.yaml").exists()
    assert not (tmp_path / ".workshop" / "shopkeep" / "sdk.yaml").exists()


def test_setup_command_reports_identity_seed_failure(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    def fail_seed(workshop: str, _: GitIdentity) -> None:
        raise subprocess.CalledProcessError(1, ["workshop", "exec", workshop])

    result = runner.invoke(
        build_test_app(
            lambda _operation, _source: None,
            lambda _: None,
            identity_seeder=fail_seed,
        ),
        ["setup", "--workshop", "dev", "--sdk", "skills"],
    )

    assert result.exit_code == 1
    assert "workshop launched but git identity was not applied" in result.stderr
    assert "shopkeep git identity --workshop dev" in result.stderr
    assert (tmp_path / ".workshop" / "dev.yaml").exists()


def test_setup_command_validates_sdk_before_resolving_identity(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git" / "info").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    resolved: list[bool] = []

    def resolve_identity(_: Path, __: str | None, ___: str | None) -> GitIdentity:
        resolved.append(True)
        return GitIdentity("Test User", "test@example.com")

    result = runner.invoke(
        build_test_app(identity_resolver=resolve_identity),
        ["setup", "--workshop", "dev", "--sdk", "custom/"],
    )

    assert result.exit_code == 2
    assert result.stderr == "error: SDK channel must not be empty\n"
    assert resolved == []


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
        build_test_app(record_remount, fail_launch),
        ["setup", "--workshop", "dev", "--from", str(source), "--sdk", "skills"],
    )

    assert result.exit_code == 1
    assert result.stderr == "error: workshop setup failed\n"
    assert calls == []
