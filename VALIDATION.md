# Wallet Server V1 Build 14 Development — validation

Validated 14 November 2026 with isolated profiles and invented SSH keys. No installed service, live authorised-key file, household profile or wallet was changed by testing.

The supplied administrator diagnosis showed `AllowTcpForwarding yes`, `DisableForwarding no`, `PermitOpen any`, and a selected key with `restrict,port-forwarding,permitopen="[::1]:8096"`. The denial is in SSH key policy before the Agent registration endpoint, not in Bitcoin RPC or IP-family fallback. The requested repair removes port restrictions only from a selected trusted key.

Nine focused checks passed. An official Ubuntu OpenSSH 10.2 server was extracted into a private test directory without installation. Its real IPv4 login plus IPv6 direct-tcpip forwarding reproduced the administrative denial; after the repair, requests to two independent IPv6 loopback ports succeeded, without restarting sshd. Unit checks cover selected-entry isolation, quoted commands/commas, preserved non-port restrictions, idempotence, exact backups/ownership/mode, audit redaction, fingerprint mismatch, dry-run, non-root refusal, account-level restriction refusal, unsafe file/symlink/hardlink refusal and concurrent-editor detection.

The related Server regression selection runs 146 checks: 144 passed and two optional integrations needing historical Agent snapshots were skipped. Current Agent Build 93 public preview/offer and active-work handling are included. Full historical suites and the household's live Agent reconnect were not tested here.

Installer checks cover metadata, exact extracted-source parity, exclusion of runtime wallets/configuration/uploads/logs/PSBTs, and isolated IPv4/IPv6 browser and Agent health startup. The package was not installed on the user's server. Installation never invokes SSH repair or widens forwarding; an administrator must explicitly apply the selected repair with sudo. Existing wallet/profile schemas and signed requests are unchanged. No Agent protocol change is required for this fix.
