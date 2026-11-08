# Install Wallaby Wallet Server

Development V1 Build 1, Ubuntu/Kubuntu 26.04 LTS. No Stable release is published.

Download `wallaby-wallet-server_1.0.0~dev1_all.deb` and `SHA256SUMS.txt` from this repository's Development/dist directory. Run `sha256sum -c SHA256SUMS.txt`, then `sudo apt install ./wallaby-wallet-server_1.0.0~dev1_all.deb` in that directory.

The system service is `wallaby-wallet-server.service`. It starts at installation and boot, running as the unprivileged `wallaby-wallet-server` system user. Application code is in `/usr/lib/wallaby-wallet-server`; saved records are in `/var/lib/wallaby-wallet-server`; disposable runtime state is in `/var/cache/wallaby-wallet-server`. Removal/purge preserves records. Browser and Agent access continue through your existing SSH setup; their loopback ports remain 38951 and 56443.

## Existing Dashboard installations

APT replaces the old `wallaby-dashboard` package. The pre-install step stops both old/new services before data migration. The installer preserves exact saved profiles, pending requests, identities, wallet names, vault records and builder state. It does not renumber stored schemas or rewrite signed messages. Legacy data/cache paths become links to their new locations so existing administrative references still resolve. Existing SSH routes and Agent endpoints keep their ports.

If both old and new data locations already contain records, the installer stops with an explanation instead of mixing them. Keep both directories and resolve which profile should be retained. A failed directory move is rolled back. Stop any manually launched server before installation. The migration does not delete wallet files on Agents or modify Bitcoin Core.

For a source installation use `python3 launch_wallaby_wallet_server.py --no-browser`. The earlier launcher module remains an import/entry-point alias for source installations. The product's version number is V1 Build 1; the package's distinct name avoids downgrading an installed Dashboard dev90 package in place.

## Mobile connections

The mobile API listens only on 127.0.0.1:56444. It cannot be configured to bind publicly. The later Android app must establish an authenticated SSH local forward to this port, verify the full OpenSSH Ed25519 host key from pairing and remember it. No TLS certificate, public HTTP listener or Agent SSH-key change is required. A changed SSH host key must stop automatic reconnection until explicitly re-verified.

The pairing page reads `/etc/ssh/ssh_host_ed25519_key.pub`, never the private host key. Install/configure OpenSSH server if it is absent. A service override can select another public key using `--mobile-ssh-host-key`; `--mobile-port 0` disables the mobile listener. It is separate from the Agent and browser protocols. The phone authenticates to SSH using the user's existing chosen SSH access; pairing does not create OS accounts, alter sshd configuration or install authorised SSH keys.

The Android app and Agent QR screens are not part of this release. They must implement [the verification contract](MOBILE_VERIFICATION.md) before end-to-end scanning is available.
