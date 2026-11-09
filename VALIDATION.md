# Wallaby Wallet Server V1 Build 5 Development — validation

Validated 9 November 2026 using isolated temporary profiles. No installed service, household profile or Agent/Mobile code was changed.

* Full Python regression: 948 tests passed, including six new shared pending-ownership/login cases. Assigned resources with no prior Ownership run open Wallets; missing assignments send every user to Ownership; a past run does not override a current missing assignment; an empty system opens Wallets; another user's saved exchange inventory is checked; saved linked builders survive without taking over login.
* 54 JavaScript suites passed. Existing builder recovery expectations were updated to preserve working state without automatic builder navigation.
* Real browser checks passed for empty-system, previously used system with another user's records and a saved transaction, and currently unassigned-resource cases. Each included OPAQUE password creation/login, a second independent browser login, Mobile pairing/revocation, token rotation and no JavaScript errors. Expected login route was asserted for both browser sessions.
* Actual SVG geometry checks confirm that the Mobile Devices sidebar icon and Pair a Phone button each have a nonempty rendered bounding box. The shared icon also appears on device cards. Replaced invalid embedded SVG markup in a path-data slot with valid phone-outline drawing commands.
* Package checks: extracted-source parity, Build 5 metadata, no private/runtime profile data, existing migration/service scripts, isolated IPv4/IPv6 browser and Agent startup. DEB built but not installed here.

Login routing derives pending assignments from shared current descriptor resources, saved inventories from all users and existing ownership records. It reuses ownership validation and canonical resource identities, excludes extinct/inactive descriptor records and does not treat display renames as missing owners. No historical Ownership-run marker is written or needed. Saved workspaces remain accessible from their normal pages; their contents are not cleared or converted into templates.

The Build 4 password policy and original Wallaby/Bitcoin artwork remain unchanged. Matching Agent/Mobile updates for the direct-peer protocol remain separate work; this build does not change that protocol or claim new real-network peer testing.
