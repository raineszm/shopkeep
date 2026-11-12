# 0002 — Herdr config is delivered through the project-shopkeep mount

**Status:** accepted

## Context

Herdr's pane shells are not login shells on Linux, so panes and the agents in
them miss the SDK environment that Workshop delivers through
`/etc/profile.d/*.sh` and `~/.profile`. Herdr reads its config on the machine
where its server runs, so the fix must live inside the Workshop as the
`workshop` user. `/home/workshop` outside mounted paths is ephemeral:
`workshop refresh` rebuilds the container.

## Decision

Shopkeep generates a `herdr-config` mount plug on the `project-shopkeep` SDK,
the same way it delivers the workshop git config, and writes
`~/.config/herdr/config.toml` through a non-interactive `workshop exec`.
`shopkeep setup` seeds it after the git identity, and `shopkeep herdr connect`
re-applies it before `herdr machine add`. No hook, service, or remount is
added.

## Consequences

- The config survives `workshop refresh` through the Workshop-allocated mount.
- `herdr connect` is both the initial delivery and the recovery path after a
  refresh or a remove-and-relaunch.
- The config is Shopkeep-owned: `herdr connect` overwrites manual edits, and a
  fresh `setup` writes the config. Users extend Shopkeep rather than hand-edit
  the file.
- A Workshop launched before the plug materializes keeps the config in its
  ephemeral home until `workshop refresh` applies the manifest.
- Only new panes get login shells; existing panes keep their environment until
  they are replaced.
