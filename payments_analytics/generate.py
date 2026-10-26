"""Deterministic, fictional event feeds with separately documented planted cases."""
from collections import defaultdict
from datetime import date, timedelta
import json
from pathlib import Path
import random

from .common import (AS_OF, BANK_FIELDS, CURRENCIES, SETTLEMENT_FIELDS, TX_FIELDS,
                     business_add, expected_fee, write_csv)


def generate(output, seed=20261026, count=1200):
    if count < 120:
        raise ValueError('At least 120 records are needed for the documented scenarios')
    rng = random.Random(seed)
    start = date(2026, 9, 21)
    transactions, settlements, bank = [], [], []
    refundable = defaultdict(list)
    scenarios = {}
    cases = ('missing_settlement', 'partial_settlement', 'amount_mismatch', 'fee_mismatch',
             'late_match', 'split_match', 'currency_mismatch', 'unexpected_settlement',
             'pending_within_grace', 'not_due')
    # Each scenario is represented once per currency, on dates well before cutoff.
    for i in range(count):
        currency = CURRENCIES[i % len(CURRENCIES)]
        forced = i < len(cases) * len(CURRENCIES)
        case = cases[i // 3] if forced else 'normal'
        day = start + timedelta(days=i // 3 if forced else rng.randrange((AS_OF - start).days + 1))
        if case == 'pending_within_grace':
            day = date(2026, 10, 22)
        elif case == 'not_due':
            day = AS_OF
        merchant = f'MERCHANT-{rng.randrange(1, 5):02d}'
        channel = rng.choice(['CARD', 'BANK_TRANSFER'])
        gross = rng.randrange(500, 250001)
        kind, original = 'PAYMENT', ''
        status = 'FAILED' if case == 'unexpected_settlement' else 'CAPTURED'
        if not forced:
            status = rng.choices(['CAPTURED', 'FAILED', 'VOIDED'], [90, 7, 3])[0]
            candidates = [t for t in refundable[currency] if t['transaction_date'] <= day.isoformat()]
            if status == 'CAPTURED' and candidates and rng.random() < 0.09:
                prior = rng.choice(candidates)
                refundable[currency].remove(prior)
                kind, original, merchant = 'REFUND', prior['transaction_id'], prior['merchant_id']
                gross = -rng.randrange(1, prior['gross_minor'] + 1)
        tx = dict(zip(TX_FIELDS, (
            f'TXN-{i + 1:06d}', merchant, 'DEMO-SWITCH', currency, kind, original,
            day.isoformat(), gross, 145 if channel == 'CARD' else 25,
            30 if channel == 'CARD' else 15, status, business_add(day, 2).isoformat(), channel,
        )))
        transactions.append(tx)
        if status == 'CAPTURED' and kind == 'PAYMENT':
            refundable[currency].append(tx)
        if forced:
            scenarios[tx['transaction_id']] = case
        if status != 'CAPTURED' and case != 'unexpected_settlement':
            continue
        if case in {'missing_settlement', 'pending_within_grace', 'not_due'}:
            continue
        settled = date.fromisoformat(tx['expected_settlement_date'])
        if case == 'late_match':
            settled = business_add(settled, 3)
        fee = expected_fee(tx)
        actual_currency = CURRENCIES[(CURRENCIES.index(currency) + 1) % 3] if case == 'currency_mismatch' else currency
        pieces = [(gross, fee, 'true')]
        if case == 'partial_settlement':
            pieces = [(gross // 2, fee, 'false')]
        elif case == 'amount_mismatch':
            pieces = [(gross - 175, fee, 'true')]
        elif case == 'fee_mismatch':
            pieces = [(gross, fee + 85, 'true')]
        elif case == 'split_match':
            pieces = [(gross // 2, fee // 2, 'false'), (gross - gross // 2, fee - fee // 2, 'true')]
        for part, (amount, actual_fee, final) in enumerate(pieces, 1):
            batch_id = f'BATCH-{settled:%Y%m%d}-{actual_currency}'
            settlements.append(dict(zip(SETTLEMENT_FIELDS, (
                f'SET-{i + 1:06d}-{part}', batch_id, tx['transaction_id'], merchant,
                tx['provider'], actual_currency, amount, actual_fee, amount - actual_fee,
                settled.isoformat(), final,
            ))))
    for currency in CURRENCIES:
        settled = date(2026, 10, 1)
        settlements.append(dict(zip(SETTLEMENT_FIELDS, (
            f'SET-ORPHAN-{currency}', f'BATCH-{settled:%Y%m%d}-{currency}',
            f'UNKNOWN-TXN-{currency}', 'MERCHANT-01', 'DEMO-SWITCH', currency,
            125000, 500, 124500, settled.isoformat(), 'true',
        ))))
    batches = defaultdict(list)
    for row in settlements:
        batches[row['batch_id']].append(row)
    bank_cases = {}
    per_currency = defaultdict(int)
    for index, (batch_id, rows) in enumerate(sorted(batches.items()), 1):
        currency = rows[0]['currency']
        scenario_index = per_currency[currency]
        per_currency[currency] += 1
        case = ('missing_bank_credit', 'bank_amount_mismatch', 'split_bank_credit')[scenario_index] if scenario_index < 3 else 'normal'
        bank_cases[batch_id] = case
        total = sum(row['net_minor'] for row in rows)
        booking = business_add(max(date.fromisoformat(row['settled_date']) for row in rows), 1)
        if case == 'missing_bank_credit':
            continue
        amounts = [total - 250] if case == 'bank_amount_mismatch' else [total]
        if case == 'split_bank_credit':
            amounts = [total // 2, total - total // 2]
        for part, amount in enumerate(amounts, 1):
            bank.append(dict(zip(BANK_FIELDS, (
                f'BANK-{index:04d}-{part}', f'PAYOUT-{index:04d}', batch_id,
                'DEMO-SWITCH', currency, booking.isoformat(), amount,
            ))))
    for currency in CURRENCIES:
        bank.append(dict(zip(BANK_FIELDS, (
            f'BANK-UNREFERENCED-{currency}', f'PAYOUT-UNKNOWN-{currency}',
            f'UNKNOWN-BATCH-{currency}', 'DEMO-SWITCH', currency, '2026-10-02', 75000,
        ))))
    # Duplicate import events are byte-identical by business fields and must not inflate totals.
    settlements.append(settlements[0].copy())
    bank.append(bank[0].copy())
    output = Path(output)
    write_csv(output / 'transaction_ledger.csv', TX_FIELDS, transactions)
    write_csv(output / 'processor_settlements.csv', SETTLEMENT_FIELDS, settlements)
    write_csv(output / 'bank_statement.csv', BANK_FIELDS, bank)
    manifest = {
        'source': 'Entirely synthetic; no banking system or real customer data',
        'seed': seed, 'transaction_count': count, 'reference_as_of': AS_OF.isoformat(),
        'calendar': 'Monday-Friday only; no country-specific holidays',
        'transaction_scenarios': scenarios, 'batch_scenarios': bank_cases,
        'note': 'This manifest is for human review and tests only; the engine does not read it. Future-dated events support cutoff replay.',
    }
    (output / 'scenario_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest
