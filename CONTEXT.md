# Context

## Domain terms

**Workshop definition**
The YAML file Shopkeep writes under `.workshop/<name>.yaml`, naming the base
image and the SDKs to install.

**Managed SDK**
A Store SDK whose canonical channel and plugs Shopkeep knows about
(`opencode`, `skills`). Shopkeep remounts its plugs by default.

**Pass-through SDK**
An SDK name Shopkeep writes into the definition without knowing its plugs or
remounting it.

**Plug**
A named mount point declared by an SDK. `workshop remount` repoints the plug at
a host directory.

**`project-shopkeep`**
The local, ignored in-project SDK Shopkeep generates at
`.workshop/shopkeep/sdk.yaml`. It provides the mount plug that carries the
workshop git config at `/home/workshop/.config/git`.

**Workshop git identity**
The developer name and email that commits authored inside the workshop use.
Resolved from the effective git config at the project root, or from
`--git-name` / `--git-email`, and written into the workshop with signing
disabled.

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
