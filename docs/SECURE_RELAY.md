# Wallaby Wallet encrypted relay v1 — Server Build 2 handoff

This is the **server implementation and binding contract** for the Agent and Mobile projects. Those clients must implement the encryption, local trust grants and transaction checks described here before the new paths can be used. Server transport is not itself an Agent authorisation. Existing Bitcoin wallet keys and vault scripts do not change.

## Trust and transport

Agents are the trust roots. Mobiles have explicitly limited grants. Wallet Server is an untrusted courier: it sees endpoint identifiers, traffic sizes, timing and public coordination data, and can drop, reorder, duplicate or delay packets. It must never receive pairing PSKs, Noise private keys, session keys, decrypted wallet-transfer files, private wallet keys or passwords. Authentic peers detect substitution/replay; encryption cannot force a compromised courier to deliver data. No publicly exposed HTTP listener or certificate infrastructure is added.

Use the existing SSH connection to reach Server loopback port 56443 (Agent) or the separate 56444 (Mobile). Agents do not need discoverable Internet addresses, inbound connections or a separate peer SSH client for **new relay transfers**. Existing server RPC/coordinator traffic still works as before and is not described as end-to-end encrypted. Public wallet inventories and policies already known to Server remain public to Server.

A signed registration binds a long-lived Ed25519 identity, its granted role (`agent` or `mobile`) and a device-local X25519 Noise static public key. Endpoint ID is SHA256(canonical JSON `{ "identity_key": OPENSSH_PUBLIC_KEY, "role": ROLE }`). Canonical JSON is sorted keys, ASCII escaping, compact separators, no NaN. Public SSH keys have exactly algorithm and base64 fields. Keys must not be silently replaced on reconnect. A role is an explicitly granted permission, not proof of an operating system or physical hardware. A phone must not be promoted to Agent authority merely because it claims to run Agent software.

## Independent QR pairing — Agent/Mobile work required

An Agent's local screen creates a one-use, two-minute invitation for one specified peer role, after local user consent. Its QR is obtained directly from that Agent, never substituted by a Server-rendered claim. Payload:

```
protocol: wallaby-wallet-peer-pair
version: 1
kind: agent_invitation
invitation_id: random 32-byte lowercase hex
issuer_role: agent
allowed_peer_role: agent | mobile
issuer_identity_key: ssh-ed25519 public key
issuer_noise_public_key: standard padded base64 X25519 public key (32 bytes)
issuer_endpoint_id: role-bound endpoint ID
cipher_suite: Noise_IKpsk2_25519_ChaChaPoly_SHA256
pairing_secret: base64 32 cryptographically random bytes
expires_at: integer UTC Unix seconds
relay: {server SSH routing details and pinned SSH host identity}
```

Sign the complete QR payload with the Agent identity using SSHSIG namespace `wallaby-wallet-peer-invitation-v1`. The signature authenticates consistency; the independently observed Agent screen supplies the initial trust. Reject a changed issuer/role/key, expired or reused invitation. SSH routing details are courier routing only, never a substitute for peer authentication. Avoid storing the pairing secret in screenshots, logs or Server data. A new invitation is needed for each peer, including each additional Agent. Other Agents need a camera/imported QR or another independent local transfer of the QR payload; **do not trust a QR payload forwarded only by Server**.

Each endpoint keeps X25519 private keys and pair-specific PSKs in its own protected storage. Use **Noise_IKpsk2_25519_ChaChaPoly_SHA256**, including the QR PSK. Initiator pins the issuer's X25519 key; issuer checks the decrypted initiator identity, requested role and proof-of-possession, and asks its local user to accept the grant. Do not give application data to a peer before pairing and the handshake finish. Peers retain their authenticated role/key relationship; reconnects use a fresh Noise handshake with fresh ephemeral keys and the pair's PSK. Rotate a compromised pairing locally, not through a Server command.

Use this canonical JSON as the Noise prologue (keys sorted):

```
{protocol:"wallaby-wallet-relay",version:1,cipher_suite:"Noise_IKpsk2_25519_ChaChaPoly_SHA256",
 channel_id:random_64_hex,invitation_id:pairing_invitation_id,
 initiator:{endpoint_id,role,identity_key,noise_public_key},
 responder:{endpoint_id,role,identity_key,noise_public_key}}
```

