"""Offline tests for Bambu Preisalarm version 1.3.3."""
import unittest
import preischeck as p


class Tests(unittest.TestCase):
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
