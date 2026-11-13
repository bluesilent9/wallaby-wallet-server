# Wallet Server V1 Build 13 Development — validation

Validated 14 November 2026 using isolated invented-wallet profiles. No live service, real wallet, household profile or Agent source was modified.

137 related checks run: 135 passed; two optional integrations requiring historical Agent snapshots were skipped. Eleven new checks cover genuine Ed25519-signed disc/node previews, byte-exact forwarding, mutation rejection, strict enum validation, unchanged request state and proposals, saved-profile validation, public discovery hints for denied wallets, preference for signed evidence, stale/reconnected/ambiguous inventory rejection, private-path exclusion and preview renewal retaining the original signed evidence.

The actual Agent Build 93 signature verifier, offer Store and sync table verify a forwarded preview and display the disc icon without creating an approval or active transfer. Related suites cover queue permissions, immutable reviews, late operation outcomes, Extinct history, retirement reconciliation, Bitaroo statement persistence and profile archives. Full historical suites and the user's live household were not rerun.

Installer checks cover metadata, exact extracted-source parity, exclusion of runtime wallets/configuration/uploads/logs/PSBTs, and isolated IPv4/IPv6 browser and Agent health startup. The installer was built but not installed on the user's system. Use Agent Build 93 for its new source-origin icon support; no profile reset is needed.
