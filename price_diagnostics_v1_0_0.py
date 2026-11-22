#!/usr/bin/env python3
"""Offline diagnostics for H2S price reports, version 1.0.0.

Does not infer live price validity from successful GitHub Actions status.
"""
import argparse
import json
import sys
from pathlib import Path

VERSION = '1.0.0'


def analyze(report):
    if not isinstance(report, dict) or not isinstance(report.get('offers', []), list):
        raise ValueError('Invalid report format')
    verified = []
    for offer in report.get('offers', []):
        if not isinstance(offer, dict):
            continue
        price = offer.get('price_cents')
        basis = offer.get('price_basis', '')
        if (isinstance(price, int) and not isinstance(price, bool)
                and 50000 <= price <= 2000000
                and isinstance(basis, str)
                and basis.lower().startswith(('bruttopreis', 'gross price'))
                and isinstance(offer.get('link'), str)
                and offer['link'].startswith('https://')):
            verified.append(offer)
    lines = [f'H2S diagnostics v{VERSION}', f'Gross EUR price candidates: {len(verified)}']
    for row in report.get('diagnostics', []):
        if isinstance(row, dict):
            notes = row.get('notes', [])
            if not isinstance(notes, list):
                notes = [str(notes)]
            lines.append(f"{row.get('merchant', 'unknown')}: {row.get('offers', 0)} offers; "
                         + ('; '.join(map(str, notes)) or 'no reason recorded'))
    for error in report.get('errors', []):
        lines.append('Fetch/error: ' + str(error))
    lines.append('NOTICE: candidate values require live retailer verification; '
                 'shipping may be unknown')
    if not verified:
        lines.append('FAIL: no eligible gross EUR price found')
    return '\n'.join(lines), bool(verified)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', nargs='?', default='output/preise.json')
    args = parser.parse_args(argv)
    try:
        summary, ok = analyze(json.loads(Path(args.report).read_text(encoding='utf-8')))
    except (OSError, ValueError, TypeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2
    print(summary)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
