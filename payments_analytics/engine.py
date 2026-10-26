"""Reference-based, two-layer reconciliation with no cross-currency netting."""
from collections import Counter, defaultdict
from datetime import date

from .common import (BANK_FIELDS, CURRENCIES, SETTLEMENT_FIELDS, TX_FIELDS,
                     business_add, business_age, expected_fee, expected_net, read_csv)

MATCHED = {'MATCHED', 'MATCHED_SPLIT', 'MATCHED_LATE', 'MATCHED_ZERO_NET'}


def load_inputs(folder):
    transactions = read_csv(folder / 'transaction_ledger.csv', TX_FIELDS,
                            ('gross_minor', 'fee_bps', 'fee_fixed_minor'),
                            ('transaction_date', 'expected_settlement_date'))
    settlements = read_csv(folder / 'processor_settlements.csv', SETTLEMENT_FIELDS,
                           ('gross_minor', 'fee_minor', 'net_minor'), ('settled_date',))
    bank = read_csv(folder / 'bank_statement.csv', BANK_FIELDS, ('amount_minor',), ('booking_date',))
    return transactions, settlements, bank


def validate(transactions, settlements, bank):
    for rows, keys in ((transactions, ('gross_minor', 'fee_bps', 'fee_fixed_minor')),
                       (settlements, ('gross_minor', 'fee_minor', 'net_minor')),
                       (bank, ('amount_minor',))):
        if any(type(row[key]) is not int for row in rows for key in keys):
            raise ValueError('Monetary inputs and fee rates must be integers')
    for tx in transactions:
        if tx['status'] not in {'CAPTURED', 'FAILED', 'VOIDED'} or tx['transaction_type'] not in {'PAYMENT', 'REFUND'}:
            raise ValueError('Unsupported transaction status or type')
        if tx['channel'] not in {'CARD', 'BANK_TRANSFER'}:
            raise ValueError('Unsupported payment channel')
        if tx['fee_bps'] < 0 or tx['fee_fixed_minor'] < 0 or tx['fee_bps'] > 10000:
            raise ValueError('Invalid fee schedule')
        if (tx['transaction_type'] == 'PAYMENT' and tx['gross_minor'] <= 0) or (tx['transaction_type'] == 'REFUND' and tx['gross_minor'] >= 0):
            raise ValueError('Payment/refund sign convention violated')
        if tx['expected_settlement_date'] < tx['transaction_date']:
            raise ValueError('Settlement due before transaction date')
    by_id = {tx['transaction_id']: tx for tx in transactions}
    refunded = defaultdict(int)
    for tx in transactions:
        if tx['transaction_type'] != 'REFUND':
            if tx['original_transaction_id']:
                raise ValueError('Payment cannot reference an original transaction')
            continue
        original = by_id.get(tx['original_transaction_id'])
        if not original or original['transaction_type'] != 'PAYMENT' or original['status'] != 'CAPTURED':
            raise ValueError('Refund must reference a captured payment')
        if any(tx[key] != original[key] for key in ('currency', 'merchant_id', 'provider')):
            raise ValueError('Refund identity differs from original payment')
        if tx['transaction_date'] < original['transaction_date']:
            raise ValueError('Refund precedes original payment')
        if tx['status'] == 'CAPTURED':
            refunded[original['transaction_id']] += -tx['gross_minor']
            if refunded[original['transaction_id']] > original['gross_minor']:
                raise ValueError('Cumulative refunds exceed original payment')
    for row in settlements:
        if row['fee_minor'] < 0 or row['net_minor'] != row['gross_minor'] - row['fee_minor']:
            raise ValueError('Processor net must equal signed gross minus nonnegative fee')
        if row['is_final'] not in {'true', 'false'}:
            raise ValueError('is_final must be true or false')
    for feed in (transactions, settlements, bank):
        for row in feed:
            if row['currency'] not in CURRENCIES:
                raise ValueError('Unsupported currency')
    batches = defaultdict(set)
    for row in settlements:
        batches[row['batch_id']].add((row['provider'], row['currency']))
    if any(len(identities) > 1 for identities in batches.values()):
        raise ValueError('A processor batch cannot mix providers or currencies')


