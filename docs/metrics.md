# KPI definitions

All metrics are calculated per currency. Monetary values are stored as signed integer minor units and divided by 100 for display. No total combines USD, AED, and EGP.

| Metric | Definition | Interpretation |
| --- | --- | --- |
| Eligible due transactions | Captured ledger payment/refund events with contractual settlement due date on/before cutoff | Transaction count, not settlement-portion count or bank-entry count |
| Matched due transactions | Eligible due events with MATCHED, MATCHED_SPLIT, or MATCHED_LATE | Late-but-financially-matched events remain in the numerator |
| Ledger match rate | 100 × matched due / eligible due | Count-based; not value-weighted. Empty denominator returns N/A |
| Expected due net | Sum of signed expected net for eligible due events | Includes negative refunds and separately flagged incompatible references |
| Ledger absolute variance | Sum of absolute expected-minus-actual net for comparable eligible due events | Includes pending due items within grace; excludes NOT_DUE and incompatible identities/currencies |
| Incompatible expected amount | Signed expected net for eligible due events whose source currency/provider/merchant cannot be compared | Reported separately, never silently added to comparable variance |
| Due bank batches | Processor batches with derived payout due date on/before cutoff | Independent of whether underlying ledger transactions matched |
| Matched due bank batches | Due bank batches with a MATCHED-family status | Includes valid split credits/debits and zero-net batches |
| Bank absolute variance | Sum of absolute expected-minus-actual payout for comparable due batches | Includes pending due batches; excludes future-due and incompatible batches |
| Exception records | Number of issue events in the selected currency | Not unique affected transactions; one transaction can have financial and SLA events |
| High-priority records | Exception events marked HIGH | Operational queue count, not total monetary exposure |

## Avoid double counting

Ledger variance asks whether the processor settled the ledger as expected. Bank variance asks whether processor batch net reached the bank. They can refer to the same underlying flow, so **do not add these control layers** into a single “loss” amount.

Orphan settlements, unreferenced cash, unexpected settlements on failed records, raw import duplicate audits, and incompatible currency/identity records are exposed separately from the comparable eligible-due ledger variance. Their existence means a high match rate alone does not demonstrate that every control has passed.

The exception queue's `amount_minor` is issue-dependent: expected-minus-actual for comparable monetary differences, expected amount in the expected currency for incompatible references, unallocated source amount for orphans, and zero for duplicate/SLA-only audit events. **Do not sum this field as financial exposure.**

## Reconciliation examples

- Payment gross 10,000 minor units, fee 1.45% plus 30: expected fee 175 and expected net 9,825.
- Refund gross -5,000 with zero new fee: expected net -5,000. The original payment fee remains retained.
- Processor settles that payment in portions net 4,920 and 4,905: aggregate 9,825, one matched transaction.
- Bank receives two entries of 5,000 and 4,825 for its batch: one matched split payout, not two batches.
- Processor reports AED against a USD ledger transaction: actual/variance is null for that ledger comparison; no rate or conversion is invented.

## Evidence and reproducibility

The generated findings and dashboard JSON use the same engine output. SQL query 1 independently recomputes the count match rate from exported SQLite facts; query 12 checks processor-batch conservation. Tests reconcile per-currency processor totals to expected bank-batch totals and verify deterministic rebuilds.
