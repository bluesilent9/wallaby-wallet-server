# Build 19 current sync regression suite

Run `PYTHONDONTWRITEBYTECODE=1 python3 tests/run_current_sync.py` from the source root. The selected suite covers Agent-owned sync boundaries, per-Agent preservation withdrawal, explicit lifecycle and preserved records, profile archives, statements, identities/opaque relay and transaction amount/history controls. Older numbered test files retain historical Server-owned scheduling expectations and are not the current sync specification. Their retired architecture is replaced by `test_wallet_server19.py`.
