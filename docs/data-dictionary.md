# Data dictionary and lineage

## Source grains

Identifiers are fictional strings. Dates are ISO `YYYY-MM-DD`, interpreted as UTC dates. Every supported currency has two decimal places. Monetary fields ending in `_minor` are signed integers, not decimal strings.

### Transaction ledger: one internal payment/refund event

| Field | Meaning |
| --- | --- |
| transaction_id | Unique source event ID and reconciliation reference |
| merchant_id | Fictional merchant reference |
| provider | Fictional payment-provider identity |
| currency | USD, AED, or EGP |
| transaction_type | PAYMENT or REFUND |
| original_transaction_id | Captured payment reference for refunds; empty for payments |
| transaction_date | Event date; later events are excluded at cutoff |
| gross_minor | Positive for a payment, negative for a refund |
| fee_bps | Contract payment fee in basis points: 145 for CARD, 25 for BANK_TRANSFER in the default demo |
| fee_fixed_minor | Fixed payment fee: 30 or 15 respectively in the default demo |
| status | CAPTURED, FAILED, or VOIDED |
| expected_settlement_date | Contractual due date supplied by the ledger; default generator uses T+2 business days |
| channel | CARD or BANK_TRANSFER |

Refund fee fields retain the transaction's schedule metadata, but `expected_fee()` deliberately returns zero for a refund. They do not imply a new refund fee or reimbursement of the original payment fee.

### Processor settlements: one portion/import event

| Field | Meaning |
| --- | --- |
| settlement_row_id | Import event ID; identical repeats are deduplicated |
| batch_id | Payout-batch reference; all its portions must have one provider and currency |
| transaction_id | Exact ledger reference, potentially orphaned |
| merchant_id, provider, currency | Identity fields required for ledger matching |
| gross_minor | Signed settled gross for this portion |
| fee_minor | Nonnegative processor fee for this portion |
| net_minor | Must equal gross_minor minus fee_minor |
| settled_date | Event date used for cutoff and completion timing |
| is_final | Literal true/false; at least one included portion must confirm transaction completion |

One transaction can have multiple legitimate portions and potentially multiple batches. Duplicate detection uses the portion ID; it does not collapse all records with the same transaction ID.

### Bank statement: one signed bank entry/import event

| Field | Meaning |
| --- | --- |
| bank_entry_id | Unique import event ID; identical repeats are deduplicated |
| payout_reference | Supporting advice reference; not a fuzzy-match key |
| batch_id | Exact processor batch reference |
| provider, currency | Required batch identity |
| booking_date | Date used for cutoff |
| amount_minor | Positive credit or negative debit |

The statement contains no bank account numbers. Entries with an unknown batch remain unallocated. Multiple distinct entries can settle a single batch.

## Output tables

`reconciliation_results` has one row per unique cutoff ledger event, including excluded and future-due items. It includes expected/actual gross, fee and net, signed net difference, currency, merchant, provider, channel, contractual due date, latest included settlement date, number of portions, primary status, matched boolean, late boolean, and business-day age. Incompatible actual/variance fields are SQL NULL / JSON null / empty CSV cells.

`batch_reconciliation` has one row per unique processor batch represented at cutoff. It includes single currency/provider, derived payout due date, expected/actual payout, signed difference, source portion/entry counts, primary status, matched boolean, and business-day age.

`exceptions` has one row per issue event: `issue_id`, `layer`, `code`, `reference`, `currency`, issue-specific `amount_minor`, due date when known, business-day age, severity, owner, action, and description. An issue may refer to a transaction, a source portion, a batch, or a bank entry; it is not a universal transaction fact table.

`run_metadata` records the reporting cutoff and grace. The JSON report additionally records raw input counts, future-row exclusions, source SHA-256 hashes, engine version, and number of SQL analyses executed.

## Lineage and relationships

Transaction ledger `transaction_id` has a one-to-many reference to processor portions. Processor `batch_id` groups many portions and relates to many bank entries. Do not join raw portions and bank entries directly and then sum both sides: that can multiply amounts in a many-to-many fan-out. The engine aggregates each side before comparing, and query 12 joins to the one-row-per-batch result.
