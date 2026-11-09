"""Integration tests that exercise ``shopkeep setup`` against a real Workshop.

These tests launch real Workshop containers and are therefore kept out of the
default unit-test run: they are skipped unless the ``workshop`` CLI is
installed and pytest is run with ``--run-integration``. Run them with::

    uv run pytest --run-integration tests/test_setup_integration.py
"""

import re
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import platformdirs
import pytest
from typer.testing import CliRunner

from shopkeep.app import create_app
from shopkeep.remount import mount_source, resolve_sdk_plugs

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        shutil.which("workshop") is None,
        reason="the workshop CLI is not installed",
    ),
]


@pytest.fixture(autouse=True)
def require_integration_flag(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("--run-integration"):
        pytest.skip("pass --run-integration to run real-Workshop integration tests")


runner = CliRunner()

REQUESTED_SDKS = ("opencode", "skills")
DEFAULT_PROFILE = "Work"
GIT_NAME = "Integration User"
GIT_EMAIL = "integration@example.com"


@dataclass(frozen=True)
class WorkshopProject:
    project: Path
    name: str
    data_root: Path


def isolated_data_root() -> Path:
    """Return an empty Shopkeep data root on the Workshop data filesystem.

    ``workshop remount`` succeeds while the workshop is running only when the
    new source is empty and shares a mounted filesystem with the current
    source. Creating the isolated data root beside the Workshop data keeps that
    invariant without touching the developer's real Shopkeep mounts.
    """
    workshop_data = platformdirs.user_data_path("workshop")
    workshop_data.parent.mkdir(parents=True, exist_ok=True)
    return Path(
        tempfile.mkdtemp(prefix="shopkeep-integration-", dir=workshop_data.parent)
    )


def run_workshop(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["workshop", *args],
        cwd=project,
        capture_output=True,
        text=True,
        check=True,
    )


def mount_sources(info: str) -> dict[str, str]:
    """Extract each mount plug's ``host-source`` from ``workshop info`` output."""
    sources: dict[str, str] = {}
    plug: str | None = None
    for line in info.splitlines():
        plug_match = re.fullmatch(r" {6}(\S+):", line)
        if plug_match:
            plug = plug_match.group(1)
            continue
        source_match = re.fullmatch(r" {8}host-source:\s+(\S+)", line)
        if source_match and plug is not None:
            # `workshop info` abbreviates paths under $HOME with a leading `~`.
            sources[plug] = str(Path(source_match.group(1)).expanduser())
    return sources


def expected_mounts() -> dict[str, str]:
    """Map each requested SDK plug to the Shopkeep-managed source it should use."""
    shopkeep_data = platformdirs.user_data_path("shopkeep")
    mounts: dict[str, str] = {}
    for sdk in REQUESTED_SDKS:
        _, plugs = resolve_sdk_plugs(sdk)
        for plug in plugs:
            mounts[plug] = str(mount_source(shopkeep_data, DEFAULT_PROFILE, sdk, plug))
    return mounts


def setup_args(workshop_name: str, source: Path | None) -> list[str]:
    args = ["setup", "--workshop", workshop_name]
    if source is not None:
        args += ["--from", str(source)]
    for sdk in REQUESTED_SDKS:
        args += ["--sdk", sdk]
    return args


@pytest.fixture
def workshop_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[WorkshopProject]:
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "config", "user.name", GIT_NAME], cwd=project, check=True)
    subprocess.run(["git", "config", "user.email", GIT_EMAIL], cwd=project, check=True)
    data_root = isolated_data_root()
    workshop_name = f"it-{uuid.uuid4().hex[:8]}"
    monkeypatch.chdir(project)
    monkeypatch.setenv("XDG_DATA_HOME", str(data_root))
    try:
        yield WorkshopProject(project, workshop_name, data_root)
    finally:
        subprocess.run(
            ["workshop", "remove", workshop_name],
            cwd=project,
            capture_output=True,
            text=True,
            check=False,
        )
        shutil.rmtree(data_root, ignore_errors=True)


def assert_workshop_is_set_up(workshop: WorkshopProject) -> None:
    """Assert the launched workshop mounts Shopkeep sources and exposes opencode."""
    info = run_workshop(workshop.project, "info", workshop.name)
    assert mount_sources(info.stdout).items() >= expected_mounts().items()

    available = run_workshop(
        workshop.project,
        "exec",
        workshop.name,
        "--",
        "bash",
        "-lc",
        "command -v opencode",
    )
    assert available.stdout.strip() != ""
    assert_git_identity_is_set(workshop)


