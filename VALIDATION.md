# Wallet Server V1 Build 10 Development — validation

Validated 13 November 2026 with isolated invented-wallet profiles. No installed service, household profile, real wallet or Agent source was changed.

36 focused checks passed. They cover the preceding route safeguards plus automatic signed-preview renewal without copying previous proofs/choices, late denials/errors/recovery/completion withdrawing replacements, already-watched Extinct addresses, unloaded-folder history comparison, and actual current Agent Build 90 approval-store queue handling. The Agent integration verifies that withdrawing an invitation preserves an active/attempted old operation and still prevents a parallel authorised batch.

Retirement-ledger checks reproduce the cached-original/Extinct double-script conflict, then reconstruct the exact balances with only one ledger. They exercise a real Server retirement-preservation state, retain the original descriptor identity and confirmed owner through background discovery, distinguish cancellation/restoration, preserve private/watch presentation, and reject unverified receipts, wrong labels and incomplete address coverage. A genuinely unrelated script collision still fails, naming both accounts.

Related sync, history, node-chain, discovery, rename, extinction and restoration suites: 100 passed; two optional integrations requiring removed historical Agent snapshots were skipped (102 checks run). The historical full regression suite was not rerun. Current Agent Build 90 is exercised directly instead.

Installer checks passed for metadata, exact extracted-source parity, exclusion of profiles/wallets/uploads/logs/PSBTs and isolated IPv4/IPv6 browser and Agent health startup. The package was built but not installed on the user's system. No live user operation or archive disc was modified by these tests.

The supplied logs do not identify which two wallet IDs collided, or the exact stored field blocking the pending invitation. This release fixes reproduced Server conditions matching those symptoms and adds named collision and renewal diagnostics rather than silently accepting unrelated ownership conflicts. Actual household sync should be re-tested after installing the build.
