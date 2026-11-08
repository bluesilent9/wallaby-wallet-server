# Wallaby Wallet Server V1 Build 3 Development — validation

Validated 9 November 2026 in isolated temporary profiles. No installed service, real wallet, household profile, firewall or OS SSH configuration was changed.

* Full regression: 939 Python tests passed. Subsequent focused verification of the final admission/expiry changes: 17 direct-peer/admission/resource tests, plus the 28 existing authentication/relay tests and browser OPAQUE login checks (see review artifacts).
* 53 JavaScript suites passed. Browser enrollment and login from a second independent browser with the same password passed, including mobile pairing/revocation and workspace-token rotation.
* New tests cover ten distinct accounts shared across browser/Mobile sessions; multiple devices counted once; simultaneous admission; 64-session cap; logout/expiry/rotation/reset; real OPAQUE enrollment refusing an eleventh account without storing its record; expired browser sessions requiring password again; bounded OPAQUE workers; mutually matching signed direct-path reports; wrong/missing channel rejected; Mobile–Mobile ciphertext delivery without Agent-role elevation; per-peer byte and request/global rate limits; idempotent retry; rejection of plaintext credential fields.
* Reference Noise IKpsk2 test passed through the Server courier, rejecting wrong PSK, tampering and replay at reference peers. No plaintext, pairing PSK or SSH credentials enter Server relay state. This is primitive/courier testing, not an audit of future native clients.
* Package audit verifies extracted source parity, version/dependencies, clean payload, migration/service scripts and isolated IPv4/IPv6 browser/Agent startup. Installer is built, not installed here.

## Delivery boundary

Only Server code is implemented. Direct SSH listeners, authenticated IP/key offers, local key-only access restrictions, 24-hour credential rotation, NAT/reachability selection and file-transfer cutover are Agent/Mobile responsibilities specified in [docs/DIRECT_PEERS.md](docs/DIRECT_PEERS.md). They require matching client builds and real-network integration tests before funds. No direct SSH client-to-client connection, real Bitcoin transaction, blockchain download or physical archive burn is claimed tested in this release.

Existing QR-paired identities remain stable. The Server accepts ciphertext negotiation and signed path status, but does not see credentials, dial peers or configure ports. Encrypted relay fallback remains bounded; Bitcoin Core network downloads are not routed through this HTTP courier.

Ten-account admission and application work limits do not protect the host from volumetric DDoS or a compromised OS login acting outside this program. No system-wide SSH login limit or firewall change is installed. OPAQUE still depends on trustworthy client code; compromised Server-delivered browser JavaScript can steal typed passwords. Native Mobile must bundle its own authentication implementation.
