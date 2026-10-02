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
channels and remounts their plugs automatically. Other SDKs use a Workshop-style
`<name>/<channel>` specification; Shopkeep preserves the requested name and
channel in the generated definition without remounting. Only the first slash
separates the name from the channel, so channels may themselves contain slashes:

```bash
shopkeep setup --workshop dev --sdk custom/latest/edge/candidate
```

Existing SDK declarations in a custom source definition are kept unchanged. The
generated definition and `.workshop.lock` are added to the repository's local
`.git/info/exclude`; Shopkeep does not modify the shared `.gitignore`.