def reconcile(transactions, settlements, bank, as_of, grace_days=1):
    if grace_days < 0:
        raise ValueError('Grace days cannot be negative')
    cutoff = as_of.isoformat()
    issues = []

    def issue(layer, code, ref, currency, amount=0, due='', message='', severity='HIGH'):
        age = business_age(date.fromisoformat(due), as_of) if due else 0
        owner = 'Settlement Operations' if layer == 'LEDGER' else 'Treasury Operations' if layer == 'BANK' else 'Data Operations'
        action = {
            'MISSING_SETTLEMENT': 'Trace the processor reference and request the missing settlement.',
            'PARTIAL_SETTLEMENT': 'Confirm remaining settlement portions and finality with the processor.',
            'AMOUNT_MISMATCH': 'Compare captured/refunded amount with processor settlement detail.',
            'FEE_MISMATCH': 'Review contracted fee schedule and processor fee calculation.',
            'CURRENCY_MISMATCH': 'Investigate currency routing; do not convert or net the amounts.',
            'REFERENCE_MISMATCH': 'Verify provider and merchant identifiers before matching.',
            'MISSING_BANK_CREDIT': 'Trace payout reference against the bank statement.',
            'BANK_AMOUNT_MISMATCH': 'Compare payout advice with the booked bank amount.',
            'UNREFERENCED_BANK_ENTRY': 'Obtain payout advice; leave the entry unallocated.',
            'ORPHAN_SETTLEMENT': 'Locate the original ledger record; leave the settlement unallocated.',
            'UNEXPECTED_SETTLEMENT': 'Review settlement against the failed or voided transaction.',
            'DUPLICATE_IMPORT': 'Remove the duplicate delivery at ingestion; retain the audit event.',
            'LATE_SETTLEMENT': 'Review SLA breach; no monetary difference remains.',
        }.get(code, 'Review the source records without changing ledger balances.')
        issues.append(dict(issue_id=f'EXC-{len(issues) + 1:05d}', layer=layer, code=code,
                           reference=ref, currency=currency, amount_minor=amount, due_date=due,
                           age_business_days=age, severity=severity, owner=owner, action=action,
                           description=message))

    def unique(rows, key, layer):
        seen, clean = {}, []
        for row in rows:
            ref = row[key]
            if ref in seen:
                if row != seen[ref]:
                    raise ValueError(f'Conflicting duplicate {key}: {ref}')
                issue('DATA', 'DUPLICATE_IMPORT', ref, row['currency'], message=f'Identical {layer} event ignored.', severity='MEDIUM')
            else:
                seen[ref] = row
                clean.append(row)
        return clean

    raw_counts = {'transactions': len(transactions), 'settlements': len(settlements), 'bank_entries': len(bank)}
    # Reject conflicting IDs even if a repeated row would fall beyond the cutoff.
    # Deduplication occurs before refund validation to avoid counting duplicate refunds twice.
    transactions = unique(transactions, 'transaction_id', 'ledger')
    settlements = unique(settlements, 'settlement_row_id', 'processor')
    bank = unique(bank, 'bank_entry_id', 'bank')
    validate(transactions, settlements, bank)
    future_counts = {
        'transactions': sum(tx['transaction_date'] > cutoff for tx in transactions),
        'settlements': sum(row['settled_date'] > cutoff for row in settlements),
        'bank_entries': sum(row['booking_date'] > cutoff for row in bank),
    }
    transactions = [tx for tx in transactions if tx['transaction_date'] <= cutoff]
    settlements = [row for row in settlements if row['settled_date'] <= cutoff]
    bank = [row for row in bank if row['booking_date'] <= cutoff]
    by_tx, by_batch, bank_by_batch = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in settlements:
        by_tx[row['transaction_id']].append(row)
        by_batch[row['batch_id']].append(row)
    for row in bank:
        bank_by_batch[row['batch_id']].append(row)
    results = []
    for tx in transactions:
        rows = by_tx.get(tx['transaction_id'], [])
        eligible = tx['status'] == 'CAPTURED'
        expected = expected_net(tx) if eligible else 0
        due = tx['expected_settlement_date']
        age = business_age(date.fromisoformat(due), as_of)
        actual_currencies = sorted({row['currency'] for row in rows})
        identity_ok = all(row['provider'] == tx['provider'] and row['merchant_id'] == tx['merchant_id'] for row in rows)
        currency_ok = all(row['currency'] == tx['currency'] for row in rows)
        actual = sum(row['net_minor'] for row in rows) if identity_ok and currency_ok else None
        actual_gross = sum(row['gross_minor'] for row in rows) if actual is not None else None
        actual_fee = sum(row['fee_minor'] for row in rows) if actual is not None else None
        delta = expected - actual if actual is not None else None
        last_date = max((row['settled_date'] for row in rows), default='')
        late = bool(last_date and business_age(date.fromisoformat(due), date.fromisoformat(last_date)) > grace_days)
        if not rows:
            status = 'EXCLUDED' if not eligible else 'NOT_DUE' if due > cutoff else 'PENDING_SETTLEMENT' if age <= grace_days else 'MISSING_SETTLEMENT'
        elif not currency_ok:
            status = 'CURRENCY_MISMATCH'
        elif not identity_ok:
            status = 'REFERENCE_MISMATCH'
        elif not eligible:
            status = 'UNEXPECTED_SETTLEMENT'
        elif not any(row['is_final'] == 'true' for row in rows):
            status = 'PARTIAL_SETTLEMENT'
        elif actual_gross != tx['gross_minor']:
            status = 'AMOUNT_MISMATCH'
        elif actual_fee != expected_fee(tx):
            status = 'FEE_MISMATCH'
        else:
            status = 'MATCHED_LATE' if late else 'MATCHED_SPLIT' if len(rows) > 1 else 'MATCHED'
        result = dict(transaction_id=tx['transaction_id'], merchant_id=tx['merchant_id'], provider=tx['provider'],
                      currency=tx['currency'], transaction_type=tx['transaction_type'], channel=tx['channel'],
                      transaction_date=tx['transaction_date'], due_date=due, eligible=eligible,
                      expected_gross_minor=tx['gross_minor'] if eligible else 0,
                      expected_fee_minor=expected_fee(tx) if eligible else 0, expected_net_minor=expected,
                      actual_gross_minor=actual_gross, actual_fee_minor=actual_fee, actual_net_minor=actual,
                      net_delta_minor=delta, actual_currencies=','.join(actual_currencies),
                      settlement_rows=len(rows), last_settled_date=last_date, age_business_days=age,
                      status=status, matched=status in MATCHED, late=late)
        results.append(result)
        if status in {'MISSING_SETTLEMENT', 'PARTIAL_SETTLEMENT', 'AMOUNT_MISMATCH', 'FEE_MISMATCH', 'UNEXPECTED_SETTLEMENT', 'CURRENCY_MISMATCH', 'REFERENCE_MISMATCH'}:
            issue('LEDGER', status, tx['transaction_id'], tx['currency'], delta if delta is not None else expected,
                  due, message='Expected minus actual net; incompatible identities/currencies are not netted.')
        if late:
            issue('LEDGER', 'LATE_SETTLEMENT', tx['transaction_id'], tx['currency'], 0, due,
                  message='Completion occurred after the contractual date plus grace.', severity='LOW')
    known_tx = {tx['transaction_id'] for tx in transactions}
    for row in settlements:
        if row['transaction_id'] not in known_tx:
            issue('LEDGER', 'ORPHAN_SETTLEMENT', row['settlement_row_id'], row['currency'], row['net_minor'],
                  message='No ledger transaction exists at the reporting cutoff.')
    batches = []
    for batch_id, rows in sorted(by_batch.items()):
        currency, provider = rows[0]['currency'], rows[0]['provider']
        expected = sum(row['net_minor'] for row in rows)
        due = business_add(max(date.fromisoformat(row['settled_date']) for row in rows), 1).isoformat()
        age = business_age(date.fromisoformat(due), as_of)
        entries = bank_by_batch.get(batch_id, [])
        same_currency = all(row['currency'] == currency for row in entries)
        same_provider = all(row['provider'] == provider for row in entries)
        actual = sum(row['amount_minor'] for row in entries) if same_currency and same_provider else None
        delta = expected - actual if actual is not None else None
        if not entries and expected == 0:
            status = 'MATCHED_ZERO_NET'
        elif not entries:
            status = 'MISSING_BANK_CREDIT' if age > grace_days else 'PENDING_BANK_CREDIT'
        elif not same_currency:
            status = 'CURRENCY_MISMATCH'
        elif not same_provider:
            status = 'REFERENCE_MISMATCH'
        elif delta:
            status = 'BANK_AMOUNT_MISMATCH'
        else:
            status = 'MATCHED_SPLIT' if len(entries) > 1 else 'MATCHED'
        batches.append(dict(batch_id=batch_id, currency=currency, provider=provider, due_date=due,
                            expected_net_minor=expected, actual_net_minor=actual, net_delta_minor=delta,
                            bank_entries=len(entries), age_business_days=age, status=status,
                            matched=status in MATCHED, settlement_rows=len(rows)))
        if status in {'MISSING_BANK_CREDIT', 'BANK_AMOUNT_MISMATCH', 'CURRENCY_MISMATCH', 'REFERENCE_MISMATCH'}:
            issue('BANK', status, batch_id, currency, delta if delta is not None else expected, due)
    for row in bank:
        if row['batch_id'] not in by_batch:
            issue('BANK', 'UNREFERENCED_BANK_ENTRY', row['bank_entry_id'], row['currency'], row['amount_minor'],
                  message='No processor batch exists at the reporting cutoff.')
    report = dict(as_of=cutoff, synthetic=True, grace_business_days=grace_days,
                  calendar='Monday-Friday; public holidays excluded from this demonstration',
                  raw_input_counts=raw_counts, future_rows_excluded=future_counts,
                  transactions=results, batches=batches, exceptions=issues)
    report['metrics'] = summarize(report)
    return report, transactions, settlements, bank


