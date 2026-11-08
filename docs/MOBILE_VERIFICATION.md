# Wallaby Wallet verification protocol v1

This document is the implementation handoff for the separate Wallaby Agent and Android chats. Wallet Server V1 Build 1 implements the server stage only. Existing Agents continue using their established signed protocols; no old signed request is rewritten. The display brand is Wallaby Wallet; the server product is Wallaby Wallet Server.

## Trust and transport

The phone connects to the user's existing OpenSSH server, with normal SSH authentication, and forwards a phone-local loopback socket to **127.0.0.1:56444** on that server. This is distinct from **56443**, the Agent interface, and **38951**, the browser interface. Mobile HTTP is carried only inside SSH. The server rejects non-loopback bind addresses; there is no public HTTP or TLS listener for mobile clients. No certificate infrastructure is needed.

Pairing QR includes the actual local OpenSSH Ed25519 public host key and full SHA256 fingerprint. Verify and remember that full key before sending SSH credentials. A changed host key stops reconnection until explicitly checked again; do not silently accept replacement keys. Do not use the Agent signing identity as an SSH host key: they are distinct identities and may differ. The server reads the public host-key file only. It does not change SSH accounts, passwords, authorised_keys, forwarding configuration or Agent credentials.

After pairing, opening the Android app should reconnect to this SSH endpoint automatically and authenticate its verification-only application session. Keep SSH credentials/private keys on the phone. Mobile verification requires neither Core RPC nor Bitcoin private keys. Any later mobile spending feature needs a separate design and authorisation scope.

The phone independently compares the scanned Agent facts with the server's claims. A server claim is not identity authority. Scan every relevant actual Agent; compare its full public identity and locally sourced SSH host key/IP against the identities/routes claimed at the other endpoint. Merely checking two copies of a server-supplied IP is insufficient. Matching means consistency, not a safe or intended payment. Agents must retain their local Bitcoin checks, addresses, amounts, quorum/vault-time display and final user approvals.

## JSON and signatures

Canonical JSON is UTF-8 with sorted object keys, no whitespace separators, ASCII escapes for non-ASCII characters, and no NaN/Infinity (`json.dumps(...,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)`). Hashes are lowercase SHA256 hex. Full Ed25519 public keys use `ssh-ed25519 <base64 OpenSSH key blob>`. A fingerprint is `SHA256:` plus the unpadded Base64 SHA256 of that decoded blob, not a short Bitcoin key fingerprint.

Envelopes have exactly `message`, `public_key`, `signature`. Sign the canonical message using OpenSSH SSHSIG Ed25519. `signature` is Base64 of the SSH signature-file bytes, including the PEM-style SSH signature armour. Namespaces are domain-separated:

- `wallaby-wallet-mobile-pair-v1`: phone pairing proof.
- `wallaby-wallet-mobile-connect-v1`: phone session proof.
- `wallaby-wallet-mobile-result-v1`: advisory phone comparison.
- `wallaby-wallet-verification-v1`: locally sourced Agent facts and future Agent QR review records. The message kind separates facts/review purposes.

## Browser management API

These endpoints are on the existing SSH-reachable browser listener, with existing Host/Origin and X-Session-Token checks. A selected family user is required; management is scoped to that user.

- GET `/api/mobile`: status, this user's paired devices, pending comparisons and mobile host fingerprint. No pairing secret or session token is returned here.
- POST `/api/mobile/pair`: body `{"ssh":{"host":"example.test","port":22,"user":"example"}}`. Returns the pairing QR SVG and payload. Host/user are explicit user input; no household/server name is hardcoded.
- POST `/api/mobile/approve`: body `{"device_id":"...","comparison_code":"012345"}`. Requires the local user to compare the same six-digit code on the phone.
- POST `/api/mobile/revoke`: body `{"device_id":"..."}`. Immediately closes its application sessions and persists revocation.

The QR payload contains `protocol="wallaby-wallet-mobile"`, integer `version=1`, `kind="pair"`, `server_id`, `transport="ssh-loopback"`, `ssh` (host, port, user, full host_public_key, host_fingerprint, forward_host and forward_port), invitation_id, secret and expires_utc. Invitations expire after 120 seconds and are single-use. Display in the trusted SSH-connected browser only. Never place a pairing secret or token in a URL, logs, telemetry or repository.

## Phone-native API

Use POST with `Content-Type: application/json`, `X-Wallaby-Mobile: 1`, a loopback Host header, no browser Origin/Cookie, and at most 65536 body bytes. Duplicate JSON keys, transfer-encoding ambiguities and browser requests are rejected. Native API does not recognise browser session tokens or Agent endpoints. Concurrent connections are bounded.

