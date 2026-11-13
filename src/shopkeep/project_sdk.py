from collections.abc import Callable, Iterator
from dataclasses import dataclass
import posixpath
import subprocess


WORKSHOP_HOME = "/home/workshop"
WORKSHOP_UID = 1000
WORKSHOP_GID = 1000


def _validate_component(value: str, label: str) -> None:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"config mount {label} must be a single path component")


def _validate_relative_directory(value: str) -> None:
    if not value or "\\" in value or value.startswith("/"):
        raise ValueError(
            "config mount directory must be a relative path without traversal"
        )
    if any(component in {"", ".", ".."} for component in value.split("/")):
        raise ValueError(
            "config mount directory must be a relative path without traversal"
        )


@dataclass(frozen=True)
class ConfigMount:
    plug: str
    directory: str
    filename: str

    def __post_init__(self) -> None:
        _validate_component(self.plug, "plug")
        _validate_relative_directory(self.directory)
        _validate_component(self.filename, "filename")

    @property
    def workshop_target(self) -> str:
        return f"{WORKSHOP_HOME}/{self.directory}"

    @property
    def destination(self) -> str:
        return f"{self.workshop_target}/{self.filename}"


@dataclass(frozen=True)
class ConfigMounts:
    git: ConfigMount
    herdr: ConfigMount

    def __iter__(self) -> Iterator[ConfigMount]:
        yield self.git
        yield self.herdr


GIT_CONFIG_MOUNT = ConfigMount(
    plug="git-config",
    directory=".config/git",
    filename="config",
)
HERDR_CONFIG_MOUNT = ConfigMount(
    plug="herdr-config",
    directory=".config/herdr",
    filename="config.toml",
)
CONFIG_MOUNTS = ConfigMounts(git=GIT_CONFIG_MOUNT, herdr=HERDR_CONFIG_MOUNT)

ConfigWriter = Callable[[str, ConfigMount, str], None]


def write_config(workshop: str, mount: ConfigMount, content: str) -> None:
    directory = posixpath.dirname(mount.destination)
    subprocess.run(
        [
            "workshop",
            "exec",
            "--non-interactive",
            "--uid",
            str(WORKSHOP_UID),
            "--gid",
            str(WORKSHOP_GID),
            workshop,
            "--",
            "bash",
            "-c",
            f"mkdir -p {directory} && cat > {mount.destination}",
        ],
        input=content,
        text=True,
        check=True,
    )
