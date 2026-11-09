import typer
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from .remount import RemountOperation, remount, run_workshop_remount
from .herdr import herdr_connect, herdr_disconnect
from .identity import GitIdentity, resolve_git_identity, seed_git_identity
from .sign import (
    GitRunner,
    SigningFailed,
    SignPlan,
    execute_sign_plan,
    format_sign_plan,
    format_signing_commands,
    head_revision,
    plan_sign,
    run_git,
    signing_commands,
)
from .sdk import canonicalize_sdk_specs, managed_sdk_names
from .setup import (
    run_workshop_launch,
    setup_definition,
    validate_workshop_name,
)


def create_app(
    executor: Callable[[RemountOperation, Path], None] = run_workshop_remount,
    launcher: Callable[[str], None] = run_workshop_launch,
    connector: Callable[[str], None] = herdr_connect,
    disconnector: Callable[[str], None] = herdr_disconnect,
    identity_resolver: Callable[
        [Path, str | None, str | None], GitIdentity
    ] = resolve_git_identity,
    identity_seeder: Callable[[str, GitIdentity], None] = seed_git_identity,
    sign_planner: Callable[[Path, str | None], SignPlan] = plan_sign,
    sign_runner: GitRunner = run_git,
) -> typer.Typer:
    app = typer.Typer()

    @app.callback()
    def root() -> None:
        """Helpers to streamline the development workflow with Workshop."""

    git_app = typer.Typer(help="Manage git identity and signed review passes.")
    app.add_typer(git_app, name="git")

    @git_app.command(name="identity")
    def git_identity_command(
        workshop: Annotated[str, typer.Option("--workshop", help="Workshop name")],
        git_name: Annotated[
            str | None,
            typer.Option("--git-name", help="Git user.name for workshop commits"),
        ] = None,
        git_email: Annotated[
            str | None,
            typer.Option("--git-email", help="Git user.email for workshop commits"),
        ] = None,
    ) -> None:
        try:
            validate_workshop_name(workshop)
            identity = identity_resolver(Path.cwd(), git_name, git_email)
            identity_seeder(workshop, identity)
        except subprocess.CalledProcessError as error:
            typer.echo(
                f"error: could not seed git identity for workshop '{workshop}'; "
                "is it running?",
                err=True,
            )
            raise typer.Exit(code=1) from error
        except ValueError as error:
            typer.echo(f"error: {error}", err=True)
            raise typer.Exit(code=2) from error

    @git_app.command(name="sign")
    def git_sign_command(
        from_rev: Annotated[
            str | None,
            typer.Option("--from", help="Sign commits after this revision"),
        ] = None,
        explain: Annotated[
            bool,
            typer.Option("--explain", help="Print the signing plan and exit"),
        ] = False,
        dry_run: Annotated[
            bool,
            typer.Option("--dry-run", help="Print the signing commands and exit"),
        ] = False,
    ) -> None:
        try:
            plan = sign_planner(Path.cwd(), from_rev)
            typer.echo(format_sign_plan(plan), nl=False)
            if not plan.commits:
                return
            commands = signing_commands(plan)
            if dry_run:
                typer.echo(format_signing_commands(commands), nl=False)
                return
            if explain:
                return
            try:
                execute_sign_plan(plan, Path.cwd(), runner=sign_runner)
                head = head_revision(Path.cwd(), runner=sign_runner)
            except SigningFailed as error:
                typer.echo(f"error: signing failed: {error}", err=True)
                if error.paused:
                    typer.echo(
                        "fix the signing configuration, then:\n"
                        "  git rebase --continue\n"
                        "or return to the original state:\n"
                        "  git rebase --abort",
                        err=True,
                    )
                else:
                    typer.echo("HEAD is unchanged.", err=True)
                raise typer.Exit(code=1) from error
            typer.echo(f"signed {len(plan.commits)} commit(s); HEAD is now {head[:7]}")
        except subprocess.CalledProcessError as error:
            typer.echo("error: git sign failed", err=True)
            raise typer.Exit(code=1) from error
        except ValueError as error:
            typer.echo(f"error: {error}", err=True)
            raise typer.Exit(code=2) from error

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
            Path | None,
            typer.Option("--from", help="Workshop definition to copy"),
        ] = None,
        sdk: Annotated[
            list[str],
            typer.Option("--sdk", help="SDK name to add; repeat for multiple SDKs"),
        ] = [],
        git_name: Annotated[
            str | None,
            typer.Option("--git-name", help="Git user.name for workshop commits"),
        ] = None,
        git_email: Annotated[
            str | None,
            typer.Option("--git-email", help="Git user.email for workshop commits"),
        ] = None,
        no_remount: Annotated[
            bool,
            typer.Option("--no-remount", help="Do not remount SDK plugs after setup"),
        ] = False,
    ) -> None:
        try:
            specs = canonicalize_sdk_specs(sdk)
            validate_workshop_name(workshop)
            identity = identity_resolver(Path.cwd(), git_name, git_email)
            setup_definition(Path.cwd(), workshop, source, sdk)
            launcher(workshop)
            try:
                identity_seeder(workshop, identity)
            except subprocess.CalledProcessError as error:
                typer.echo(
                    "error: workshop launched but git identity was not applied; "
                    f"run `shopkeep git identity --workshop {workshop}`",
                    err=True,
                )
                raise typer.Exit(code=1) from error
            if not no_remount:
                remount(workshop, managed_sdk_names(specs), executor=executor)
        except subprocess.CalledProcessError as error:
            typer.echo("error: workshop setup failed", err=True)
            raise typer.Exit(code=1) from error
        except ValueError as error:
            typer.echo(f"error: {error}", err=True)
            raise typer.Exit(code=2) from error

    herdr_app = typer.Typer(help="Manage Workshop entries in Herdr.")
    app.add_typer(herdr_app, name="herdr")

    @herdr_app.command(name="connect")
    def herdr_connect_command(
        workshop: Annotated[str, typer.Option("--workshop", help="Workshop name")],
    ) -> None:
        try:
            connector(workshop)
        except subprocess.CalledProcessError as error:
            typer.echo("error: herdr machine add failed", err=True)
            raise typer.Exit(code=1) from error
        except ValueError as error:
            typer.echo(f"error: {error}", err=True)
            raise typer.Exit(code=2) from error

    @herdr_app.command(name="disconnect")
    def herdr_disconnect_command(
        workshop: Annotated[str, typer.Option("--workshop", help="Workshop name")],
    ) -> None:
        try:
            disconnector(workshop)
        except subprocess.CalledProcessError as error:
            typer.echo("error: herdr machine remove failed", err=True)
            raise typer.Exit(code=1) from error
        except ValueError as error:
            typer.echo(f"error: {error}", err=True)
            raise typer.Exit(code=2) from error

    return app


app = create_app()


def main() -> None:
    app()
