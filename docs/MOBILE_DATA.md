# Mobile account reads — Server Build 2

After both device pairing/reconnection and OPAQUE account login, native `POST /mobile/v1/data` accepts exactly `{section:"balances"|"trace"|"cgt"}`. It uses saved data only and never obtains a market/FX quote or triggers a calculation, node RPC or upload. Device scope remains read-only plus encrypted relay; it grants no signing, spending or approval authority.

* `balances`: saved BTC and exact integer satoshis, names, ownership labels and selected wallet traits. No live AUD valuation, unrealised gain, quote, FX rate or converted total is returned. No tax evidence/document paths are exposed as balance labels. Labels use the latest saved Wallet Server display name.
* `trace`: saved transaction/cost-provenance graph, explicitly labelled historical tracing data. Historical AUD tax evidence can appear here; it is not a current wallet valuation.
* `cgt`: this logged-in user's saved CGT report, including historical AUD proceeds/cost/gains; live balance/quote sections are stripped recursively, including annual reports. Another user's CGT report cannot be requested by changing a user ID.

The Mobile app obtains its own current BTC/AUD prices. Server data is labelled untrusted: amounts and ownership are server claims until independently checked against Agents/Bitcoin. Relay ciphertext is distinct from these readable Server data replies. No exchange-price lookup is added on the Server. Future document-price endpoints must explicitly identify the original source record and distinguish direct document amounts from market valuations; no generic dump of live-valued internal structures is authorised by this API.
