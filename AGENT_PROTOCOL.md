# Current Agent protocol — Wallet Server Build 68

Requires Agent V2 Build 56 or later. No older Agent release fallback or presence-only registration is supported. Wire endpoint `/agent/v1` and exchange `/agent/v2` remain the current APIs used by Agent 56.

The archive queue and public-policy renewal payloads are described in [the integration contract](docs/BUILD27_AGENT_CONTRACT.md); their wire schemas remain in use by Agent 56.

## Agent HTTP and RPC capability schemas

Wallet Server is the hub. Wallaby Agent initiates every connection through its authorised SSH tunnel, polls for commands, calls its local Bitcoin Core, and posts results. No server-initiated connection to a laptop is required. The production Agent application is **not** bundled with this Wallet Server; the server contract is implemented and integration-tested with the actual Agent client and a simulated Core HTTP endpoint.

## Transport

- Wallet Server browser: **38951**, unchanged.
- Agent HTTP/JSON: **56443**, bound to IPv4 `127.0.0.1` and IPv6 `::1` by default. `--agent-port` changes it; `--ipv4-only` / `--ipv6-only` apply to both listeners. Client-side SSH forwarding ports may differ.
- These are separate loopback listeners. SSH authenticates and restricts access; the browser and agent endpoints are not public Internet services. Agents do not use browser session credentials. Core RPC credentials remain on the node computer and must never be included in a hub message.
- POST headers: `Content-Type: application/json`, one Content-Length, `X-Wallaby-Agent: 1`, `X-Wallaby-Agent-Version: 2.0.0~dev56` (or a newer supported version). After registration add `Authorization: Bearer <connection_token>`. Tokens are temporary, not entered by users, never URL parameters, logs or profile data.
- Control requests: at most 4,096 bytes. `/agent/v1/result`: at most 16 MiB plus 4 KiB of envelope space; the decoded result/error has its own 16 MiB limit. Oversized results must be narrowed/paginated using Core's method parameters. No chunks are silently discarded.
- JSON must be UTF-8, have no duplicate keys, and no NaN/infinity. Browser Origin headers are rejected. Host must name a loopback endpoint, with any valid tunnel port. Unknown endpoints/fields are rejected.

## 1. Registration and permission negotiation

`POST /agent/v1/register`

```json
{"mac":"02:11:22:33:44:55","hostname":"example-node","rpc":{"version":1,"methods":["getblockchaininfo","getbalances","listdescriptors"]}}
```

The example identifies no built-in device. The Agent chooses a stable unicast adapter MAC consistently across restarts. Hostname/MAC are normalised and are self-reported identity hints, not proof of device authenticity. SSH supplies authentication. Changed MACs create new remembered nodes; a hostname can update for the same MAC when the previous connection is no longer live.

`rpc` and the `X-Wallaby-Agent-Version` header are required. Unsupported/missing Agent versions and presence-only registration are rejected. Methods are negotiated as the intersection of the agent's enabled methods and the hub's permitted methods. Advertising a method never overrides the hub's policy. The Agent must independently enforce its advertised methods and the public-data restrictions below.

Response:

```json
{"protocol":"wallaby-agent","version":1,"connection_token":"<temporary secret>","node_id":"<stable ID>","heartbeat_seconds":15,"disconnect_after_seconds":45,"capabilities":["presence","rpc"],"rpc_methods":["getbalances","getblockchaininfo","listdescriptors"],"commands":[]}
```

Only advertise methods that the local Agent is configured and capable of executing. Core GUI requires RPC server mode enabled. Use the relevant Core version's method documentation; the initial target is Core V31.

`GET /agent/v1/health` exposes the server protocol/capabilities and permitted method names, without node identities or credentials.

## 2. Heartbeat, command poll and disconnection

Every 15 seconds send `POST /agent/v1/heartbeat` with `{}`. Its response includes any pending command. A dedicated command loop should also send `POST /agent/v1/poll`:

```json
{"wait_seconds":20}
```

