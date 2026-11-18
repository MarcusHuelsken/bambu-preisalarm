import datetime as dt
import unittest
from unittest.mock import patch
import preischeck as p


class MonitorTests(unittest.TestCase):
    def test_target_only(self):
        self.assertTrue(p.target_variant('Bambu Lab H2S – Laser Full Combo – 10 W'))
        for name in ('H2S Combo', 'H2D Laser Full Combo 10W', 'H2S Laser Full Combo 40W',
                     'H2S Laser Module Only 10W', 'H2S Laser Full Combo 10W Upgrade Kit'):
            self.assertFalse(p.target_variant(name), name)

    def test_cents(self):
        self.assertEqual(p.cents('1499.00'), 149900)
        for invalid in ('1.499,00', '-1', 'nan', True, '12.345'):
            self.assertIsNone(p.cents(invalid))

    def test_product_filter(self):
        data = {'products': [{'title': 'H2S', 'handle': 'h2s', 'variants': [
            {'title': 'Laser Full Combo 10W', 'price': '1499.00', 'id': 1, 'available': True},
            {'title': 'Combo', 'price': '1199.00', 'id': 2},
            {'title': 'Laser Full Combo 40W', 'price': '1899.00', 'id': 3}]}]}
        rows = p.parse_shopify(data, 'fixture-not-live')
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['price_cents'], 149900)
        self.assertIsNone(rows[0]['total_cents'])

    def test_change_basis_does_not_compare_total_to_product(self):
        rows = [{'id': 'x', 'price_cents': 150000, 'total_cents': None}]
        p.attach_changes(rows, {'x': {'price_cents': 149000, 'total_cents': 153000}})
        self.assertEqual(rows[0]['change_cents'], 1000)
        self.assertEqual(rows[0]['change_basis'], 'Geraetepreis (ohne Versand)')

    def test_endprice_change(self):
        rows = [{'id': 'x', 'price_cents': 150000, 'total_cents': 151000}]
        p.attach_changes(rows, {'x': {'price_cents': 149000, 'total_cents': 153000}})
        self.assertEqual(rows[0]['change_cents'], -2000)
        self.assertEqual(rows[0]['change_basis'], 'Endpreis')

    def test_official_endpoint_fallback(self):
        def fake(url):
            if '/collections/' in url:
                raise OSError('blocked')
            return ({'products': [{'title': 'H2S', 'handle': 'h2s', 'variants': [
                {'title': 'Laser Full Combo 10W', 'price': '1499.00'}]}]}, url)
        errors, diagnostics = [], []
        with patch.object(p, 'get_json', side_effect=fake):
            rows = p.official_offers(errors, diagnostics)
        self.assertEqual(len(rows), 1)
        self.assertTrue(errors)

    def test_no_invented_total(self):
        self.assertEqual(p.money(None), 'unbekannt')
        self.assertEqual(p.money(149900), '1.499,00 €')


if __name__ == '__main__':
    unittest.main()
