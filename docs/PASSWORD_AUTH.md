# Account passwords — Server Build 2

Wallet Server now requires OPAQUE authentication before selecting a user. The same password works from independent browser and paired Mobile clients; it is not bound to a particular device. Mobile device pairing/SSH authentication is separate from user login. Local Agent approval is still required for sensitive Bitcoin actions.

## Existing profiles

No profile reset, wallet deletion or builder cancellation is required. Select the existing user and create a strong unique password. After the OPAQUE registration, a real login exchange proves the newly registered record works before it is committed. Saved user IDs, ownership, vault policies and pending work remain unchanged. An existing account cannot be overwritten using the registration endpoints. Use at least 12 characters in the UI. Keep a recoverable record of the account password; never reuse a wallet encryption password.

There was no prior per-user authentication. Therefore first enrollment cannot cryptographically prove ownership of an old user icon. Perform it on the household's trusted SSH access and have each person claim their own account before granting additional SSH access. Password registration does not magically repair a server or browser already compromised. In particular, server-delivered browser JavaScript can be replaced to steal a typed password; a separately installed trusted Mobile client avoids that specific code-delivery dependence. A compromised server can bypass its own access checks and alter stored data regardless of OPAQUE. Agent trust is independently pinned through QR pairing.

## Implementation and wire contract

Bundled, pinned MIT package `@serenity-kit/opaque` **1.1.0**, implementing RFC 9807 using Rust opaque-ke compiled to WASM. Registry SHA512 integrity and original licence are preserved in `vendor/opaque/PROVENANCE.json`. Browser dynamically imports the bundled ESM client; Python invokes a narrow Node.js adapter for server operations. No runtime npm install or CDN is used. Ubuntu package depends on Node.js >=18. The adapter accepts only server actions, never client passwords. A helper failure fails closed.

Protocol suite identifier: `opaque-serenity-1.1.0-argon2id-m65536-t3-p1`. Client key stretching is fixed Argon2id with iterations=3, memory=65536 KiB, parallelism=1. Client identity is the stable user ID; server identity is the random installation/profile authentication ID. Use the pinned library's `identifiers` on registration and all login stages. The Mobile password screen and cryptography must be bundled with the independently installed app, never fetched as executable login code from Server. Android must use a byte-compatible RFC9807 suite/library, including serialized messages, key stretching and identity binding; do not assume another library's defaults interoperate. Publish shared vectors and test both sides before release.

Browser endpoints require its existing workspace token, same-origin/loopback/SSH restrictions:

* `POST /api/auth/info {user_id}` → registration_required, suite, key_stretching, client_identity, server_identity.
* `/api/auth/start {user_id,mode:"register"|"login",request}` → id, response, server_identity, client_identity, suite. `request` is the library's registrationRequest or startLoginRequest.
* `/api/auth/register {id,record,request}` → id, login response, identities. `record` is the library registrationRecord, and `request` a new startLoginRequest. This is still tentative; no account is overwritten.
* `/api/auth/finish {id,request}` → the usual logged-in family view. `request` is finishLoginRequest. Only successful cryptographic completion selects a user. The response includes a rotated `session_token`; replace the anonymous browser token immediately and discard the old one.

The old `/api/login {user_id}` shortcut is rejected. Account APIs, profile administration, logs and saved reports require an authenticated user. Before any user exists, SSH-trusted first-user creation/profile import are available. The unauthenticated user chooser exposes only ID/name/avatar, not DOB, holdings, ownership or reports. Logout clears the selected user. A server restart requires login again, and saved builder work is restored after login as before.

A paired phone uses its existing device Bearer token on `/mobile/v1/auth/info {}`, `/start {user_id,mode:"login",request}`, `/finish {id,request}`. It can only authenticate the account to which it was paired. Initial registration is performed in the trusted browser workflow. Successful login grants account reads for 15 minutes (bounded by the existing 15-minute device session). Pairing itself is not proof of password knowledge. Revocation removes all phone sessions, relay routes and account access; re-pairing does not bypass passwords.

Pending exchanges are in memory, limited to 128, expire after 120 seconds and are bound to the exact browser/device workspace. Finishing consumes the exchange before verification to prevent replay. Limits are 10 starts/minute per user and per workspace. Setup/records persist atomically in `data/password-auth.json`, mode 0600, under a dedicated lock; background inventory writers cannot stall a normal read-only login. Profile backup includes these OPAQUE setup/registration records but no active sessions, blindings, session keys or passwords. Restoring a pre-password profile prompts enrollment; restoring a password-bearing profile restores its passwords. An older backup can roll account credentials back, so profile restore remains a privileged household action. Treat backups as sensitive: stolen OPAQUE server records/secrets can allow offline guessing of weak passwords. OPAQUE is password-hiding, not protection from weak passwords or a compromised client.

No automatic password-reset bypass is introduced. A deliberate household recovery process can be designed separately.

## Concurrent users (Build 3)

Ten distinct logged-in accounts across browser and Mobile; multiple devices for one account share that user slot. At most 64 authenticated account sessions and two concurrent OPAQUE worker processes. Mobile adds `/mobile/v1/auth/logout {}` to release its account authentication while retaining device pairing/relay access. See [DIRECT_PEERS.md](DIRECT_PEERS.md) for expiry and resource boundaries.
