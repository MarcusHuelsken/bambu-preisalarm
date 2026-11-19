"""Offline tests for Bambu Preisalarm version 1.3.5."""
import unittest
import datetime as dt
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import preischeck as p


class Tests(unittest.TestCase):
    def test_manual_free_shipping_and_discount_precision(self):
        today = dt.date(2026, 11, 19)
        base = {'name': 'Bambu Lab H2S Laser Full Combo 10W', 'merchant': 'test',
                'link': 'https://example.com/h2s', 'price_eur': '1699.00',
                'shipping_eur': '0.00', 'discount_eur': '10.00',
                'vat_included': True, 'verified_on': today.isoformat()}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'offers.json'
            with patch.object(p, 'ROOT', Path(tmp)):
                path.write_text(json.dumps([base]), encoding='utf-8')
                errors = []
                offers = p.extra_offers(today, errors)
                self.assertEqual(errors, [])
                self.assertEqual(offers[0]['shipping_cents'], 0)
                self.assertEqual(offers[0]['total_cents'], 168900)
                base['discount_eur'] = '10.999'
                path.write_text(json.dumps([base]), encoding='utf-8')
                errors = []
                self.assertEqual(p.extra_offers(today, errors), [])
                self.assertTrue(errors)

    def test_conrad_source_exact_model_and_tax_guard(self):
        sources = [s for s in p.SOURCES if s['merchant'] == 'Conrad']
        self.assertEqual(len(sources), 1)
        self.assertIn('3466450.html', sources[0]['url'])
        self.assertEqual(sources[0]['kind'], 'gross')
        page = ('<script type="application/ld+json">'
                '{"@type":"Product","name":"Bambu Lab H2S Laser Full Combo 10 W",'
                '"offers":{"price":"1759.00","priceCurrency":"EUR"}}'
                '</script>')
        offers, notes = p.product_offers(page, sources[0])
        self.assertEqual(offers, [])
        self.assertTrue(notes)

    def test_model(self):
        self.assertTrue(p.target_variant('Bambu Lab H2S Laser Full Combo 10W'))
        for name in ('H2D Laser Full Combo 10W', 'H2S Laser Full Combo 40W', 'H2S Combo', 'H2S Laser Full Combo 10W Upgrade'):
            self.assertFalse(p.target_variant(name))

    def test_price(self):
        self.assertEqual(p.cents('1699.00'), 169900)
        self.assertIsNone(p.cents('1.699,00'))
        self.assertIsNone(p.cents('0'))

    def test_variant_not_mispriced(self):
        offers, warnings = p.product_offers('<html>€ 1.699,00</html>', {'kind': 'variant'})
        self.assertFalse(offers)
        self.assertTrue(warnings)

    def test_net_not_gross(self):
        page = '<script type="application/ld+json">{"@type":"Product","name":"H2S Laser Full Combo 10W","offers":{"price":"1427.73","priceCurrency":"EUR"}}</script>'
        offers, warnings = p.product_offers(page, {'kind': 'net', 'merchant': 'test', 'url': 'https://example.com'})
        self.assertFalse(offers)
        self.assertTrue(warnings)

    def test_ambiguous_tax_not_accepted(self):
        page = '<script type="application/ld+json">{"@type":"Product","name":"H2S Laser Full Combo 10W","offers":{"price":"1699.00","priceCurrency":"EUR"}}</script>'
        offers, warnings = p.product_offers(page, {'kind': 'gross', 'merchant': 'test', 'url': 'https://example.com'})
        self.assertFalse(offers)
        self.assertTrue(warnings)

    def test_verified_gross(self):
        page = '<script type="application/ld+json">{"@type":"Product","name":"H2S Laser Full Combo 10W","offers":{"price":"1699.00","priceCurrency":"EUR","valueAddedTaxIncluded":true}}</script>'
        offers, _ = p.product_offers(page, {'kind': 'gross', 'merchant': 'test', 'url': 'https://example.com'})
        self.assertEqual(offers[0]['price_cents'], 169900)
        self.assertIsNone(offers[0]['total_cents'])


if __name__ == '__main__':
    unittest.main()
