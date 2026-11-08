# Wallet Server Build 90 / Agent Build 65 lifecycle coordination

Wallet Server persists the intended active/extinct state independently of signed Agent work. Extinction moves the logical wallet card immediately; Restore immediately moves that same identity back to Active Wallets. Opposite-state copies found on later Agent reconnection enter the corresponding locally approved workflow. Absence alone does not prove extinction. Locally denied requests do not silently change Wallet Server intent.

Actual Core history, private keys, LOST labels, blockchain catchup and local archive handling remain Agent-owned. Verified preservation in an existing Extinct wallet is still required before any zero-balance local deletion. Extinction does not require every signer or a signing quorum.

## Direct SSH restoration

Both fresh wallet_transfer v2 proposals carry restoration={version:1,policy_id:<canonical SHA256 of sorted normalized public descriptors>}. Both peers must be Agent Build 65 or later. The sender's signed public preview must carry the identical restoration object. Wallet Server validates its schema, complete policy hash, signature and binding to the frozen invitation. This purpose cannot be added to an existing ordinary-sync preview. Route changes, deliberate retries and unattempted-denial invitations retain the purpose on new identities, without reusing approval.

Agent 65 independently records original role/key ownership before extinction and authenticates a transfer-specific receiver permit over direct SSH. It checks the actual encrypted backup key ownership before file transmission and before loading. Wallet Server never receives private wallet material and cannot authorise arbitrary signer replication. The complete public descriptor set, including old vault generations, is retained. Missing original role evidence is blocked. An unavailable signer does not prevent restoring another available signer.

Wallet Server keeps exact original per-node accounts separately even when public descriptors coincide; these do not create separate logical Wallets cards. Sources are exact policy matches. Agent-side key ownership checks are authoritative. Unknown roles and missing sources remain visibly waiting rather than being silently downgraded or guessed.

The first qualifying active copy observed after Wallet Server Restore must contain private keys. Watch copies cannot clear the non-dismissible missing-active-private-source warning. Once a qualifying private copy has been observed, that fact persists; extra Agents may have or receive watch copies. Per-Agent stale extinct-copy notifications are separately dismissible and persist their dismissals through restarts/profile backups.

## Withdrawal and audit

Restore uses existing wallet_retire_cancel v1 for delivered pending retirement requests and stops undelivered requests. It withdraws pending extinction-related disc-destruction tasks, including after an interrupted Wallet Server restart; no claim is made about undoing completed physical destruction or deletion. Archive queue snapshots immediately hide obsolete destructive intent. All actual restoration still requires local approval and direct SSH.

Completed/uncertain outcomes are immutable. An unattempted local Deny may produce one fresh invitation with a new nonce/transfer identity while intent remains. Agent persistent deny entries suppress it until removed locally. A temporary local Cancel has no terminal outcome, so unchanged Wallet Server intent may be reoffered. Private material is never relayed through Wallet Server. Desired state, retained identity/history, per-node progress and notification dismissals are included in Wallet Server profiles.
