# Wallet Server V1 Build 22 Development — validation

Validated 15 November 2026 with isolated invented public wallets, temporary profiles and Agent state. No live household profile, wallet, service, SSH permission or Agent source was changed. No real funds or Bitcoin network transactions were used.

178 selected Server checks: **176 passed; two optional historical integrations skipped**. Run `PYTHONDONTWRITEBYTECODE=1 python3 tests/run_current_sync.py`; `WALLABY_AGENT_HINT_SOURCE` pointed to current Agent Build 103's `src` directory for the actual Agent advisory integration.

Eight new Server checks cover completed late preservation after all deletion work has finished, idempotent verification, pending advisory data not proving completion, missing transactions, conflicting labels, mismatched signed receipts, disconnected archives and export/import of verified outcomes. The orchestration tests use an isolated RPC fixture and signature-verification fixture; they do not exercise real Core wallet transfers. Agent Build 103's existing-archive/Core checks are tested separately by the Agent chat.

The interface regression executes the real pending-list renderer: verified completed preservation disappears, unverified/pending preservation remains, and unrelated deletion work and actions remain visible. The existing combined-process renderer check also passes.

Earlier advisory, preservation, lifecycle, profile, retirement-ledger, statement, identity/relay and transaction checks remain in the selected suite. The user's live laptops and complete end-to-end workflow were not tested here.

Installer verification checks version/metadata, exact extracted-source parity, exclusion of runtime wallet/config/upload/log/PSBT records, and isolated IPv4/IPv6 browser plus Agent-health startup. The installer is not installed on the user's server by these checks. No wallet, saved profile, policy or build is reset. Use Agent Build 103 for its matching existing-archive completion check.
