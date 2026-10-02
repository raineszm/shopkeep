# Add pass-through SDKs without remounting

**Status:** closed

**Type:** AFK

**Requires real Workshop access:** No. The command contract and remount selection can be verified through unit and CLI tests.

## What to build

Allow `shopkeep setup --sdk <name>/<channel>` to accept any valid Workshop SDK
specification, including SDKs that Shopkeep does not manage. The first slash
separates the SDK name from its channel; preserve the complete remainder as the
channel, including any additional slashes. Add each pass-through SDK to the
generated definition with its requested name and channel, but do not plan or
execute a remount for it. Continue to generate canonical declarations and
remount plugs for Shopkeep-managed SDKs, and reject invalid SDK specifications
before writing a generated definition.

## Acceptance criteria

- [x] An unrecognized valid `<name>/<channel>` SDK specification passed to `setup --sdk` is appended to the generated definition with that name and channel.
- [x] A channel containing additional slashes is preserved exactly after splitting the SDK name at the first slash.
- [x] A pass-through SDK does not cause a remount command or local mount directory to be created.
- [x] Managed SDKs retain their canonical declarations and automatic remount behavior when mixed with pass-through SDK specifications.
- [x] Invalid SDK specifications fail before the generated definition is written, and focused tests cover source-selected and default-template setup.

## Blocked by

None - can start immediately.

## Comments

- SDK specifications require a non-empty name and channel. Shopkeep preserves
  other Workshop SDK syntax and safely serializes it; Workshop remains the
  authority for its complete SDK grammar. Implemented by the current commit.
