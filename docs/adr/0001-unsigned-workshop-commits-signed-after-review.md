# 0001 — Workshop commits are unsigned and signed after review

**Status:** accepted

## Context

Agents working inside a Shopkeep-managed Workshop need a git identity, but the
container does not inherit the host's home directory. Copying signing keys or a
signing agent into the workshop would let an agent sign commits the human has
not reviewed yet. The review step is the point of the workflow, not an
afterthought.

## Decision

Shopkeep gives the workshop the developer's git name and email and explicitly
disables commit and tag signing inside it. Commits authored inside the
workshop are therefore unsigned.

After the human reviews the commits on the host, `shopkeep git sign` signs the
contiguous unsigned tail using the host's configured signer. The signing pass
preserves commit authorship and leaves the rebase paused if signing fails.

## Consequences

- The workshop never needs a signing key, GPG configuration, or SSH agent
  forwarding.
- Review is a required human step before a signature exists.
- Signing rewrites commit hashes; branches already pushed need a force-push.
- A remove-and-relaunch of the workshop can lose the auto-allocated config
  mount, so `shopkeep git identity --workshop <name>` re-seeds it.
- Only the contiguous unsigned tail is signed. Older unsigned commits behind a
  signed boundary are left alone.
