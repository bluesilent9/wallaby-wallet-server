# Public sync source storage

Agent Build 93 and Wallet Server Build 13 support optional `source_storage` with exactly `node` or `disc` in signed version-3 wallet previews and version-1 public wallet offers. Normal node previews may omit the field.

The source Agent reads its local Core/disc router and signs the field as part of the canonical preview. The Server verifies the complete signature and existing peer, request, challenge, policy and restoration bindings, stores the frozen envelope, and forwards it without adding or rewriting signed members. Unknown values and the field on older preview formats are rejected. New invitations require a fresh signed preview; the old signed envelope remains on its old request.

Before a signed preview exists, offers may use the source Agent's current inventory `getwalletinfo.wallaby_storage`, matched by full public policy. That hint is omitted for stale/reconnected inventory, missing origin or disagreement among matching copies. Once a signed preview exists it takes precedence, including absence of the field. Inventory paths and private material are never forwarded. Denied offers can display origin without creating an executable route or authorising a transfer.

Origin is only a disc-icon hint. Agent-local verification, direct pairing, local receive permissions and sensitive-action approval remain authoritative. Saved public offer snapshots and signed preview envelopes retain this metadata through profile validation.
