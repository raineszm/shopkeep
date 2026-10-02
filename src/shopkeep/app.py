import typer
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from .remount import RemountOperation, remount, run_workshop_remount
from .setup import run_workshop_launch, setup_definition, unique_sdk_names


def create_app(
    executor: Callable[[RemountOperation, Path], None] = run_workshop_remount,
    launcher: Callable[[str], None] = run_workshop_launch,
) -> typer.Typer:
    app = typer.Typer()

    @app.callback()
    def root() -> None:
        """Helpers to streamline the development workflow with Workshop."""

    @app.command(name="remount")
    def remount_command(
        workshop: Annotated[str, typer.Argument(help="Workshop name")],
        sdk: Annotated[
            list[str],
            typer.Option("--sdk", help="SDK name to remount; repeat for multiple SDKs"),
        ],
        profile: Annotated[
            str,
            typer.Option("--profile", help="Profile root directory"),
        ] = "Work",
    ) -> None:
        remount(workshop, sdk, profile, executor)

    @app.command(name="setup")
    def setup_command(
        workshop: Annotated[str, typer.Option("--workshop", help="Workshop name")],
        source: Annotated[
            Path,
            typer.Option("--from", help="Workshop definition to copy"),
        ],
        sdk: Annotated[
            list[str],
            typer.Option("--sdk", help="SDK name to add; repeat for multiple SDKs"),
        ],
        no_remount: Annotated[
            bool,
            typer.Option("--no-remount", help="Do not remount SDK plugs after setup"),
        ] = False,
    ) -> None:
        try:
            sdk = unique_sdk_names(sdk)
            setup_definition(Path.cwd(), workshop, source, sdk)
            launcher(workshop)
            if not no_remount:
                remount(workshop, sdk, executor=executor)
        except subprocess.CalledProcessError as error:
            typer.echo("error: workshop setup failed", err=True)
            raise typer.Exit(code=1) from error
        except ValueError as error:
            typer.echo(f"error: {error}", err=True)
            raise typer.Exit(code=2) from error

    return app


app = create_app()


def main() -> None:
    app()
