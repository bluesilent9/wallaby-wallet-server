# Wallaby Wallet Server V1 Build 1 — validation

Development successor to Wallaby Dashboard V1 Build 90. Product and package versions restart; profile schemas and existing signed Agent formats are retained.

## Passed checks

- 897 Python regression tests against Agent Build 65 sources, including prior Bitcoin/vault/ownership/history and lifecycle coverage.
- 53 JavaScript interface suites.
- 20 focused new server checks: explicit SSH QR pairing, one-time invitations, full-key/namespace proof checks, reconnect replay rejection, durable revocation, user-scoped public claims, stale comparison rejection, no approval side effects, profile access-grant exclusion, native/browser protocol isolation, loopback-only binding, opt-in signed Agent facts, byte-preserving directory migration, conflict refusal and rollback.
- Real headless browser: renamed branding, user login, Mobile Devices navigation, pending phone code confirmation, pairing QR generation, revocation and no JavaScript errors. Responsive Wallet landing page checked at desktop and 390-pixel phone widths.
- Installer audit: package/service identity, source parity, migration scripts, absence of runtime records and fresh IPv4/IPv6 browser/Agent-health startup.

Mobile transport is a separate 127.0.0.1:56444 SSH-forwarded API. Agent remains 56443; browser remains 38951. Non-loopback mobile binds are rejected. No TLS certificates, public mobile HTTP listener or SSH credential/account changes are included. The phone's SSH authentication is separate from application pairing. Signed mobile comparisons are advisory only and cannot authorise operations or execute Core RPCs.

## Scope of testing

The Android application and actual Agent QR screens are not implemented in this repository. Their end-to-end hardware scanning cannot yet be tested; simulated phone clients exercise the server with real Ed25519 SSHSIG signatures. The opt-in Agent facts protocol is validated with signed fixtures. Existing Agents receive no new verification requests unless they advertise wallet_mobile_verification_v1. See docs/MOBILE_VERIFICATION.md for the later implementation stages.

Migration was exercised against isolated filesystem fixtures and existing profile-format regression tests, not by installing over the user's live server. Source/DEB preparation changes no installed service, production profile, real wallet, Bitcoin Core node, disc or funds. Agent and Mobile source/repositories were left untouched. The earlier Dashboard repository is retained for history.
