-- 1. Transaction match counts and rate, using the same eligible/due denominator as the dashboard
SELECT r.currency, COUNT(*) AS eligible_due,
       SUM(r.matched) AS matched_due,
       ROUND(100.0 * SUM(r.matched) / NULLIF(COUNT(*), 0), 2) AS match_rate_pct
FROM reconciliation_results r CROSS JOIN run_metadata m
WHERE r.eligible = 1 AND r.due_date <= m.as_of
GROUP BY r.currency ORDER BY r.currency;

-- 2. Ledger financial differences stay in minor units and within one currency
SELECT r.currency, SUM(r.expected_net_minor) AS expected_due_net_minor,
       SUM(CASE WHEN r.net_delta_minor IS NOT NULL THEN ABS(r.net_delta_minor) ELSE 0 END) AS absolute_variance_minor,
       SUM(CASE WHEN r.net_delta_minor IS NULL THEN 1 ELSE 0 END) AS incompatible_records
FROM reconciliation_results r CROSS JOIN run_metadata m
WHERE r.eligible = 1 AND r.due_date <= m.as_of
GROUP BY r.currency ORDER BY r.currency;

-- 3. Status distribution, including excluded and not-yet-due records
SELECT currency, status, COUNT(*) AS transaction_count
FROM reconciliation_results GROUP BY currency, status ORDER BY currency, transaction_count DESC, status;

-- 4. Fee exceptions: positive extra fee means the processor charged more than the contract
SELECT transaction_id, currency, expected_fee_minor, actual_fee_minor,
       actual_fee_minor - expected_fee_minor AS extra_fee_minor
FROM reconciliation_results WHERE status = 'FEE_MISMATCH' ORDER BY currency, transaction_id;

-- 5. Settlement aging: weekday-only age, not calendar days
WITH aged AS (
    SELECT currency, CASE WHEN age_business_days <= 1 THEN '0-1 business days'
                         WHEN age_business_days <= 5 THEN '2-5 business days'
                         ELSE '6+ business days' END AS age_bucket,
           net_delta_minor
    FROM reconciliation_results WHERE status IN ('MISSING_SETTLEMENT', 'PARTIAL_SETTLEMENT')
)
SELECT currency, age_bucket, COUNT(*) AS transaction_count,
       SUM(ABS(net_delta_minor)) AS absolute_variance_minor
FROM aged GROUP BY currency, age_bucket ORDER BY currency, age_bucket;

-- 6. Bank reconciliation by currency: a separate control layer
SELECT b.currency, COUNT(*) AS due_batches, SUM(b.matched) AS matched_batches,
       SUM(CASE WHEN b.net_delta_minor IS NOT NULL THEN ABS(b.net_delta_minor) ELSE 0 END) AS absolute_bank_variance_minor
FROM batch_reconciliation b CROSS JOIN run_metadata m
WHERE b.due_date <= m.as_of GROUP BY b.currency ORDER BY b.currency;

-- 7. Operational exception queue, excluding low-severity SLA-only events
SELECT layer, code, reference, currency, amount_minor, age_business_days, owner, action
FROM exceptions WHERE severity = 'HIGH' ORDER BY age_business_days DESC, layer, code, reference;

-- 8. Orphan records are unallocated, not automatically applied to another transaction
SELECT layer, code, reference, currency, amount_minor
FROM exceptions WHERE code IN ('ORPHAN_SETTLEMENT', 'UNREFERENCED_BANK_ENTRY')
ORDER BY layer, currency, reference;

-- 9. Duplicate import audit events: excluded from monetary totals
SELECT reference, currency, description FROM exceptions WHERE code = 'DUPLICATE_IMPORT' ORDER BY reference;

-- 10. Daily due expected net and cumulative running net by currency
WITH daily AS (
    SELECT due_date, currency, SUM(expected_net_minor) AS expected_net_minor
    FROM reconciliation_results WHERE eligible = 1 GROUP BY due_date, currency
)
SELECT due_date, currency, expected_net_minor,
       SUM(expected_net_minor) OVER (PARTITION BY currency ORDER BY due_date ROWS UNBOUNDED PRECEDING) AS cumulative_expected_net_minor
FROM daily ORDER BY currency, due_date;

-- 11. Merchant matching uses transaction counts, not an average of daily percentages
SELECT r.merchant_id, r.currency, COUNT(*) AS eligible_due, SUM(r.matched) AS matched_due,
       ROUND(100.0 * SUM(r.matched) / COUNT(*), 2) AS match_rate_pct
FROM reconciliation_results r CROSS JOIN run_metadata m
WHERE r.eligible = 1 AND r.due_date <= m.as_of
GROUP BY r.merchant_id, r.currency ORDER BY r.currency, match_rate_pct, r.merchant_id;

-- 12. Example control: distinct settlement portions reconcile back to processor batches
SELECT p.batch_id, p.currency, COUNT(*) AS settlement_portions, SUM(p.net_minor) AS processor_net_minor,
       b.expected_net_minor AS bank_expected_net_minor,
       SUM(p.net_minor) - b.expected_net_minor AS conservation_difference_minor
FROM processor_settlements p JOIN batch_reconciliation b ON p.batch_id = b.batch_id AND p.currency = b.currency
GROUP BY p.batch_id, p.currency, b.expected_net_minor ORDER BY p.currency, p.batch_id;
