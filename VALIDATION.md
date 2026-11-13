# Wallet Server V1 Build 8 Development — validation

Validated 13 November 2026 with isolated invented-wallet profiles. No installed service, household profile or Agent source was changed.

Fourteen focused route tests passed, including the current Agent Build 90 proposal validator. They cover absent IPv6 addresses, replacement by paired-identity version-3 requests, stable repeated polling, preserved original proposals, signed-review/operation evidence, terminal/recovery outcomes, receive denial, missing/stale inventories, busy peers, unpaired transport, late delivery blocking a replacement, same-address history updates and already-current version-3 requests.

Related history and public-offer regressions also passed: 25 checks passed and two optional integrations requiring removed historical Agent snapshots were skipped. The new replacement request is checked against the actual current Agent source instead. The change is limited to sync-route renewal; no browser controls, signing, archive, ownership or balance logic changed. The old full regression suite was not rerun for this narrowly scoped release.

Installer checks passed for package metadata, exact extracted-source parity, exclusion of profile/wallet files, logs, uploads and PSBTs, and isolated IPv4/IPv6 web/Agent startup. The installer was built but not installed on the user's system.

An automatic replacement requires both authenticated peers, fresh inventories, source-wallet presence, current receive permission and no signed review or other operation evidence. The earlier proposal remains immutable and any late outcome remains recordable. A fresh invitation has a new ID/challenge and carries no previous approval or signature. Real execution still requires paired identities and fresh local approval. Extinct history-purpose metadata is retained when present, so matching addresses cannot conceal a pending history update.
