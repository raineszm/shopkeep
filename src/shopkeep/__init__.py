import subprocess
from typing import Annotated

import typer
from platformdirs import user_data_path


app = typer.Typer()

SDK_PLUGS = {
    "opencode": ["opencode-config", "opencode-data"],
    "skills": ["skills"],
}


@app.callback()
def root() -> None:
    """Helpers to streamline the development workflow with Workshop."""


@app.command()
def remount(
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
    for spec in sdk:
        sdk_name, _, plug = spec.partition(":")
        plugs = [plug] if plug else SDK_PLUGS.get(sdk_name)
        if not plugs:
            known_sdks = ", ".join(sorted(SDK_PLUGS))
            typer.echo(
                f"error: unknown plugs for SDK '{sdk_name}'; known SDKs: {known_sdks} "
                "(or pass sdk:plug)",
                err=True,
            )
            raise typer.Exit(code=2)
        for plug_name in plugs:
            source = (
                user_data_path("shopkeep")
                / "mounts"
                / profile
                / sdk_name
                / plug_name
            )
            source.mkdir(parents=True, exist_ok=True)
            typer.echo(f"remount {workshop}/{sdk_name}:{plug_name} {source}")
            subprocess.run(
                [
                    "workshop",
                    "remount",
                    f"{workshop}/{sdk_name}:{plug_name}",
                    str(source),
                ],
                check=True,
            )


def main() -> None:
    app()
