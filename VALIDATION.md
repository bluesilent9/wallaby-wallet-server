# Wallaby Wallet Server V1 Build 4 Development — validation

Validated 9 November 2026 in isolated temporary profiles. No installed service, household profile, wallet or Agent/Mobile source was changed.

* Full Python regression suite: 942 tests passed, including OPAQUE registration/login, shared account admission, profile preservation, encrypted relay and wallet workflows.
* 54 JavaScript suites passed, including password boundary/composition checks: 7 versus 8 characters, 1024 versus 1025, missing digit, missing symbol, whitespace not counting as a symbol, and Unicode punctuation/symbol support.
* Actual browser OPAQUE enrollment with the eight-character invented password `abcde1!f` passed, followed by login from a second independent browser. Missing digit/symbol and whitespace-only special-character inputs were rejected before registration. Matching confirmation, Mobile pairing/revocation and workspace-token rotation still passed.
* Recovered the original SVG from the historical v129 source; changed only its title to Wallaby Wallet. Browser inspection verified the restored Wallaby-and-Bitcoin badge in the sidebar and the new password instructions. Server favicon and generated report shell use the same artwork. Repository README and shared Wallet/Suite product marks are updated; Agent/Popcorn/Suite-wide identities remain their own.
* Package audit: exact extracted source parity, V1 Build 4 metadata, clean payload without runtime records/keys/logs/uploads, migration and service scripts, and isolated IPv4/IPv6 browser/Agent startup. The DEB is built, not installed here.

Password creation policy is enforced in trusted client software, because OPAQUE does not disclose the password to the Server. Metadata advertises the policy to future native Mobile clients. Existing password records, OPAQUE suite, user IDs, saved wallet/vault data and login acceptance are unchanged; no password or profile reset occurs.

The direct-peer protocol remains the Build 3 contract in [docs/DIRECT_PEERS.md](docs/DIRECT_PEERS.md). Agent/Mobile implementations and real-network direct SSH integration tests are still separate work. No real Bitcoin transaction or physical archive operation was performed for this release. Compromised Server-delivered browser code remains a password-entry trust limitation; independently installed Mobile authentication code must be bundled with the app.
