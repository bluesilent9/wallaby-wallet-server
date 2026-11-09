# Wallaby Wallet Server V1 Build 6 Development — validation

Validated 9 November 2026 using isolated temporary profiles. No installed service, household profile, Agent source or Mobile code was changed by this Server task.

* Full Python regression: 958 tests passed, including ten new public-offer checks. The new checks cover both unpaired directions, exact transfer linkage after pairing, stable snapshot revisions, local denial/re-enable, completed withdrawal, capability selection, malformed saved offers, superseded signer withdrawal without changing frozen proposals, offline-source naming, and discovery while the first signed permission record is pending.
* Real Agent Build 70 source accepted the generated unpaired offer, showed no executable request/approval, hid it on local denial and re-showed it when re-enabled. This is an isolated public-message/store integration test; no real wallets or Bitcoin were transferred.
* 54 JavaScript suites passed. Browser UI behavior is unchanged by this release; Build 5 browser login, ownership-routing, Mobile icon, OPAQUE login/pair/revoke checks remain the baseline.
* Existing regression coverage for signed permissions, separate multisig signer accounts, frozen transfer proposals, endpoint/peer binding, restores, extinction, wallet creation and policy refresh passed. Existing frozen pre-upgrade operation fixtures remain regression fixtures; the new offer path is tested with Agent Build 70.
* Package checks: extracted-source parity, Build 6 metadata, exclusion of private/runtime records, unchanged service migration, isolated IPv4/IPv6 browser and Agent startup. DEB built but not installed here.

Public offers do not contain challenges, transport keys, credentials, signed previews or approval authority. Real transfers still pass the existing pairing, readiness, signed preview and local approval gates. The optional list is sent only to Agents advertising `wallet_sync_offers_v1`. Local denials remain Agent-owned; no denial list is restored over an Agent's current choices.

The new saved public snapshots are included in profile validation. Existing wallet identities, workspace state, frozen proposals and outcomes are retained. Matching Agent Build 70 is required for the new visible pre-pairing offer list. No live household-node or disc-burn test was performed by the Server task.
