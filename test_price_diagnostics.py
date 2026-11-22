"""Offline unit tests for versioned live price diagnostics."""
import unittest
from price_diagnostics_v1_0_0 import analyze


class PriceDiagnosticsTests(unittest.TestCase):
    def test_missing_prices_fail_and_explain_merchant(self):
        summary, ok = analyze({'offers': [], 'diagnostics': [
            {'merchant': 'Conrad', 'offers': 0, 'notes': ['VAT not confirmed']}]})
        self.assertFalse(ok)
        self.assertIn('Conrad', summary)
        self.assertIn('VAT not confirmed', summary)

    def test_valid_gross_candidate_not_final_price(self):
        summary, ok = analyze({'offers': [{
            'price_cents': 159900, 'price_basis': 'Bruttopreis; Versand unbekannt',
            'link': 'https://example.org'}]})
        self.assertTrue(ok)
        self.assertIn('shipping may be unknown', summary)

    def test_net_price_not_accepted(self):
        _, ok = analyze({'offers': [{
            'price_cents': 130000, 'price_basis': 'Nettopreis',
            'link': 'https://example.org'}]})
        self.assertFalse(ok)

    def test_invalid_format_rejected(self):
        with self.assertRaises(ValueError):
            analyze({'offers': 'invalid'})


if __name__ == '__main__':
    unittest.main()
