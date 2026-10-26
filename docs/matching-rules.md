# Matching rules and state transitions

## Shared controls

1. Validate exact CSV schema, integer monetary fields, supported currency/type/status, date order, fee bounds, refund identity/limits, and `net = gross - fee`.
2. Deduplicate by the source event ID, not by transaction reference or amount. An identical repeat becomes a `DUPLICATE_IMPORT` audit record; a conflicting repeat stops the run.
3. Validate the full source before applying the reporting cutoff. Exclude ledger events after `as_of`, settlement portions with later settlement dates, and bank entries with later booking dates. Raw-feed duplicate audits can remain visible even for future events; monetary controls use cutoff-filtered unique rows.
4. Preserve signed integers. All supported currencies have two decimal places. No FX conversion, tolerance threshold, or amount-only fuzzy matching is used.

## Layer 1: ledger to processor

Group processor portions by exact transaction ID. Require matching provider, merchant, and currency. Aggregate distinct portions' gross, fee, and net. At least one included portion must carry `is_final=true` to confirm transaction completion.

Payments have positive gross. Expected payment fee is `floor((gross_minor × fee_bps + 5000) / 10000) + fixed_minor`, which rounds the basis-point component half up. Expected net is signed gross minus expected fee. Refunds have negative gross and zero new refund fee; the original payment fee is not returned. `FAILED` and `VOIDED` ledger events are ineligible for normal matching.

Primary status precedence is explicit:

| Condition | Status |
| --- | --- |
| No portions; ledger not captured | EXCLUDED |
| No portions; expected settlement date is after cutoff | NOT_DUE |
| No portions; due, but age is within grace | PENDING_SETTLEMENT |
| No portions; beyond grace | MISSING_SETTLEMENT |
| At least one portion has another currency | CURRENCY_MISMATCH |
| Provider or merchant differs | REFERENCE_MISMATCH |
| Portions exist for an ineligible transaction | UNEXPECTED_SETTLEMENT |
| No included portion confirms finality | PARTIAL_SETTLEMENT |
| Final signed gross differs | AMOUNT_MISMATCH |
| Final gross agrees but fee differs | FEE_MISMATCH |
| All amounts agree and completion is beyond due plus grace | MATCHED_LATE |
| All amounts agree in multiple portions | MATCHED_SPLIT |
| All amounts agree in one portion | MATCHED |

If amount and fee are both wrong, the primary status is `AMOUNT_MISMATCH`; separate gross/fee values remain in the result for review. `LATE_SETTLEMENT` is an independent low-severity event, including when a late record also has a monetary discrepancy. A financial match can therefore retain a timing exception.

An incompatible identity/currency produces null actual/variance values, rather than zero or an FX-converted result. The expected amount is flagged separately in the expected currency. Inspect the source feed for incompatible actual amounts. A processor transaction absent from the cutoff ledger becomes `ORPHAN_SETTLEMENT`; its money is not automatically applied elsewhere.

## Layer 2: processor batch to bank

A processor batch must contain exactly one provider and one currency; a mixed batch fails validation. Expected bank payout is the signed sum of its unique settlement portions, including portions with unresolved ledger problems. This deliberately measures bank delivery independently of ledger correctness.

Bank entries match on exact batch ID, provider, and currency. Multiple distinct entries can form a valid split credit or debit. Positive amounts represent bank credits; negative amounts represent bank debits. No bank entry is required for a zero-net batch (`MATCHED_ZERO_NET`).

| Condition | Status |
| --- | --- |
| No bank entry, zero expected net | MATCHED_ZERO_NET |
| No entry and not beyond payout due date plus grace | PENDING_BANK_CREDIT |
| No entry and beyond grace | MISSING_BANK_CREDIT |
| Entry currency differs | CURRENCY_MISMATCH |
| Entry provider differs | REFERENCE_MISMATCH |
| Sum of entries differs from expected | BANK_AMOUNT_MISMATCH |
| Sum agrees in multiple entries | MATCHED_SPLIT |
| Sum agrees in one entry | MATCHED |

An entry with no processor batch at the cutoff becomes `UNREFERENCED_BANK_ENTRY`. The generic “credit” status names also apply to an expected net debit, using signed amounts. The current model does not create a separate late-bank-payout status.

## Timing assumptions

Default generated settlement due date is transaction date plus two Monday–Friday business days. Batch payout due date is one business day after the latest included settlement portion. The reporting cutoff uses UTC calendar dates; there is no intraday or timezone conversion. Age counts business days strictly after due date through cutoff. Default grace is one business day. Public holidays and provider-specific cutoffs are not modeled.
