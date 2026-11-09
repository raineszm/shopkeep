import json
import re
import shutil
import subprocess
from collections.abc import Callable


def parse_hostname(info_output: str) -> str | None:
    match = re.search(r"^hostname:\s*(\S+)\s*$", info_output, flags=re.MULTILINE)
    return match.group(1) if match else None


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


def find_machine_id(list_output: str, label: str) -> str | None:
    for machine in json.loads(list_output):
        if machine.get("label") == label:
            return machine.get("id")
    return None


def herdr_connect(
    workshop: str,
    which: Callable[[str], str | None] = shutil.which,
    info_runner: Callable[[str], str] = run_workshop_info,
    machine_add: Callable[[str, str], None] = run_herdr_machine_add,
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
    label = hostname.removesuffix(".wp")
    machine_add(f"workshop@{hostname}", label)


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
    try:
        listing = machine_lister()
    except subprocess.CalledProcessError as error:
        raise ValueError("could not list herdr machines") from error
    profile_id = find_machine_id(listing, hostname.removesuffix(".wp"))
    if profile_id is None:
        raise ValueError(f"workshop '{workshop}' is not registered with herdr")
    machine_remove(profile_id)
