# Wallet Server V1 Build 12 Development — validation

Validated 13 November 2026 with isolated invented-wallet profiles. No live service, real wallet or household profile was modified.

126 related checks run: 124 passed; two optional integrations requiring historical Agent snapshots were skipped. Four new tests reproduce denied-source discovery and two genuinely signed previews under the same invitation after an Agent restart. They verify fresh IDs/challenges, unchanged frozen reviews, no inherited approvals/choices, stable repeated polls, and refusal to renew after operation evidence or denial. Current Agent Build 92 source is exercised through its actual approval Store and queue handling, including retention of an active old attempt.

Related suites cover public offers, Extinct history comparisons, route renewal, late outcomes, retirement reconciliation, statement persistence and profile archives. The full historical suite and household live sync were not rerun.

Installer validation checks metadata, exact extracted-source parity, absence of runtime wallet/config/upload/log/PSBT files, and isolated IPv4/IPv6 browser and Agent health startup. The package is not installed on the live system. Agent Build 92 separately fixes its approval list grouping and protected Wallets interface.
