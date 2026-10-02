from pathlib import Path
import re
import subprocess


SDK_DECLARATIONS = {
    "opencode": {"channel": "latest/stable"},
    "skills": {"channel": "latest/edge"},
}
DEFAULT_DEFINITION = "base: ubuntu@26.04\nsdks: []\n"


def run_workshop_launch(workshop: str) -> None:
    subprocess.run(["workshop", "launch", workshop], check=True)


def setup_definition(
    project_root: Path, workshop: str, source: Path | None, sdk_names: list[str]
) -> Path:
    validate_workshop_name(workshop)
    sdk_names = unique_sdk_names(sdk_names)
    if source is None:
        definition = DEFAULT_DEFINITION
    else:
        try:
            definition = source.read_text(encoding="utf-8")
        except OSError as error:
            raise ValueError(f"cannot read source definition: {source}") from error

    unknown_sdks = [sdk for sdk in sdk_names if sdk not in SDK_DECLARATIONS]
    if unknown_sdks:
        raise ValueError(f"unknown SDK: {unknown_sdks[0]}")

    target = project_root / ".workshop" / f"{workshop}.yaml"
    if target.exists():
        raise ValueError(
            f"workshop definition already exists: {target.relative_to(project_root)}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        add_missing_sdks(set_workshop_name(definition, workshop), sdk_names),
        encoding="utf-8",
    )
    add_local_excludes(project_root, [f".workshop/{workshop}.yaml", ".workshop.lock"])
    return target


def unique_sdk_names(sdk_names: list[str]) -> list[str]:
    return list(dict.fromkeys(sdk_names))


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
    if sdk_names:
        definition = re.sub(
            r"^sdks:[ \t]*\[\][ \t]*$", "sdks:", definition, flags=re.MULTILINE
        )
    sdks_match = re.search(r"^sdks:\s*$", definition, flags=re.MULTILINE)
    content_start, insertion = sdk_section_bounds(definition, sdks_match)
    existing = {
        line.split(":", 1)[1].strip()
        for line in definition[content_start:insertion].splitlines()
        if line.startswith("  - name:")
    }
    missing = [sdk for sdk in sdk_names if sdk not in existing]
    if not missing:
        return definition

    if not sdks_match:
        definition = f"{definition.rstrip()}\nsdks:\n"
    declarations = "".join(
        f"  - name: {sdk}\n    channel: {SDK_DECLARATIONS[sdk]['channel']}\n"
        for sdk in missing
    )
    if not sdks_match:
        return definition + declarations

    return definition[:insertion] + declarations + definition[insertion:]


def sdk_section_bounds(
    definition: str, sdks_match: re.Match[str] | None
) -> tuple[int, int]:
    if not sdks_match:
        return len(definition), len(definition)
    content_start = sdks_match.end()
    if definition[content_start : content_start + 1] == "\n":
        content_start += 1
    next_section = re.search(r"^[^ \t#].*$", definition[content_start:], re.MULTILINE)
    insertion = (
        content_start + next_section.start() if next_section else len(definition)
    )
    return content_start, insertion


def add_local_excludes(project_root: Path, entries: list[str]) -> None:
    exclude = git_exclude_path(project_root)
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    missing = [entry for entry in entries if entry not in existing.splitlines()]
    if not missing:
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    separator = "" if not existing or existing.endswith("\n") else "\n"
    exclude.write_text(
        existing + separator + "\n".join(missing) + "\n", encoding="utf-8"
    )


def git_exclude_path(project_root: Path) -> Path:
    git_path = project_root / ".git"
    if git_path.is_dir():
        return git_path / "info" / "exclude"
    git_dir = git_path.read_text(encoding="utf-8").removeprefix("gitdir: ").strip()
    return (git_path.parent / git_dir).resolve() / "info" / "exclude"