Each handshake payload includes an SSHSIG envelope in namespace `wallaby-wallet-peer-handshake-v1` over the prologue hash and both participant identities/roles. Validate the issuer/subject role grant against local pairing state, both Ed25519 proofs, both Noise static keys and the exact transcript. Never import a pairing grant from the relay directory. This applies equally to Agent–Agent and Mobile–Agent. Mobile–Mobile channels are permitted with independent local Mobile-role grants; see [DIRECT_PEERS.md](DIRECT_PEERS.md). Mobile must not be accepted as a multisig producing Agent or a private-wallet sync recipient under an Agent-only grant.

## Direct connections

Prefer direct SSH for bulk data after encrypted rendezvous. [DIRECT_PEERS.md](DIRECT_PEERS.md) specifies key-only bootstrap, reachable role selection, 24-hour credentials, IP changes, path reports and bounded fallback. Existing peer transport bindings identify the secure logical channel, not the physical route of file bytes.

## Server endpoints

Agent: authenticated `POST /agent/v1/relay`, normal connection Bearer token, `X-Wallaby-Agent: 1`. Return a normal signed wallet-setup identity first. Advertise `wallet_relay_v1` in the regular exchange.

Mobile: authenticated `POST /mobile/v1/relay`, paired device Bearer token, `X-Wallaby-Mobile: 1`. Existing pairing and reconnect stay available; relaying never grants wallet approval/signing authority. Requests require JSON, a loopback Host, no browser Origin, and one Content-Length. Maximum request 70,000 bytes.

Actions:

* `{action:"policy"}` → direct transport policy and bounded relay limits.
* `{action:"path",proof:ENVELOPE}` → optional signed direct/relay path status; see DIRECT_PEERS.md.
* `{action:"challenge"}` → fresh 45-second nonce bound to this exact connection and role.
* `{action:"register",proof:ENVELOPE}` → signed identity registration.
* `{action:"directory"}` → public registrations, including original signed proofs. These are **untrusted discovery**, not pairing authority.
* `{action:"send",frame:FRAME}` → queue immutable ciphertext.
* `{action:"receive"}` → at most 16 pending frames addressed to this endpoint.
* `{action:"ack",ids:[MESSAGE_ID,...]}` → acknowledge only this recipient's frames, **after successful authenticated processing**. Delivery ACK is not workflow approval.
* `{action:"channel",proof:ENVELOPE}` → signed local handshake/liveness report for UI readiness, not a key or approval.
* `{action:"disconnect"}` → invalidate the endpoint's relay queues and channel reports.

Control envelopes use SSHSIG namespace `wallaby-wallet-relay-control-v1` and `{message,public_key,signature}` exactly like other setup signatures. Registration message fields:

```
{protocol:"wallaby-wallet-relay",version:1,kind:"register",endpoint_id,role,
 challenge,noise_public_key,cipher_suite:"Noise_IKpsk2_25519_ChaChaPoly_SHA256"}
```

Channel message fields:

```
{protocol:"wallaby-wallet-relay",version:1,kind:"channel",endpoint_id,role,challenge,
 peer_id,peer_role,peer_noise_public_key,channel_id,handshake_hash,
 state:"ready"|"closed",paired_by_qr:true}
```

Report only after authenticated handshake + locally authorised pairing. `handshake_hash` is the completed Noise handshake hash as 64 lowercase hex. Refresh the report roughly every 30 seconds while the peer channel is alive; immediately report `closed` on loss of peer session/trust. Server reports expire after 90 seconds and a server/transport restart requires re-registration. Both reports must name the same channel and transcript. A mobile report can never count as an Agent's report. Server cannot meaningfully certify its own untrustworthiness away: Agents independently enforce readiness even if Server shows a green dot.

Frame schema (no extra fields):

```
{version:1,id:random_64_hex,from:endpoint_id,to:endpoint_id,channel_id:64_hex,
 sequence:integer_0_to_2^53_minus_1,kind:"handshake"|"transport",ciphertext:standard_padded_base64}
```