The integer wait is from 0 to 20 seconds. The poll returns immediately when work is available, otherwise at the timeout. A poll refreshes in-memory connectivity; regular heartbeats persist the Last seen timestamp. Keep the heartbeat/poll loop active while a separate worker executes a slow Core RPC. Otherwise an RPC that takes longer than 45 seconds could look like a disconnected Agent.

Both responses use `{"ok":true,"commands":[...]}` and deliver at most one RPC command per response. A command has:

```json
{"id":"<request ID>","kind":"rpc","method":"getbalances","params":[],"wallet":"Exact Core wallet name","expires_in_seconds":29.5}
```

The request ID identifies one immutable request. `wallet` is null for node-wide methods. `params` is an array or named-parameter object. Expiry is a remaining duration, independent of the Agent's wall clock. Never start expired work.

Gracefully end the connection with `POST /agent/v1/disconnect` and `{}`. Heartbeat/poll authentication expiry returns HTTP 401: register again. Do not register on each poll. Two live registrations claiming the same hostname or MAC produce conflict warnings and disable RPC to the affected connections. Resolve the duplicate before retrying any operation.

## 3. Acknowledge before execution

`POST /agent/v1/ack`

```json
{"id":"<request ID>"}
```

Response: `{"ok":true,"state":"running","execute":true}` for the first acknowledged delivery. Duplicate acknowledgements return `execute:false`. Terminal/expired requests cannot be restarted. Maintain a local per-connection record of request IDs and completed results: duplicate deliveries are not new work.

Execute only after receiving `execute:true`. If that acknowledgement response is lost, do not blindly execute or assume another acknowledgement authorises execution. Report/resolve the uncertain state; the request will time out. This favours avoiding an accidental repeated wallet operation over pretending that distributed systems can guarantee exactly-once execution.

## 4. Local Core call and result

The Agent sends Core a JSON-RPC 2.0 request using the command ID, method and params. For wallet methods, URL-encode the exact wallet name as one path segment in `/wallet/<encoded-name>/`. The Core host, port and credentials come from trusted local Agent configuration, never from hub parameters. Verify the returned Core response ID. Do not invoke a shell or construct console command strings.

Post exactly one of:

```json
{"id":"<request ID>","result":{"blocks":970000,"chain":"main"}}
```

```json
{"id":"<request ID>","error":{"code":-18,"message":"Requested wallet does not exist."}}
```

`POST /agent/v1/result` accepts arbitrary bounded JSON results, including null. Errors require code (integer or string) and message; optional data is supported. The server correlates replies to both request ID and the assigned connection token. Another node cannot complete a request. Duplicate or late replies cannot overwrite a terminal result; the acknowledgement includes `accepted:false`.

Preserve decimal values from Core without binary-floating-point conversion. Forward the original JSON value or decode numbers with an exact decimal parser. The hub exposes fractional JSON numbers as **plain decimal strings** to preserve monetary precision (`0.00000001` becomes `"0.00000001"`). Integer heights/counts remain integers. Do not convert BTC to floats in the future Agent.

## 5. Wallet Server application API

Authenticated, logged-in browser workspaces can queue:

`POST /api/nodes/rpc`

```json
{"node_id":"<stable node ID>","method":"getblockchaininfo","params":[],"timeout_seconds":30}
```

Wallet calls additionally need `wallet`. Timeout defaults to 30 seconds and must be from 1 to 3,600 seconds. Parameters are limited to 4 MiB. The response is HTTP 202 with a request ID/state. Poll `GET /api/nodes/rpc/result?id=<request ID>` in that same browser/profile. Results are not available to another browser workspace or a different selected profile. Request parameters, response bodies and credentials are not written into session logs; method/ID/state summaries are.

The Nodes page's **Check node** button uses this exact API for `getblockchaininfo`. It is disabled for disconnected agents, conflicting identities, or agents not advertising that method.

Future Python features can use `sessions.nodes.rpc.queue(...)`, `.status(...)`, or synchronous `.call(...)`. The same policy, deadlines and identity checks apply. No generic node URL or authentication secret is accepted through these interfaces.

## Permissions and lifecycle

