# Wallet Server V1 Build 19 Development — validation

Validated 15 November 2026 using isolated invented wallets, keys and profiles. No live household profile, wallet, SSH permissions, service or Agent source was changed.

141 selected Server checks run: 139 passed and two optional Agent integrations were skipped. Run `python3 tests/run_current_sync.py`. Fifteen new checks cover missing-wallet polls without Server offers/queues/previews/transfers; retirement of old queue delivery metadata without rewriting proposals or outcomes; late original results; rejection of Server retries; Agent-managed node status; and restoration observation without Server copying private or watch wallets.

Preservation tests cover current directory absence, an existing unloaded archive, stale/failed/offline/previous-connection inventory, withdrawal before delivery without an invented receipt, actual Agent cancellation before or after the Server refresh, preservation on another Agent remaining unchanged, and refusal to release deletion after a late completion of a withdrawn route. Complete preservations and deletion requests are never withdrawn by the missing-archive path. Original manifests and the extinction decision remain unchanged.

Related regressions cover explicit extinction barriers, archived/restored profile data, retirement ledger reconciliation, accepted personal/SMSF statements, direct rendezvous and opaque relay, identity responses, disc signing aliases, and transaction amount/history controls. Older historical tests expecting Server-owned transfer scheduling are superseded, not the current acceptance suite. Full historical-suite discovery was not run.

Agent Build 99 or later is required on both peers for the new Agent-owned catalogue. The Agent implementation is being developed in the separate Agent chat. Its live household pairing, discovery and receiving procedure was not exercised here; the Server's tests do not constitute end-to-end Agent validation. No real funds or Bitcoin network transactions were used.

Installer checks cover version/metadata, exact extracted-source parity, absence of runtime wallet/config/upload/log/PSBT files, and isolated IPv4/IPv6 browser and Agent health startup. The package is not installed on the user's server here. Existing profiles, policies and saved wallet builds are retained. No reset, wallet deletion or recreation is required.
