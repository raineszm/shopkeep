from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ManagedSDK:
    name: str
    default_channel: str
    plugs: tuple[str, ...]


@dataclass(frozen=True)
class SDKSpec:
    name: str
    channel: str | None
    managed: ManagedSDK | None

    @property
    def definition_channel(self) -> str | None:
        if self.channel is not None:
            return self.channel
        return self.managed.default_channel if self.managed else None


MANAGED_SDKS = {
    "opencode": ManagedSDK(
        "opencode", "2/stable", ("opencode-config", "opencode-data")
    ),
    "skills": ManagedSDK("skills", "latest/edge", ("skills",)),
}


def parse_sdk_spec(spec: str) -> SDKSpec:
    name, separator, channel = spec.partition("/")
    if not name or name.isspace():
        raise ValueError("SDK name must not be empty")
    if separator and (not channel or channel.isspace()):
        raise ValueError("SDK channel must not be empty")
    return SDKSpec(name, channel if separator else None, MANAGED_SDKS.get(name))


def canonicalize_sdk_specs(specs: Iterable[str]) -> list[SDKSpec]:
    declarations: dict[str, SDKSpec] = {}
    for raw in specs:
        spec = parse_sdk_spec(raw)
        existing = declarations.get(spec.name)
        if existing is None:
            declarations[spec.name] = spec
            continue
        if spec.channel is None:
            continue
        if existing.channel is not None and existing.channel != spec.channel:
            raise ValueError(
                f"SDK '{spec.name}' has conflicting channels: "
                f"{existing.channel}, {spec.channel}"
            )
        declarations[spec.name] = SDKSpec(
            spec.name, spec.channel, spec.managed or existing.managed
        )
    return list(declarations.values())


def managed_sdk_names(specs: Iterable[SDKSpec]) -> list[str]:
    return [spec.name for spec in specs if spec.managed is not None]
