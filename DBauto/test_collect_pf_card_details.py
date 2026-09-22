import unittest

from collect_pf_card_details import (
    DETAILS_SCHEMA_VERSION,
    _clean_color_label,
    checkpoint_is_details_only,
    project_minimal_records,
)


class PFCardDetailsTests(unittest.TestCase):
    def test_rejects_pre_v4_checkpoint(self):
        self.assertFalse(
            checkpoint_is_details_only(
                [{
                    "sku": "SKU-1",
                    "display_name_PF": "Old schema",
                    "product_color": "Black",
                }]
            )
        )
        self.assertTrue(
            checkpoint_is_details_only(
                [{
                    "sku": "SKU-1",
                    "display_name_pf": "New schema",
                    "product_color_pf": "Black",
                    "color_selection_verified": True,
                    "details_schema_version": DETAILS_SCHEMA_VERSION,
                }]
            )
        )
        self.assertFalse(
            checkpoint_is_details_only(
                [{
                    "sku": "SKU-1",
                    "display_name_pf": "Missing verification",
                    "product_color_pf": "Black",
                    "details_schema_version": DETAILS_SCHEMA_VERSION,
                }]
            )
        )

    def test_outputs_exactly_three_fields_per_sku(self):
        records = [
            {
                "sku": "sku-1",
                "display_name_pf": "Galaxy Example",
                "product_color_pf": "Black",
                "category": "ignored",
            },
            {
                "sku": "SKU-1",
                "display_name_pf": "Galaxy Example",
                "product_color_pf": "Black",
            },
        ]
        output, metadata = project_minimal_records(records)
        self.assertEqual(
            output,
            [{
                "sku": "SKU-1",
                "display_name_pf": "Galaxy Example",
                "product_color_pf": "Black",
            }],
        )
        self.assertEqual(metadata["unique_skus"], 1)
        self.assertEqual(metadata["display_name_conflict_skus"], [])
        self.assertEqual(metadata["product_color_conflict_skus"], [])

    def test_reports_conflicting_pf_values(self):
        records = [
            {
                "sku": "SKU-1", "display_name_pf": "Name A",
                "product_color_pf": "Black", "representative_sku": "SKU-1",
                "representative_color_pf": "Blue",
            },
            {
                "sku": "SKU-1", "display_name_pf": "Name B",
                "product_color_pf": "Blue", "representative_sku": "SKU-1",
                "representative_color_pf": "Blue",
            },
        ]
        output, metadata = project_minimal_records(records)
        self.assertEqual(metadata["display_name_conflict_skus"], ["SKU-1"])
        self.assertEqual(metadata["product_color_conflict_skus"], ["SKU-1"])
        self.assertEqual(metadata["representative_color_resolved_skus"], ["SKU-1"])
        self.assertEqual(metadata["unresolved_color_conflict_skus"], [])
        self.assertEqual(output[0]["product_color_pf"], "Blue")

    def test_majority_verified_color_beats_representative_tie_breaker(self):
        records = [
            {
                "sku": "SKU-1", "display_name_pf": "Name",
                "product_color_pf": "Black", "representative_sku": "SKU-1",
                "representative_color_pf": "Blue", "color_selection_verified": True,
            },
            {
                "sku": "SKU-1", "display_name_pf": "Name",
                "product_color_pf": "Black", "representative_sku": "SKU-1",
                "representative_color_pf": "Blue", "color_selection_verified": True,
            },
            {
                "sku": "SKU-1", "display_name_pf": "Name",
                "product_color_pf": "Blue", "representative_sku": "SKU-1",
                "representative_color_pf": "Blue", "color_selection_verified": True,
            },
        ]
        output, metadata = project_minimal_records(records)
        self.assertEqual(output[0]["product_color_pf"], "Black")
        self.assertEqual(metadata["majority_color_resolved_skus"], ["SKU-1"])
        self.assertEqual(metadata["representative_color_resolved_skus"], [])

    def test_cleans_accessible_color_label(self):
        self.assertEqual(
            _clean_color_label("Color: Titanium Gray, selected"),
            "Titanium Gray",
        )



if __name__ == "__main__":
    unittest.main()
