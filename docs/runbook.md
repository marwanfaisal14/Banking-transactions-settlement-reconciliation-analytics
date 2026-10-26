# Operations and reproduction runbook

## Daily demonstration workflow

1. Preserve the three input feeds in `data/raw` and record the intended cutoff.
2. Run `python -m payments_analytics build --as-of 2026-10-26` from the project root.
3. Require a successful exit. The run stops on malformed schema, bad monetary values, broken refund relationships, invalid processor net, conflicting import IDs, or mixed-currency/provider processor batches.
4. Inspect the generated source hashes and future-row exclusions in `docs/data/report.json`.
5. Review eligible-due match rates by currency and each control layer independently.
6. Investigate the exception queue by priority, age, source reference, and owner. Pending within-grace items remain in the transactions/batches view without a high-severity missing event.
7. Keep unmatched cash and orphan settlement items unallocated. Never close them by matching an amount alone.
8. Run the tests after any rule change and rebuild the generated findings and dashboard artifacts.

The demonstration does not persist a case's resolution state or change accounting balances. Export the filtered queue for investigation; evidence that a discrepancy was resolved must come from corrected source data and a new build.

## Commands

```bash
python -m payments_analytics generate
python -m payments_analytics build
python -m unittest discover -v
python -m http.server 8000 --directory docs
```

To avoid overwriting the committed snapshot while replaying another cutoff:

```bash
python -m payments_analytics build --as-of 2026-10-20 \
  --output outputs/replay-2026-10-20 \
  --dashboard-json outputs/replay-2026-10-20/report.json \
  --findings outputs/replay-2026-10-20/findings.md
```

The report JSON's adjacent directory also receives the three reconciliation CSVs and run metadata. A changed cutoff can create apparently orphaned bank/processor references when their matching source event is not yet visible; the label means unmatched **at that cutoff**.

## Failure handling

| Failure | Action |
| --- | --- |
| Unexpected CSV schema or decimal monetary strings | Correct the upstream feed contract; monetary fields are integer minor units |
| Conflicting duplicate ID | Quarantine and resolve the conflicting source deliveries; do not choose one arbitrarily |
| Broken refund reference or excessive refund | Check original payment identity, date, and captured amount |
| Mixed processor batch currency/provider | Correct batch partitioning before financial aggregation |
| Dashboard data-load error | Serve `docs` over HTTP and check that `data/report.json` is present and valid |
| A rate changes after cutoff replay | Compare new eligibility, event visibility, and future exclusions before interpreting the change |

## CI and publication

`.github/workflows/ci.yml` configures Python engine/SQL validation on 3.11 and 3.12 and a separate Playwright browser job. It also regenerates the default data and verifies that committed input/snapshot/findings files reproduce. The configured workflow does not prove a remote CI run has completed; inspect the repository's Actions results after publication.

GitHub Pages serves the static dashboard from `main:/docs` when enabled in repository settings. The Python HTTP server is an alternative for local review; no financial service or backend is required.

## Production extensions outside this version

Provider-specific schemas and authentication, agreed banking holidays/cutoffs, timezone conversion, rolling reserves, FX settlement, chargebacks, settlement adjustments, bank-payout lateness classification, account-level controls, access control, persistent case management, incremental runs, and atomic publication of a complete multi-file artifact set are not implemented. The current run stages SQLite/CSV results before replacing outputs, but does not coordinate simultaneous runs.
