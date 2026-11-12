import posixpath
import subprocess


def write_workshop_file(workshop: str, config: str, destination: str) -> None:
    directory = posixpath.dirname(destination)
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
            f"mkdir -p {directory} && cat > {destination}",
        ],
        input=config,
        text=True,
        check=True,
    )
