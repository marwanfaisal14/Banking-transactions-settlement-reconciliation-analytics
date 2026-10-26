# Power BI source project — open this first

**Download the report: [BankingReconciliation.pbix](https://raw.githubusercontent.com/marwanfaisal14/Banking-transactions-settlement-reconciliation-analytics/main/powerbi/BankingReconciliation.pbix).** The file contains an embedded model and three report pages with 32 visual containers. Its archive integrity, size, and SHA-256 hash are recorded in [validation evidence](https://github.com/marwanfaisal14/Banking-transactions-settlement-reconciliation-analytics/blob/main/docs/pbix-validation.json).

The PBIP source and ZIP are available separately. The source ZIP contains the editable project and embedded snapshot; download the PBIX separately to open the report directly.

## Open the PBIX directly

Download `BankingReconciliation.pbix` using GitHub’s download button and open it in a current Windows Power BI Desktop installation. Compare the selected-currency values with the acceptance table below. Keep the source ZIP only if you also want to edit the PBIP/PBIR project files.

## Open or rebuild from the PBIP source on Windows

1. Download [BankingReconciliation-PowerBI.zip](BankingReconciliation-PowerBI.zip) using GitHub's download button. **Extract the ZIP first.**
2. Install or update [Power BI Desktop](https://powerbi.microsoft.com/desktop/) on Windows.
3. Open `BankingReconciliation.pbip` from the extracted folder. Keep the `.Report` and `.SemanticModel` folders beside it.
4. If your Desktop version exposes Power BI project/PBIR support as a preview option, enable the relevant option under **File → Options and settings → Options → Preview features** and restart. Use a current Desktop release.
5. Click **Refresh** to import the embedded snapshot and evaluate the measures. No bank credentials, web data source, or local CSV path is required.
6. Confirm the three pages render and compare the figures below. If Desktop reports a source/measure/format error, preserve the exact error for correction rather than treating the source as a verified report.
7. Choose **File → Save As → Power BI file (*.pbix)** and save as `BankingReconciliation.pbix`. If a file-type selector is shown, explicitly select PBIX; do not rename the `.pbip` extension.
8. Upload that actual Desktop-saved `.pbix` into this folder on GitHub. The source package itself does not perform this serialization.

## Report design

| Page | Defined visuals |
| --- | --- |
| 01 · Overview | Currency slicer, four KPI cards, due-date settlement chart, merchant open-case chart, ledger detail, and definitions footer |
| 02 · Settlement & Bank | Currency slicer, four bank KPI cards, expected/booked payout chart, batch status chart, and bank batch detail |
| 03 · Exceptions | Currency slicer, four operational KPI cards, issue/team/priority slicers, owner chart, and investigation queue with actions |

The source uses a navy/teal palette, 1440×900 pages, native Power BI visuals, and synced single-select currency slicers initialized to USD. Summary card interactions are disabled for charts/tables and issue slicers so the cards retain their selected-currency context.

## Model and data

Six tables: `Currency`, `Ledger`, `BankBatches`, `Exceptions`, `RunMetadata`, and `Metrics`. Currency has one-to-many, single-direction relationships to the three fact tables. The three facts are not joined directly. Twenty-one DAX measures define count-based match rates, due net, separate absolute variances, and exception counts. Monetary measures require a single currency and remain blank when multiple currencies are in context.

All four source CSVs are embedded as Base64 payloads in Power Query expressions. They preserve integer minor-unit calculations, boolean flags, null incompatible amounts, and date fields. Additional fixed-decimal columns divide amounts by 100 for table display and use `summarizeBy: none`; exception reported amounts are never exposed as a sum measure.

The snapshot is fixed at **26 October 2026**. It is not a live connection. To update it after a Python build, run `python scripts/build_powerbi.py` from the project root and reopen/refresh the project in Desktop.

## Financial and visual acceptance checks

| Currency | Due transactions | Matched | Ledger match rate | Expected due net | Ledger absolute variance | Bank absolute variance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| USD | 321 | 315 | 98.13% | 329,773.67 | 2,615.52 | 13,047.26 |
| AED | 328 | 322 | 98.17% | 352,642.09 | 4,399.01 | 9,910.90 |
| EGP | 322 | 316 | 98.14% | 351,260.44 | 3,530.63 | 14,677.98 |

Also verify the three incompatible ledger references (one per currency), valid split settlements/payouts, negative refunds, null actuals on currency mismatches, and zero-denominator behavior. Check chart/table sorting, slicer synchronization, and interactions visually. The ledger and bank variance columns must never be added together.

## Validation scope

Automated checks cover archive integrity, project paths, visual field references, relationships, embedded CSV hashes/counts, source-package contents, and PBIP/PBIR JSON against Microsoft's versioned published schemas. The Python/SQL engine has financial control tests.

Desktop refresh, Power Query/DAX evaluation, native visual appearance, and selected-currency KPI reconciliation are separate acceptance checks. Use the reference values above when reviewing the report. The web dashboard screenshot in the repository illustrates the web interface.

Schema reference: [Microsoft JSON schemas](https://github.com/microsoft/json-schemas). The validator uses the official raw GitHub mirror with TLS verification and retains the original schema IDs.
