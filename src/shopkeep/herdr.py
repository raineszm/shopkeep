import json
import re
import shutil
import subprocess
from collections.abc import Callable

from .workshop import write_workshop_file

HERDR_CONFIG_PATH = "~/.config/herdr/config.toml"


class HerdrConfigSeedFailed(RuntimeError):
    """The herdr config could not be written into the workshop."""


def parse_hostname(info_output: str) -> str | None:
    match = re.search(r"^hostname:\s*(\S+)\s*$", info_output, flags=re.MULTILINE)
    return match.group(1) if match else None


def render_herdr_config() -> str:
    return '[terminal]\nshell_mode = "login"\nnew_cwd = "/project"\n'


def run_workshop_exec(workshop: str, config: str) -> None:
    write_workshop_file(workshop, config, HERDR_CONFIG_PATH)


def seed_herdr_config(
    workshop: str,
    runner: Callable[[str, str], None] = run_workshop_exec,
) -> None:
    runner(workshop, render_herdr_config())


def run_workshop_info(workshop: str) -> str:
    return subprocess.run(
        ["workshop", "info", workshop],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def run_herdr_machine_add(user_host: str, label: str) -> None:
    subprocess.run(["herdr", "machine", "add", user_host, "--label", label], check=True)


def run_herdr_machine_list() -> str:
    return subprocess.run(
        ["herdr", "machine", "list", "--json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def run_herdr_machine_remove(profile_id: str) -> None:
    subprocess.run(["herdr", "machine", "remove", profile_id], check=True)


def find_machine_ids(list_output: str, label: str) -> list[str]:
    return [
        machine["id"]
        for machine in json.loads(list_output)
        if machine.get("label") == label
    ]


def machine_ids_for_label(
    label: str,
    machine_lister: Callable[[], str] = run_herdr_machine_list,
) -> list[str]:
    try:
        listing = machine_lister()
    except subprocess.CalledProcessError as error:
        raise ValueError("could not list herdr machines") from error
    return find_machine_ids(listing, label)


def herdr_connect(
    workshop: str,
    which: Callable[[str], str | None] = shutil.which,
    info_runner: Callable[[str], str] = run_workshop_info,
    config_seeder: Callable[[str], None] = seed_herdr_config,
    machine_lister: Callable[[], str] = run_herdr_machine_list,
    machine_add: Callable[[str, str], None] = run_herdr_machine_add,
    machine_remove: Callable[[str], None] = run_herdr_machine_remove,
) -> None:
    if which("herdr") is None:
        raise ValueError("herdr is not installed")
    try:
        output = info_runner(workshop)
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"workshop '{workshop}' is not running; run `workshop launch {workshop}`"
        ) from error
    hostname = parse_hostname(output)
    if hostname is None:
        raise ValueError(
            f"workshop '{workshop}' has no Workshop-managed SSH hostname; "
            "remove and relaunch it to pick up CA-based SSH (0.9.5+)"
        )
    try:
        config_seeder(workshop)
    except subprocess.CalledProcessError as error:
        raise HerdrConfigSeedFailed(
            f"could not seed herdr config for workshop '{workshop}'; is it running?"
        ) from error
    label = hostname.removesuffix(".wp")
    stale_profile_ids = machine_ids_for_label(label, machine_lister)
    machine_add(f"workshop@{hostname}", label)
    for profile_id in stale_profile_ids:
        machine_remove(profile_id)


def herdr_disconnect(
    workshop: str,
    which: Callable[[str], str | None] = shutil.which,
    info_runner: Callable[[str], str] = run_workshop_info,
    machine_lister: Callable[[], str] = run_herdr_machine_list,
    machine_remove: Callable[[str], None] = run_herdr_machine_remove,
) -> None:
    if which("herdr") is None:
        raise ValueError("herdr is not installed")
    try:
        output = info_runner(workshop)
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"workshop '{workshop}' is not running; run `workshop launch {workshop}`"
        ) from error
    hostname = parse_hostname(output)
    if hostname is None:
        raise ValueError(
            f"workshop '{workshop}' has no Workshop-managed SSH hostname; "
            "cannot resolve its herdr machine"
        )
    profile_ids = machine_ids_for_label(hostname.removesuffix(".wp"), machine_lister)
    if not profile_ids:
        raise ValueError(f"workshop '{workshop}' is not registered with herdr")
    for profile_id in profile_ids:
        machine_remove(profile_id)
