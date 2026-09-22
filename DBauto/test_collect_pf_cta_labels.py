import unittest

import collect_pf_cta_labels as details_collector
import verify_samsung_smartphones as collector


class PFCTADetectionTests(unittest.TestCase):
    def test_prefers_complete_pf_display_name(self):
        self.assertEqual(
            details_collector.select_pf_display_name(
                ["65-inch Neo QLED 8K...", "65-inch Neo QLED 8K Smart TV"]
            ),
            "65-inch Neo QLED 8K Smart TV",
        )
        self.assertEqual(
            details_collector.select_pf_display_name(["Galaxy S26 FE"]),
            "Galaxy S26 FE",
        )
        self.assertEqual(
            details_collector.select_pf_display_name([
                "Long Galaxy Product...\nLong Galaxy Product Full Name"
            ]),
            "Long Galaxy Product Full Name",
        )
        self.assertEqual(
            details_collector.select_pf_display_name([
                "Long Galaxy Product...\nA marketing tagline",
                "Long Galaxy Product Full Name",
            ]),
            "Long Galaxy Product Full Name",
        )

    def test_removes_model_code_from_accessible_name(self):
        self.assertEqual(
            details_collector._without_model_suffix(
                "Galaxy S26 FE. SM-S741WLGAXAC", ["SM-S741WLGAXAC"]
            ),
            "Galaxy S26 FE",
        )

    def test_old_checkpoints_are_rescanned_for_display_names(self):
        self.assertFalse(
            details_collector._checkpoint_has_display_names(
                [{"sku": "OLD", "product_color": "Black"}]
            )
        )
        self.assertTrue(
            details_collector._checkpoint_has_display_names(
                [{"sku": "NEW", "display_name_PF": "Galaxy"}]
            )
        )

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
