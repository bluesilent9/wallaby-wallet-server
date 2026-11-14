# Agent-owned wallet discovery — Server Build 19 / Agent Build 99

Routine wallet re-sync is a direct, authenticated peer operation. The Agents inventory their own loaded and unloaded Core wallets and build their own complete public offers. They compare and transfer full wallet data over their paired channel. The receiving Agent owns its deny list, source choice, local review, approval, active-owner conflict checks, imported-history merge and recovery. Wallet Server cannot define a wallet subset, request a transfer, select a source or retry a failed operation.

Wallet Server still provides rendezvous and bounded opaque relay, displays general wallet/chain observations, and coordinates explicit archive, rename, extinction, restore intent, Builder, policy and transaction requests. These explicit requests retain their Agent authorisation and preservation barriers. Server inventory is display/tracing evidence, not the peer wallet catalogue. The peer catalogue feature is exchanged by the Agents, not advertised as a Server capability. Native Agent-owned transfer outcomes stay on the Agents.

## Upgrade and saved work

Install matching Agent Build 99 or later on both peers. No profile reset or wallet recreation is required. On exchange the Server retires delivery metadata for its earlier pending wallet-transfer queues and clears old public queue/offer snapshots. It does not rewrite frozen proposals, earlier reviews or real terminal outcomes. Late results are accepted only against their original known request and do not restart work. The Agent update separately preserves attempted operations and local recovery. Old-profile validators remain solely to preserve historical evidence; they do not enable old Server scheduling.

Local receiving choices and approvals must be made on the receiving Agent. Restoration intent in Wallet Server remains recorded, but copying a restored wallet is now selected and approved through the paired Agents. Wallet Server observes actual private-key and watch copies as they appear; it does not create copy requests or infer a successful restore from intent alone.

## Obsolete preservation requests

A current, unambiguous connected Agent's successful Core wallet-directory inventory can show that the exact target archive of a pending preserve-only request no longer exists. The scan must postdate that request. Unloaded wallets remain in the directory and are never treated as deleted. Stale, failed, ambiguous or previous-connection inventory cannot withdraw a request.

Only that per-Agent preservation route is marked withdrawn. Its original proposal, manifest, previous outcomes and overall extinction decision are retained. An undelivered request is retired without inventing an Agent receipt. An already delivered request receives the existing cancellation request and awaits the Agent's real acknowledgement. Agent Build 99 can also cancel its obsolete unstarted local task after confirming actual directory absence. Neither side reports preservation or deletion success for this case.

Other Agents' preservation tasks and the verified-preservation-before-deletion barrier remain. A withdrawn route cannot supply that barrier. If an appropriate archive later appears, a fresh explicit preservation request may be created under the unchanged extinction intent. Cancelling routine sync is not cancelling that intent.
