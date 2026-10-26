"""Validate PBIP/PBIR JSON using Microsoft's versioned official schema mirror.

This does not execute Power Query or DAX and does not replace Power BI Desktop.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urldefrag, urljoin
import urllib.request

from jsonschema import Draft7Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent.parent
PREFIX = 'https://developer.microsoft.com/json-schemas/'
MIRROR = 'https://raw.githubusercontent.com/microsoft/json-schemas/main/'


def refs(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == '$ref':
                yield child
            else:
                yield from refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from refs(child)


def validate_project(cache):
    files = []
    for path in (ROOT / 'powerbi').rglob('*'):
        if path.suffix in {'.pbip', '.pbir', '.pbism', '.json'} and path.is_file():
            value = json.loads(path.read_text())
            if '$schema' in value:
                files.append((path, value))
    queue = [value['$schema'] for _, value in files]
    schemas = {}
    while queue:
        uri = queue.pop()
        if uri in schemas:
            continue
        if not uri.startswith(PREFIX):
            raise ValueError('Unexpected schema authority: ' + uri)
        relative = uri.removeprefix(PREFIX)
        if '..' in Path(relative).parts:
            raise ValueError('Invalid schema path')
        local = cache / relative
        if local.exists():
            schema = json.loads(local.read_text())
        else:
            with urllib.request.urlopen(MIRROR + relative, timeout=30) as response:
                schema = json.load(response)
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text(json.dumps(schema, indent=2) + '\n')
        schemas[uri] = schema
        for ref in refs(schema):
            target = urldefrag(urljoin(uri, ref))[0]
            if target not in schemas:
                queue.append(target)
    registry = Registry().with_resources((uri, Resource.from_contents(schema)) for uri, schema in schemas.items())
    failures = []
    for path, value in files:
        validator = Draft7Validator(schemas[value['$schema']], registry=registry)
        for error in validator.iter_errors(value):
            failures.append(f'{path.relative_to(ROOT)}:{list(error.absolute_path)}: {error.message}')
    if failures:
        raise ValueError('\n'.join(failures))
    print(f'Validated {len(files)} PBIP/PBIR documents against {len(schemas)} official Microsoft schemas.')
    print('Validation scope: PBIP/PBIR JSON schemas. Desktop refresh, DAX evaluation, visual review, and KPI reconciliation are separate acceptance checks.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schema-cache', type=Path, default=ROOT / 'outputs' / 'pbir-schemas')
    args = parser.parse_args()
    validate_project(args.schema_cache)
