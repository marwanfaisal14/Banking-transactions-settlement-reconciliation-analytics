# Synthetic data provenance

Every identifier and amount is generated locally by [generate.py](../payments_analytics/generate.py), using Python's seeded random generator with seed `20261026`. No external financial dataset, scraped records, account credentials, bank feed, customer name, card number, or real account number is used.

The default generation writes 1,200 ledger records: 400 per currency across USD, AED, and EGP, with fictional merchant references `MERCHANT-01` through `MERCHANT-04` and provider `DEMO-SWITCH`. The transaction date range is 21 September through 26 October 2026.

## Files and grain

| File | Raw rows | Grain |
| --- | ---: | --- |
| transaction_ledger.csv | 1,200 | One internal payment or refund event |
| processor_settlements.csv | 1,087 | One settlement portion/import event; includes one identical repeated ID |
| bank_statement.csv | 82 | One signed bank entry/import event; includes one identical repeated ID |
| scenario_manifest.json | — | Human-readable scenario assignments and generation settings |

At the default cutoff, 112 unique future-dated settlement portions and nine unique future-dated bank entries are excluded. Future events are intentional: they test reporting-cutoff replay and prevent future cash from resolving an earlier exception.

The scenario manifest is **not read by the reconciliation engine**. Tests verify the pipeline works when it is removed.

## Deliberate scenarios

Each currency includes a missing settlement, partial settlement, final amount mismatch, fee mismatch, late match, successful split match, currency mismatch, settlement against a failed payment, pending settlement within grace, and a not-yet-due transaction. Other cases include orphan processor records, missing bank payouts, short bank payouts, split bank credits, unreferenced bank entries, and duplicate imports.

Captured refunds reference an existing captured payment of the same provider, merchant, and currency; their aggregate refunded amount cannot exceed the original gross amount. A refund does not return the original processing fee in this fictional contract.

The data is intentionally constructed to demonstrate control behavior. Exception frequencies, transaction sizes, refund proportions, and match rates are not estimates of a real institution or industry benchmark.

## Reproduction

Run `python -m payments_analytics generate` from the project root, then `python -m payments_analytics build`. The JSON report records SHA-256 hashes of the three exact input files. LF line endings are used for stable source hashes. The MIT license applies to this generated demo data.
