# Document managed and pass-through SDKs

**Status:** closed

**Type:** AFK

**Requires real Workshop access:** No. This ticket documents the implemented setup contract.

## What to build

Document the distinction between Shopkeep-managed SDKs and pass-through SDKs
in the local Workshop setup guide. Explain that `--sdk` accepts Workshop-style
`<name>/<channel>` specifications, Shopkeep preserves the requested declaration
for a pass-through SDK, and only managed SDKs receive canonical declarations
and automatic plug remounting. Only the first slash separates the SDK name from
the channel, which may itself contain slashes.

## Acceptance criteria

- [x] The README identifies `opencode` and `skills` as SDKs Shopkeep remounts automatically.
- [x] The README explains that other valid `<name>/<channel>` SDK specifications are added with their requested declaration and are not remounted.
- [x] The README explains that channels may contain slashes after the first name/channel separator.
- [x] The setup examples and `--no-remount` guidance remain accurate.

## Blocked by

- [Add pass-through SDKs without remounting](14-add-pass-through-sdks-without-remounting.md)
