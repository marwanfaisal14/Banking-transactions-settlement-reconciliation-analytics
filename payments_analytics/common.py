"""Exact minor-unit amounts and an explicit weekday-only settlement calendar."""
import csv
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURRENCIES = ('USD', 'AED', 'EGP')
TX_FIELDS = ('transaction_id', 'merchant_id', 'provider', 'currency', 'transaction_type',
             'original_transaction_id', 'transaction_date', 'gross_minor', 'fee_bps',
             'fee_fixed_minor', 'status', 'expected_settlement_date', 'channel')
SETTLEMENT_FIELDS = ('settlement_row_id', 'batch_id', 'transaction_id', 'merchant_id',
                     'provider', 'currency', 'gross_minor', 'fee_minor', 'net_minor',
                     'settled_date', 'is_final')
BANK_FIELDS = ('bank_entry_id', 'payout_reference', 'batch_id', 'provider', 'currency',
               'booking_date', 'amount_minor')
AS_OF = date(2026, 10, 26)


def business_add(day, count):
    if count < 0:
        raise ValueError('Business day offset must be nonnegative')
    while count:
        day += timedelta(days=1)
        if day.weekday() < 5:
            count -= 1
    return day


def business_age(due, as_of):
    if as_of <= due:
        return 0
    return sum((due + timedelta(days=i)).weekday() < 5 for i in range(1, (as_of - due).days + 1))


def expected_fee(tx):
    if tx['transaction_type'] == 'REFUND':
        return 0
    return (tx['gross_minor'] * tx['fee_bps'] + 5000) // 10000 + tx['fee_fixed_minor']


def expected_net(tx):
    return tx['gross_minor'] - expected_fee(tx)


def write_csv(path, fields, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='raise', lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path, fields, numeric_fields, date_fields):
    with Path(path).open(newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != fields:
            raise ValueError(f'{Path(path).name}: unexpected or reordered CSV schema')
        rows = []
        for number, row in enumerate(reader, 2):
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f'{Path(path).name}:{number}: invalid column count')
            for key in fields:
                if not row[key] and key != 'original_transaction_id':
                    raise ValueError(f'{Path(path).name}:{number}: missing {key}')
            for key in numeric_fields:
                value = row[key]
                if not value.removeprefix('-').isascii() or not value.removeprefix('-').isdigit():
                    raise ValueError(f'{Path(path).name}:{number}: {key} must be integer minor units')
                row[key] = int(value)
            for key in date_fields:
                row[key] = date.fromisoformat(row[key]).isoformat()
            if row['currency'] not in CURRENCIES:
                raise ValueError(f'{Path(path).name}:{number}: unsupported currency')
            rows.append(row)
    return rows
