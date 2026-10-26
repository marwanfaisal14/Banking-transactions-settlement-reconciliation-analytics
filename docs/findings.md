# Generated reconciliation findings

Reporting cutoff: **2026-10-26**. Every record and result is synthetic.

| Currency | Due eligible transactions | Matched | Count match rate | Expected due net | Ledger absolute variance | Bank absolute variance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| USD | 321 | 315 | 98.13% | 329,773.67 | 2,615.52 | 13,047.26 |
| AED | 328 | 322 | 98.17% | 352,642.09 | 4,399.01 | 9,910.90 |
| EGP | 322 | 316 | 98.14% | 351,260.44 | 3,530.63 | 14,677.98 |

The two variance columns represent different reconciliation layers and must not be added together. They include pending items already due, and exclude incompatible identities/currencies, which are separately flagged. Not-yet-due items are excluded. See [metric definitions](metrics.md).

## Exception records by code

| Code | Records |
| --- | ---: |
| AMOUNT_MISMATCH | 3 |
| BANK_AMOUNT_MISMATCH | 3 |
| CURRENCY_MISMATCH | 3 |
| DUPLICATE_IMPORT | 2 |
| FEE_MISMATCH | 3 |
| LATE_SETTLEMENT | 3 |
| MISSING_BANK_CREDIT | 3 |
| MISSING_SETTLEMENT | 3 |
| ORPHAN_SETTLEMENT | 3 |
| PARTIAL_SETTLEMENT | 3 |
| UNEXPECTED_SETTLEMENT | 3 |
| UNREFERENCED_BANK_ENTRY | 3 |

Exception counts are event records, not unique transactions. A late mismatched transaction can produce more than one record. No business recovery, revenue increase, or production result is claimed.

## Control interpretation

- Trace overdue ledger items to the processor before treating them as missing bank cash.
- Trace unmatched bank batches against payout advice; do not net them with ledger differences.
- Review fee mismatches against the explicit synthetic fee contract.
- Investigate currency/identity mismatches manually; automatic FX conversion and fuzzy matching are disabled.
- Preserve duplicate-delivery audit records while removing identical import copies from monetary totals.

All 12 SQL analyses executed during this build. Source SHA-256 hashes and excluded future-row counts are in the dashboard data JSON.