The method catalogue in `agent_rpc.py` covers node/chain/mempool reads, descriptor/address inspection, wallet balances/history, historical scanning/block retrieval, and public watch-only setup. Wallet methods require an explicit wallet endpoint. `listdescriptors` permits only its public form. `createwallet` permits only named, blank, private-key-disabled descriptor-wallet creation. `importdescriptors` validates supported public descriptors before delivery.

Signing, wallet unlocking, private exports, broadcast, arbitrary method names and arbitrary commands are not allowed. Cold-storage signing remains a local user-controlled action. An Agent must apply these same rules locally even if its SSH-trusted hub is compromised. Expanding the catalogue is a deliberate future permission change, not an agent-supplied bypass.

States are queued → delivered → running → succeeded/failed, with timed_out also terminal. Pending requests fail on connection expiry/disconnect, identity conflict, profile replacement or server shutdown. They are **not automatically replayed** on reconnect. A failure/timeout after delivery does not prove Core cancelled the operation: the local operation may still finish. Reconcile the actual Core state before deliberately issuing a new write request.

The queue is bounded (16 pending requests per node, 256 retained requests and 64 MiB aggregate request/result storage). Terminal results expire after 10 minutes. Live requests/results are memory-only; they do not survive service restart or enter profile backups. Remembered node identities still reside in `data/nodes.json` and profile.7z.

## V156 node wallet discovery

Load Node Wallets queries every connected RPC-ready node. Required read methods: listwallets, listwalletdir, getwalletinfo, listdescriptors (private=false), listsinceblock (include_change=true), getaddressinfo. Wallet endpoints retain the exact node-local name, including the empty default name. Replicas are recognised by public descriptors rather than labels. An unloaded wallet is reported for the user to load in Core; Wallet Server does not silently load or unlock it. A failed node prevents publishing a partial catalog. Public tracing remains separate.

Application-internal read workflows consume completed RPC payloads promptly. Short-lived bounded tombstones retain only token/state metadata so a retried Agent acknowledgement/result is safely recognised without retaining wallet-history payloads. Cancelling Load Node Wallets cancels its pending read waits; no write RPC is replayed.

## Exact Core wallet routing and dispatch capacity

Wallet-scoped requests use `/wallet/` plus the URL-encoded exact Core wallet name, without appending a slash. A null wallet is node-wide; an empty string denotes Core's default wallet. Names are never inferred from display labels.

Wallet Server V1 Build 6 limits delivered/running work to two commands per Agent connection, with queued work released as results arrive. Agent V2 Development Build 4 independently bounds execution to two workers and tolerates a brief completion/slot-release race. Multiple nodes can execute concurrently, and equivalent public-descriptor replicas can share follow-up reads. These limits do not insert an artificial delay between successful requests.

## Build 6 background scheduling

Read-only calculation workers use a private loopback bridge with a per-workspace bearer secret and a strict method allowlist. Core cookies and private keys never enter worker configuration. Foreground calls use priority 0; fee observations use priority 100. Queued foreground work precedes background work, and background calls wait while foreground commands are queued or executing. Already executing RPCs are not preempted. No Agent wire-protocol change or signing permission is required.

Build 34 retirement replaces new wallet-retirement requests with the two-phase wallet_retirement_v3 contract in [docs/BUILD34_EXTINCTION_PROTOCOL.md](docs/BUILD34_EXTINCTION_PROTOCOL.md). No v2 execution fallback is provided.


# Wallet Server Build 80 / Agent coordination

The user wants Wallet Builder to remain open until all involved Agents approve the new vault policy. One row and one policy request per Agent, including an Agent holding multiple loaded disc signers.

Wallet Server keeps the existing `wallet_policy_refresh` version-1 proposal fields. Agent should advertise `wallet_policy_refresh_batch_v1` in addition to `wallet_policy_refresh_v1`. Requests requiring this feature are withheld until the capability is advertised; no old-Agent fallback treats sending as receipt.

After durably accepting a proposal, Agent queues `wallet_policy_refresh_receipt`, signed with the existing wallet-setup signing envelope:

