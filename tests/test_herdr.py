from collections.abc import Callable
import json
import subprocess

import pytest
from typer.testing import CliRunner

from shopkeep.app import create_app
from shopkeep.herdr import (
    HerdrConfigSeedFailed,
    herdr_connect,
    herdr_disconnect,
    parse_hostname,
    render_herdr_config,
    run_workshop_exec,
    seed_herdr_config,
)


runner = CliRunner()


class FakeHerdrMachines:
    """In-memory stand-in for `herdr machine list|add|remove`."""

    def __init__(self) -> None:
        self.machines: list[dict[str, str]] = []
        self._next_id = 1

    def add(self, user_host: str, label: str) -> None:
        self.machines.append(
            {"id": f"profile-{self._next_id}", "label": label, "target": user_host}
        )
        self._next_id += 1

    def list(self) -> str:
        return json.dumps(self.machines)

    def remove(self, profile_id: str) -> None:
        self.machines = [
            machine for machine in self.machines if machine["id"] != profile_id
        ]


def connect(herdr: FakeHerdrMachines) -> None:
    herdr_connect(
        "dev",
        which=lambda name: "/usr/bin/herdr",
        info_runner=lambda workshop: "hostname: dev.myproj.wp\n",
        config_seeder=lambda workshop: None,
        machine_lister=herdr.list,
        machine_add=herdr.add,
        machine_remove=herdr.remove,
    )


def test_parse_hostname_extracts_the_hostname_line() -> None:
    output = "name: dev\nhostname: dev.myproj.wp\nstatus: Ready\n"

    assert parse_hostname(output) == "dev.myproj.wp"


def test_render_herdr_config_starts_login_shells_in_the_project() -> None:
    assert render_herdr_config() == (
        '[terminal]\nshell_mode = "login"\nnew_cwd = "/project"\n'
    )


