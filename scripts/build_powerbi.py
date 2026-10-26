"""Generate a self-contained PBIP source project, not a PBIX binary."""
import base64
import csv
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import uuid
import zipfile

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'powerbi'
SCHEMA = 'https://developer.microsoft.com/json-schemas/'
REPORT = 'BankingReconciliation.Report'
MODEL = 'BankingReconciliation.SemanticModel'
NAMESPACE = uuid.UUID('19ba3466-5df2-4516-9b39-468430bd63f0')


def guid(name):
    return str(uuid.uuid5(NAMESPACE, name))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def literal(value):
    text = 'true' if value is True else 'false' if value is False else f'{value}D' if isinstance(value, (int, float)) else "'" + str(value).replace("'", "''") + "'"
    return {'expr': {'Literal': {'Value': text}}}


def solid(color):
    return {'solid': {'color': literal(color)}}


def column(table, name):
    return {'Column': {'Expression': {'SourceRef': {'Entity': table}}, 'Property': name}}


def measure(name):
    return {'Measure': {'Expression': {'SourceRef': {'Entity': 'Metrics'}}, 'Property': name}}


def projection(field, display=None):
    kind = 'Column' if 'Column' in field else 'Measure'
    definition = field[kind]
    result = {'field': field, 'queryRef': definition['Expression']['SourceRef']['Entity'] + '.' + definition['Property']}
    if display:
        result['displayName'] = display
    if kind == 'Column':
        result['active'] = True
    return result


def currency_filter():
    return {'Version': 2, 'From': [{'Name': 'c', 'Entity': 'Currency', 'Type': 0}],
            'Where': [{'Condition': {'In': {'Expressions': [{'Column': {'Expression': {'SourceRef': {'Source': 'c'}}, 'Property': 'currency'}}],
                                          'Values': [[{'Literal': {'Value': "'USD'"}}]]}}}]}


def container(name, kind, title, x, y, width, height, roles=None, objects=None):
    visual = {'visualType': kind, 'drillFilterOtherVisuals': True,
              'visualContainerObjects': {
                  'title': [{'properties': {'show': literal(bool(title)), 'text': literal(title),
                              'fontColor': solid('#142338'), 'fontSize': literal(12), 'bold': literal(True)}}],
                  'background': [{'properties': {'show': literal(True), 'color': solid('#FFFFFF'), 'transparency': literal(0)}}],
                  'border': [{'properties': {'show': literal(True), 'color': solid('#E4EAF0'), 'radius': literal(8)}}],
                  'padding': [{'properties': {side: literal(12) for side in ('top', 'bottom', 'left', 'right')}}],
              }}
    if roles:
        visual['query'] = {'queryState': {role: {'projections': [projection(field) for field in fields]} for role, fields in roles.items()}}
    if objects:
        visual['objects'] = objects
    return {'$schema': SCHEMA + 'fabric/item/report/definition/visualContainer/2.4.0/schema.json',
            'name': name, 'position': {'x': x, 'y': y, 'z': y * 100 + x, 'width': width, 'height': height, 'tabOrder': y * 100 + x}, 'visual': visual}


def textbox(name, lines, x, y, width, height, dark=False):
    paragraphs = [{'textRuns': [{'value': text, 'textStyle': {'fontFamily': 'Segoe UI', 'fontSize': size, 'color': color, 'fontWeight': weight}}]} for text, size, color, weight in lines]
    visual = container(name, 'textbox', '', x, y, width, height,
                       objects={'general': [{'properties': {'paragraphs': paragraphs}}]})
    objects = visual['visual']['visualContainerObjects']
    objects['background'][0]['properties']['color'] = solid('#101F31' if dark else '#F4F7FA')
    objects['border'][0]['properties']['show'] = literal(False)
    return visual


def header(page_name, title, as_of):
    formatted_date = date.fromisoformat(as_of).strftime('%d %B %Y')
    return textbox(page_name + '_header', [
        ('SETTLEMENT LAB   /   BANKING & PAYMENTS', '11pt', '#67DCC8', 'bold'),
        (title, '27pt', '#FFFFFF', 'bold'),
        (f'Synthetic snapshot · {formatted_date} · Select one reporting currency', '10pt', '#C8D3E1', 'normal')],
        0, 0, 1440, 110, True)