```
{"version":1,"request_id":"<proposal request_id>","request_hash":"<digest of complete proposal>","status":"received"}
```

Wallet Server validates the Agent identity, node, request ID and exact proposal hash. This changes the dot from red to amber. Merely delivering an HTTP response never counts as receipt.

A single local review/approval must independently identify and update ALL related currently loaded signers, policy monitors and disc recovery metadata for that same previous policy. It must preserve private keys, quorum, old descriptors and unrelated archive members. In particular, updating a regular node signer must not omit other loaded disc roles, and updating one archive member must not omit another role on the same Agent. Public-key-only accounts may need their associated approved policy/monitor updated without replacing their key material. Archive policy_extensions/replacement-archive requirements must cover each affected member. A failed or partial update must not report full approval.

The signed `wallet_policy_refresh_result` keeps its existing fields and adds `updated_wallets`: a list of every local RPC wallet alias covered by the approval, including the requested wallet/monitor and each related private signer alias. Names must be actual loaded local RPC routes. One signed approval result covers the entire local batch. Wallet Server independently reads each expected alias's public descriptors to verify the new receive/change policies and retention of the earlier public descriptors. It does not trust a claim that multiple signers were updated merely because the monitor was updated. This changes the dot to green only after full verification. `history_required`, denial and errors remain blocking.

Existing source policy identity comes from locally verified public descriptors and approved setup/archive records; no new-wallet fingerprint challenge or key-generation ceremony is introduced. Policy previews and current transaction drafts must be retained through reconnects/restarts. Repeated identical requests must reuse the same review/receipt and reconcile partial work safely, rather than create duplicate approvals.

Agent Build 57 currently has no separate policy receipt and its Refresh.approve updates a single targeted local wallet/archive record. It needs the above change for the full requested behaviour. Wallet Server code is confined to the Wallet Server build; this chat does not modify Agent source.

## Cancellation / an Agent declining (latest user request)

If any Agent returns a signed `denied` result for the pending linked renewal,
Wallet Server durably cancels the whole refresh, returns the user to the original
unchanged Transaction Builder diagram, and stops issuing that policy proposal.
It keeps delivery of cancellations to offline participants in its saved queue.
The Transaction Builder remains disabled while the approval phase is active.

Wallet Server uses existing `builder_cancel` v1 for every Agent to which the exact
policy request was delivered, including Agents which already approved it.
`builder` is `wallet`, `workspace_id` is the linked Wallet Builder id,
`request_hashes` contains the complete original policy proposal digest, and
`operations` is empty: these are existing wallets, NOT wallet-setup sessions to
delete. The existing receipt ends delivery only; local cleanup remains under
Agent authorisation. Never interpret this as deleting existing signer wallets.

Agent should resolve the exact proposal from that hash, withdraw pending review,
and for an approved proposal offer safe local cancellation of the newly added
policy and matching disc replacement/destruction handling. Existing keys, older
policies, funded history and unrelated disc members must survive. If Core cannot
physically remove the imported descriptor safely, retain recovery/monitoring
history and explicitly record retirement of the cancelled receiving policy;
never pretend this invalidates its Bitcoin spending script or erases funds.
Discs containing other required data need a verified replacement before an
old-disc destruction task becomes available. No automatic deletion or disc
confirmation by Wallet Server.

The matching Agent58 implementation adds signed outbox
`wallet_policy_refresh_cancel_result`. Wallet Server accepts/persists it only for the
exact delivered `builder_cancel` target:
`{version:1,cancellation_id,request_hash:<builder_cancel digest>,status:"complete",
policy_request_hashes:[<exact sorted original proposal digests>],
retired_policy_hashes:[digest([receive_descriptor,change_descriptor]), ...],
descriptors_retained:true,keys_retained:true,destroyed_archives:[<archive IDs>]}`.
This is local Agent completion evidence, distinct from the earlier delivery-only
`builder_cancel_receipt`. Wallet Server never asserts physical destruction itself.

