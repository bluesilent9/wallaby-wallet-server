# Wallaby Wallet Server V1 Build 7 Development — validation

Validated 10 November 2026 with isolated temporary profiles. No installed service, real household profile, Agent source or Mobile code was changed by this Server task.

* Full Python regression: 975 tests passed. Seventeen focused history-sync checks cover identical addresses with differing spent history, label-only differences, equal fingerprints, unpaired/unknown permissions, denials, incomplete sources, stale/reconnected inventories, stable polling, no automatic retry after terminal outcomes, reverse comparison after a union, existing-address retry, malformed saved metadata, bounded RPC inputs, ambiguous archives, pending retirement and pausing if a peer loses history support.
* The real Agent Build 78 proposal parser accepted the Server-generated existing direct-sync signal. Generated proposals contain no historical transaction records or authoritative label data from the Server. Signed direct-peer preview and transport validation remain unchanged.
* Optional history-summary failure leaves ordinary wallet inventory usable. Summary RPCs are collected outside the durable state lock, in periodic background inventory, and skipped during foreground Agent work. Completed-inventory timestamps and current connection tokens guard against stale comparisons.
* 54 JavaScript suites passed; no application browser controls changed. Existing Build 5 browser login/routing/OPAQUE/mobile-icon tests remain the UI baseline.
* Package audit passed: Build 7 metadata, exact extracted-source parity, no profile/wallet files, logs, uploaded records or PSBTs, existing service migration scripts and isolated IPv4/IPv6 browser and Agent listener startup. The installer was not installed on the user's system.

The Agent chat separately tests actual direct history merging on isolated Bitcoin Core regtest nodes, including missing spent history and receiving-side records. This Server task does not claim a live household-wallet, optical-disc or mainnet transfer test.

The Server compares bounded discovery summaries only. A hash mismatch is not proof of which copy is newer or trustworthy. Agents independently validate and merge records directly over authenticated SSH. Local denial, pairing, signed review and local approval remain required; an active wallet cannot silently become extinct. Existing frozen operations are not rewritten, and unchanged mismatches do not create repeated automatic retries. Matching Agent Build 78 is required for this feature.
