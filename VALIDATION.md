# Wallet Server V1 Build 9 Development — validation

Validated 13 November 2026 using isolated invented-wallet profiles. No installed service, household profile, wallet or Agent source was changed.

Twenty-two route tests passed, including eight new unloaded-folder regressions and the current Agent Build 90 proposal validator. The reproduced failure now produces and delivers identity-bound version-3 requests when both nodes have unrelated unloaded folders. Coverage also checks either node alone, failed loaded-wallet scans, stale scans, a missing source wallet, a destination already containing the wallet, local receive denial, immutable earlier proposals, and retained signed reviews. Existing route tests cover busy peers, terminal/recovery results, late outcomes suppressing replacements, current version-3 immutability and paired transport.

Related public-offer and history checks: 25 passed; two optional integrations requiring removed historical Agent snapshots were skipped. The focused tests use current Agent Build 90 instead. The historical full regression suite was not rerun for this narrowly scoped Python-only correction.

The change distinguishes successful loaded-wallet discovery from complete discovery of every wallet directory entry. It only renews an existing invitation; it does not infer wallet absence from an unloaded folder. Freshness, source presence, local permission, signing-account boundaries and prior-operation barriers remain unchanged. No previous approval or preview is copied to a replacement request.

Installer checks: package metadata, exact extracted-source parity, exclusion of runtime profiles, wallets, uploads, logs and PSBTs, and isolated IPv4/IPv6 browser and Agent health startup. See the accompanying review logs. The installer was not installed on the user's system.