Agent58 also reports `status:"retained_funded"` when its local funding check
prevents retirement and the Agent user explicitly retains the funded policy.
For this outcome `retired_policy_hashes` and `destroyed_archives` must be empty;
keys/descriptors must still be retained. Wallet Server accepts and saves this safe
local outcome, ends cancellation delivery, and produces one red notification
that the funded policy and discs were retained. It never describes it as a
successful retirement/destruction.


## Build 81 — released Agent58 capability negotiation

`wallet_policy_refresh_cancel_v1` is an accepted, implemented Agent capability. It complements grouped policy refresh, existing builder_cancel requests and signed wallet_policy_refresh_cancel_result outcomes. Unknown capabilities remain rejected. Agent version display is not substituted for capability or signature validation.


# Agent Build 60: exact refresh address comparison

Status: implementation in work/wallaby-agent-v2-build60; tests and release in progress. Agent 59 rejects the new optional field, so Wallet Server must require worker_version >= 2.0.0~dev60 before sending it. Do not change an already delivered/approved proposal in place.

Diagnosis confirmed on user wallet-laptop: green proposed receiving address is index 15 of the exact new descriptor reviewed on all three Agents (height 1,008,286). Earlier reviews displayed only samples 0 and 1. No incorrect derivation was found.

## Request

Keep wallet_policy_refresh version 1 and all existing mandatory fields. Add one optional field:

    "receiving_address": {"index": 15, "address": "<reserved green receiving address>"}

The index must be an integer (not bool), 0–999 inclusive. The address is the receiving descriptor at that index, on the proposal network. Both fields are required together; no other members are accepted. Wallet Server should copy both values from the same saved destination used by the Address page and funding transaction; never reserve another address for the review. Do not infer the index from Agent Core next_index.

## Agent verification and presentation

Validate the address by local independent descriptor derivation at acceptance. Before presenting review, also compare that result with local Core deriveaddresses. A mismatch refuses the request/review. The index/address are covered by the canonical request hash and exact reviewed proposal equality before approval.

Show the actual proposed receiving address prominently. Then show Receive #15, #16, #17 and Change #15, #16, #17, each independently derived and checked against Core. Both lists start at the requested receiving index for comparison; the change samples are not a promise that a future transaction will use that change index. At indexes 998 and 999 show only remaining in-range entries; never wrap or exceed 999.

Old requests without the field remain valid with samples starting at 0, but explicitly say they do not identify Wallet Server's reserved destination. No field is guessed or silently added to an existing approved request.

The underlying descriptor-pair policy hash and archive policy extension format do not change: selecting an address does not create a new spending policy. The complete proposal request hash does include the new field. Existing receipts/results/cancellation hashes continue to bind the complete proposal. No new capability string is introduced (old Wallet Server capability allowlists reject unknown capabilities).

## Wallet Server side needed

wallet_policy_updates.queue: add receiving_address using d['index'] and d['address'], only when the target Agent supports Build 60. Keep the saved green destination and proposed height unchanged. Show the same receive/change comparison indexes in Wallet Server, independently derived from its saved descriptor pair. Test nonzero index 15, mismatches, boundary 999, and no change to reservation/reuse behaviour. Existing requests should be preserved; explain that their old review samples are not the reserved address.

## Wallet Server Build 84 implementation

New requests always contain receiving_address from the validated saved receiving destination (index and address), without making another reservation. They are withheld until the connection advertises Agent 2.0.0~dev60 or later; no old-Agent downgrade strips the field. Existing proposals are never rewritten, rehashed, or re-signed. Existing unindexed requests retain their original evidence and cancellation binding. A new refresh is required for an index-bound review of a cancelled old request.

The Address Book’s proposed destination includes comparison_samples: three independently derived Receiving and Change entries starting at that same index, bounded at 999. These are explicitly comparison samples, not a commitment to the actual change index of a future transaction. Index-zero disc-loading samples remain separately labelled.

Agent result policy_hash remains the descriptor-pair/timestamp transition hash. Receipt, result request_hash, and cancellation hashes bind the complete proposal including receiving_address. No new capability identifier or policy extension schema is introduced.