Handshake bytes are Noise protocol messages; transport bytes are Noise ciphertext. Max decoded size 49,152 bytes. Fragment large wallet archives inside the encrypted application protocol, with authenticated whole-file digest, total size, chunk index/count, transfer ID and expiry; verify everything before committing a wallet locally. Never stream a partially authenticated file into Core. Receiver reassembles in its protected workspace. Sender retransmits the same frame bytes/ID after an ambiguous response. An ID reused with different bytes is rejected. Queue lifetime is 30 minutes; restart/profile replacement loses relay buffers, **not wallets, workflow records or pairings on the clients**. Re-handshake and resume at an application-acknowledged offset. Bounds: 128 queued frames per recipient, 1,024 live frames plus receipt tombstones overall, 120 newly queued frames/minute/sender, 2 MiB ciphertext/minute/sender, 600 requests/minute/identity and 6,000 requests/minute globally. No ciphertext contents are logged or included in Dashboard profile exports.

Noise encrypts application records containing the full outer header again, plus protocol, authenticated role, operation ID/hash, payload type, expiry and body. After decryption compare every repeated header to the outer header, the pinned peer and local channel. Enforce contiguous per-direction transport counters; drop/reconnect on reordering rather than accepting an unauthenticated frame. Reject repeated counters, old channel IDs and changed operation digests. Outer Server headers are never trusted as application facts. Enforce resource/chunk limits locally too. Rekey with a fresh Noise handshake well before counter exhaustion. Never share a PSK between distinct pairings or reuse a channel ID on a new handshake.

## Wallet Builder, refresh and synchronisation

New multisig Wallet Builder requests require a fresh mutually attested mesh for all selected distinct producing Agents. Every selected Agent, even if holding several signer roles, must be registered. New `wallet_setup` proposals are version 2 and include:

```
peer_transport:{protocol:"wallaby-wallet-relay",version:1,
 cipher_suite:"Noise_IKpsk2_25519_ChaChaPoly_SHA256",required_agent_keys:[sorted_unique_OpenSSH_keys]}
```

Each Agent must independently have a locally trusted Agent-role pairing and live encrypted channel to every other producer. Before generating/contributing a key or approving a policy, exchange the exact immutable proposal/policy hashes with all peers over those channels and require agreement. Keep local address, quorum, amount, vault-height/time and archive reviews. Medium-trust Mobile confirmation is not a producer approval. Existing saved version-1 proposals retain their exact signed hashes; do not regenerate keys or rewrite those in-flight records as version 2.

New multisig refresh handoffs also require the signer mesh before reserving/sending new policy requests. New `wallet_policy_refresh` proposals are version 2 and include the same `peer_transport` requirement object. Advertise `wallet_policy_refresh_relay_v1`; without it the Server withholds the new proposal. Receipts/results keep their version-1 envelope schema and bind the exact new request hash, including the peer requirements. Channel readiness is checked during delivery too. Existing approved/in-progress handoffs resume without replacing their original signed requests. Refresh never creates a new wallet identity or changes signer names. Agent changes must ensure peer-policy agreement for new refresh requests independently of Server UI.

New wallet sync invitations use `transfer_version:3`. `node_ipv6` and `peer.ipv6` are null; connections route by signed stable identities, not addresses. `transport` has exactly:

```
{protocol,version:1,cipher_suite,sender_endpoint,receiver_endpoint,
 sender_identity,receiver_identity,sender_noise_key,receiver_noise_key}
```

Direction does not reverse sender/receiver in this object. The signed public `preview` is version 3, has `sender_ipv6:null`, `receiver_ipv6:null`, and repeats this exact `transport`. Other version-2 preview fields remain unchanged, including transfer/challenge, public wallet, funded outpoints, vaults, labels and restoration purpose. Continue the existing preview SSHSIG namespace and immutable request-hash binding. Agents must compare all three bindings against the authenticated channel and their local permissions. The private file travels only inside Noise transport; no extra direct SSH connection, manually entered peer IP or Server-provided key approval is used. Existing frozen version-2 requests are retained to reconcile their real outcomes; new invitations never silently fall back to that direct-SSH protocol. Interrupted private transfers remain recovery-required until locally reconciled.

## Required client tests

Test malicious courier substitutions of both identities/roles/static keys, PSKs and invitations; replayed/expired/used invitations; wrong PSK; altered prologue and payload; deleted/reordered/replayed frames; server and peer restarts; rotated/revoked pairings; offline peers; forged green readiness; mobile impersonating Agent; multiple disc signers on one Agent; partial archive/chunk failures; repeated multisig refreshes. No acceptance or key regeneration on a retry. Test actual Agent/Mobile builds together before using the new path with funds.
