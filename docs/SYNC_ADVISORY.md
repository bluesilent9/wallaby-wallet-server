# Advisory wallet snapshots — Server Build 21 / Agent Build 102

Server observations are display hints, not wallet discovery or transfer authority. Agents remain responsible for direct discovery, full wallet contents, source selection, live paired identity checks, denial lists and local receiving approval. A Server hint never creates a transfer job, requires pairing, consults a denial list or constrains direct Agent work. The snapshot includes connected sources regardless of receiver denial or previously completed transfers.

## Wire format

Agent capability `wallet_sync_offers_v1` enables the existing version-1 full snapshot: `kind=wallet_sync_offers`, `version=1`, monotonic per-recipient `revision`, and `offers`. Each advisory has stable display `id` and `transfer_id`, `direction=receive`, `peer={node_id,hostname}`, the source's public `public_wallet`, `status=discovery_pending`, and **`source_online=true`**. Optional `source_storage` is `node` or `disc` when actually reported. These display IDs are not queued transfer IDs, request hashes, signatures or approvals. The snapshot has no receiving or sending selection, private-key flag, transport route, preview, address subset or execution instruction.

No new capability or executable message is introduced. Agent 101 explicitly treats these as advisory even if a Server claims another status. It expires unrefreshed advisory snapshots after 45 seconds. Direct Agent offers take precedence; local denials remain independent and may outlive a hint.

## Presence and freshness

Only an unambiguous live registered source, with current-connection successful public inventory observed within 90 seconds, supplies hints. No saved/offline node history or restored-profile snapshot can supply a live hint. Failed, old-connection or expired inventory does not qualify. A new refresh attempt cannot make an old observation fresh. Valid loaded observations may be advertised while unrelated wallets are unloaded; this does not prove those other wallets absent.

Each capable receiving Agent gets a current full snapshot on exchange, including an empty list when sources disappear. A source disconnect or inventory withdrawal removes only that source's hints by the next exchange. A reconnected source must first provide fresh public inventory; its current hostname is used. A briefly lost connection has no effect on local Agent denial persistence, direct approvals, active work or real outcomes. The existing exchange/heartbeat cadence and disconnect timeout determine when a silent network failure is detected; no instantaneous push is claimed.

The Server does no additional RPC, public-history fetch, network pricing lookup, pairing or permission check to construct hints. Its existing low-priority inventory process supplies the observations. Each envelope is bounded to 128 complete wallet hints and 2 MiB. Hints can be non-exhaustive at those bounds; no wallet is split. Extinct ownership display children are recombined per source into one public archive hint; they are not offered as separate retired wallets. Internal managed policy monitors, routing aliases and scanning observations are not advertised as independent usable wallets. Agents independently determine their actual complete transfer scope.

## Saved data and other operations

Snapshot/revision metadata is saved with the profile so it validates on restore, but live-source presence is always recomputed. Old frozen requests and actual outcomes remain intact. Build 19's disabled transfer queues and retry endpoints remain disabled. Explicit Builder, signing, broadcast, archive, rename and extinction requests retain their existing separate authorisation/barrier rules.

## Reserved implementation accounts (Build 21)

Filter complete reserved names before advisory grouping and deduplication, checking both the actual Core route and the exported public wallet name. Patterns are `.wallaby-history-[0-9a-f]{24}`, `Wallaby policy [0-9a-f]{20}(?:_watch)?` and `Wallaby key [0-9a-f]{12} [0-9a-f]{8}(?:_watch)?`, matched as whole names. Similar user names remain eligible. Expanded historical children retain the actual Core route, so a staging copy cannot enter the combined Extinct hint under one of its labels. Earlier advisory snapshots are replaced on the next exchange.

History staging is excluded before history-discovery RPC and from unloaded-wallet availability warnings. The actual Core directory observation retains its complete raw name list for presence checks. This is not wallet deletion or recovery cleanup. Policy monitors and private signer accounts remain in the separate Builder/signing inventory; hiding their independent advisory rows does not hide signing keys or change approval requirements. Agent 102 separately excludes these accounts from direct discovery and receiving offers.
