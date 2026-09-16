import unittest
import json
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from verify_cta_labels import (
    extract_from_html,
    labels_match,
    load_pf_data,
    normalize_label,
    with_model_code,
)


class CTALabelTests(unittest.TestCase):
    def test_react_pdp_cta(self):
        html = '<button class="Summary_ctaATCButton Button_disable" disabled aria-label="Add to cart">Add to cart</button>'
        result = extract_from_html(html, "Notify Me")
        self.assertEqual(result["actual_cta"], "Add to cart")
        self.assertFalse(result["enabled"])

    def test_disabled_state_does_not_change_label(self):
        html = '<button class="Summary_ctaATCButton Button_disable" disabled>Notify Me</button>'
        result = extract_from_html(html, "Notify Me")
        self.assertEqual(normalize_label(result["actual_cta"]), normalize_label("Notify Me"))

    def test_flagship_cta_and_normalization(self):
        html = '<a class="floating-navigation__button" href="/buy/">Buy now</a>'
        result = extract_from_html(html, "Buy Now")
        self.assertEqual(normalize_label(result["actual_cta"]), normalize_label("Buy Now"))
        self.assertTrue(result["enabled"])

    def test_ignores_global_cart(self):
        html = '<a class="utility-cart" href="https://shop.samsung.com/us/cart">Cart</a>'
        self.assertIsNone(extract_from_html(html)["actual_cta"])

    def test_ignores_generic_menu_button(self):
        html = '<button role="button" class="nv00-gnb-v4__utility">Open My Menu</button>'
        self.assertIsNone(extract_from_html(html)["actual_cta"])

    def test_ignores_ca_fr_global_buy_direct_promotion(self):
        html = (
            '<a class="nv00-gnb-v4__l1-featured-link" '
            'href="/ca_fr/buy-direct-get-more/">'
            'Achetez directement obtenez plus</a>'
        )
        self.assertIsNone(extract_from_html(html)["actual_cta"])

    def test_ignores_faq_question_containing_buy(self):
        html = (
            '<button role="button">What accessories can I buy for my phone?</button>'
            '<button role="button">Add to cart</button>'
        )
        self.assertEqual(extract_from_html(html)["actual_cta"], "Add to cart")

    def test_applies_column_b_model_code_to_url(self):
        url = "https://www.samsung.com/us/example/?modelCode=OLD&foo=1"
        result = with_model_code(url, "SM-S938UZKAXAA")
        query = parse_qs(urlsplit(result).query)
        self.assertEqual(query["modelCode"], ["SM-S938UZKAXAA"])
        self.assertEqual(query["foo"], ["1"])

    def test_ca_fr_english_and_french_ctas_are_equivalent(self):
        pairs = (
            ("Add to cart", "Ajouter au panier"),
            ("Where to Buy", "Où acheter"),
            ("Notify Me", "Avisez-moi"),
            ("Buy now", "Acheter maintenant"),
            ("Buy", "Achetez"),
            ("Pre order", "Précommander"),
        )
        for expected, actual in pairs:
            with self.subTest(expected=expected, actual=actual):
                self.assertTrue(labels_match(actual, expected, "ca_fr"))

    def test_ca_fr_buy_and_buy_now_remain_different(self):
        self.assertFalse(labels_match("Acheter maintenant", "Buy", "ca_fr"))

    def test_pf_data_uses_new_cta_records_and_ignores_legacy_records(self):
        payload = {"records": [
            {
                "sku": "SKU-NEW", "source_pf_url": "/ca_fr/test/all-products",
                "pf_cta_label": "Ajouter au panier", "pf_cta_class": "js-cta-addon",
                "pf_cta_enabled": True, "sort_type": "Recommended",
            },
            {"sku": "SKU-OLD", "source_pf_url": "/ca_fr/test/all-products"},
        ]}
        with patch("pathlib.Path.read_text", return_value=json.dumps(payload)):
            records, ignored, conflicts = load_pf_data(["pf.json"])
        self.assertIn(("ca_fr", "SKU-NEW"), records)
        self.assertNotIn(("ca_fr", "SKU-OLD"), records)
        self.assertEqual(records[("ca_fr", "SKU-NEW")]["actual_cta"], "Ajouter au panier")
        self.assertEqual(ignored, 1)
        self.assertEqual(conflicts, 0)


if __name__ == "__main__":
    unittest.main()
