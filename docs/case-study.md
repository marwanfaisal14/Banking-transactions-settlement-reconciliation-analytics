# Case study: reconciling a payment all the way to the bank

## Decision context

A payments operations reviewer needs to distinguish three different facts: the ledger recorded a payment, the processor settled it, and the bank booked the batch payout. Treating these as interchangeable can hide incomplete settlement or double-count a difference as a loss.

This case builds an explainable reconciliation workflow on fictional data so its behavior can be inspected without access to a financial institution.

## Approach

1. Define grains before matching: one ledger event, one processor settlement portion, and one bank entry.
2. Represent monetary calculations in integer minor units with an explicit payment-fee contract and refund-sign policy.
3. Apply source validation, deterministic duplicate controls, and an explicit reporting cutoff.
4. Compare ledger references to aggregated processor portions, including identity, currency, finality, gross, and fees.
5. Independently compare processor batch totals with referenced bank entries.
6. Translate exceptions into owners, aging, and follow-up actions.
7. Export the same facts to SQL, CSV, JSON, and an interactive dashboard; validate through independent totals and boundary cases.

## Demonstration evidence

At the default 26 October 2026 cutoff, the USD ledger has 321 eligible due events, with 315 financially matched (98.13%). Of the six open due events, one is pending within grace, four have comparable financial differences, and one has an incompatible currency. A matched late transaction remains in the match numerator while generating a separate timing event.

USD expected due net is 329,773.67. Comparable due ledger absolute variance is 2,615.52, including the pending item. A separate incompatible expected USD amount of 583.12 is not silently folded into that variance. The bank control has absolute variance of 13,047.26 across due USD batches, with 21 of 23 batches matched. These layers measure different relationships and are not combined into a single loss number.

All cases were deliberately generated. The match rates and amounts are evidence of implemented control behavior, not a result achieved for a bank or an industry benchmark.

## Design tradeoffs

Exact references make the engine explainable and reduce false amount-based matches, but leave unreferenced items for manual investigation. Strict currency isolation preserves meaning but does not resolve FX-settled transactions. A weekday-only calendar and fixed fee rules keep the demonstration reproducible but must be replaced by real provider contracts and operational calendars before operational use.

An exception uses one primary financial status plus an independent late event. This keeps the queue understandable while retaining the evidence needed to inspect multiple discrepancies.

## Recommendations to evaluate

- Settlement Operations should trace overdue or incomplete processor settlement portions before escalating the issue as missing bank funds.
- Treasury Operations should trace batch payouts against bank booking references and retain unallocated cash separately.
- Fee exceptions should be checked against the applicable agreement; no automatic recovery is assumed.
- Data Operations should investigate conflicting IDs immediately and distinguish duplicate deliveries from legitimate split records.
- A business reviewer should use per-currency, per-layer controls alongside match counts, rather than relying on one headline rate.

## Validation and boundaries

The engine tests cover normal matches, split settlements and bank entries, refunds and over-refund rejection, fees, partial completion, lateness, missing/orphan records, source duplication, identity/currency mismatches, cutoff replay, empty denominators, and source validation. Pipeline tests reconcile processor-to-batch sums and rebuild outputs identically. Browser checks exercise the actual dashboard interactions and CSV contents.

No production data, client engagement, recovered funds, live integration, bank-account access, or measured operating improvement is claimed.
