from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import json
import re
import subprocess


@dataclass(frozen=True)
class GitIdentity:
    name: str
    email: str


def read_git_config_value(project_root: Path, key: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), "config", "--get", key],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as error:
        raise ValueError("git is not installed") from error
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def resolve_git_identity(
    project_root: Path,
    name: str | None = None,
    email: str | None = None,
    reader: Callable[[Path, str], str | None] = read_git_config_value,
) -> GitIdentity:
    resolved_name = (
        name.strip()
        if name is not None
        else (reader(project_root, "user.name") or "").strip()
    )
    resolved_email = (
        email.strip()
        if email is not None
        else (reader(project_root, "user.email") or "").strip()
    )
    missing = []
    if not resolved_name:
        missing.append("user.name (pass --git-name)")
    if not resolved_email:
        missing.append("user.email (pass --git-email)")
    if missing:
        raise ValueError("git identity is not configured: " + ", ".join(missing))
    return GitIdentity(resolved_name, resolved_email)


def render_git_config(identity: GitIdentity) -> str:
    return (
        "[user]\n"
        f"\tname = {git_config_value(identity.name)}\n"
        f"\temail = {git_config_value(identity.email)}\n"
        "[commit]\n"
        "\tgpgsign = false\n"
        "[tag]\n"
        "\tgpgsign = false\n"
    )


def git_config_value(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9@._ +-]*", value) and not value.endswith(
        " "
    ):
        return value
    return json.dumps(value, ensure_ascii=False)


def run_workshop_exec(workshop: str, config: str) -> None:
    subprocess.run(
        [
            "workshop",
            "exec",
            "--non-interactive",
            "--uid",
            "1000",
            "--gid",
            "1000",
            workshop,
            "--",
            "bash",
            "-c",
            "mkdir -p ~/.config/git && cat > ~/.config/git/config",
        ],
        input=config,
        text=True,
        check=True,
    )


def seed_git_identity(
    workshop: str,
    identity: GitIdentity,
    runner: Callable[[str, str], None] = run_workshop_exec,
) -> None:
    runner(workshop, render_git_config(identity))
