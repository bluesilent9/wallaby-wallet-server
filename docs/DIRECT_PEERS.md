# Direct peer transport v1 — Agent and Mobile implementation contract

Wallet Server V1 Build 3 Development, 9 November 2026. This is the client handoff contract; the Server is implemented, Agent/Mobile direct SSH engines are not part of this package.

## Trust and connection lifecycle

The existing independently scanned, role-bound QR pairing and Noise channel remain the root of trust. Keep long-lived paired identity/role grants and pairing secrets in protected client storage; do not erase those every day. A Server directory entry or IP address never grants trust. This release also permits Mobile–Mobile ciphertext courier delivery, but each native client must independently approve its peer and grant only Mobile permissions. A Mobile can issue a Mobile-role invitation under its own locally paired identity, never an Agent-role grant. An Agent invitation can grant either role, as before. Direct SSH does not replace Agent authorisation of wallet operations.

Prefer a direct SSH connection for bulk data. Use the encrypted relay for initial pairing, endpoint/key negotiation, address changes, rotation and bounded fallback. There is no new public Server listener and no Server-owned SSH key for peer connections. Existing mobile/Agent Server loopback ports stay 56444/56443. Peer SSH is a separate restricted application service; never open the machine's administrative SSH account for this feature.

A peer generates its fresh client key locally and sends **only its public key** over the authenticated Noise channel. The accepting peer generates its host key locally and sends only its public host key plus reachable IP/port and a restricted random application login identifier. Never send a private key, password, root credential or wallet key. Install the public-key authorisation before accepting a connection. Pin the host key from the authenticated offer before the first SSH connection: no TOFU prompt or accept-new for direct peer SSH. Require key-only authentication from the first connection; a temporary password phase is unnecessary.

The SSH endpoint permits only the Wallaby peer subsystem, no shell, commands, PTY, agent forwarding, X11, general TCP forwarding or arbitrary file access. Use an application-owned listener or dedicated restricted account; the endpoint implementer must enforce the same limits regardless of the SSH library. Login identifiers are not OS users to create/delete every day. Protect wallet/archive streams in the existing protected Agent workspace. The Server cannot and does not install or configure these endpoint services.

Keep the Noise-authenticated application framing inside SSH. Bind the SSH epoch and endpoint identity/role pair in an authenticated application confirmation before sending any wallet data. A malicious Server can relay or substitute addresses but cannot supply the matching pinned host key or paired application proof. Validate operation IDs, hashes, role grants, freshness and file/chunk digests at the endpoints as specified in SECURE_RELAY.md.

## Reachability and roles

Agent–Mobile: the Agent is always SSH server and the Mobile SSH client. If that Agent cannot accept an inbound connection, retain encrypted relay fallback or report that a direct path is unavailable. Never quietly reverse this permission boundary.

Agent–Agent or Mobile–Mobile: choose randomly among the orientations that both peers have confirmed reachable. A Mobile SSH listener is optional: Android suspension/mobile carrier NAT can prevent it. If only one orientation works, use that one. If neither works, use bounded encrypted relay fallback; ordinary SSH alone does not punch through arbitrary NAT/CGNAT/firewalls. No automatic firewall changes, UPnP or public ports are authorised by this protocol.

Simultaneous negotiations: each side submits a random 256-bit negotiation ID over the authenticated channel. Both elect the lexicographically smaller ID; only that initiator selects the reachable orientation using a cryptographic random bit if both work. Acknowledge the same choice before opening a connection. Ignore superseded proposals; cap one active plus one pending epoch per paired device pair. Public/private LAN candidates must come from the authenticated peer, not an untrusted Server suggestion; reject unspecified, multicast, broadcast and unrelated service targets. Use a bounded allowlist of peer addresses and the specific peer service port; do not turn negotiation into a network scanner.

## Encrypted negotiation records

These are **inside Noise ciphertext**, not additional plaintext Server fields. Each record repeats the authenticated frame headers and common peer fields in SECURE_RELAY.md. Include `type`, `negotiation_id`, `epoch_id` (each ID 64 lowercase hex), both endpoint IDs/roles, `created_utc`, `expires_utc`, and `body`. Times must be integers in UTC seconds. Reject expired/future-skewed, replayed, role-swapped, changed or contradictory records; local monotonic expiry is authoritative after receipt.

* `peer.direct.offer`: body `{server_endpoint,client_endpoint,candidates:[{ip,port}],host_public_key,login_id,client_public_key,credential_max_age_seconds:86400}`. At most 8 literal IP candidates; port integer 1..65535. Ed25519 OpenSSH keys only. `login_id` is an application identifier, random lowercase letters/digits, 16..48 characters. No hostnames, shell fragments, passwords or private keys. Offer expires within 120 seconds. Client may supply its fresh public key in a prior encrypted `peer.direct.client-key` record; both signed/Noise-bound offers must agree on it.
* `peer.direct.accept`: `{offer_hash}` over canonical complete offer, after key installation and exact host pin agreement.
* `peer.direct.ready`: `{offer_hash,ssh_session_binding}`; exchange inside the new direct connection after fresh Noise handshake and authenticated binding of the offer hash, epoch, roles and SSH host/client public keys. Both sides confirm before cutting over.
* `peer.direct.retire`: `{old_epoch_id,new_epoch_id,reason}`. An application receipt confirms destruction of old credentials on that endpoint; it is not permission to destroy wallet/archive material.