def summarize(report):
    metrics = {}
    for currency in CURRENCIES:
        txs = [tx for tx in report['transactions'] if tx['currency'] == currency]
        due = [tx for tx in txs if tx['eligible'] and tx['due_date'] <= report['as_of']]
        batches = [row for row in report['batches'] if row['currency'] == currency]
        matured_batches = [row for row in batches if row['due_date'] <= report['as_of']]
        matched = sum(tx['matched'] for tx in due)
        metrics[currency] = dict(
            ledger_records=len(txs), eligible_due=len(due), matched_due=matched,
            match_rate_pct=round(100 * matched / len(due), 2) if due else None,
            expected_due_net_minor=sum(tx['expected_net_minor'] for tx in due),
            ledger_abs_variance_minor=sum(abs(tx['net_delta_minor']) for tx in due if tx['net_delta_minor'] is not None),
            ledger_incompatible_count=sum(tx['net_delta_minor'] is None for tx in due),
            ledger_incompatible_expected_minor=sum(tx['expected_net_minor'] for tx in due if tx['net_delta_minor'] is None),
            bank_abs_variance_minor=sum(abs(row['net_delta_minor']) for row in matured_batches if row['net_delta_minor'] is not None),
            bank_due_batches=len(matured_batches), bank_matched_batches=sum(row['matched'] for row in matured_batches),
            exception_records=sum(row['currency'] == currency for row in report['exceptions']),
            status_counts=dict(Counter(tx['status'] for tx in txs)),
        )
    return metrics
