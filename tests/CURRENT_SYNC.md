# Build 22 current sync regression suite

Run `PYTHONDONTWRITEBYTECODE=1 python3 tests/run_current_sync.py` from the source root. Set `WALLABY_AGENT_HINT_SOURCE` to the current Agent 103 `src` directory to exercise actual Agent handling of the Server snapshot in a separate temporary process.

The selected suite covers live-source advisory snapshots, local-only denial, disconnect/reconnect, saved hint validation, and Agent-owned sync boundaries, per-Agent preservation withdrawal, explicit lifecycle and preserved records, profile archives, statements, identities/opaque relay and transaction amount/history controls. Older numbered test files retain historical Server-owned scheduling expectations and are not the current sync specification. Their retired architecture is replaced by `test_wallet_server19.py` and `test_wallet_server20.py` and `test_wallet_server21.py`.

Build 22 adds `test_wallet_server22.py` for late completed preservation, archive read-back, rejection of incomplete or mismatched evidence, idempotency and saved-profile round trips. `build22_preservation.js` checks pending-list rendering.
