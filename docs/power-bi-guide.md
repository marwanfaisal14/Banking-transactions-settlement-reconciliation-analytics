# Power BI integration guide

The working web dashboard is a dependency-free static report. A [PBIP source project](../powerbi/README.md) now provides a native Power BI report definition, six-table model, 21 DAX measures, and embedded CSV data. Its Desktop behavior and DAX execution are unverified and no PBIX binary is included. Open the project on Windows, refresh and validate it, then save a PBIX. The manual-import route below is an alternative and preserves the same financial definitions.

## Import

After a successful build, import these CSV files from `docs/data` or `outputs`:

- `transaction_reconciliation.csv`: one row per cutoff ledger transaction.
- `batch_reconciliation.csv`: one row per cutoff processor batch.
- `exceptions.csv`: one row per issue event.
- `run_metadata.csv`: one row with reporting cutoff and grace, present alongside the browser-ready exports.

Set `_minor` monetary columns to **Whole Number**, date fields to **Date**, and currency/reference/status fields to **Text**. Parse boolean fields consistently (Python CSV uses True/False), and retain null actual/difference values for incompatible references. Do not replace those nulls with zero. Divide monetary measures by 100 only for presentation.

## Model

Create a shared currency dimension with USD, AED, and EGP and single-direction one-to-many relationships to each fact table. Require a single currency selection for monetary visuals. A date dimension can relate to settlement due date for transaction views and payout due date for bank views; label each date role precisely.

Do not directly join transactions, processor portions, bank entries, and exceptions then sum their amounts. Their grains differ and can multiply records. Use the pre-aggregated facts and separate control pages. Exception references are polymorphic and should not be assumed to be universal transaction IDs.

## Suggested pages

1. **Settlement overview:** eligible due transaction count, matched count/rate, expected due net, comparable ledger absolute variance, and incompatible expected amounts.
2. **Bank payout control:** due batches, matched batches, comparable bank absolute variance, and pending/missing payouts.
3. **Exception operations:** issue code, layer, owner, age, priority, source reference, and action.

Implement the definitions in [metrics.md](metrics.md), including the reporting cutoff, captured eligibility, matched-family status handling, and absolute differences. Keep the two monetary control layers separate. Do not sum the issue-specific exception amount column as a financial exposure KPI.

## Validate before sharing

Reconcile each currency's card values against `findings.md` and the generated JSON snapshot. Confirm that the default USD rate is 315/321 = 98.13%, ledger absolute variance is 2,615.52, and bank absolute variance is 13,047.26. Confirm that USD incompatible expected net of 583.12 remains separately visible. Check the same controls for AED and EGP and test single-currency selection, null handling, and the effect of filters on the denominator.

Only describe a Power BI report as implemented after its model, measures, filtering, and refresh have actually been built and validated on Windows.
