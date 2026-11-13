# Context

## Domain terms

**Workshop definition**
The YAML file Shopkeep writes under `.workshop/<name>.yaml`, naming the base
image and the SDKs to install.

**Managed SDK**
A Store SDK whose default channel and plugs Shopkeep knows about
(`opencode`, `skills`). An explicit channel overrides the default, and
Shopkeep remounts the SDK's plugs by default.

**Pass-through SDK**
An SDK name Shopkeep writes into the definition without knowing its plugs or
remounting it.

**Plug**
A named mount point declared by an SDK. `workshop remount` repoints the plug at
a host directory.

**Config mount**
A Shopkeep-owned file delivered through a `project-shopkeep` plug. It names the
plug, the mount directory, and the filename, so the plug's workshop target and
the in-workshop write path are one fact.

**Populated mount source**
A Shopkeep mount source directory that already contains data. `workshop
remount` cannot replace a populated source atomically while the workshop runs.

**Remount stop/start cycle**
Stop the workshop, remount every plug, and start it again. Shopkeep uses it
whenever a remount source is populated and the workshop is running.

**`project-shopkeep`**
The local, ignored in-project SDK Shopkeep generates at
`.workshop/shopkeep/sdk.yaml`. It provides the mount plugs that carry the
workshop git config at `/home/workshop/.config/git` and the herdr config at
`/home/workshop/.config/herdr`.

**Legacy `project-shopkeep` manifest**
The previous one-plug form of the generated SDK manifest, containing only the
`git-config` mount. `shopkeep upgrade` recognizes it by exact content and
rewrites it to the current two-plug form.

**`shopkeep upgrade`**
The project SDK upgrade command. It rewrites a legacy one-plug
`project-shopkeep` manifest in place, creates a missing manifest, and leaves
the workshop definition untouched; any other manifest content is refused.

**Workshop git identity**
The developer name and email that commits authored inside the workshop use.
Resolved from the effective git config at the project root, or from
`--git-name` / `--git-email`, and written into the workshop with signing
disabled.

**Herdr config**
The Shopkeep-owned `config.toml` at
`/home/workshop/.config/herdr/config.toml` that starts new Herdr panes as
login shells in `/project`, so panes see the same SDK environment as
`workshop shell`. Delivered through the `project-shopkeep` mount and seeded by
`shopkeep setup` and `shopkeep herdr connect`, which overwrite manual edits.

**Review pass**
The human step outside the workshop: inspect the unsigned commits before
anything is signed.

**Signing pass**
The host-side rewrite after review. `shopkeep git sign` signs the contiguous
unsigned tail with the host's configured signer.

**Contiguous unsigned tail**
The unbroken run of commits with no signature (`%G? == N`) starting at `HEAD`
and walking back to the branch boundary. A `G`/`U` signature stops the walk;
`B`/`E`/`X`/`Y`/`R` inside the tail is refused rather than rewritten.
