import unittest
import preischeck as p

class MonitorTests(unittest.TestCase):
    def test_target_only(self):
        self.assertTrue(p.target_variant('H2S Laser Full Combo 10W'))
        self.assertTrue(p.target_variant('Bambu Lab H2S – Laser Full Combo – 10 W'))
        for name in ('H2S Combo', 'H2D Laser Full Combo 10W', 'H2S Laser Full Combo 40W',
                     'H2S Laser Module Only 10W', 'H2S Laser Full Combo 10W Upgrade Kit'):
            self.assertFalse(p.target_variant(name), name)

    def test_cents(self):
        self.assertEqual(p.cents('1499.00'), 149900)
        self.assertEqual(p.cents('75'), 7500)
        self.assertIsNone(p.cents('1.499,00'))

    def test_product_filter(self):
        data = {'products': [{'title': 'H2S', 'handle': 'h2s', 'variants': [
            {'title': 'Laser Full Combo 10W', 'price': '1499.00', 'id': 1, 'available': True},
            {'title': 'Combo', 'price': '1199.00', 'id': 2},
            {'title': 'Laser Full Combo 40W', 'price': '1899.00', 'id': 3}]}]}
        offers = p.parse_shopify(data, 'test-source')
        self.assertEqual(len(offers), 1)
        self.assertEqual(offers[0]['price_cents'], 149900)
        self.assertIsNone(offers[0]['total_cents'])

if __name__ == '__main__':
    unittest.main()
