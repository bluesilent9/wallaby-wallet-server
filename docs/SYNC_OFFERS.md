# Public wallet availability — Server Build 6 / Agent Build 70

Agents advertise `wallet_sync_offers_v1` alongside `wallet_transfer`. The Server sends a separate authoritative snapshot:

```json
{"kind":"wallet_sync_offers","version":1,"revision":0,"offers":[]}
```

Each offer has exactly `id`, `transfer_id`, `direction` (`send` or `receive`), `peer` (`node_id`, `hostname`), `public_wallet`, and `status`. IDs are lowercase 64-character hexadecimal hashes; `id` is SHA256 of the canonical JSON object containing the transfer ID and direction. The public wallet is the same validated public descriptor record used by the existing transfer, containing no private keys. At most 128 offers are sent per Agent. A new revision replaces the whole list, including an empty withdrawal; a stable snapshot retains its revision. Session changes follow the Agent's existing authenticated connection handling.

`status` uses the synchronization blocker codes (`secure_pairing_required`, `peer_offline`, `permissions_pending`, `discovery_pending`, `disabled`, `review_paused`, `history_recovery`, `local_outcome`, `earlier_operation`, `peer_changed`, `preview_changed`, `preview_expired`, `invalid_pair`) or `ready`.

The offer never contains a transfer challenge, Noise binding, credential, signed preview, or executable approval. It can be displayed and denied before pairing. Local Agent denials remain authoritative through the existing signed `wallet_sync_preferences` snapshots; deleting a denial permits the Server to offer the wallet again. Pairing and supported transport, local approval, and the exact signed preview remain mandatory for a real transfer in the existing `wallet_sync_queue`.

Intentional private multisig signer containers, obsolete transfer attempts, completed imports, active renames, deleted nodes, and suppressed/extinct wallet lifecycle operations are not reintroduced as missing-wallet offers. Existing frozen proposals and operation outcomes are never rewritten to construct the public list.

A watch-only wallet that is already a complete public copy is not a missing wallet. This update does not replace it with private keys automatically.
