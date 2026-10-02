# Shopkeep

Shopkeep prepares a project-local [Workshop](https://canonical.github.io/workshop/)
definition and remounts SDK data from a stable location on the developer machine.

## Local Workshop setup

Run the command from the root of a newly cloned project. `--from` selects the
source Workshop definition, `--workshop` gives the generated Workshop its name,
and `--sdk` may be repeated for each SDK to add:

```bash
shopkeep setup \
  --workshop dev \
  --from .workshop/base.yaml \
  --sdk opencode \
  --sdk skills
```

The command writes `.workshop/dev.yaml`, starts the `dev` Workshop, and remounts
the requested SDK plugs by default. After setup completes, start OpenCode in the
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

Existing SDK declarations in the source definition are kept unchanged. The
generated definition and `.workshop.lock` are added to the repository's local
`.git/info/exclude`; Shopkeep does not modify the shared `.gitignore`.