def slicer(name, table, field, title, x, y, width=220, height=75, currency=False):
    objects = {'data': [{'properties': {'mode': literal('Dropdown')}}],
               'selection': [{'properties': {'singleSelect': literal(currency), 'selectAllCheckboxEnabled': literal(False)}}]}
    if currency:
        objects['general'] = [{'properties': {'filter': {'filter': currency_filter()}}}]
    visual = container(name, 'slicer', title, x, y, width, height, {'Values': [column(table, field)]}, objects)
    if currency:
        visual['visual']['syncGroup'] = {'groupName': 'ReportingCurrency', 'fieldChanges': True, 'filterChanges': True}
    return visual


def card(name, metric, title, index):
    return container(name, 'cardVisual', title, 32 + index * 349, 134, 329, 128,
                     {'Data': [measure(metric)]},
                     {'value': [{'selector': {'id': 'default'}, 'properties': {'fontSize': literal(28), 'fontColor': solid('#07877C'), 'bold': literal(True)}}],
                      'label': [{'selector': {'id': 'default'}, 'properties': {'show': literal(False)}}]})


def bar(name, title, table, category, metrics, x, y, width, height, kind='clusteredBarChart'):
    visual = container(name, kind, title, x, y, width, height,
                       {'Category': [column(table, category)], 'Y': [measure(m) for m in metrics]},
                       {'dataPoint': [{'properties': {'defaultColor': solid('#07877C')}}],
                        'legend': [{'properties': {'show': literal(len(metrics) > 1)}}]})
    if category == 'due_date':
        visual['visual']['query']['sortDefinition'] = {'sort': [{'field': column(table, category), 'direction': 'Ascending'}], 'isDefaultSort': False}
    if len(metrics) > 1:
        for metric, color in zip(metrics, ['#07877C', '#D88B30']):
            visual['visual']['objects']['dataPoint'].append({'selector': {'metadata': 'Metrics.' + metric}, 'properties': {'fill': solid(color)}})
    return visual


def data_table(name, title, table, columns, x, y, width, height):
    return container(name, 'tableEx', title, x, y, width, height,
                     {'Values': [column(table, field) for field in columns]},
                     {'grid': [{'properties': {'textSize': literal(10)}}],
                      'columnHeaders': [{'properties': {'fontColor': solid('#142338'), 'backColor': solid('#E9F3F2')}}],
                      'total': [{'properties': {'totals': literal(False)}}]})


def csv_table(name, filename):
    raw = (ROOT / 'docs' / 'data' / filename).read_bytes()
    reader = csv.DictReader(io.StringIO(raw.decode()))
    rows = list(reader)
    fields = reader.fieldnames
    bools = {'eligible', 'matched', 'late'}
    dates = {'transaction_date', 'due_date', 'last_settled_date', 'as_of'}
    ints = {field for field in fields if field.endswith('_minor') or field in {'age_business_days', 'settlement_rows', 'bank_entries', 'grace_business_days'}}
    columns = []
    mtypes = []
    for field in fields:
        dtype, mtype = ('boolean', 'type logical') if field in bools else ('dateTime', 'type date') if field in dates else ('int64', 'Int64.Type') if field in ints else ('string', 'type text')
        col = {'name': field, 'dataType': dtype, 'sourceColumn': field, 'summarizeBy': 'none', 'lineageTag': guid(name + '.' + field)}
        if field in ints or field in bools:
            col['isHidden'] = True
        if field in dates:
            col['formatString'] = 'dd MMM yyyy'
        columns.append(col)
        mtypes.append('{"' + field + '", ' + mtype + '}')
    encoded = base64.b64encode(raw).decode()
    chunks = [encoded[i:i + 12000] for i in range(0, len(encoded), 12000)]
    expression = ['let', '    Payload = Text.Combine({'] + ['        "' + chunk + '"' + (',' if i < len(chunks) - 1 else '') for i, chunk in enumerate(chunks)]
    expression += ['    }),', '    Source = Csv.Document(Binary.FromText(Payload, BinaryEncoding.Base64), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
                   '    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
                   '    Nulls = Table.ReplaceValue(Headers, "", null, Replacer.ReplaceValue, Table.ColumnNames(Headers)),',
                   '    Typed = Table.TransformColumnTypes(Nulls, {' + ', '.join(mtypes) + '}, "en-US")']
    previous = 'Typed'
    for field in fields:
        if not field.endswith('_minor'):
            continue
        friendly = 'reported_amount' if field == 'amount_minor' else field.removesuffix('_minor')
        step = 'With_' + friendly
        expression[-1] += ','
        expression.append(f'    {step} = Table.AddColumn({previous}, "{friendly}", each if [{field}] = null then null else [{field}] / 100, Currency.Type)')
        previous = step
        columns.append({'name': friendly, 'dataType': 'decimal', 'sourceColumn': friendly, 'summarizeBy': 'none',
                        'formatString': '#,0.00;(#,0.00);0.00', 'lineageTag': guid(name + '.' + friendly)})
    expression += ['in', '    ' + previous]
    definition = {'name': name, 'lineageTag': guid(name), 'columns': columns,
                  'partitions': [{'name': name, 'mode': 'import', 'source': {'type': 'm', 'expression': expression}}]}
    return definition, {'source': 'docs/data/' + filename, 'sha256': hashlib.sha256(raw).hexdigest(), 'rows': len(rows), 'base64': encoded}


