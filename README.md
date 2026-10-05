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
`base: ubuntu@26.04`, and an empty SDK list before adding requested SDKs. To
use a custom source definition instead, pass `--from`:

```bash
shopkeep setup --workshop dev --from .workshop/base.yaml --sdk opencode
```

The command writes `.workshop/dev.yaml`, starts the `dev` Workshop, and remounts
managed SDK plugs by default. After setup completes, start OpenCode in the
Workshop with:

```bash
workshop exec -- opencode --auto
```

Use `--no-remount` when the Workshop definition should be created and launched
without remounting SDK plugs:

```bash
shopkeep setup --workshop dev --from .workshop/base.yaml --sdk opencode --no-remount
```

Shopkeep supports these SDK declarations when they are absent from the source
definition:

| SDK | Channel | Remounted plugs |
| --- | --- | --- |
| `opencode` | `latest/stable` | `opencode-config`, `opencode-data` |
| `skills` | `latest/edge` | `skills` |

`opencode` and `skills` are Shopkeep-managed SDKs: Shopkeep uses their canonical
channels and remounts their plugs automatically, even when the name is given
without a channel. Other SDKs are pass-through SDKs: Shopkeep writes the
requested SDK into the generated definition and does not remount it.

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
generated definition and `.workshop.lock` are added to the repository's local
`.git/info/exclude`; Shopkeep does not modify the shared `.gitignore`.

## Connecting a Workshop to Herdr

Register a running Workshop as a [Herdr](https://herdr.dev/) machine, so Herdr
can control terminals inside it:

```bash
shopkeep herdr-connect --workshop dev
```

This reads the Workshop's `.wp` hostname from `workshop info` and runs `herdr machine add workshop@<workshop>.<project>.wp --label <workshop>.<project>`. It
relies on Workshop's built-in SSH certificate authority (0.9.5+), so no SSH
key import or `authorized_keys` setup is needed — the target Workshop just
needs to be running. Workshops launched before 0.9.5 must be removed and
relaunched to pick up the automatic SSH configuration first.
