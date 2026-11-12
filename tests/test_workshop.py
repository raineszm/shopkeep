import subprocess

from shopkeep.workshop import write_workshop_file


def test_write_workshop_file_writes_the_config_to_the_destination(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("shopkeep.workshop.subprocess.run", fake_run)

    write_workshop_file("dev", "[terminal]\n", "~/.config/herdr/config.toml")

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
