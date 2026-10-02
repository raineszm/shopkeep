from pathlib import Path
import re
import subprocess


SDK_DECLARATIONS = {
    "opencode": {"channel": "latest/stable"},
    "skills": {"channel": "latest/edge"},
}


def run_workshop_launch(workshop: str) -> None:
    subprocess.run(["workshop", "launch", workshop], check=True)


def setup_definition(
    project_root: Path, workshop: str, source: Path, sdk_names: list[str]
) -> Path:
    validate_workshop_name(workshop)
    try:
        definition = source.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"cannot read source definition: {source}") from error

    unknown_sdks = [sdk for sdk in sdk_names if sdk not in SDK_DECLARATIONS]
    if unknown_sdks:
        raise ValueError(f"unknown SDK: {unknown_sdks[0]}")

    target = project_root / ".workshop" / f"{workshop}.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        add_missing_sdks(set_workshop_name(definition, workshop), sdk_names),
        encoding="utf-8",
    )
    add_local_excludes(project_root, [f".workshop/{workshop}.yaml", ".workshop.lock"])
    return target


def validate_workshop_name(workshop: str) -> None:
    if not workshop:
        raise ValueError("workshop name must not be empty")
    if Path(workshop).is_absolute() or "/" in workshop or "\\" in workshop:
        raise ValueError("workshop name must not contain path separators")
    if workshop in {".", ".."}:
        raise ValueError("workshop name must not be a traversal component")


def set_workshop_name(definition: str, workshop: str) -> str:
    if re.search(r"^name:\s*.*$", definition, flags=re.MULTILINE):
        return re.sub(
            r"^name:\s*.*$",
            f"name: {workshop}",
            definition,
            count=1,
            flags=re.MULTILINE,
        )
    return f"name: {workshop}\n{definition}"


def add_missing_sdks(definition: str, sdk_names: list[str]) -> str:
    existing = {
        line.split(":", 1)[1].strip()
        for line in definition.splitlines()
        if line.startswith("  - name:")
    }
    missing = [sdk for sdk in sdk_names if sdk not in existing]
    if not missing:
        return definition

    if "sdks:\n" not in definition:
        definition = f"{definition.rstrip()}\nsdks:\n"
    elif not definition.endswith("\n"):
        definition += "\n"
    declarations = "".join(
        f"  - name: {sdk}\n    channel: {SDK_DECLARATIONS[sdk]['channel']}\n"
        for sdk in missing
    )
    return definition + declarations


def add_local_excludes(project_root: Path, entries: list[str]) -> None:
    exclude = project_root / ".git" / "info" / "exclude"
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    missing = [entry for entry in entries if entry not in existing.splitlines()]
    if not missing:
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    separator = "" if not existing or existing.endswith("\n") else "\n"
    exclude.write_text(
        existing + separator + "\n".join(missing) + "\n", encoding="utf-8"
    )
