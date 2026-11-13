# Unpaired wallet discovery and first-time Agent identities

Public wallet offers are informational. A newly connected Agent can see source names and public wallet policies, then deny or re-enable incoming wallets before QR pairing with another Agent. Discovery is not authority to send, import or overwrite a wallet. The existing permission, direct-pairing and local approval checks still apply.

## Loaded source availability

A successful loaded-wallet scan can prove a known source wallet exists even when unrelated folders on that source are unloaded. Build 15 allows those sources to create offers, rather than discarding the entire source inventory. For partial inventories it requires `loaded_complete`, a scan no older than 90 seconds and a matching current connection token. Failed, stale and reconnected partial inventories do not create new offers.

The receiver still needs its existing complete inventory to establish that the wallet is missing. An unloaded/unknown destination wallet is not treated as absent. Existing logical-wallet lineage, duplicate-policy, signer-account separation, retirement and active-ceremony filters are unchanged. Public offers do not need a public IPv6 address or an established direct pairing. Unpaired offers show secure_pairing_required and have no executable transfer proposal. An explicit denial continues to show the public source while preventing execution.

## First-time identity bootstrap

The permission handshake already receives and verifies a signed, fresh-challenge Agent identity. Previously it retained that key only in volatile permission state while the relay looked solely in the saved Wallet Builder identity store. An Agent that had never entered Wallet Builder could therefore fail relay registration indefinitely.

Build 15 saves a new verified identity envelope in the shared identity store after checking the connection is still current. Existing observed keys must match. It preserves an existing Wallet Builder envelope/challenge rather than replacing it during routine permission checks. No Builder ceremony is started or approved. Signed relay registration still requires possession of the matching key, a current relay challenge and the authenticated connection scope. QR pairing and end-to-end peer checks remain independent requirements. Old challenges, invalid signatures and key mismatches cannot create or replace the identity record. Saved profile validation verifies the envelope normally.
