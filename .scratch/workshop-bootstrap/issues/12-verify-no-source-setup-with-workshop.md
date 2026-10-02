# Verify no-source setup against a real Workshop

**Status:** closed

**Type:** AFK

**Requires real Workshop access:** Yes. The verification environment must provide the `workshop` CLI and its usable container backend.

## What to build

Extend the real-Workshop setup verification to run the public `shopkeep setup`
command without `--from`. Prove that the generated default definition launches,
requested SDK plugs remount from Shopkeep-managed local sources, and `opencode`
is available in the resulting Workshop.

## Acceptance criteria

- [x] The integration test invokes `shopkeep setup` without `--from` in a disposable Git project.
- [x] The test verifies launch and requested SDK remounts from Shopkeep-managed local sources.
- [x] The test verifies `opencode` is available after no-source setup.
- [x] The real-Workshop coverage remains clearly separate from unit tests.

## Blocked by

- [Bootstrap a Workshop without a source definition](11-bootstrap-workshop-without-source.md)

## Comments

Implemented as the no-source case of `test_setup_integration.py`. Run with
`uv run pytest --run-integration`. Driving the interactive TUI is out of scope;
the test asserts `opencode` is available.
