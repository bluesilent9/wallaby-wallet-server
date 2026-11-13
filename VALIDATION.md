# Wallet Server V1 Build 11 Development — validation

Validated 13 November 2026 with isolated invented-wallet profiles. No installed service, real wallet, household profile or Agent source was modified.

The supplied read-only diagnosis identified a saved extinction request with a verified preservation record, a matching original wallet ID/policy and six matching archived addresses, but no `dashboard_wallet` or `dashboard_extinct` metadata. The migration now reconstructs only those missing fields from recorded evidence. Original signed proposals and receipt payloads remain byte-for-byte unchanged. It does not infer relationships from wallet names.

18 focused tests passed. They reproduce the identified missing-field state, complete background tracing while the original holder is offline, retain one retired account when the old copy reconnects, validate actual persisted AgentHub state, and repair the catalog before an explicit scan without waiting for background polling. Migration refuses unverified preservation and unrelated policy/name matches.

Statement tests cover personal/SMSF account separation, family-wide notification removal without a completed Ownership run, rejected single/malformed uploads, historical-only additions, duplicate avoidance, stale-browser input merging, persistence across sessions, profile archive round-trip/integrity checks, independent ageing and explicit clearing. Successful PDF acceptance does not change the saved Ownership completion metadata.

Related route, statement-upload HTTP, history, discovery, rename, extinction and restoration suites: 158 passed; two optional integrations requiring removed historical Agent snapshots were skipped (160 checks run). Current Agent Build 90 parser and actual approval-store handling are exercised. The historical full regression suite was not rerun.

Installer checks passed for metadata, exact extracted-source parity, exclusion of profiles/wallets/uploads/logs/PSBTs, and isolated IPv4/IPv6 browser and Agent health startup. The installer was built but not installed on the user's system. Previously unsaved uploads from failed runs on older builds must be supplied again; this release durably retains newly accepted PDFs.
