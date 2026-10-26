"""Export auditable JSON, CSV, and SQLite artifacts from the same reconciliation."""
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile

from .common import BANK_FIELDS, SETTLEMENT_FIELDS, TX_FIELDS, ROOT, write_csv
from .engine import load_inputs, reconcile

TX_RESULT_FIELDS = ('transaction_id', 'merchant_id', 'provider', 'currency', 'transaction_type',
    'channel', 'transaction_date', 'due_date', 'eligible', 'expected_gross_minor', 'expected_fee_minor',
    'expected_net_minor', 'actual_gross_minor', 'actual_fee_minor', 'actual_net_minor', 'net_delta_minor',
    'actual_currencies', 'settlement_rows', 'last_settled_date', 'age_business_days', 'status', 'matched', 'late')
BATCH_RESULT_FIELDS = ('batch_id', 'currency', 'provider', 'due_date', 'expected_net_minor',
    'actual_net_minor', 'net_delta_minor', 'bank_entries', 'age_business_days', 'status', 'matched', 'settlement_rows')
ISSUE_FIELDS = ('issue_id', 'layer', 'code', 'reference', 'currency', 'amount_minor', 'due_date',
    'age_business_days', 'severity', 'owner', 'action', 'description')
INTEGER_FIELDS = {'gross_minor', 'fee_bps', 'fee_fixed_minor', 'fee_minor', 'net_minor', 'amount_minor',
    'eligible', 'expected_gross_minor', 'expected_fee_minor', 'expected_net_minor', 'actual_gross_minor',
    'actual_fee_minor', 'actual_net_minor', 'net_delta_minor', 'settlement_rows', 'age_business_days',
    'matched', 'late', 'bank_entries', 'grace_business_days'}


def table(db, name, fields, rows):
    columns = ','.join(f'"{key}" ' + ('INTEGER' if key in INTEGER_FIELDS else 'TEXT') for key in fields)
    db.execute(f'CREATE TABLE "{name}" ({columns})')
    db.executemany(f'INSERT INTO "{name}" VALUES (' + ','.join('?' for _ in fields) + ')',
                   [tuple(row[key] for key in fields) for row in rows])


