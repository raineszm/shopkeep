import json
import subprocess

import pytest
from typer.testing import CliRunner

from shopkeep.app import create_app
from shopkeep.herdr import herdr_connect, herdr_disconnect, parse_hostname


runner = CliRunner()


def test_parse_hostname_extracts_the_hostname_line() -> None:
    output = "name: dev\nhostname: dev.myproj.wp\nstatus: Ready\n"

    assert parse_hostname(output) == "dev.myproj.wp"


def test_parse_hostname_returns_none_when_the_line_is_missing() -> None:
    output = "name: dev\nstatus: Ready\n"

    assert parse_hostname(output) is None


def test_herdr_connect_rejects_when_herdr_is_not_installed() -> None:
    with pytest.raises(ValueError, match="herdr is not installed"):
        herdr_connect("dev", which=lambda name: None)


def test_herdr_disconnect_rejects_when_herdr_is_not_installed() -> None:
    with pytest.raises(ValueError, match="herdr is not installed"):
        herdr_disconnect("dev", which=lambda name: None)


def test_herdr_disconnect_rejects_when_the_workshop_is_not_running() -> None:
    def failing_info(workshop: str) -> str:
        raise subprocess.CalledProcessError(1, ["workshop", "info", workshop])

    with pytest.raises(ValueError, match="dev.*not running"):
        herdr_disconnect(
            "dev", which=lambda name: "/usr/bin/herdr", info_runner=failing_info
        )


def test_herdr_connect_rejects_when_the_workshop_is_not_running() -> None:
    def failing_info(workshop: str) -> str:
        raise subprocess.CalledProcessError(1, ["workshop", "info", workshop])

    with pytest.raises(ValueError, match="dev.*not running"):
        herdr_connect(
            "dev", which=lambda name: "/usr/bin/herdr", info_runner=failing_info
        )


def test_herdr_disconnect_rejects_when_there_is_no_hostname() -> None:
    def info_without_hostname(workshop: str) -> str:
        return "name: dev\nstatus: Ready\n"

    with pytest.raises(ValueError, match="dev.*hostname"):
        herdr_disconnect(
            "dev",
            which=lambda name: "/usr/bin/herdr",
            info_runner=info_without_hostname,
        )


def test_herdr_connect_rejects_when_there_is_no_hostname() -> None:
    def info_without_hostname(workshop: str) -> str:
        return "name: dev\nstatus: Ready\n"

    with pytest.raises(ValueError, match="dev.*hostname"):
        herdr_connect(
            "dev",
            which=lambda name: "/usr/bin/herdr",
            info_runner=info_without_hostname,
        )


def test_herdr_disconnect_removes_the_machine_matching_the_workshop_label() -> None:
    removed: list[str] = []
    listing = json.dumps(
        [
            {"id": "other-id", "label": "other.myproj", "target": "workshop@other"},
            {"id": "dev-id", "label": "dev.myproj", "target": "workshop@dev"},
        ]
    )

    herdr_disconnect(
        "dev",
        which=lambda name: "/usr/bin/herdr",
        info_runner=lambda workshop: "hostname: dev.myproj.wp\n",
        machine_lister=lambda: listing,
        machine_remove=removed.append,
    )

    assert removed == ["dev-id"]


def test_herdr_disconnect_rejects_a_workshop_without_a_saved_machine() -> None:
    removed: list[str] = []

    with pytest.raises(ValueError, match="dev.*not registered with herdr"):
        herdr_disconnect(
            "dev",
            which=lambda name: "/usr/bin/herdr",
            info_runner=lambda workshop: "hostname: dev.myproj.wp\n",
            machine_lister=lambda: "[]",
            machine_remove=removed.append,
        )

    assert removed == []


def test_herdr_disconnect_rejects_when_the_machine_list_fails() -> None:
    def failing_list() -> str:
        raise subprocess.CalledProcessError(1, ["herdr", "machine", "list"])

    with pytest.raises(ValueError, match="could not list herdr machines"):
        herdr_disconnect(
            "dev",
            which=lambda name: "/usr/bin/herdr",
            info_runner=lambda workshop: "hostname: dev.myproj.wp\n",
            machine_lister=failing_list,
        )


def test_herdr_connect_adds_the_machine_using_the_workshop_hostname() -> None:
    calls: list[tuple[str, str]] = []

    def record_machine_add(user_host: str, label: str) -> None:
        calls.append((user_host, label))

    herdr_connect(
        "dev",
        which=lambda name: "/usr/bin/herdr",
        info_runner=lambda workshop: "hostname: dev.myproj.wp\n",
        machine_add=record_machine_add,
    )

    assert calls == [("workshop@dev.myproj.wp", "dev.myproj")]


def test_herdr_connect_command_connects_the_named_workshop() -> None:
    calls: list[str] = []

    def record_connect(workshop: str) -> None:
        calls.append(workshop)

    result = runner.invoke(
        create_app(connector=record_connect), ["herdr", "connect", "--workshop", "dev"]
    )

    assert result.exit_code == 0
    assert calls == ["dev"]


def test_herdr_connect_command_reports_a_value_error(monkeypatch) -> None:
    def failing_connect(workshop: str) -> None:
        raise ValueError("herdr is not installed")

    result = runner.invoke(
        create_app(connector=failing_connect), ["herdr", "connect", "--workshop", "dev"]
    )

    assert result.exit_code == 2
    assert "error: herdr is not installed" in result.output


def test_herdr_connect_command_reports_a_subprocess_failure() -> None:
    def failing_connect(workshop: str) -> None:
        raise subprocess.CalledProcessError(1, ["herdr", "machine", "add"])

    result = runner.invoke(
        create_app(connector=failing_connect), ["herdr", "connect", "--workshop", "dev"]
    )

    assert result.exit_code == 1
    assert "error: herdr machine add failed" in result.output


def test_herdr_disconnect_command_disconnects_the_named_workshop() -> None:
    calls: list[str] = []

    def record_disconnect(workshop: str) -> None:
        calls.append(workshop)

    result = runner.invoke(
        create_app(disconnector=record_disconnect),
        ["herdr", "disconnect", "--workshop", "dev"],
    )

    assert result.exit_code == 0
    assert calls == ["dev"]


def test_herdr_disconnect_command_reports_a_value_error() -> None:
    def failing_disconnect(workshop: str) -> None:
        raise ValueError("workshop 'dev' is not registered with herdr")

    result = runner.invoke(
        create_app(disconnector=failing_disconnect),
        ["herdr", "disconnect", "--workshop", "dev"],
    )

    assert result.exit_code == 2
    assert "error: workshop 'dev' is not registered with herdr" in result.output


def test_herdr_disconnect_command_reports_a_subprocess_failure() -> None:
    def failing_disconnect(workshop: str) -> None:
        raise subprocess.CalledProcessError(1, ["herdr", "machine", "remove"])

    result = runner.invoke(
        create_app(disconnector=failing_disconnect),
        ["herdr", "disconnect", "--workshop", "dev"],
    )

    assert result.exit_code == 1
    assert "error: herdr machine remove failed" in result.output
