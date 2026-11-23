#!/usr/bin/env python3
"""Summarise H2S live-price diagnostics without claiming price verification.

Version 1.0.0. Standard library only; no network requests or email.
"""
import argparse
import json
import sys
from pathlib import Path

VERSION = '1.0.0'


def summarize(report):
    if not isinstance(report, dict):
        raise ValueError('Report root must be an object')
    offers = report.get('offers', [])
    diagnostics = report.get('diagnostics', [])
    errors = report.get('errors', [])
    if not isinstance(offers, list) or not isinstance(diagnostics, list) or not isinstance(errors, list):
        raise ValueError('Report offers, diagnostics and errors must be arrays')
    lines = [f'Price diagnostics v{VERSION}', f'Report version: {report.get("version", "unknown")}',
             f'Offers recorded: {len(offers)} (NOT proof of a live gross price)']
    for item in diagnostics:
        if not isinstance(item, dict):
            continue
        merchant = str(item.get('merchant', '?'))[:80]
        count = item.get('offers', '?')
        notes = item.get('notes', [])
        if not isinstance(notes, list):
            notes = []
        lines.append(f'{merchant}: {count} candidate(s); ' + '; '.join(str(x)[:160] for x in notes))
    for item in errors:
        lines.append('Fetch/error: ' + str(item)[:240])
    if not offers:
        lines.append('VERDICT: No verified offer in the report. Live-price check FAILED.')
    else:
        lines.append('VERDICT: Candidate offers exist; run verify_live.py for strict verification.')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', nargs='?', default='output/preise.json')
    args = parser.parse_args(argv)
    try:
        report = json.loads(Path(args.report).read_text(encoding='utf-8'))
        print(summarize(report))
        return 0
    except (OSError, ValueError) as exc:
        print(f'No usable diagnostics: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
