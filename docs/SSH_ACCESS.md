# SSH forwarding access for trusted devices

SSH authentication and permission to forward are separate. A key with `restrict,port-forwarding,permitopen="[::1]:8096"` can authenticate but cannot forward to the Agent interface `[::1]:56443`. An IPv4 Internet SSH connection can forward to IPv6 loopback on the Server: these address families are independent. Do not change the Agent target to bypass the intended IPv6 route.

The Server application receives no HTTP request when sshd rejects forwarding. A DEB upgrade alone cannot correct a selected operating-system key policy safely. Build 14 provides an explicit administrator tool, not an automatic permissions migration. It never changes keys during installation, web login or Agent registration.

## Audit first

On the Server, replace SSH_ACCOUNT with the actual OS account:

```bash
sudo python3 /usr/lib/wallaby-wallet-server/ssh_access.py --user SSH_ACCOUNT
```

Output lists effective sshd forwarding policy, key line numbers and SHA256 public-key fingerprints, without key bodies or forced-command contents. The default effective-policy check uses client address 127.0.0.1. If sshd has address-based Match rules, pass the actual client address with `--client-address ADDRESS`.

## Remove port restrictions from a trusted key

Choose the audited key line number, replacing ENTRY:

```bash
sudo python3 /usr/lib/wallaby-wallet-server/ssh_access.py --user SSH_ACCOUNT --entry ENTRY --allow-all-ports
sudo python3 /usr/lib/wallaby-wallet-server/ssh_access.py --user SSH_ACCOUNT --entry ENTRY --allow-all-ports --apply
```

The first command previews; only `--apply` writes. Optionally supply `--expected-fingerprint SHA256:...` to stop if the selected key has changed since inspection. Only default `.ssh/authorized_keys` files are repaired; custom key paths and global restrictions require manual administration.

This explicitly grants that key forwarding to any port permitted by its SSH account, not only Wallet Server ports. Use it for trusted devices. It removes `permitopen`, `permitlisten` and `no-port-forwarding` from that selected entry and ensures `port-forwarding` is present after `restrict`. It preserves forced commands, source-address restrictions, PTY/X11/agent restrictions, the public key, other entries and all other accounts. It does not change sshd listeners, passwords, group membership, GatewayPorts or globally disabled forwarding. If account-level forwarding restrictions remain, it refuses to apply rather than modifying them.

The tool checks ownership, permissions and file type, refuses symlinks/hardlinks, keeps an exact private backup in the same `.ssh` directory, preserves file ownership/mode, and replaces the file atomically. It stops if another editor changed the file. `keys_before` is the prior policy and `keys` is the applied policy in the JSON output. Repeat application is idempotent.

Reconnect the Agent's SSH connection afterward: an already authenticated master retains the restrictions it had when it logged in. No sshd restart is required for an authorised-key change. Wallets, builders, signed requests and profiles are not touched.

## Roll back

The apply result identifies `authorized_keys.wallaby-....bak`. Review it before restoring. If no subsequent keys have been added, copy that backup over the same account's `authorized_keys`, preserving its owner and permissions. Reconnect afterward. If other entries have changed since the repair, restore only the selected entry rather than overwriting later work.