1. POST `/mobile/v1/pair` with invitation_id, secret, name, public_key and proof. The exact signed pairing message is `{protocol,version:1,purpose:"pair",server_id,invitation_id,secret,public_key,name,ssh_host_fingerprint}`. The host fingerprint must be the one from the verified SSH pairing record. Returns device_id, six-digit comparison_code and state `awaiting-server-confirmation`. Device ID is SHA256 of canonical JSON of the public-key string.
2. The server user approves after comparing the code. An unapproved phone has no application access. The phone may retry the challenge endpoint while awaiting that explicit action; failure never means approval.
3. POST `/mobile/v1/challenge` with device_id. Returns the exact connect message `{protocol,version:1,purpose:"connect",server_id,device_id,challenge}`. The random challenge expires after 45 seconds and is single-use.
4. POST `/mobile/v1/connect` with `proof` signing that exact message. Returns a memory-only bearer token, expiry (15 minutes) and scope `verification-only`. A new connection supersedes the previous token for that device. Reconnect with a fresh proof after expiry; do not repeatedly pair.
5. POST `/mobile/v1/claims` with `{}` and `Authorization: Bearer <token>`. Poll occasionally while the app is open (for example every 15–20 seconds); no polling is needed after the app closes. Returns current public identity/operation claims, a fresh session comparison challenge, claims_digest and approval_authority=false. No wallet files, passphrases, Bitcoin private keys or raw transaction/PSBT contents are exposed.
6. Optionally POST `/mobile/v1/result` with a signed proof. Exact message keys: protocol, integer version=1, purpose="comparison", server_id, device_id, challenge, claims_digest, matches and mismatches. The latter arrays contain distinct current claim IDs, without overlap. Scans not yet performed are omitted. Returns recorded=true and approval_authority=false. The challenge rotates; an old result cannot replay. Results are advisory, expire after two minutes, and never mutate Agent approvals, builders, RPCs or transaction state.

Paired public keys and revocations persist on this installation. Invitations, tokens, connection challenges and comparison results do not. Profile save/load excludes mobile access grants, and replacing/clearing the shared profile invalidates application sessions; phones must pair again. Removing a family profile also removes its mobile session authority. No Bitcoin key material is involved.

## Claims and freshness

Claims include current Agent identities, pending shared wallet-sync routing metadata, the logged-in mobile user's pending wallet setups, policy/retirement requests and transaction operations. Other users' transaction requests are excluded. Agent claims include full signing identity, server-claimed node/route, and fresh signed Agent facts when supported. Node ID is a routing label, not cryptographic identity. An old Agent without QR support remains explicitly unverified; the phone must not infer a successful scan from missing data.

An operation's request_digest is SHA256 of its exact immutable original proposal. A changed amount, address, policy, nonce, signing payload or endpoint changes its binding. Completed, cancelled, superseded and withdrawn requests are omitted. Do not accept a different operation merely because the wallet name or shortened fingerprint matches.

`claims_digest` binds a semantic projection of the sorted claim list: remove each claim's signed_agent_facts envelope and add `agent_facts` containing only agent_public_key, ssh_host_public_key, ipv6 and hostname from its signed message, or null when no current facts exist. Hash that projected list canonically. The phone must independently reproduce it. This preserves a comparison when only an unchanged fact's signature/time/challenge is refreshed; changed identity, SSH key, route or operation invalidates it. Fresh signatures still require independent validity checks. See `mobile_devices.comparison_digest` for the exact projection.

## Required Agent work (not implemented in this repository)

Opt in with capability **wallet_mobile_verification_v1** only when implemented. Old Agents never receive these new messages. When a paired phone is present, the server may send a low-priority proposal:

`{"kind":"wallet_mobile_verification","version":1,"challenge":"<64 hex>","peer_facts":[{"node_id":"...","envelope":<signed facts>}...]}`

Generate public facts locally, without user key material, and queue outbox kind **wallet_mobile_verification_record** with a signed envelope in namespace `wallaby-wallet-verification-v1`. Its message has exactly:

`protocol="wallaby-wallet-verification"`, integer version=1, kind="agent_facts", the challenge, agent_public_key, agent_fingerprint, ssh_host_public_key, ssh_host_fingerprint, ipv6, hostname, integer generated_at and expires_at (Unix seconds). Expiry is at most 120 seconds after generation. Use the established Agent signing/preview identity and the actual local OpenSSH Ed25519 host public key; do not echo a server-provided key/IP as a locally verified fact. The server verifies the signature against that connected Agent's already observed identity and discards authenticated stale challenges. Facts/challenges are temporary and do not grant authority.

The Agent must display independently generated QR records on Services and relevant review screens. An operation review QR should be a signed message in the same namespace with kind="operation_review", version=1, protocol, the current request_digest, operation kind/identity, its own full identity, relevant local/peer routes and full host keys, plus a short validity interval. The phone compares every required endpoint, including cross-checking the peer key against the peer's own scanned QR. The Agent chat and Mobile chat should agree on the exact operation-review QR schema before shipping those stages; the server's native API already provides the immutable proposal digest and fresh public identity/route facts they need.

Do not trust a server-reported phone success as automatic authorisation. Keep final approval local. Only after the human has checked the independent phone result should an Agent's user-confirmed verification control substitute for manual fingerprint entry; it must use the exact verified peer key and operation. Never remove the normal wallet/address/amount/vault review. This server release does not change any Agent prompt or require an existing Agent update just to continue its current operations.