Retain existing signed control namespace and exact relay frame format; no new financial proposal hash/schema changes are necessary. The existing transport binding is a peer identity/Noise binding, not a requirement that all file bytes physically traverse the Server.

## Rotation and failures

Credentials last at most 24 hours from creation, enforced locally by both endpoints, not extended by traffic, reconnect, IP change or Server instruction. Generate a fresh login identifier, client key and host key for each new epoch. New ephemeral credentials must not enter profile exports, backups, diagnostics or archive discs. After authenticated cutover close the old SSH connection, remove authorisation/pins and release old private-key memory. Best-effort zeroisation cannot guarantee physical erasure from managed runtimes, flash or snapshots; use protected volatile storage to avoid persistent copies in the first place.

Begin rollover shortly before expiry when connected. If offline after expiry, negotiate at next contact over Noise/relay; do not reuse expired SSH keys to bootstrap. If rollover fails, do not delete the permanent QR pairing or wallet, and do not continue the expired SSH session: fall back to the encrypted courier or wait. A not-yet-expired old epoch may continue while a replacement is being confirmed. Never retire it merely because the Server says the new connection is ready. Resume files only from a mutually acknowledged authenticated chunk offset; verify the full digest before committing.

Dynamic IP change triggers fresh reachability negotiation promptly, without waiting for the daily expiry. A new IP is a location change, not a new trusted identity. Reconnect using an unexpired bound epoch or negotiate fresh credentials, always verifying the pinned host key and paired application identity.

## Server API and readiness

Existing authenticated relay endpoint accepts `{action:"policy"}`. It returns `peer_transport:"direct-ssh-v1"`, direct preference, fallback availability, 86400-second credential maximum, password-bootstrap false and resource limits. This is advisory: clients hardcode security floors and cannot accept weaker limits from the untrusted Server.

Existing `channel` reports still describe the live authenticated logical peer channel, whether its application records travel over relay or direct SSH. Refresh every ~30 seconds; report closed promptly. Direct SSH still requires fresh peer Noise handshake and identical transcript reports. The Server's multisig readiness gating continues to require all selected Agents, never Mobile role substitutes.

Optional signed path report: POST relay `{action:"path",proof:ENVELOPE}`. SSHSIG namespace is `wallaby-wallet-relay-control-v1`; obtain a new one-use challenge first. Exact message:

```
{protocol:"wallaby-wallet-relay",version:1,kind:"path",endpoint_id,role,challenge,
 peer_id,channel_id,epoch_id,transport:"direct-ssh"|"relay",state:"ready"|"closed"}
```

Must match this endpoint's current ready logical channel. Reports expire after 90 seconds. Server mesh reports `transport:"direct-ssh"` only when both sides attest matching live epoch/channel; otherwise `relay`. Path status is informational and never approval authority. No IP addresses, usernames, passwords, SSH public/private session keys or direct data enter this Server report. Direct credentials are invisible to the Server, so rotation enforcement belongs to the endpoints. Server restart resets directory/queues/reports; peer pairings remain local.

## Resource protection and limits

Ten distinct account users may be logged into the Wallet Server simultaneously across browser and Mobile password sessions. Multiple devices logged into one account count as one user. Overall account sessions are bounded at 64, browser workspaces at the existing 32. Mobile authentication expires within 15 minutes; browser leases use the existing 24-hour idle window. Logout/revocation/reconnection/expiry releases capacity; capacity is memory-only and all sessions need reauthentication after restart. This is not a limit on configured family users, Agents or operating-system SSH accounts.

OPAQUE subprocess concurrency is capped at two. Existing password attempt limits remain. Relay actions: 600/minute/identity and 6000/minute globally; newly queued frames remain capped at 120/minute/identity, now also 2 MiB decoded ciphertext/minute/identity. Idempotent retransmission is not charged twice to the byte allowance, but every API request counts toward request limits. Queue size/lifetime and frame bounds remain as in SECURE_RELAY.md. The 2 MiB fallback budget is for control and small transfers; sustained archive/blockchain transfer belongs on the direct path. Clients back off on rejection, retain bounded local queues and show waiting status rather than retry-flooding.

Application limits cannot prevent a volumetric Internet DDoS, or a logged-in OS account from consuming bandwidth/CPU outside this program. No host firewall, system SSH configuration or OS login limits are changed. Existing direct Bitcoin P2P chain sync is unaffected; the Server was never a general blockchain download proxy. SSH MaxStartups/PerSource limits, firewall/upstream rate controls and bandwidth policing are separate administrator tasks, not implemented by this application setting.

## Required client acceptance tests

Before funds: direct relay-to-SSH cutover with Server recording no secrets; changed candidate/host/client key, replayed offer, mismatched roles or epoch and Server-forged ready rejected; key-only listener exposes no shell/forwarding; two-way simultaneous renewal converges; 24h offline expiry cannot reuse keys; failed renewal preserves QR trust and wallet data; IP changes and unreachable Agent/Mobile suspend safely; Mobile never counts as multisig Agent; full file digest verified across interrupted transfer; deletion of old session keys does not remove wallet keys. Test real Android background/CGNAT and firewalled IPv6 networks. Server-only tests cannot establish those client behaviours.
