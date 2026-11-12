# Shopkeep

Shopkeep prepares a project-local [Workshop](https://canonical.github.io/workshop/)
definition and remounts SDK data from a stable location on the developer machine.

## Local Workshop setup

Run the command from the root of a newly cloned project. `--workshop` gives the
generated Workshop its name, and `--sdk` may be repeated for each SDK to add:

```bash
shopkeep setup \
  --workshop dev \
  --sdk opencode \
  --sdk skills
```

Without `--from`, Shopkeep writes a minimal definition with the selected name,
`base: ubuntu@26.04`, and an empty SDK list before adding requested SDKs and the
local `project-shopkeep` SDK. To use a custom source definition instead, pass
`--from`:

```bash
shopkeep setup --workshop dev --from .workshop/base.yaml --sdk opencode
```

The command writes `.workshop/dev.yaml`, starts the `dev` Workshop, seeds the
workshop git identity and herdr config, and remounts managed SDK plugs by
default. After setup completes, start OpenCode in the Workshop with:

```bash
workshop exec -- opencode --auto
```

Use `--no-remount` when the Workshop definition should be created and launched
without remounting SDK plugs:

```bash
shopkeep setup --workshop dev --from .workshop/base.yaml --sdk opencode --no-remount
```

`--no-remount` still writes the workshop git identity and seeds the herdr
config; it only skips SDK data remounts.

Shopkeep supports these SDK declarations when they are absent from the source
definition:

| SDK | Default channel | Remounted plugs |
| --- | --- | --- |
| `opencode` | `2/stable` | `opencode-config`, `opencode-data` |
| `skills` | `latest/edge` | `skills` |

`opencode` and `skills` are Shopkeep-managed SDKs: Shopkeep uses their default
channels and remounts their plugs automatically, even when the name is given
without a channel. Pass an explicit channel to override the default; the plugs
are still remounted:

```bash
shopkeep setup --workshop dev --sdk skills/candidate
```

Other SDKs are pass-through SDKs: Shopkeep writes the requested SDK into the
generated definition and does not remount it.

A pass-through SDK with a channel uses a Workshop-style `<name>/<channel>`
specification. Shopkeep preserves the requested name and channel, and only the
first slash separates the name from the channel, so channels may themselves
contain slashes:

```bash
shopkeep setup --workshop dev --sdk custom/latest/edge/candidate
```

An unrecognized bare SDK name is written without a channel and is not
remounted:

```bash
shopkeep setup --workshop dev --sdk custom
```

Existing SDK declarations in a custom source definition are kept unchanged. The
generated definition, `.workshop/shopkeep/`, and `.workshop.lock` are added to
the repository's local `.git/info/exclude`; Shopkeep does not modify the shared
`.gitignore`.

Shopkeep also generates the local, ignored `project-shopkeep` SDK at
`.workshop/shopkeep/sdk.yaml`. It provides the persistent mounts used for the
workshop git config and herdr config; it is not a Store SDK and has no
channel.

## Upgrading an existing project

`shopkeep setup` is first-time-only; re-running it on an existing project
reports `workshop definition already exists`. To upgrade a project's
`project-shopkeep` SDK manifest in place, run:

```bash
shopkeep upgrade
workshop refresh <name>
shopkeep herdr connect --workshop <name>
```

`shopkeep upgrade` rewrites a legacy one-plug manifest to the current two-plug
manifest and leaves `.workshop/<name>.yaml` untouched. An already-current
manifest is a no-op, a missing manifest is created, and any other content is
rejected. The manifest directory and `.workshop.lock` are added to the local
`.git/info/exclude`, matching `setup`, so an upgrade-created manifest stays
local. The `workshop refresh` applies the new mount to a running Workshop.

## Git identity inside the workshop

`shopkeep setup` resolves the effective `user.name` and `user.email` from the
project root on the host, so a repository-local identity wins over the global
one. Pass `--git-name` and `--git-email` to override either value:

```bash
shopkeep setup \
  --workshop dev \
  --sdk opencode \
  --git-name "Your Name" \
  --git-email "you@example.com"
```

If either value is missing, setup fails before writing anything. The identity is
written to `/home/workshop/.config/git/config` through the mount provided by
`project-shopkeep`. Commit and tag signing are explicitly disabled inside the
workshop.

Identity is resolved once at setup. After `workshop remove` and `workshop launch`, or after changing the host identity, re-apply it with:

```bash
shopkeep git identity --workshop dev
```

## Reviewing and signing commits

Commits authored inside the workshop are unsigned by design. Review them on the
host, then sign them with the host's configured signer:

```bash
shopkeep git sign --explain
shopkeep git sign --dry-run
shopkeep git sign
```

`shopkeep git sign` signs the contiguous unsigned tail of the current branch.
It resolves the boundary from `--from <rev>` when given, otherwise from the
branch upstream, otherwise from `origin/HEAD`; pass `--from` explicitly when
neither exists. `--explain` prints the range and commits, and `--dry-run` also
prints the exact git commands without changing anything.

To sign a different range, name its base:

```bash
shopkeep git sign --from origin/main
```

Signed commits stop the walk, so the command never rewrites already-signed
history. It refuses a detached HEAD, tracked or staged changes, an in-progress
rebase, merge commits in the unsigned range, and `B`/`E`/`X`/`Y`/`R` signature
states.

If signing fails, a multi-commit rebase is left paused:

```bash
git rebase --continue   # after fixing the signer
git rebase --abort      # to return to the original state
```

Signing rewrites commit hashes. If the branch was already pushed, force-push it
after the review pass.

## Connecting a Workshop to Herdr

Register a running Workshop as a [Herdr](https://herdr.dev/) machine, so Herdr
can control terminals inside it:

```bash
shopkeep herdr connect --workshop dev
```

This reads the Workshop's `.wp` hostname from `workshop info`, runs
`herdr machine add workshop@<workshop>.<project>.wp --label <workshop>.<project>`,
and then removes older saved machine profiles with the same label. Re-running
it is safe: each successful connect leaves exactly one profile, so
`herdr --machine <label>` keeps working, and a failed add leaves the existing
registration in place. It relies on Workshop's built-in SSH
certificate authority (0.9.5+), so no SSH key import or `authorized_keys`
setup is needed — the target Workshop just needs to be running. Workshops
launched before 0.9.5 must be removed and relaunched to pick up the automatic
SSH configuration first.

The first connect to a Workshop that has no Herdr binary fails when run
non-interactively: Herdr installs its remote binary over SSH and needs
approval in an interactive terminal, so `shopkeep herdr connect` exits with
`herdr machine add failed`. The failed connect still seeds the Herdr config;
only the machine registration is missing. Run the underlying command once in
an interactive terminal and answer `y` at the install prompt:

```bash
herdr machine add workshop@<workshop>.<project>.wp --label <workshop>.<project>
```

Herdr then installs the binary and saves the machine. After that one-time
approval, `shopkeep herdr connect` succeeds non-interactively.

New Herdr panes run login shells in `/project`, so panes and the agents inside
them see the same SDK environment as `workshop shell`. Workshop delivers that
environment through `/etc/profile.d/*.sh` and `~/.profile`, which only login
shells source, while Herdr's Linux default (`terminal.shell_mode = "auto"`)
starts non-login shells; SDK binaries such as `uv` and variables such as
`UV_LINK_MODE` were therefore missing from panes.

`shopkeep setup` and `shopkeep herdr connect` write
`/home/workshop/.config/herdr/config.toml` with:

```toml
[terminal]
shell_mode = "login"
new_cwd = "/project"
```

The file is delivered through the `herdr-config` mount plug on the generated
`project-shopkeep` SDK, so it survives `workshop refresh` with no hooks or
remounts. It is Shopkeep-owned, like the workshop git config: `herdr connect`
overwrites manual edits, and a fresh `setup` writes the config.

Existing panes keep their old environment; split new panes or restart the
Workshop-side Herdr server after the first seed. `workshop refresh` keeps the
config but destroys the Herdr binary, server, panes, and session state — re-run
`shopkeep herdr connect` afterwards; because the rebuilt container has no Herdr
binary, that first connect after a refresh needs the same interactive approval
as above.

To remove the Workshop's saved Herdr machine again, run:

```bash
shopkeep herdr disconnect --workshop dev
```

This resolves the same label from `workshop info`, finds every matching
profile ID with `herdr machine list --json`, and runs
`herdr machine remove <profile-id>` for each. It therefore also clears out
duplicates left by earlier versions of `connect`. Removing the machine
disconnects it from Herdr but leaves its remote sessions and agents running.
