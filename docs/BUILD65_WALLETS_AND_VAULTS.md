# Build 65 — wallet history, vault verification and transaction previews

## Wallets and Vaults

Hover retains graphical wallet/policy details. Clicking a wallet opens a Bitcoin-only ledger, locks the other cards and filters, and restores their previous controls when dismissed. Exchange cards do nothing on click. Rows use confirmed block UTC timestamps and exclude transactions below six confirmations. The balance is the total across the wallet's public outputs, reconstructed in block/ancestry order before reversing the display. Multiple receipts in one transaction are grouped; receive addresses are individually linked when needed. Sends show the wallet decrease including the fee. A self-transfer changes the whole-wallet balance only by its fee and is identified in the detailed tooltip.

History uses the saved descriptor blockchain snapshot and existing Core history. It does not consult cost provenance, tax calculations or exchange statements. Core `listsinceblock` includes change because the scanner needs it for exact balances; public parent descriptors distinguish those change outputs from intended recipients. Unknown history/fees/flags are never fabricated as zero/false. Existing explorer queries can enrich missing flags on hover. Links open the Wallet Server's Mempool page.

Vault bottom text is its confirmed balance in pipe notation, except verified mixed protected/unprotected funds show “Mixed - Needs Attention” and red. Both ordinary outputs outside the vault and funds under an expired policy alongside a still-active policy count toward mixed protection. Unfunded vaults remain visible: amber before expiry, red after expiry. Stale/unavailable verification shows a rotating amber refresh card, with no overdue banner; on success the icon fades out for 500 ms and current content fades in for 500 ms.

## Transaction Builder

Only a funded vault can have two related cards. Its second card reserves a new receiving address and cannot be a sender. Regular/unfunded wallets have one card. Removing a base card normalises a remaining untouched receiving card only when neither related card had a line; connected addresses are retained. HTTP validation also limits related cards and checks the funded-vault evidence.

Amounts and fees have browser autocomplete disabled. Maximum, Bitcoin and AUD edits preview the balances and fee before Apply. Oversized inputs are resolved against all confirmed spendable inputs, other payments and the conservative fee; the resolved maximum is visible in both fields and cards. AUD stays blank unless used. Apply keeps the preview; an outside click, Escape or × restores the complete prior set of edge amounts, rates and maximum flags. Preview data is not saved as a committed draft. Final preparation and signing retain their independent checks.

## Agent contract audit

Minimum Agent is V2 Build 56. Registration requires the version header and RPC capability object. The old presence-only registration path, pre-permission Agent bypass, pre-56 version gating, retired `wallet_retirement`/`wallet_retirement_v2` capabilities and the old v2 retirement profile decoder are removed. Obsolete messages remain rejected; they are never translated into current signing or deletion authority.

Current `/agent/v1` transport, `/agent/v2/exchange`, public vault records, unsigned fixed vault proposals, phased retirement, queue revisions, archive request versions and Bitcoin legacy script handling remain because Agent 56 still uses them or they describe current wallet policies. These are not compatibility fallbacks for old Agent releases. Existing live wallet setups and PSBTs are not rewritten by this update. No Agent source or live wallet/profile is modified during development/testing.

## Bitaroo statements

Freshness warnings apply to all declared family personal and SMSF accounts, regardless of the logged-in viewer. They become yellow at seven days and red at ten days. The red warning replaces yellow. Opening Wallets, Vaults or Notifications marks them read. They cannot be dismissed; supplying fresh matching BTC/AUD coverage removes the account's warning. Non-Bitaroo accounts are excluded.

The browser sends each selected package as one batch. PDF headers determine the asset and financial year, never filenames. The server validates every member in a temporary directory before replacing the session input folder. A rejected batch is discarded, retains the previous inputs/report, and is removed from the browser selection. Current-year statements must contain matching BTC and AUD date ranges in that batch, even when a stale counterpart is already saved. Historical and current years can be supplied together; an individual complete historical statement can fill a missing asset. Identical re-uploads are idempotent, including PDFs re-exported with different metadata but identical public text. Conflicting statements for an identical period are rejected rather than silently choosing between different financial records.

Saved history remains when a fresh pair is supplied. Effective processing selects one newest matched pair per financial year and replaces overlapping prior rows rather than appending them. Genuine repeated trades inside a statement remain intact. A historical year still requires both assets before financial processing can use it. The rollover exception applies only on local 1 July: a matched pair ending on the previous day's 30 June is accepted as current coverage. No wider July grace period is introduced. Upload validation and warning changes require no Agent update.
