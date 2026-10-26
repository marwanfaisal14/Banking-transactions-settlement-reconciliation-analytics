from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from payments_analytics.build import build
from payments_analytics.common import AS_OF
from payments_analytics.generate import generate


class PipelineTests(unittest.TestCase):
    def test_deterministic_generation_and_full_reconciliation_without_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a, b = root / 'a', root / 'b'
            manifest = generate(a)
            generate(b)
            for name in ('transaction_ledger.csv', 'processor_settlements.csv', 'bank_statement.csv'):
                self.assertEqual((a / name).read_bytes(), (b / name).read_bytes())
            (a / 'scenario_manifest.json').unlink()
            report = build(a, root / 'out', root / 'report.json', root / 'findings.md', AS_OF)
            self.assertEqual(len(report['transactions']), 1200)
            self.assertEqual(report['sql_queries_executed'], 12)
            self.assertEqual(sum(row['code'] == 'DUPLICATE_IMPORT' for row in report['exceptions']), 2)
            expected = {'missing_settlement': 'MISSING_SETTLEMENT', 'partial_settlement': 'PARTIAL_SETTLEMENT',
                        'amount_mismatch': 'AMOUNT_MISMATCH', 'fee_mismatch': 'FEE_MISMATCH', 'late_match': 'MATCHED_LATE',
                        'split_match': 'MATCHED_SPLIT', 'currency_mismatch': 'CURRENCY_MISMATCH',
                        'unexpected_settlement': 'UNEXPECTED_SETTLEMENT', 'pending_within_grace': 'PENDING_SETTLEMENT',
                        'not_due': 'NOT_DUE'}
            indexed = {row['transaction_id']: row for row in report['transactions']}
            for ref, case in manifest['transaction_scenarios'].items():
                self.assertEqual(indexed[ref]['status'], expected[case], ref)
            self.assertGreater(report['future_rows_excluded']['settlements'], 0)
            snapshot = (root / 'report.json').read_bytes()
            second = build(a, root / 'out', root / 'report.json', root / 'findings.md', AS_OF)
            self.assertEqual(snapshot, (root / 'report.json').read_bytes())
            self.assertEqual(report, second)
            db = sqlite3.connect(root / 'out' / 'reconciliation.sqlite')
            try:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone(), ('ok',))
                for currency, metric in report['metrics'].items():
                    matched, due = db.execute('SELECT SUM(matched), COUNT(*) FROM reconciliation_results WHERE eligible = 1 AND due_date <= ? AND currency = ?', (AS_OF.isoformat(), currency)).fetchone()
                    self.assertEqual((matched, due), (metric['matched_due'], metric['eligible_due']))
                    source_net = db.execute('SELECT SUM(net_minor) FROM processor_settlements WHERE currency = ?', (currency,)).fetchone()[0]
                    batch_net = db.execute('SELECT SUM(expected_net_minor) FROM batch_reconciliation WHERE currency = ?', (currency,)).fetchone()[0]
                    self.assertEqual(source_net, batch_net)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM transaction_ledger').fetchone()[0], 1200)
            finally:
                db.close()
            for index in range(1, 13):
                self.assertTrue((root / 'out' / f'analysis-{index:02d}.csv').is_file())

    def test_empty_cutoff_has_no_false_match_rate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            generate(root / 'data', count=120)
            report = build(root / 'data', root / 'out', root / 'report.json', root / 'findings.md', date(2026, 9, 1))
            self.assertEqual(report['transactions'], [])
            self.assertTrue(all(metric['match_rate_pct'] is None for metric in report['metrics'].values()))


if __name__ == '__main__':
    unittest.main()
