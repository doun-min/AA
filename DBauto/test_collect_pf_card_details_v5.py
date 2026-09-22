import unittest

from collect_pf_card_details_v5 import (
    DETAILS_SCHEMA_VERSION,
    checkpoint_is_v5,
    project_v5_records,
)


class PFCardDetailsV5Tests(unittest.TestCase):
    def test_projects_both_sorts_and_key_model(self):
        records = [
            {
                "sku": "sku-1", "display_name_pf": "Phone", "product_color_pf": "Black",
                "sort_type": "recommended", "sorting_no": 3, "key_model_yn": "Y",
                "source_pf_url": "/us/phones", "category": "Phones",
            },
            {
                "sku": "sku-1", "display_name_pf": "Phone", "product_color_pf": "Black",
                "sort_type": "newest", "sorting_no": 7, "key_model_yn": "Y",
                "source_pf_url": "/us/phones", "category": "Phones",
            },
        ]
        output, metadata = project_v5_records(records)
        self.assertEqual(len(output), 2)
        self.assertEqual(
            {(row["sort_type"], row["sorting_no"]) for row in output},
            {("recommended", 3), ("newest", 7)},
        )
        self.assertTrue(all(row["key_model_yn"] == "Y" for row in output))
        self.assertEqual(metadata["key_model_conflicts"], [])

    def test_keeps_same_sku_positions_from_different_pf_pages(self):
        records = [
            {
                "sku": "SKU-1", "display_name_pf": "Phone", "product_color_pf": "Black",
                "sort_type": "recommended", "sorting_no": 2, "key_model_yn": "N",
                "source_pf_url": "/us/all-phones",
            },
            {
                "sku": "SKU-1", "display_name_pf": "Phone", "product_color_pf": "Black",
                "sort_type": "recommended", "sorting_no": 1, "key_model_yn": "N",
                "source_pf_url": "/us/galaxy-phones",
            },
        ]
        output, _metadata = project_v5_records(records)
        self.assertEqual(len(output), 2)

    def test_rejects_v4_checkpoint(self):
        self.assertFalse(checkpoint_is_v5([{
            "sku": "SKU-1",
            "details_schema_version": 4,
            "display_name_pf": "Phone",
        }]))
        self.assertTrue(checkpoint_is_v5([{
            "sku": "SKU-1",
            "details_schema_version": DETAILS_SCHEMA_VERSION,
            "sort_type": "recommended",
            "sorting_no": 1,
            "key_model_yn": "Y",
        }]))

    def test_rejects_checkpoint_without_untouched_key_model(self):
        self.assertFalse(checkpoint_is_v5([{
            "sku": "SKU-2",
            "details_schema_version": DETAILS_SCHEMA_VERSION,
            "sort_type": "recommended",
            "sorting_no": 1,
            "cardidx": "0",
            "key_model_yn": "N",
        }]))


if __name__ == "__main__":
    unittest.main()
