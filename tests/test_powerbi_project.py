"""Source-package integration checks; these do not run Power BI or evaluate DAX."""
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent.parent
PBI = ROOT / 'powerbi'


class PowerBISourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = json.loads((PBI / 'BankingReconciliation.SemanticModel/model.bim').read_text())['model']
        cls.tables = {table['name']: table for table in cls.model['tables']}

    def test_project_artifact_paths_and_page_order(self):
        project = json.loads((PBI / 'BankingReconciliation.pbip').read_text())
        report_path = PBI / project['artifacts'][0]['report']['path']
        definition = json.loads((report_path / 'definition.pbir').read_text())
        model_path = (report_path / definition['datasetReference']['byPath']['path']).resolve()
        self.assertEqual(model_path, (PBI / 'BankingReconciliation.SemanticModel').resolve())
        self.assertTrue((model_path / 'definition.pbism').is_file())
        metadata = json.loads((report_path / 'definition/pages/pages.json').read_text())
        self.assertEqual(metadata['pageOrder'], ['overview', 'bank_control', 'exceptions'])
        self.assertEqual(metadata['activePageName'], 'overview')
        for name in metadata['pageOrder']:
            page = json.loads((report_path / 'definition/pages' / name / 'page.json').read_text())
            self.assertEqual(page['name'], name)

    def test_every_visual_field_resolves_and_fits_its_page(self):
        count = 0
        for path in (PBI / 'BankingReconciliation.Report/definition/pages').glob('*/visuals/*/visual.json'):
            visual = json.loads(path.read_text())
            position = visual['position']
            self.assertGreaterEqual(position['x'], 0)
            self.assertGreaterEqual(position['y'], 0)
            self.assertLessEqual(position['x'] + position['width'], 1440)
            self.assertLessEqual(position['y'] + position['height'], 900)
            for role in visual['visual'].get('query', {}).get('queryState', {}).values():
                for field in role['projections']:
                    definition = field['field']
                    kind = 'Column' if 'Column' in definition else 'Measure'
                    table = definition[kind]['Expression']['SourceRef']['Entity']
                    prop = definition[kind]['Property']
                    names = {item['name'] for item in self.tables[table]['columns' if kind == 'Column' else 'measures']}
                    self.assertIn(prop, names, str(path))
            count += 1
        self.assertEqual(count, 32)

    def test_embedded_payloads_are_the_exact_verified_csv_snapshots(self):
        manifest = json.loads((PBI / 'snapshot-manifest.json').read_text())
        for name, source in manifest['tables'].items():
            expression = self.tables[name]['partitions'][0]['source']['expression']
            chunks = [re.fullmatch(r'        "([A-Za-z0-9+/=]+)"[,]?', line) for line in expression]
            payload = base64.b64decode(''.join(match.group(1) for match in chunks if match), validate=True)
            expected = (ROOT / source['source']).read_bytes()
            self.assertEqual(payload, expected, name)
            self.assertEqual(hashlib.sha256(payload).hexdigest(), source['sha256'])
            rows = list(csv.DictReader(io.StringIO(payload.decode())))
            self.assertEqual(len(rows), source['rows'])
            self.assertNotIn('File.Contents', '\n'.join(expression))
            self.assertNotIn('Web.Contents', '\n'.join(expression))
        ledger = json.loads((ROOT / 'docs/data/report.json').read_text())['transactions']
        self.assertTrue(any(row['expected_net_minor'] < 0 for row in ledger))
        self.assertTrue(any(row['actual_net_minor'] is None for row in ledger))

    def test_currency_relationships_do_not_join_the_fact_tables(self):
        relationships = self.model['relationships']
        self.assertEqual(len(relationships), 3)
        for relationship in relationships:
            self.assertEqual(relationship['toTable'], 'Currency')
            self.assertEqual(relationship['toColumn'], 'currency')
            self.assertEqual(relationship['fromColumn'], 'currency')
            self.assertEqual(relationship['crossFilteringBehavior'], 'oneDirection')
            self.assertEqual(relationship['fromCardinality'], 'many')
            self.assertEqual(relationship['toCardinality'], 'one')
            self.assertIn(relationship['fromTable'], {'Ledger', 'BankBatches', 'Exceptions'})
        self.assertEqual(len(self.tables['Metrics']['measures']), 21)
        for table in self.tables.values():
            for column in table['columns']:
                if column['dataType'] in {'decimal', 'int64'}:
                    self.assertEqual(column['summarizeBy'], 'none')

    def test_download_archive_contains_current_complete_project(self):
        path = PBI / 'BankingReconciliation-PowerBI.zip'
        with zipfile.ZipFile(path) as archive:
            self.assertIsNone(archive.testzip())
            names = set(archive.namelist())
            self.assertIn('BankingReconciliation.pbip', names)
            self.assertIn('README.md', names)
            self.assertFalse(any(name.lower().endswith('.pbix') for name in names))
            for source in PBI.rglob('*'):
                if source.is_file() and source != path and '.pbi' not in source.parts and source.suffix.lower() != '.pbix':
                    self.assertEqual(archive.read(source.relative_to(PBI).as_posix()), source.read_bytes())


if __name__ == '__main__':
    unittest.main()
