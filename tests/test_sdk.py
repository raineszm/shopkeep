import pytest

from shopkeep.sdk import (
    canonicalize_sdk_specs,
    managed_sdk_names,
    parse_sdk_spec,
)


def test_parse_sdk_spec_uses_the_default_channel_for_a_bare_managed_sdk() -> None:
    spec = parse_sdk_spec("skills")

    assert spec.definition_channel == "latest/edge"
    assert spec.managed is not None
    assert spec.managed.plugs == ("skills",)


def test_parse_sdk_spec_prefers_an_explicit_channel_for_a_managed_sdk() -> None:
    spec = parse_sdk_spec("skills/candidate")

    assert spec.definition_channel == "candidate"
    assert spec.managed is not None
    assert spec.managed.plugs == ("skills",)


def test_parse_sdk_spec_preserves_a_pass_through_channel() -> None:
    spec = parse_sdk_spec("custom/latest/edge/candidate")

    assert spec.definition_channel == "latest/edge/candidate"
    assert spec.managed is None


def test_parse_sdk_spec_allows_a_channel_less_pass_through_sdk() -> None:
    spec = parse_sdk_spec("custom")

    assert spec.definition_channel is None
    assert spec.managed is None


def test_canonicalize_sdk_specs_deduplicates_repeated_specs() -> None:
    specs = canonicalize_sdk_specs(["skills", "skills"])

    assert [(spec.name, spec.definition_channel) for spec in specs] == [
        ("skills", "latest/edge")
    ]


def test_canonicalize_sdk_specs_upgrades_a_bare_spec_in_first_occurrence_order() -> (
    None
):
    specs = canonicalize_sdk_specs(["skills", "opencode", "skills/candidate"])

    assert [(spec.name, spec.definition_channel) for spec in specs] == [
        ("skills", "candidate"),
        ("opencode", "2/stable"),
    ]


def test_canonicalize_sdk_specs_rejects_conflicting_explicit_channels() -> None:
    with pytest.raises(
        ValueError,
        match="SDK 'skills' has conflicting channels: candidate, edge",
    ):
        canonicalize_sdk_specs(["skills/candidate", "skills/edge"])


def test_managed_sdk_names_keeps_only_managed_specs() -> None:
    specs = canonicalize_sdk_specs(["custom", "skills", "opencode"])

    assert managed_sdk_names(specs) == ["skills", "opencode"]
