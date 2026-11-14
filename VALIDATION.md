# Wallet Server V1 Build 21 Development — validation

Validated 15 November 2026 with isolated invented public wallets, keys, temporary profiles and Agent state. No live household profile, wallet, service, SSH permission or Agent source was changed. No real funds or Bitcoin network transactions were used.

170 selected Server checks: **168 passed; two optional historical integrations skipped**. Run `PYTHONDONTWRITEBYTECODE=1 python3 tests/run_current_sync.py`; `WALLABY_AGENT_HINT_SOURCE` pointed to current Agent Build 102's `src` directory for the actual Agent advisory integration.

Nine added checks cover exact reserved-name patterns and similar legitimate names; actual-route and exported-name filtering; a retained staging child with conflicting metadata preceding the real Extinct source; a duplicate-descriptor staging wallet preceding a real ordinary wallet; policy/key/history advisory exclusions independent of denial; withdrawal of old bad hint snapshots; signer and policy accounts retained for Wallet Builder while staging is not queried; ordinary unloaded wallets still requiring discovery; and staging exclusion from historical discovery and cached export without RPC.

Earlier advisory, preservation, lifecycle, profile, retirement-ledger, statement, identity/relay and transaction checks remain in the selected suite. Actual Agent integration confirms advisory display, local denial persistence, empty-snapshot withdrawal and no Server-created transfer jobs. Direct Core transfers, stable receiving selection and the green/red browser regression are tested separately by the Agent chat for Build 102. The user's live laptops and complete end-to-end workflow were not tested here.

Installer verification checks version/metadata, exact extracted-source parity, exclusion of runtime wallet/config/upload/log/PSBT records, and isolated IPv4/IPv6 browser plus Agent-health startup. The installer is not installed on the user's server by these checks. No retained directory is removed, no staged history is merged into a live archive, and no saved profile, policy or build is reset. Use Agent Build 102 for its matching direct-discovery fix.
