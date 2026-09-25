import typer

from .remount import remount


app = typer.Typer()


@app.callback()
def root() -> None:
    """Helpers to streamline the development workflow with Workshop."""


app.command()(remount)


def main() -> None:
    app()