def measures():
    cutoff = "VAR Cutoff = MAX('RunMetadata'[as_of])\n"
    due = "'Ledger'[eligible] = TRUE() && 'Ledger'[due_date] <= Cutoff"
    bank_due = "'BankBatches'[due_date] <= Cutoff"
    definitions = [
        ('Ledger Records', "COALESCE(COUNTROWS('Ledger'), 0)", '#,0'),
        ('Eligible Due Transactions', cutoff + "RETURN COALESCE(COUNTROWS(FILTER('Ledger', " + due + ')), 0)', '#,0'),
        ('Matched Due Transactions', cutoff + "RETURN COALESCE(COUNTROWS(FILTER('Ledger', " + due + " && 'Ledger'[matched] = TRUE())), 0)", '#,0'),
        ('Open Due Transactions', '[Eligible Due Transactions] - [Matched Due Transactions]', '#,0'),
        ('Ledger Match Rate', 'DIVIDE([Matched Due Transactions], [Eligible Due Transactions])', '0.00%'),
        ('Expected Due Net', cutoff + "RETURN IF(HASONEVALUE('Currency'[currency]), DIVIDE(SUMX(FILTER('Ledger', " + due + "), 'Ledger'[expected_net_minor]), 100))", '#,0.00'),
        ('Ledger Absolute Variance', cutoff + "RETURN IF(HASONEVALUE('Currency'[currency]), DIVIDE(SUMX(FILTER('Ledger', " + due + " && NOT(ISBLANK('Ledger'[net_delta_minor]))), ABS('Ledger'[net_delta_minor])), 100))", '#,0.00'),
        ('Incompatible Ledger References', cutoff + "RETURN COALESCE(COUNTROWS(FILTER('Ledger', " + due + " && ISBLANK('Ledger'[net_delta_minor]))), 0)", '#,0'),
        ('Incompatible Expected Net', cutoff + "RETURN IF(HASONEVALUE('Currency'[currency]), DIVIDE(SUMX(FILTER('Ledger', " + due + " && ISBLANK('Ledger'[net_delta_minor])), 'Ledger'[expected_net_minor]), 100))", '#,0.00'),
        ('Expected Fees Due', cutoff + "RETURN IF(HASONEVALUE('Currency'[currency]), DIVIDE(SUMX(FILTER('Ledger', " + due + "), 'Ledger'[expected_fee_minor]), 100))", '#,0.00'),
        ('Bank Batch Records', "COALESCE(COUNTROWS('BankBatches'), 0)", '#,0'),
        ('Due Bank Batches', cutoff + "RETURN COALESCE(COUNTROWS(FILTER('BankBatches', " + bank_due + ')), 0)', '#,0'),
        ('Matched Due Bank Batches', cutoff + "RETURN COALESCE(COUNTROWS(FILTER('BankBatches', " + bank_due + " && 'BankBatches'[matched] = TRUE())), 0)", '#,0'),
        ('Bank Match Rate', 'DIVIDE([Matched Due Bank Batches], [Due Bank Batches])', '0.00%'),
        ('Expected Due Bank Net', cutoff + "RETURN IF(HASONEVALUE('Currency'[currency]), DIVIDE(SUMX(FILTER('BankBatches', " + bank_due + "), 'BankBatches'[expected_net_minor]), 100))", '#,0.00'),
        ('Actual Due Bank Net', cutoff + "RETURN IF(HASONEVALUE('Currency'[currency]), DIVIDE(SUMX(FILTER('BankBatches', " + bank_due + "), 'BankBatches'[actual_net_minor]), 100))", '#,0.00'),
        ('Bank Absolute Variance', cutoff + "RETURN IF(HASONEVALUE('Currency'[currency]), DIVIDE(SUMX(FILTER('BankBatches', " + bank_due + " && NOT(ISBLANK('BankBatches'[net_delta_minor]))), ABS('BankBatches'[net_delta_minor])), 100))", '#,0.00'),
        ('Exception Records', "COALESCE(COUNTROWS('Exceptions'), 0)", '#,0'),
        ('High Priority Records', "COALESCE(COUNTROWS(FILTER('Exceptions', 'Exceptions'[severity] = \"HIGH\")), 0)", '#,0'),
        ('Aged High Priority Records', "VAR Grace = MAX('RunMetadata'[grace_business_days])\nRETURN COALESCE(COUNTROWS(FILTER('Exceptions', 'Exceptions'[severity] = \"HIGH\" && 'Exceptions'[age_business_days] > Grace)), 0)", '#,0'),
        ('Late Settlement Events', "COALESCE(COUNTROWS(FILTER('Exceptions', 'Exceptions'[code] = \"LATE_SETTLEMENT\")), 0)", '#,0'),
    ]
    return [{'name': name, 'expression': expression.splitlines(), 'formatString': fmt,
             'displayFolder': 'Bank controls' if 'Bank' in name else 'Exceptions' if 'Priority' in name or 'Exception' in name else 'Ledger controls',
             'lineageTag': guid('Metrics.' + name)} for name, expression, fmt in definitions]


