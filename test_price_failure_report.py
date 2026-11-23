import unittest

from price_failure_report_v1_0_0 import summarize


class DiagnosticsTests(unittest.TestCase):
    def test_failed_live_prices_explain_retailer(self):
        result = summarize({'offers': [], 'diagnostics': [
            {'merchant': 'Conrad', 'offers': 0, 'notes': ['VAT not confirmed']}
        ], 'errors': ['Reichelt: HTTP 403']})
        self.assertIn('Conrad: 0 candidate(s); VAT not confirmed', result)
        self.assertIn('Reichelt: HTTP 403', result)
        self.assertIn('Live-price check FAILED', result)

    def test_candidates_do_not_claim_verification(self):
        result = summarize({'offers': [{}], 'diagnostics': [], 'errors': []})
        self.assertIn('run verify_live.py', result)
        self.assertNotIn('Live-price check FAILED', result)

    def test_reject_malformed_report(self):
        with self.assertRaises(ValueError):
            summarize({'offers': {}})


if __name__ == '__main__':
    unittest.main()
