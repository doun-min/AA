import unittest

import verify_samsung_smartphones as collector


class PFCTADetectionTests(unittest.TestCase):
    def test_recognizes_english_transactional_labels(self):
        for label in (
            "Buy",
            "Buy now",
            "Add to cart",
            "Where to buy",
            "Notify me",
            "Pre-order",
        ):
            with self.subTest(label=label):
                self.assertIsNotNone(collector.PF_CTA_TERMS.search(label))

    def test_recognizes_french_transactional_labels(self):
        for label in (
            "Acheter",
            "Acheter maintenant",
            "Ajouter au panier",
            "Où acheter",
            "M'avertir",
        ):
            with self.subTest(label=label):
                self.assertIsNotNone(collector.PF_CTA_TERMS.search(label))

    def test_includes_us_cta_container(self):
        self.assertIn("pd21-product-card__cta-container", collector.PF_CTA_SELECTOR)


if __name__ == "__main__":
    unittest.main()
