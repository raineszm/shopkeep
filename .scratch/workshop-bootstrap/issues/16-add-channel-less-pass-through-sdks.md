# Add channel-less pass-through SDKs

**Status:** closed

**Type:** AFK

**Requires real Workshop access:** No. Definition generation and remount selection can be verified through unit and CLI tests.

## What to build

Allow `shopkeep setup --sdk <name>` to add an SDK that Shopkeep does not manage
without requiring a channel. Write it to the generated Workshop definition as a
name-only declaration and do not remount it. Keep the existing canonical
declarations and automatic remounting for bare Shopkeep-managed SDKs such as
`opencode` and `skills`. Channel-qualified pass-through SDK behavior must remain
unchanged.

## Acceptance criteria

- [x] A bare unrecognized SDK is written as a name-only declaration in both default-template and source-selected setup.
- [x] A bare unrecognized SDK does not cause a remount command or local mount directory to be created.
- [x] Bare managed SDKs retain canonical channels and automatic remounting when mixed with name-only pass-through SDKs.
- [x] Channel-qualified pass-through SDKs still preserve the requested channel, including additional slashes.
- [x] Empty SDK names are rejected before a generated definition is written, with focused tests covering default-template and source-selected setup.

## Blocked by

None - can start immediately.
