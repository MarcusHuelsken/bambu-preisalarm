#!/usr/bin/env python3
"""Verify independently observed gross EUR prices for the exact H2S 10W model.

Version 1.1.0. A green workflow or a manually entered offer is not live proof.
"""
import json
import sys
from pathlib import Path

VERSION = '1.1.0'
TRUSTED_MERCHANTS = frozenset({'reichelt elektronik', 'IGO3D', 'Polyfab3D', 'Conrad'})


def verified_live_offers(report):
    """Return validated live observations, excluding manual and ambiguous offers."""
    if not isinstance(report, dict) or not isinstance(report.get('offers'), list):
        return []
    from preischeck import target_variant
    result = []
    for offer in report['offers']:
        if not isinstance(offer, dict):
            continue
        amount = offer.get('price_cents')
        if (offer.get('source') != 'Live JSON-LD'
                or offer.get('merchant') not in TRUSTED_MERCHANTS
                or type(amount) is not int or not 50000 <= amount <= 2000000
                or not target_variant(offer.get('name', ''))
                or not isinstance(offer.get('link'), str)
                or not offer['link'].startswith('https://')
                or 'Bruttopreis' not in str(offer.get('price_basis', ''))):
            continue
        result.append(offer)
    return result


def main():
    try:
        report = json.loads(Path('output/preise.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        print(f'LIVE VERIFICATION FAILED: cannot read report: {exc}', file=sys.stderr)
        return 1
    offers = verified_live_offers(report)
    if not offers:
        print('LIVE VERIFICATION FAILED: no verified live gross EUR price for exact H2S Laser Full Combo 10W.', file=sys.stderr)
        return 1
    print(f'Live verification passed: {len(offers)} exact-model gross EUR offer(s); shipping may be unknown.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
