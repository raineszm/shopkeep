import typer
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Protocol

from .remount import RemountOperation, remount, run_workshop_remount
from .herdr import (
    HerdrConfigSeedFailed,
    herdr_connect,
    herdr_disconnect,
    seed_herdr_config,
)
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
    upgrade_project_shopkeep_sdk,
    validate_workshop_name,
)


class HerdrConnector(Protocol):
    def __call__(
        self, workshop: str, *, config_seeder: Callable[[str], None]
    ) -> None: ...


def seed_or_exit(seed: Callable[[], None], message: str) -> None:
    try:
        seed()
    except subprocess.CalledProcessError as error:
        typer.echo(message, err=True)
        raise typer.Exit(code=1) from error


def create_app(
    executor: Callable[[RemountOperation, Path], None] = run_workshop_remount,
    launcher: Callable[[str], None] = run_workshop_launch,
    connector: HerdrConnector = herdr_connect,
    disconnector: Callable[[str], None] = herdr_disconnect,
    identity_resolver: Callable[
        [Path, str | None, str | None], GitIdentity
    ] = resolve_git_identity,
    identity_seeder: Callable[[str, GitIdentity], None] = seed_git_identity,
    config_seeder: Callable[[str], None] = seed_herdr_config,
    sign_planner: Callable[[Path, str | None], SignPlan] = plan_sign,
    sign_runner: GitRunner = run_git,
) -> typer.Typer:
    app = typer.Typer(no_args_is_help=True)

    @app.callback()
    def root() -> None:
        """Helpers to streamline the development workflow with Workshop."""

    git_app = typer.Typer(
        help="Manage git identity and signed review passes.",
        no_args_is_help=True,
    )
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
        """Write the resolved git identity into a running workshop.

        Resolves user.name and user.email from the project root unless
        --git-name or --git-email overrides them, then applies the identity
        through the workshop's project-shopkeep mount.
        """
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
        """Sign the contiguous unsigned tail of the current branch.

        The boundary comes from --from, then the branch upstream, then
        origin/HEAD. --explain prints the plan without signing; --dry-run also
        prints the git commands.
        """
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
        """Remount SDK data from the host into a running workshop.

        Pass --sdk once per SDK to remount; each SDK's declared plugs are
        pointed at their directories under the profile root.
        """
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
        """Create a project-local workshop definition, launch it, and remount SDKs.

        Without --from, writes a minimal definition at .workshop/<name>.yaml.
        Adds the requested SDKs plus the local project-shopkeep SDK, applies
        the git identity, seeds the herdr config, and remounts managed SDK
        plugs unless --no-remount is given.
        """
        try:
            specs = canonicalize_sdk_specs(sdk)
            validate_workshop_name(workshop)
            identity = identity_resolver(Path.cwd(), git_name, git_email)
            setup_definition(Path.cwd(), workshop, source, sdk)
            launcher(workshop)
            seed_or_exit(
                lambda: identity_seeder(workshop, identity),
                "error: workshop launched but git identity was not applied; "
                f"run `shopkeep git identity --workshop {workshop}`",
            )
            seed_or_exit(
                lambda: config_seeder(workshop),
                "error: workshop launched but herdr config was not applied; "
                f"run `shopkeep herdr connect --workshop {workshop}`",
            )
            if not no_remount:
                remount(workshop, managed_sdk_names(specs), executor=executor)
        except subprocess.CalledProcessError as error:
            typer.echo("error: workshop setup failed", err=True)
            raise typer.Exit(code=1) from error
        except ValueError as error:
            typer.echo(f"error: {error}", err=True)
            raise typer.Exit(code=2) from error

    @app.command(name="upgrade")
    def upgrade_command() -> None:
        """Upgrade the project-local project-shopkeep SDK manifest in place.

        Rewrites a legacy one-plug manifest to the current two-plug manifest,
        creates the manifest when it is missing, and leaves the workshop
        definition untouched.
        """
        try:
            upgrade_project_shopkeep_sdk(Path.cwd())
        except ValueError as error:
            typer.echo(f"error: {error}", err=True)
            raise typer.Exit(code=2) from error

    herdr_app = typer.Typer(
        help="Manage Workshop entries in Herdr.",
        no_args_is_help=True,
    )
    app.add_typer(herdr_app, name="herdr")

    @herdr_app.command(name="connect")
    def herdr_connect_command(
        workshop: Annotated[str, typer.Option("--workshop", help="Workshop name")],
    ) -> None:
        """Register a running workshop as a Herdr machine.

        Reads the workshop's .wp hostname from `workshop info` and runs
        `herdr machine add` with the workshop's label.
        """
        try:
            connector(workshop, config_seeder=config_seeder)
        except HerdrConfigSeedFailed as error:
            typer.echo(f"error: {error}", err=True)
            raise typer.Exit(code=1) from error
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
        """Remove a workshop's saved Herdr machine.

        Finds the machine by the workshop's label and runs
        `herdr machine remove`; remote sessions and agents keep running.
        """
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
