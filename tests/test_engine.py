from copy import deepcopy
from datetime import date
from pathlib import Path
import tempfile
import unittest

from payments_analytics.common import (TX_FIELDS, business_add, business_age, expected_fee,
                                      read_csv, write_csv)
from payments_analytics.engine import reconcile


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.tx = dict(transaction_id='T1', merchant_id='M1', provider='P1', currency='USD',
                       transaction_type='PAYMENT', original_transaction_id='', transaction_date='2026-10-01',
                       gross_minor=10000, fee_bps=145, fee_fixed_minor=30, status='CAPTURED',
                       expected_settlement_date='2026-10-05', channel='CARD')
        self.settlement = dict(settlement_row_id='S1', batch_id='B1', transaction_id='T1', merchant_id='M1',
                               provider='P1', currency='USD', gross_minor=10000, fee_minor=175,
                               net_minor=9825, settled_date='2026-10-05', is_final='true')
        self.bank = dict(bank_entry_id='K1', payout_reference='PAYOUT1', batch_id='B1', provider='P1',
                         currency='USD', booking_date='2026-10-06', amount_minor=9825)
        self.cutoff = date(2026, 10, 12)

    def run_case(self, txs=None, settlements=None, banks=None, cutoff=None):
        return reconcile([self.tx] if txs is None else txs,
                         [self.settlement] if settlements is None else settlements,
                         [self.bank] if banks is None else banks, cutoff or self.cutoff)[0]

    def test_exact_match_and_two_layer_conservation(self):
        report = self.run_case()
        self.assertEqual(report['transactions'][0]['status'], 'MATCHED')
        self.assertEqual(report['batches'][0]['status'], 'MATCHED')
        self.assertEqual(report['metrics']['USD']['ledger_abs_variance_minor'], 0)
        self.assertEqual(report['metrics']['USD']['bank_abs_variance_minor'], 0)
        self.assertEqual(report['metrics']['USD']['match_rate_pct'], 100)

    def test_minor_unit_round_half_up(self):
        self.tx.update(gross_minor=100, fee_bps=50, fee_fixed_minor=0)
        self.assertEqual(expected_fee(self.tx), 1)

    def test_weekends_are_not_business_days(self):
        self.assertEqual(business_add(date(2026, 10, 2), 2), date(2026, 10, 6))
        self.assertEqual(business_age(date(2026, 10, 2), date(2026, 10, 5)), 1)

    def test_identical_imports_do_not_inflate_totals(self):
        report = self.run_case(txs=[self.tx, self.tx.copy()], settlements=[self.settlement, self.settlement.copy()], banks=[self.bank, self.bank.copy()])
        self.assertEqual(report['transactions'][0]['actual_net_minor'], 9825)
        self.assertEqual(report['batches'][0]['actual_net_minor'], 9825)
        self.assertEqual(sum(row['code'] == 'DUPLICATE_IMPORT' for row in report['exceptions']), 3)

    def test_conflicting_event_id_fails_closed(self):
        other = {**self.bank, 'amount_minor': 1}
        with self.assertRaisesRegex(ValueError, 'Conflicting duplicate'):
            self.run_case(banks=[self.bank, other])

    def test_ledger_missing_is_separate_from_unreferenced_bank_cash(self):
        report = self.run_case(settlements=[])
        self.assertEqual(report['transactions'][0]['status'], 'MISSING_SETTLEMENT')
        self.assertEqual(report['transactions'][0]['net_delta_minor'], 9825)
        self.assertTrue(any(row['code'] == 'UNREFERENCED_BANK_ENTRY' for row in report['exceptions']))

    def test_due_but_within_grace_is_pending(self):
        report = self.run_case(settlements=[], banks=[], cutoff=date(2026, 10, 6))
        self.assertEqual(report['transactions'][0]['status'], 'PENDING_SETTLEMENT')
        self.assertFalse(any(row['code'] == 'MISSING_SETTLEMENT' for row in report['exceptions']))

    def test_not_due_excluded_from_match_denominator(self):
        report = self.run_case(settlements=[], banks=[], cutoff=date(2026, 10, 2))
        self.assertEqual(report['transactions'][0]['status'], 'NOT_DUE')
        self.assertIsNone(report['metrics']['USD']['match_rate_pct'])

    def test_future_events_do_not_resolve_current_difference(self):
        self.settlement['settled_date'] = '2026-10-13'
        self.bank['booking_date'] = '2026-10-14'
        report = self.run_case()
        self.assertEqual(report['transactions'][0]['status'], 'MISSING_SETTLEMENT')
        self.assertEqual(report['future_rows_excluded']['settlements'], 1)
        self.assertEqual(report['future_rows_excluded']['bank_entries'], 1)

    def test_partial_settlement_finality(self):
        self.settlement.update(gross_minor=5000, net_minor=4825, is_final='false')
        report = self.run_case(banks=[])
        self.assertEqual(report['transactions'][0]['status'], 'PARTIAL_SETTLEMENT')
        self.assertEqual(report['transactions'][0]['net_delta_minor'], 5000)

    def test_split_settlement_matches_without_counting_two_transactions(self):
        a = {**self.settlement, 'gross_minor': 5000, 'fee_minor': 80, 'net_minor': 4920, 'is_final': 'false'}
        b = {**self.settlement, 'settlement_row_id': 'S2', 'gross_minor': 5000, 'fee_minor': 95, 'net_minor': 4905}
        report = self.run_case(settlements=[a, b])
        self.assertEqual(report['transactions'][0]['status'], 'MATCHED_SPLIT')
        self.assertEqual(report['metrics']['USD']['matched_due'], 1)
        self.assertEqual(report['batches'][0]['expected_net_minor'], 9825)

    def test_final_wrong_amount_and_fee_are_distinct(self):
        self.settlement.update(gross_minor=9999, net_minor=9824)
        self.assertEqual(self.run_case()['transactions'][0]['status'], 'AMOUNT_MISMATCH')
        self.settlement.update(gross_minor=10000, fee_minor=176, net_minor=9824)
        report = self.run_case()
        self.assertEqual(report['transactions'][0]['status'], 'FEE_MISMATCH')
        self.assertEqual(report['transactions'][0]['net_delta_minor'], 1)

    def test_late_matched_is_financially_reconciled(self):
        self.settlement['settled_date'] = '2026-10-08'
        report = self.run_case()
        self.assertEqual(report['transactions'][0]['status'], 'MATCHED_LATE')
        self.assertEqual(report['metrics']['USD']['matched_due'], 1)
        self.assertTrue(any(row['code'] == 'LATE_SETTLEMENT' and row['amount_minor'] == 0 for row in report['exceptions']))

    def test_currency_mismatch_is_never_netted(self):
        self.settlement['currency'] = 'AED'
        report = self.run_case()
        self.assertEqual(report['transactions'][0]['status'], 'CURRENCY_MISMATCH')
        self.assertIsNone(report['transactions'][0]['actual_net_minor'])
        self.assertIsNone(report['transactions'][0]['net_delta_minor'])
        self.assertEqual(report['metrics']['USD']['ledger_abs_variance_minor'], 0)
        self.assertEqual(report['metrics']['USD']['ledger_incompatible_expected_minor'], 9825)
        self.assertEqual(report['batches'][0]['status'], 'CURRENCY_MISMATCH')

    def test_merchant_reference_is_required(self):
        self.settlement['merchant_id'] = 'OTHER-MERCHANT'
        report = self.run_case()
        self.assertEqual(report['transactions'][0]['status'], 'REFERENCE_MISMATCH')
        self.assertIsNone(report['transactions'][0]['net_delta_minor'])

    def test_failed_payment_never_becomes_matched(self):
        self.tx['status'] = 'FAILED'
        report = self.run_case()
        self.assertEqual(report['transactions'][0]['status'], 'UNEXPECTED_SETTLEMENT')
        self.assertEqual(report['metrics']['USD']['eligible_due'], 0)

    def test_failed_payment_with_no_settlement_is_excluded(self):
        self.tx['status'] = 'FAILED'
        self.assertEqual(self.run_case(settlements=[], banks=[])['transactions'][0]['status'], 'EXCLUDED')

    def test_orphan_settlement_is_not_fuzzy_matched_by_amount(self):
        self.settlement['transaction_id'] = 'UNKNOWN'
        report = self.run_case()
        self.assertEqual(report['transactions'][0]['status'], 'MISSING_SETTLEMENT')
        self.assertTrue(any(row['code'] == 'ORPHAN_SETTLEMENT' for row in report['exceptions']))

    def test_missing_bank_credit_does_not_unmatch_ledger(self):
        report = self.run_case(banks=[])
        self.assertEqual(report['transactions'][0]['status'], 'MATCHED')
        self.assertEqual(report['batches'][0]['status'], 'MISSING_BANK_CREDIT')

    def test_bank_pending_and_split_credit(self):
        pending = self.run_case(banks=[], cutoff=date(2026, 10, 6))
        self.assertEqual(pending['batches'][0]['status'], 'PENDING_BANK_CREDIT')
        a = {**self.bank, 'amount_minor': 5000}
        b = {**self.bank, 'bank_entry_id': 'K2', 'amount_minor': 4825}
        self.assertEqual(self.run_case(banks=[a, b])['batches'][0]['status'], 'MATCHED_SPLIT')

    def test_bank_shortfall(self):
        self.bank['amount_minor'] -= 25
        report = self.run_case()
        self.assertEqual(report['batches'][0]['status'], 'BANK_AMOUNT_MISMATCH')
        self.assertEqual(report['metrics']['USD']['bank_abs_variance_minor'], 25)

    def test_refund_is_signed_and_original_fee_is_not_returned(self):
        refund = {**self.tx, 'transaction_id': 'R1', 'original_transaction_id': 'T1',
                  'transaction_type': 'REFUND', 'gross_minor': -5000}
        row = {**self.settlement, 'settlement_row_id': 'S2', 'transaction_id': 'R1',
               'gross_minor': -5000, 'fee_minor': 0, 'net_minor': -5000}
        self.bank['amount_minor'] = 4825
        report = self.run_case(txs=[self.tx, refund], settlements=[self.settlement, row])
        self.assertTrue(all(tx['matched'] for tx in report['transactions']))
        self.assertEqual(report['batches'][0]['expected_net_minor'], 4825)
        self.assertEqual(report['batches'][0]['status'], 'MATCHED')

    def test_cumulative_refunds_cannot_exceed_original_payment(self):
        refund = {**self.tx, 'transaction_id': 'R1', 'original_transaction_id': 'T1',
                  'transaction_type': 'REFUND', 'gross_minor': -10001}
        with self.assertRaisesRegex(ValueError, 'refunds exceed'):
            self.run_case(txs=[self.tx, refund])

    def test_zero_net_batch_needs_no_bank_credit(self):
        refund = {**self.tx, 'transaction_id': 'R1', 'original_transaction_id': 'T1',
                  'transaction_type': 'REFUND', 'gross_minor': -9825}
        row = {**self.settlement, 'settlement_row_id': 'S2', 'transaction_id': 'R1',
               'gross_minor': -9825, 'fee_minor': 0, 'net_minor': -9825}
        report = self.run_case(txs=[self.tx, refund], settlements=[self.settlement, row], banks=[])
        self.assertEqual(report['batches'][0]['status'], 'MATCHED_ZERO_NET')

    def test_bad_processor_net_and_mixed_currency_batch_fail(self):
        self.settlement['net_minor'] += 1
        with self.assertRaisesRegex(ValueError, 'Processor net'):
            self.run_case()
        self.settlement['net_minor'] -= 1
        other = {**self.settlement, 'settlement_row_id': 'S2', 'currency': 'AED'}
        with self.assertRaisesRegex(ValueError, 'cannot mix'):
            self.run_case(settlements=[self.settlement, other])

    def test_decimal_csv_amount_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ledger.csv'
            write_csv(path, TX_FIELDS, [{**self.tx, 'gross_minor': '100.50'}])
            with self.assertRaisesRegex(ValueError, 'integer minor units'):
                read_csv(path, TX_FIELDS, ('gross_minor',), ('transaction_date',))


if __name__ == '__main__':
    unittest.main()
