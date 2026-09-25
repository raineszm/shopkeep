import typer
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from .remount import RemountOperation, remount, run_workshop_remount


def create_app(
    executor: Callable[[RemountOperation, Path], None] = run_workshop_remount,
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

    return app


app = create_app()


def main() -> None:
    app()