def test_run_workshop_exec_writes_the_config_through_bash(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("shopkeep.workshop.subprocess.run", fake_run)

    run_workshop_exec("dev", "[terminal]\n")

    assert calls == [
        (
            [
                "workshop",
                "exec",
                "--non-interactive",
                "--uid",
                "1000",
                "--gid",
                "1000",
                "dev",
                "--",
                "bash",
                "-c",
                "mkdir -p ~/.config/herdr && cat > ~/.config/herdr/config.toml",
            ],
            {"input": "[terminal]\n", "text": True, "check": True},
        )
    ]


def test_seed_herdr_config_writes_the_rendered_config() -> None:
    calls: list[tuple[str, str]] = []

    def record(workshop: str, config: str) -> None:
        calls.append((workshop, config))

    seed_herdr_config("dev", runner=record)

    assert calls == [
        (
            "dev",
            '[terminal]\nshell_mode = "login"\nnew_cwd = "/project"\n',
        )
    ]


def test_seeding_twice_leaves_the_same_content() -> None:
    config: dict[str, str] = {}

    def write(workshop: str, content: str) -> None:
        config["content"] = content

    seed_herdr_config("dev", runner=write)
    first_write = dict(config)
    seed_herdr_config("dev", runner=write)

    expected = '[terminal]\nshell_mode = "login"\nnew_cwd = "/project"\n'
    assert first_write == {"content": expected}
    assert config == first_write


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


def test_herdr_disconnect_removes_all_profiles_with_the_workshop_label() -> None:
    removed: list[str] = []
    listing = json.dumps(
        [
            {
                "id": "dev-1",
                "label": "dev.myproj",
                "target": "workshop@dev.myproj.wp",
            },
            {
                "id": "other",
                "label": "other.myproj",
                "target": "workshop@other.myproj.wp",
            },
            {
                "id": "dev-2",
                "label": "dev.myproj",
                "target": "workshop@dev.myproj.wp",
            },
        ]
    )

    herdr_disconnect(
        "dev",
        which=lambda name: "/usr/bin/herdr",
        info_runner=lambda workshop: "hostname: dev.myproj.wp\n",
        machine_lister=lambda: listing,
        machine_remove=removed.append,
    )

    assert removed == ["dev-1", "dev-2"]


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


def test_herdr_connect_seeds_the_config_before_adding_the_machine() -> None:
    calls: list[tuple[str, str]] = []

    def record_seed(workshop: str) -> None:
        calls.append(("seed", workshop))

    def record_machine_add(user_host: str, label: str) -> None:
        calls.append(("add", user_host))

    herdr_connect(
        "dev",
        which=lambda name: "/usr/bin/herdr",
        info_runner=lambda workshop: "hostname: dev.myproj.wp\n",
        config_seeder=record_seed,
        machine_lister=lambda: "[]",
        machine_add=record_machine_add,
    )

    assert calls == [("seed", "dev"), ("add", "workshop@dev.myproj.wp")]


def test_herdr_connect_adds_the_machine_using_the_workshop_hostname() -> None:
    calls: list[tuple[str, str]] = []

    def record_machine_add(user_host: str, label: str) -> None:
        calls.append((user_host, label))

    herdr_connect(
        "dev",
        which=lambda name: "/usr/bin/herdr",
        info_runner=lambda workshop: "hostname: dev.myproj.wp\n",
        config_seeder=lambda workshop: None,
        machine_lister=lambda: "[]",
        machine_add=record_machine_add,
    )

    assert calls == [("workshop@dev.myproj.wp", "dev.myproj")]


def test_herdr_connect_twice_leaves_one_profile_for_the_workshop_label() -> None:
    herdr = FakeHerdrMachines()

    connect(herdr)
    connect(herdr)

    assert [(machine["label"], machine["target"]) for machine in herdr.machines] == [
        ("dev.myproj", "workshop@dev.myproj.wp")
    ]


def test_herdr_connect_removes_stale_duplicate_profiles_after_adding() -> None:
    herdr = FakeHerdrMachines()
    herdr.machines = [
        {"id": "stale-1", "label": "dev.myproj", "target": "workshop@dev.myproj.wp"},
        {"id": "stale-2", "label": "dev.myproj", "target": "workshop@dev.myproj.wp"},
        {
            "id": "other",
            "label": "other.myproj",
            "target": "workshop@other.myproj.wp",
        },
    ]

    connect(herdr)

    assert [machine["id"] for machine in herdr.machines] == ["other", "profile-1"]


def test_herdr_connect_keeps_the_existing_profile_when_adding_fails() -> None:
    herdr = FakeHerdrMachines()
    herdr.machines = [
        {"id": "dev-1", "label": "dev.myproj", "target": "workshop@dev.myproj.wp"}
    ]

    def failing_add(user_host: str, label: str) -> None:
        raise subprocess.CalledProcessError(1, ["herdr", "machine", "add"])

    with pytest.raises(subprocess.CalledProcessError):
        herdr_connect(
            "dev",
            which=lambda name: "/usr/bin/herdr",
            info_runner=lambda workshop: "hostname: dev.myproj.wp\n",
            config_seeder=lambda workshop: None,
            machine_lister=herdr.list,
            machine_add=failing_add,
            machine_remove=herdr.remove,
        )

    assert herdr.machines == [
        {"id": "dev-1", "label": "dev.myproj", "target": "workshop@dev.myproj.wp"}
    ]


def test_herdr_connect_reports_when_the_machine_list_fails_without_adding() -> None:
    added: list[tuple[str, str]] = []

    def failing_list() -> str:
        raise subprocess.CalledProcessError(1, ["herdr", "machine", "list"])

    with pytest.raises(ValueError, match="could not list herdr machines"):
        herdr_connect(
            "dev",
            which=lambda name: "/usr/bin/herdr",
            info_runner=lambda workshop: "hostname: dev.myproj.wp\n",
            config_seeder=lambda workshop: None,
            machine_lister=failing_list,
            machine_add=lambda user_host, label: added.append((user_host, label)),
        )

    assert added == []


def test_herdr_connect_reports_a_seeding_failure_without_adding_the_machine() -> None:
    added: list[tuple[str, str]] = []

    def failing_seed(workshop: str) -> None:
        raise subprocess.CalledProcessError(1, ["workshop", "exec", workshop])

    with pytest.raises(
        HerdrConfigSeedFailed,
        match="could not seed herdr config for workshop 'dev'; is it running\\?",
    ):
        herdr_connect(
            "dev",
            which=lambda name: "/usr/bin/herdr",
            info_runner=lambda workshop: "hostname: dev.myproj.wp\n",
            config_seeder=failing_seed,
            machine_add=lambda user_host, label: added.append((user_host, label)),
        )

    assert added == []


def test_herdr_help_lists_commands_with_descriptions() -> None:
    result = runner.invoke(create_app(), ["herdr", "--help"])

    assert result.exit_code == 0
    assert "Register a running workshop as a Herdr machine." in result.stdout
    assert "Remove a workshop's saved Herdr machine." in result.stdout


def test_herdr_without_a_subcommand_prints_help() -> None:
    result = runner.invoke(create_app(), ["herdr"])

    assert "Manage Workshop entries in Herdr." in result.stdout
    assert "connect" in result.stdout
    assert "disconnect" in result.stdout


def test_herdr_connect_command_passes_the_config_seeder_to_the_connector() -> None:
    received: list[Callable[[str], None]] = []

    def record_connect(workshop: str, *, config_seeder: Callable[[str], None]) -> None:
        received.append(config_seeder)

    def injected_seeder(workshop: str) -> None:
        pass

    result = runner.invoke(
        create_app(connector=record_connect, config_seeder=injected_seeder),
        ["herdr", "connect", "--workshop", "dev"],
    )

    assert result.exit_code == 0
    assert received == [injected_seeder]


def test_herdr_connect_command_connects_the_named_workshop() -> None:
    calls: list[str] = []

    def record_connect(workshop: str, *, config_seeder: Callable[[str], None]) -> None:
        calls.append(workshop)

    result = runner.invoke(
        create_app(connector=record_connect), ["herdr", "connect", "--workshop", "dev"]
    )

    assert result.exit_code == 0
    assert calls == ["dev"]


def test_herdr_connect_command_reports_a_value_error(monkeypatch) -> None:
    def failing_connect(workshop: str, *, config_seeder: Callable[[str], None]) -> None:
        raise ValueError("herdr is not installed")

    result = runner.invoke(
        create_app(connector=failing_connect), ["herdr", "connect", "--workshop", "dev"]
    )

    assert result.exit_code == 2
    assert "error: herdr is not installed" in result.output


def test_herdr_connect_command_reports_a_subprocess_failure() -> None:
    def failing_connect(workshop: str, *, config_seeder: Callable[[str], None]) -> None:
        raise subprocess.CalledProcessError(1, ["herdr", "machine", "add"])

    result = runner.invoke(
        create_app(connector=failing_connect), ["herdr", "connect", "--workshop", "dev"]
    )

    assert result.exit_code == 1
    assert "error: herdr machine add failed" in result.output


def test_herdr_connect_command_reports_a_config_seed_failure() -> None:
    def failing_connect(workshop: str, *, config_seeder: Callable[[str], None]) -> None:
        raise HerdrConfigSeedFailed(
            f"could not seed herdr config for workshop '{workshop}'; is it running?"
        )

    result = runner.invoke(
        create_app(connector=failing_connect), ["herdr", "connect", "--workshop", "dev"]
    )

    assert result.exit_code == 1
    assert result.stderr == (
        "error: could not seed herdr config for workshop 'dev'; is it running?\n"
    )


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