def build(data, output, dashboard_json, findings, as_of, grace_days=1):
    report, transactions, settlements, bank = reconcile(*load_inputs(data), as_of, grace_days)
    report['source_sha256'] = {name: hashlib.sha256((data / name).read_bytes()).hexdigest()
                              for name in ('transaction_ledger.csv', 'processor_settlements.csv', 'bank_statement.csv')}
    report['engine_version'] = '1.0.0'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as stage_name:
        stage = Path(stage_name)
        db = sqlite3.connect(stage / 'reconciliation.sqlite')
        try:
            table(db, 'transaction_ledger', TX_FIELDS, transactions)
            table(db, 'processor_settlements', SETTLEMENT_FIELDS, settlements)
            table(db, 'bank_statement', BANK_FIELDS, bank)
            table(db, 'reconciliation_results', TX_RESULT_FIELDS, report['transactions'])
            table(db, 'batch_reconciliation', BATCH_RESULT_FIELDS, report['batches'])
            table(db, 'exceptions', ISSUE_FIELDS, report['exceptions'])
            table(db, 'run_metadata', ('as_of', 'grace_business_days'), [dict(as_of=report['as_of'], grace_business_days=grace_days)])
            db.execute('CREATE INDEX settlement_transaction_idx ON processor_settlements(transaction_id)')
            db.execute('CREATE INDEX bank_batch_idx ON bank_statement(batch_id)')
            db.commit()
            if db.execute('PRAGMA integrity_check').fetchone() != ('ok',):
                raise ValueError('Generated database failed integrity validation')
            statement, query_count = '', 0
            for line in (ROOT / 'sql' / 'analysis.sql').read_text().splitlines(keepends=True):
                statement += line
                if sqlite3.complete_statement(statement):
                    cursor = db.execute(statement)
                    if cursor.description is None:
                        raise ValueError('Analysis SQL must produce a result set')
                    query_count += 1
                    with (stage / f'analysis-{query_count:02d}.csv').open('w', newline='') as handle:
                        writer = csv.writer(handle)
                        writer.writerow([col[0] for col in cursor.description])
                        writer.writerows(cursor.fetchall())
                    statement = ''
            if any(line.strip() and not line.lstrip().startswith('--') for line in statement.splitlines()):
                raise ValueError('Incomplete analysis SQL statement')
            if query_count != 12:
                raise ValueError(f'Expected 12 SQL analyses, got {query_count}')
            report['sql_queries_executed'] = query_count
        finally:
            db.close()
        for name, fields, rows in (
            ('transaction_reconciliation.csv', TX_RESULT_FIELDS, report['transactions']),
            ('batch_reconciliation.csv', BATCH_RESULT_FIELDS, report['batches']),
            ('exceptions.csv', ISSUE_FIELDS, report['exceptions']),
        ):
            write_csv(stage / name, fields, rows)
        for file in stage.iterdir():
            file.replace(output / file.name)
    dashboard_json.parent.mkdir(parents=True, exist_ok=True)
    dashboard_json.write_text(json.dumps(report, separators=(',', ':'), sort_keys=True) + '\n')
    for name, fields, rows in (
        ('transaction_reconciliation.csv', TX_RESULT_FIELDS, report['transactions']),
        ('batch_reconciliation.csv', BATCH_RESULT_FIELDS, report['batches']),
        ('exceptions.csv', ISSUE_FIELDS, report['exceptions']),
    ):
        write_csv(dashboard_json.parent / name, fields, rows)
    write_csv(dashboard_json.parent / 'run_metadata.csv', ('as_of', 'grace_business_days'),
              [dict(as_of=report['as_of'], grace_business_days=grace_days)])
    findings.parent.mkdir(parents=True, exist_ok=True)
    findings.write_text(render_findings(report))
    return report


def render_findings(report):
    lines = ['# Generated reconciliation findings', '',
             f"Reporting cutoff: **{report['as_of']}**. Every record and result is synthetic.", '',
             '| Currency | Due eligible transactions | Matched | Count match rate | Expected due net | Ledger absolute variance | Bank absolute variance |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for currency, metric in report['metrics'].items():
        money = lambda key: f"{metric[key] / 100:,.2f}"
        rate = 'N/A' if metric['match_rate_pct'] is None else f"{metric['match_rate_pct']:.2f}%"
        lines.append(f"| {currency} | {metric['eligible_due']} | {metric['matched_due']} | {rate} | {money('expected_due_net_minor')} | {money('ledger_abs_variance_minor')} | {money('bank_abs_variance_minor')} |")
    lines += ['', 'The two variance columns represent different reconciliation layers and must not be added together. They include pending items already due, and exclude incompatible identities/currencies, which are separately flagged. Not-yet-due items are excluded. See [metric definitions](metrics.md).', '',
              '## Exception records by code', '', '| Code | Records |', '| --- | ---: |']
    from collections import Counter
    for code, count in sorted(Counter(row['code'] for row in report['exceptions']).items()):
        lines.append(f'| {code} | {count} |')
    lines += ['', 'Exception counts are event records, not unique transactions. A late mismatched transaction can produce more than one record. No business recovery, revenue increase, or production result is claimed.', '',
              '## Control interpretation', '',
              '- Trace overdue ledger items to the processor before treating them as missing bank cash.',
              '- Trace unmatched bank batches against payout advice; do not net them with ledger differences.',
              '- Review fee mismatches against the explicit synthetic fee contract.',
              '- Investigate currency/identity mismatches manually; automatic FX conversion and fuzzy matching are disabled.',
              '- Preserve duplicate-delivery audit records while removing identical import copies from monetary totals.', '',
              f"All {report['sql_queries_executed']} SQL analyses executed during this build. Source SHA-256 hashes and excluded future-row counts are in the dashboard data JSON.", '']
    return '\n'.join(lines)
