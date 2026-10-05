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