def assert_git_identity_is_set(workshop: WorkshopProject) -> None:
    config = run_workshop(
        workshop.project,
        "exec",
        "--uid",
        "1000",
        "--gid",
        "1000",
        workshop.name,
        "--",
        "bash",
        "-lc",
        "cat ~/.config/git/config",
    ).stdout
    assert (
        f"[user]\n\tname = {GIT_NAME}\n\temail = {GIT_EMAIL}\n"
        "[commit]\n\tgpgsign = false\n"
        "[tag]\n\tgpgsign = false\n"
    ) == config

    git_available = run_workshop(
        workshop.project,
        "exec",
        "--uid",
        "1000",
        "--gid",
        "1000",
        workshop.name,
        "--",
        "bash",
        "-lc",
        "command -v git",
    )
    if git_available.stdout.strip():
        email = run_workshop(
            workshop.project,
            "exec",
            "--uid",
            "1000",
            "--gid",
            "1000",
            workshop.name,
            "--",
            "git",
            "config",
            "--get",
            "user.email",
        )
        assert email.stdout.strip() == GIT_EMAIL


def test_setup_copies_a_source_definition_and_mounts_supported_sdks(
    workshop_project: WorkshopProject,
) -> None:
    source = workshop_project.project / "source.yaml"
    source.write_text(
        "name: base\nbase: ubuntu@26.04\nsdks: []\nactions:\n  hello: echo hello\n",
        encoding="utf-8",
    )

    result = runner.invoke(create_app(), setup_args(workshop_project.name, source))
    assert result.exit_code == 0, result.output

    definition = (
        workshop_project.project / ".workshop" / f"{workshop_project.name}.yaml"
    ).read_text(encoding="utf-8")
    assert "base: ubuntu@26.04\n" in definition
    assert "  - name: opencode\n    channel: 2/stable\n" in definition
    assert "  - name: skills\n    channel: latest/edge\n" in definition
    assert "  - name: project-shopkeep\n" in definition
    assert "actions:\n  hello: echo hello\n" in definition

    assert_workshop_is_set_up(workshop_project)


def test_git_identity_survives_a_refresh(
    workshop_project: WorkshopProject,
) -> None:
    result = runner.invoke(create_app(), setup_args(workshop_project.name, None))
    assert result.exit_code == 0, result.output

    run_workshop(workshop_project.project, "refresh", workshop_project.name)

    assert_git_identity_is_set(workshop_project)


def test_git_identity_command_restores_a_deleted_config(
    workshop_project: WorkshopProject,
) -> None:
    result = runner.invoke(create_app(), setup_args(workshop_project.name, None))
    assert result.exit_code == 0, result.output

    run_workshop(
        workshop_project.project,
        "exec",
        "--uid",
        "1000",
        "--gid",
        "1000",
        workshop_project.name,
        "--",
        "bash",
        "-lc",
        "rm -f ~/.config/git/config",
    )
    status = run_workshop(
        workshop_project.project,
        "exec",
        "--uid",
        "1000",
        "--gid",
        "1000",
        workshop_project.name,
        "--",
        "bash",
        "-lc",
        "[ -f ~/.config/git/config ] && echo present || echo missing",
    )
    assert status.stdout.strip() == "missing"

    result = runner.invoke(
        create_app(),
        ["git", "identity", "--workshop", workshop_project.name],
    )
    assert result.exit_code == 0, result.output

    assert_git_identity_is_set(workshop_project)


def test_setup_bootstraps_the_default_definition_without_a_source(
    workshop_project: WorkshopProject,
) -> None:
    result = runner.invoke(create_app(), setup_args(workshop_project.name, None))
    assert result.exit_code == 0, result.output

    definition = (
        workshop_project.project / ".workshop" / f"{workshop_project.name}.yaml"
    ).read_text(encoding="utf-8")
    assert definition == (
        f"name: {workshop_project.name}\n"
        "base: ubuntu@26.04\n"
        "sdks:\n"
        "  - name: opencode\n"
        "    channel: 2/stable\n"
        "  - name: skills\n"
        "    channel: latest/edge\n"
        "  - name: project-shopkeep\n"
    )

    assert_workshop_is_set_up(workshop_project)
