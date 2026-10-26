import argparse
from datetime import date
import json
from pathlib import Path

from .build import build
from .common import AS_OF, ROOT
from .generate import generate


def main():
    parser = argparse.ArgumentParser(description='Synthetic banking transactions and settlement reconciliation analytics')
    commands = parser.add_subparsers(dest='command', required=True)
    gen = commands.add_parser('generate', help='Regenerate the deterministic fictional input feeds')
    gen.add_argument('--data', type=Path, default=ROOT / 'data' / 'raw')
    gen.add_argument('--seed', type=int, default=20261026)
    gen.add_argument('--count', type=int, default=1200)
    run = commands.add_parser('build', help='Reconcile feeds and export dashboard/SQL/CSV artifacts')
    run.add_argument('--data', type=Path, default=ROOT / 'data' / 'raw')
    run.add_argument('--output', type=Path, default=ROOT / 'outputs')
    run.add_argument('--dashboard-json', type=Path, default=ROOT / 'docs' / 'data' / 'report.json')
    run.add_argument('--findings', type=Path, default=ROOT / 'docs' / 'findings.md')
    run.add_argument('--as-of', type=date.fromisoformat, default=AS_OF)
    run.add_argument('--grace-days', type=int, default=1)
    args = parser.parse_args()
    if args.command == 'generate':
        manifest = generate(args.data, args.seed, args.count)
        print(f"Generated {manifest['transaction_count']} fictional transactions (seed {args.seed}).")
    else:
        report = build(args.data, args.output, args.dashboard_json, args.findings, args.as_of, args.grace_days)
        print(json.dumps({'as_of': report['as_of'], 'metrics': report['metrics'],
                          'sql_queries_executed': report['sql_queries_executed']}, indent=2))


if __name__ == '__main__':
    main()
