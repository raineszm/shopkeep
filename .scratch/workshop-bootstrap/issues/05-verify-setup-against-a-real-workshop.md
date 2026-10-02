# Verify setup against a real Workshop

**Status:** closed

**Type:** AFK

**Requires real Workshop access:** Yes. The implementation and verification environment must provide the `workshop` CLI and its usable container backend.

## What to build

Add an integration test that exercises `shopkeep setup` in a disposable Git project against a real Workshop. It must prove that a copied source definition plus the `opencode` and `skills` SDKs can be launched, remounted, and used to run `opencode` inside the Workshop. Driving the interactive TUI is out of scope; the test asserts `opencode` is available.

## Acceptance criteria

- [x] The test runs the public `shopkeep setup` command in a disposable project with a source definition and both supported SDKs.
- [x] The test verifies the generated Workshop is launched and its requested mounts are remounted from Shopkeep-managed local sources.
- [x] The test verifies `opencode` is available inside the running Workshop.
- [x] The test is clearly separated from unit tests that can run without Workshop installed.

## Blocked by

None - can start immediately.

## Comments

Implemented in `tests/test_setup_integration.py` alongside the source-selected case.
Run with `uv run pytest --run-integration`. The test isolates `XDG_DATA_HOME` beside
the Workshop data so the first-call remount sees an empty source on the same mounted
filesystem; driving the interactive TUI is out of scope.
