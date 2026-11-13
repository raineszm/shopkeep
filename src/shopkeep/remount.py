from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
import re
import subprocess

import typer
from platformdirs import user_data_path

from .sdk import MANAGED_SDKS


NOT_RUNNING_STATUSES = frozenset({"stopped", "off", "failed", "error"})


@dataclass(frozen=True)
class WorkshopLifecycle:
    """How Shopkeep observes and changes a workshop's run state."""

    status_reader: Callable[[str], str]
    stopper: Callable[[str], None]
    starter: Callable[[str], None]

    def is_running(self, workshop: str) -> bool:
        try:
            status = self.status_reader(workshop)
        except subprocess.CalledProcessError:
            return False
        normalized = status.strip().lower()
        return bool(normalized) and normalized not in NOT_RUNNING_STATUSES

    def is_ready(self, workshop: str) -> bool:
        try:
            status = self.status_reader(workshop)
        except subprocess.CalledProcessError:
            return False
        return status.strip().lower() == "ready"

    def stop(self, workshop: str) -> None:
        self.stopper(workshop)

    def start(self, workshop: str) -> None:
        self.starter(workshop)


@dataclass(frozen=True)
class RemountOperation:
    workshop: str
    sdk: str
    plug: str


def resolve_sdk_plugs(spec: str) -> tuple[str, list[str]]:
    sdk_name, separator, plug = spec.partition(":")
    if separator:
        return sdk_name, [plug]
    managed = MANAGED_SDKS.get(sdk_name)
    if managed:
        return sdk_name, list(managed.plugs)
    known_sdks = ", ".join(sorted(MANAGED_SDKS))
    raise ValueError(
        f"unknown plugs for SDK '{sdk_name}'; known SDKs: {known_sdks} "
        "(or pass sdk:plug)"
    )


def plan_remount_operations(
    workshop: str, sdk_specs: list[str]
) -> list[RemountOperation]:
    operations: list[RemountOperation] = []
    for spec in sdk_specs:
        sdk_name, plugs = resolve_sdk_plugs(spec)
        operations.extend(
            RemountOperation(workshop, sdk_name, plug_name) for plug_name in plugs
        )
    return operations


def mount_source(data_root: Path, profile: str, sdk: str, plug: str) -> Path:
    for component in (profile, sdk, plug):
        if not component:
            raise ValueError("profile, SDK, and plug must not be empty")
        if Path(component).is_absolute() or "/" in component or "\\" in component:
            raise ValueError("profile, SDK, and plug must not contain path separators")
        if component in {".", ".."}:
            raise ValueError("profile, SDK, and plug must not be traversal components")
    return data_root / "mounts" / profile / sdk / plug


def execute_remount_operations(
    operations: list[RemountOperation],
    data_root: Path,
    profile: str,
    executor: Callable[[RemountOperation, Path], None],
) -> None:
    for operation in operations:
        source = mount_source(data_root, profile, operation.sdk, operation.plug)
        source.mkdir(parents=True, exist_ok=True)
        executor(operation, source)


def run_workshop_remount(operation: RemountOperation, source: Path) -> None:
    subprocess.run(
        [
            "workshop",
            "remount",
            f"{operation.workshop}/{operation.sdk}:{operation.plug}",
            str(source),
        ],
        check=True,
    )


def parse_workshop_status(info_output: str) -> str:
    match = re.search(r"^status:\s*(\S+)\s*$", info_output, flags=re.MULTILINE)
    return match.group(1) if match else ""


def read_workshop_status(workshop: str) -> str:
    output = subprocess.run(
        ["workshop", "info", workshop],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return parse_workshop_status(output)


def run_workshop_stop(workshop: str) -> None:
    subprocess.run(["workshop", "stop", workshop], check=True)


def run_workshop_start(workshop: str) -> None:
    subprocess.run(["workshop", "start", workshop], check=True)


DEFAULT_LIFECYCLE = WorkshopLifecycle(
    status_reader=read_workshop_status,
    stopper=run_workshop_stop,
    starter=run_workshop_start,
)


class WorkshopRestartFailed(RuntimeError):
    """The workshop did not come back up after Shopkeep stopped it."""


def restart_workshop(lifecycle: WorkshopLifecycle, workshop: str) -> None:
    message = (
        f"workshop '{workshop}' did not restart after remounting; "
        f"run `workshop start {workshop}`"
    )
    try:
        lifecycle.start(workshop)
    except subprocess.CalledProcessError as error:
        raise WorkshopRestartFailed(message) from error
    if not lifecycle.is_ready(workshop):
        raise WorkshopRestartFailed(message)


def source_is_populated(source: Path) -> bool:
    return source.is_dir() and any(source.iterdir())


def remount(
    workshop: str,
    sdk: list[str],
    profile: str = "Work",
    executor: Callable[[RemountOperation, Path], None] = run_workshop_remount,
    lifecycle: WorkshopLifecycle = DEFAULT_LIFECYCLE,
) -> None:
    def display_and_run(operation: RemountOperation, source: Path) -> None:
        typer.echo(
            f"remount {operation.workshop}/{operation.sdk}:{operation.plug} {source}"
        )
        executor(operation, source)

    try:
        operations = plan_remount_operations(workshop, sdk)
        data_root = user_data_path("shopkeep")
        sources = [
            mount_source(data_root, profile, operation.sdk, operation.plug)
            for operation in operations
        ]
        restart = any(source_is_populated(source) for source in sources) and (
            lifecycle.is_running(workshop)
        )
        if restart:
            lifecycle.stop(workshop)
        try:
            execute_remount_operations(operations, data_root, profile, display_and_run)
        except BaseException as error:
            if restart:
                try:
                    restart_workshop(lifecycle, workshop)
                except Exception as restart_error:
                    error.add_note(
                        f"also failed to restart workshop '{workshop}': {restart_error}"
                    )
            raise
        if restart:
            try:
                restart_workshop(lifecycle, workshop)
            except WorkshopRestartFailed as error:
                typer.echo(f"error: {error}", err=True)
                raise typer.Exit(code=1) from error
    except subprocess.CalledProcessError as error:
        typer.echo("error: workshop remount failed", err=True)
        raise typer.Exit(code=1) from error
    except ValueError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