def build_project():
    OUT.mkdir(parents=True, exist_ok=True)
    as_of = json.loads((ROOT / 'docs/data/report.json').read_text())['as_of']
    write_json(OUT / 'BankingReconciliation.pbip', {'$schema': SCHEMA + 'fabric/pbip/pbipProperties/1.0.0/schema.json',
               'version': '1.0', 'artifacts': [{'report': {'path': REPORT}}], 'settings': {'enableAutoRecovery': True}})
    write_json(OUT / REPORT / 'definition.pbir', {'$schema': SCHEMA + 'fabric/item/report/definitionProperties/2.0.0/schema.json',
               'version': '4.0', 'datasetReference': {'byPath': {'path': '../' + MODEL}}})
    write_json(OUT / MODEL / 'definition.pbism', {'$schema': SCHEMA + 'fabric/item/semanticModel/definitionProperties/1.0.0/schema.json',
               'version': '1.0', 'settings': {'qnaEnabled': False}})
    tables, snapshots = [], {}
    for name, file in [('Ledger', 'transaction_reconciliation.csv'), ('BankBatches', 'batch_reconciliation.csv'),
                       ('Exceptions', 'exceptions.csv'), ('RunMetadata', 'run_metadata.csv')]:
        table, snapshot = csv_table(name, file)
        tables.append(table)
        snapshots[name] = {key: value for key, value in snapshot.items() if key != 'base64'}
    tables.append({'name': 'Currency', 'lineageTag': guid('Currency'), 'columns': [{'name': 'currency', 'dataType': 'string', 'sourceColumn': 'currency', 'summarizeBy': 'none', 'lineageTag': guid('Currency.currency')}],
                   'partitions': [{'name': 'Currency', 'mode': 'import', 'source': {'type': 'm', 'expression': ['#table(type table [currency = text], {{"USD"}, {"AED"}, {"EGP"}})']}}]})
    tables.append({'name': 'Metrics', 'lineageTag': guid('Metrics'), 'columns': [{'name': 'Anchor', 'dataType': 'int64', 'sourceColumn': 'Anchor', 'isHidden': True, 'summarizeBy': 'none'}],
                   'partitions': [{'name': 'Metrics', 'mode': 'import', 'source': {'type': 'm', 'expression': ['#table(type table [Anchor = Int64.Type], {{1}})']}}], 'measures': measures()})
    tables[3]['isHidden'] = True
    relationships = [{'name': guid('Currency-' + name), 'fromTable': name, 'fromColumn': 'currency', 'toTable': 'Currency',
                      'toColumn': 'currency', 'fromCardinality': 'many', 'toCardinality': 'one',
                      'crossFilteringBehavior': 'oneDirection', 'isActive': True} for name in ['Ledger', 'BankBatches', 'Exceptions']]
    write_json(OUT / MODEL / 'model.bim', {'name': 'BankingReconciliation', 'compatibilityLevel': 1601,
               'model': {'culture': 'en-US', 'sourceQueryCulture': 'en-US', 'defaultPowerBIDataSourceVersion': 'powerBI_V3',
                         'dataAccessOptions': {'legacyRedirects': True, 'returnErrorValuesAsNull': True},
                         'tables': tables, 'relationships': relationships,
                         'annotations': [{'name': 'PBI_QueryOrder', 'value': json.dumps([t['name'] for t in tables])},
                                         {'name': 'SnapshotProvenance', 'value': 'All financial events are synthetic. The embedded CSV payloads match the documented source snapshot.'}]}})
    (OUT / 'measures.dax').write_text('\n\n'.join('// ' + m['name'] + '\n' + '\n'.join(m['expression']) for m in measures()) + '\n')
    definition = OUT / REPORT / 'definition'
    write_json(definition / 'version.json', {'$schema': SCHEMA + 'fabric/item/report/definition/versionMetadata/1.0.0/schema.json', 'version': '2.0.0'})
    write_json(definition / 'report.json', {'$schema': SCHEMA + 'fabric/item/report/definition/report/2.0.0/schema.json',
               'themeCollection': {}, 'settings': {'useStylableVisualContainerHeader': True, 'exportDataMode': 'AllowSummarizedAndUnderlying', 'pagesPosition': 'Bottom'}})
    page_order = ['overview', 'bank_control', 'exceptions']
    write_json(definition / 'pages' / 'pages.json', {'$schema': SCHEMA + 'fabric/item/report/definition/pagesMetadata/1.0.0/schema.json', 'pageOrder': page_order, 'activePageName': 'overview'})
    pages = {}
    for name, title in [('overview', 'Reconciliation overview'), ('bank_control', 'Settlement & bank payouts'), ('exceptions', 'Exception operations')]:
        visuals = [header(name, title, as_of), slicer(name + '_currency', 'Currency', 'currency', 'Reporting currency', 1184, 20, currency=True)]
        pages[name] = visuals
    pages['overview'] += [card('ov_card_' + str(i), metric, title, i) for i, (metric, title) in enumerate([
        ('Eligible Due Transactions', 'Eligible due transactions'), ('Ledger Match Rate', 'Ledger match rate'),
        ('Expected Due Net', 'Expected due net'), ('Ledger Absolute Variance', 'Ledger absolute variance')])]
    pages['overview'] += [
        bar('ov_daily', 'Due transactions by settlement date', 'Ledger', 'due_date', ['Matched Due Transactions', 'Open Due Transactions'], 32, 286, 860, 274, 'columnChart'),
        bar('ov_merchants', 'Open due transactions by merchant', 'Ledger', 'merchant_id', ['Open Due Transactions'], 916, 286, 492, 274),
        data_table('ov_ledger', 'Transaction detail · amounts in selected currency', 'Ledger', ['transaction_id', 'merchant_id', 'due_date', 'expected_net', 'actual_net', 'net_delta', 'status'], 32, 584, 1376, 250),
        textbox('ov_note', [('Comparable due variance includes pending items. Incompatible references are separately flagged. Never combine different currencies or add ledger and bank variances.', '10pt', '#647489', 'normal')], 32, 852, 1376, 42)]
    pages['bank_control'] += [card('bank_card_' + str(i), metric, title, i) for i, (metric, title) in enumerate([
        ('Due Bank Batches', 'Due bank batches'), ('Bank Match Rate', 'Bank match rate'),
        ('Expected Due Bank Net', 'Expected due payout net'), ('Bank Absolute Variance', 'Bank absolute variance')])]
    pages['bank_control'] += [
        bar('bank_daily', 'Expected vs booked due payout · selected currency', 'BankBatches', 'due_date', ['Expected Due Bank Net', 'Actual Due Bank Net'], 32, 286, 860, 274, 'clusteredColumnChart'),
        bar('bank_status', 'Payout status · all visible batches', 'BankBatches', 'status', ['Bank Batch Records'], 916, 286, 492, 274),
        data_table('bank_detail', 'Bank batch detail · amounts in selected currency', 'BankBatches', ['batch_id', 'due_date', 'expected_net', 'actual_net', 'net_delta', 'status', 'bank_entries'], 32, 584, 1376, 250),
        textbox('bank_note', [('The bank control is independent of ledger matching. Pending and future-due batches remain visible in detail; headline metrics include only due batches.', '10pt', '#647489', 'normal')], 32, 852, 1376, 42)]
    pages['exceptions'] += [card('ex_card_' + str(i), metric, title, i) for i, (metric, title) in enumerate([
        ('Exception Records', 'Exception records'), ('High Priority Records', 'High-priority records'),
        ('Aged High Priority Records', 'Aged high-priority records'), ('Incompatible Ledger References', 'Incompatible ledger references')])]
    pages['exceptions'] += [
        slicer('ex_code', 'Exceptions', 'code', 'Issue code', 32, 286, 442, 72),
        slicer('ex_owner', 'Exceptions', 'owner', 'Responsible team', 498, 286, 442, 72),
        slicer('ex_priority', 'Exceptions', 'severity', 'Priority', 964, 286, 444, 72),
        bar('ex_owners', 'Exception records by team', 'Exceptions', 'owner', ['Exception Records'], 32, 382, 350, 452),
        data_table('ex_detail', 'Investigation queue · reported amount is not a combined exposure', 'Exceptions',
                   ['reference', 'code', 'layer', 'currency', 'reported_amount', 'age_business_days', 'owner', 'severity', 'action'], 406, 382, 1002, 452),
        textbox('ex_note', [('Reported amounts are issue-specific: financial difference, expected incompatible amount, or unallocated cash. Never sum this column as financial exposure.', '10pt', '#647489', 'normal')], 32, 852, 1376, 42)]
    visual_count = 0
    for name, visuals in pages.items():
        path = definition / 'pages' / name
        # Keep summary cards stable while users inspect charts/tables or issue slicers.
        cards = [v['name'] for v in visuals if v['visual']['visualType'] == 'cardVisual']
        interactions = [{'source': source['name'], 'target': target, 'type': 'NoFilter'} for source in visuals
                        if source['visual']['visualType'] not in {'textbox', 'cardVisual'} and not source['name'].endswith('_currency')
                        for target in cards]
        write_json(path / 'page.json', {'$schema': SCHEMA + 'fabric/item/report/definition/page/2.0.0/schema.json',
                   'name': name, 'displayName': {'overview': '01 · Overview', 'bank_control': '02 · Settlement & Bank', 'exceptions': '03 · Exceptions'}[name],
                   'displayOption': 'FitToPage', 'width': 1440, 'height': 900,
                   'objects': {'background': [{'properties': {'color': solid('#F4F7FA'), 'transparency': literal(0)}}]},
                   'visualInteractions': interactions})
        for visual in visuals:
            write_json(path / 'visuals' / visual['name'] / 'visual.json', visual)
            visual_count += 1
    write_json(OUT / 'snapshot-manifest.json', {'synthetic': True, 'as_of': as_of, 'tables': snapshots,
               'pages': len(pages), 'visuals': visual_count, 'measures': len(measures()),
               'validation_boundary': 'PBIP source validation covers JSON schemas, model references, and embedded CSV snapshots. Desktop refresh, DAX evaluation, visual review, and KPI reconciliation are separate acceptance checks. The PBIX is distributed separately from the source ZIP.'})
    zip_path = OUT / 'BankingReconciliation-PowerBI.zip'
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(OUT.rglob('*')):
            if path.is_file() and path != zip_path and '.pbi' not in path.parts and path.suffix.lower() != '.pbix':
                info = zipfile.ZipInfo(path.relative_to(OUT).as_posix(), date_time=(2026, 10, 26, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
    print(f'Generated PBIP source: {len(pages)} pages, {visual_count} visuals, {len(measures())} measures. ZIP: {zip_path.name}')


if __name__ == '__main__':
    build_project()
