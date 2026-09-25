from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
import subprocess

import typer
from platformdirs import user_data_path


@dataclass(frozen=True)
class SDKKnowledge:
    plugs_by_sdk: dict[str, list[str]]

    def resolve(self, spec: str) -> tuple[str, list[str]]:
        sdk_name, separator, plug = spec.partition(":")
        if separator:
            return sdk_name, [plug]
        plugs = self.plugs_by_sdk.get(sdk_name)
        if plugs:
            return sdk_name, list(plugs)
        known_sdks = ", ".join(sorted(self.plugs_by_sdk))
        raise ValueError(
            f"unknown plugs for SDK '{sdk_name}'; known SDKs: {known_sdks} "
            "(or pass sdk:plug)"
        )


SDK_KNOWLEDGE = SDKKnowledge(
    {
        "opencode": ["opencode-config", "opencode-data"],
        "skills": ["skills"],
    }
)


@dataclass(frozen=True)
class RemountOperation:
    workshop: str
    sdk: str
    plug: str


def resolve_sdk_plugs(spec: str) -> tuple[str, list[str]]:
    return SDK_KNOWLEDGE.resolve(spec)


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


def remount(
    workshop: str,
    sdk: list[str],
    profile: str = "Work",
    executor: Callable[[RemountOperation, Path], None] = run_workshop_remount,
) -> None:
    try:

        def display_and_run(operation: RemountOperation, source: Path) -> None:
            typer.echo(
                f"remount {operation.workshop}/{operation.sdk}:{operation.plug} {source}"
            )
            executor(operation, source)

        for spec in sdk:
            execute_remount_operations(
                plan_remount_operations(workshop, [spec]),
                user_data_path("shopkeep"),
                profile,
                display_and_run,
            )
    except subprocess.CalledProcessError as error:
        typer.echo("error: workshop remount failed", err=True)
        raise typer.Exit(code=1) from error
    except ValueError as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(code=2) from error
