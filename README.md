<p align="center"><img src="assets/logo.svg" width="112" alt="Wallaby Wallet"></p>
<p align="center"><img src="assets/logo.svg" width="112" alt="Wallaby Wallet — Wallaby and Bitcoin"></p>
<h1 align="center">Wallaby Wallet Server</h1>
<p align="center">Your Bitcoin. Managed together.</p>

**V1 Build 12 · Development. No Stable release is available yet.**

[Explore Wallaby Wallet](https://bluesilent9.github.io/wallaby-suite/wallet/) · [Wallaby Suite](https://bluesilent9.github.io/wallaby-suite/) · [Development installer](https://github.com/bluesilent9/wallaby-wallet-server/raw/refs/heads/Development/dist/wallaby-wallet-server_1.0.0~dev12_all.deb) · [Checksums](dist/SHA256SUMS.txt) · [User guide](docs/USER_GUIDE.md)

Wallaby Wallet Server is the Bitcoin-focused successor to Wallaby Dashboard. It coordinates family wallet management, single-signature and multisignature wallets, height-locked vaults, transaction building, optical archive requests, balances, a node-backed Mempool explorer, salary planning and Australian CGT working papers. The interface is branded **Wallaby Wallet**.

Private wallet material and signing remain on independently controlled Wallaby Agents. The server's statements are proposals; Agents must independently validate and locally authorise sensitive actions. This development software is not a guarantee against loss of funds.

## Version 1 Build 2

New in this build: OPAQUE passwords with preserved existing profiles, Agent–Agent/Mobile–Agent opaque relaying, role-bound QR pairing contracts, multisig channel readiness, and BTC-only mobile balance responses. Matching Agent and Mobile changes are required before the new encrypted peer workflows can operate. See [secure relay](docs/SECURE_RELAY.md), [password migration](docs/PASSWORD_AUTH.md) and [mobile data](docs/MOBILE_DATA.md).

## Earlier rename migration

The rename reset the product version from Dashboard V1 Build 120 to Wallet Server V1 Build 1; this release advances it to Build 2. Saved profile formats, existing wallet identities, rename history, builders, vault policies and signed in-flight requests do not reset. Existing Agent communication keeps its established, product-neutral signed formats. New mobile messages use the `wallaby-wallet-mobile` protocol.

The new **Mobile Devices** page supports explicit QR pairing, per-user encrypted relay and password-authenticated account reads, automatic reconnection authentication, revocation, and current public verification claims. Mobile transport uses a separate SSH-loopback interface on **56444**. The existing Agent interface remains on **56443**, and the browser interface remains on **38951**. Mobile comparisons never approve a wallet, sign a transaction, run a Core RPC or bypass an Agent prompt.

This release implements the **server stage only**. The Android application and Agent QR screens will be implemented separately. The server can be upgraded independently; existing Agent workflows remain available. Restoring extinct managed signers retains Build 90's requirement for Agent V2 Build 65 or later on both peers and locally recorded original role evidence.

## Installation and upgrades

Ubuntu/Kubuntu 26.04 LTS: download the Development DEB, verify its checksum, then install with `sudo apt install ./wallaby-wallet-server_1.0.0~dev12_all.deb`.

The new package replaces `wallaby-dashboard`. Its migration stops the previous system service, moves existing application data and cache to `/var/lib/wallaby-wallet-server` and `/var/cache/wallaby-wallet-server`, preserves the data byte-for-byte, and starts `wallaby-wallet-server.service`. Existing legacy data paths remain compatibility links. Conflicting nonempty old/new profiles are never silently merged. Stop manually launched copies before upgrading. No live installation is performed by the build process.

See [installation and migration](docs/CLEAN_INSTALL.md), [mobile/Agent integration contract](docs/MOBILE_VERIFICATION.md) and [validation](VALIDATION.md).

## Repository and project boundaries

`Development` contains this build. `Stable` contains release information until a Stable version is explicitly approved. Wallaby Wallet Server replaces the former Dashboard project. The old repository is retired; its Git history is preserved locally. Mobile and Agent repositories are separate projects. This repository does not implement firewall management, email hosting or other general server-management features.

Licensed under AGPL-3.0; see [LICENSE.txt](LICENSE.txt). Bundled components retain their own notices. QR generation uses Project Nayuki's MIT-licensed library.

Build 3 adds direct-peer SSH rendezvous policy and path status, Mobile–Mobile courier support, shared ten-account admission and bounded authentication/relay work. Agent/Mobile implement direct SSH using [DIRECT_PEERS.md](docs/DIRECT_PEERS.md). Matching clients are required; the Server never receives SSH credentials or opens peer ports.

Build 4 restores the original Wallaby-and-Bitcoin logo and changes password creation to 8–1,024 characters with at least one digit and one punctuation/symbol character. Saved passwords and profile data are not reset.

Build 11 migrates older saved extinction records that predate the newer wallet metadata, so a retained old replica and its verified Extinct copy are traced as one account. Reconciliation runs before explicit Ownership tracing as well as during background discovery; frozen requests and Agent receipts are unchanged. Accepted personal and SMSF Bitaroo PDFs now persist independently of wallet-tracing success, and freshness warnings use their paired statement dates. Saved calculations are not marked complete by an upload. No Agent update or profile reset is required.


Build 12 keeps public wallet source offers visible when receiving is denied, without creating executable transfer requests. If an Agent restarts and regenerates its signed preview, an unattempted invitation is renewed with a fresh challenge and fresh local choices. Frozen reviews, active work and recorded outcomes are retained. No profile reset is required.
