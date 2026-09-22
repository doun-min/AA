"""Collect PF details plus Recommended/Newest order and untouched key model."""

import os
from collections import Counter


os.environ.setdefault("SAMSUNG_SORTS", "recommended,newest")
os.environ.setdefault("SAMSUNG_QV_AUDIT_N", "0")
_SITE = (os.environ.get("SAMSUNG_SITE", "us") or "us").strip().lower()
os.environ.setdefault("SAMSUNG_OUTPUT", f"pf_card_details_{_SITE}_v5.json")
os.environ.setdefault("SAMSUNG_RESUME_DIR", f"pf_card_details_resume_{_SITE}_v5")

import collect_pf_card_details as v4  # noqa: E402
import collect_pf_cta_labels as traversal  # noqa: E402
import verify_samsung_smartphones as core  # noqa: E402


DETAILS_SCHEMA_VERSION = 5


def _normalized_sku(value):
    return str(value or "").strip().upper()


def _initial_card_sku(page, card):
    """Read the untouched card SKU before any color/capacity interaction."""
    try:
        sku, source, mismatch = core.read_variant_sku(page, card, prev_code=None)
        return _normalized_sku(sku), source, mismatch, None
    except Exception as exc:  # keep the PF scan alive and retain audit context
        core._close_quick_view(page)
        codes = [_normalized_sku(value) for value in core._card_codes(card)]
        codes = [value for value in codes if value]
        fallback = Counter(codes).most_common(1)[0][0] if codes else None
        return fallback, "initial-dom-fallback" if fallback else None, None, (
            f"{type(exc).__name__}: {exc}"
        )


def extract_card_options(page, card, sort_type, sorting_no):
    initial_sku, initial_source, initial_mismatch, initial_error = _initial_card_sku(
        page, card
    )
    default_selection = v4._selected_color(card)
    default_color = default_selection.get("label") if default_selection else None
    initial_record = {
        "sku": initial_sku,
        "display_name_pf": traversal.read_pf_display_name(card),
        "product_color_pf": default_color,
        "representative_sku": initial_sku,
        "representative_color_pf": default_color,
        "color_label_source": (
            default_selection.get("label_source") if default_selection else None
        ),
        "color_selection_verified": default_selection is not None,
        "details_schema_version": DETAILS_SCHEMA_VERSION,
    }
    records = v4.extract_card_options(page, card, sort_type, sorting_no)
    # Preserve the untouched state as its own observation. This guarantees the
    # key model is retained even when a capped test run does not later revisit
    # the initially selected color/capacity combination.
    if initial_sku:
        records.insert(0, initial_record)
    normalized_sort = str(sort_type or "").strip().casefold()

    for record in records:
        sku = _normalized_sku(record.get("sku"))
        record.update({
            "representative_sku": initial_sku,
            "sort_type": normalized_sort,
            "sorting_no": sorting_no,
            "key_model_yn": "Y" if sku and sku == initial_sku else "N",
            "details_schema_version": DETAILS_SCHEMA_VERSION,
        })
        if initial_source:
            record["initial_sku_source"] = initial_source
        if initial_mismatch:
            record["initial_sku_audit_mismatch"] = initial_mismatch
        if initial_error:
            record["initial_sku_error"] = initial_error
    return records


def _most_common(records, field):
    values = [record.get(field) for record in records if record.get(field) is not None]
    return Counter(values).most_common(1)[0][0] if values else None


def annotate_sort_presence(records, metadata):
    """Label one-sort SKUs without requiring another PF crawl."""
    sorts_by_sku = {}
    for record in records:
        sku = _normalized_sku(record.get("model_code") or record.get("sku"))
        sort_type = str(record.get("sort_type") or "").strip().casefold()
        if sku and sort_type in {"recommended", "newest"}:
            sorts_by_sku.setdefault(sku, set()).add(sort_type)

    for record in records:
        sku = _normalized_sku(record.get("model_code") or record.get("sku"))
        sort_type = str(record.get("sort_type") or "").strip().casefold()
        sorts = sorts_by_sku.get(sku, set())
        if sort_type in {"recommended", "newest"}:
            record["sort_presence"] = (
                "both" if sorts == {"recommended", "newest"}
                else f"{sort_type}_only"
            )

    recommended_skus = {
        sku for sku, sorts in sorts_by_sku.items() if "recommended" in sorts
    }
    newest_skus = {sku for sku, sorts in sorts_by_sku.items() if "newest" in sorts}
    metadata["recommended_only_skus"] = sorted(recommended_skus - newest_skus)
    metadata["newest_only_skus"] = sorted(newest_skus - recommended_skus)
    metadata["both_sort_sku_count"] = len(recommended_skus & newest_skus)
    return {
        "recommended_only": len(recommended_skus - newest_skus),
        "newest_only": len(newest_skus - recommended_skus),
        "both": len(recommended_skus & newest_skus),
    }


def project_v5_records(records):
    """Keep one auditable SKU observation per PF, sort, and card position."""
    base_records, base_metadata = v4.project_minimal_records(records)
    base_by_sku = {record["sku"]: record for record in base_records}
    grouped = {}
    issue_count = 0

    for record in records:
        sku = _normalized_sku(record.get("sku"))
        sort_type = str(record.get("sort_type") or "").strip().casefold()
        source_pf_url = str(record.get("source_pf_url") or "").strip()
        try:
            sorting_no = int(record.get("sorting_no"))
        except (TypeError, ValueError):
            sorting_no = None
        if not sku or sort_type not in {"recommended", "newest"} or sorting_no is None:
            issue_count += bool(record.get("status") or record.get("error") or sku)
            continue
        key = (sku, sort_type, source_pf_url, sorting_no)
        grouped.setdefault(key, []).append(record)

    output = []
    key_model_conflicts = []
    for (sku, sort_type, source_pf_url, sorting_no), observations in grouped.items():
        flags = {record.get("key_model_yn") for record in observations}
        flags.discard(None)
        if len(flags) > 1:
            key_model_conflicts.append({
                "model_code": sku,
                "sort_type": sort_type,
                "source_pf_url": source_pf_url,
                "sorting_no": sorting_no,
                "values": sorted(flags),
            })
        base = base_by_sku.get(sku, {})
        output.append({
            "sku": sku,
            "model_code": sku,
            "display_name_pf": base.get("display_name_pf"),
            "product_color_pf": base.get("product_color_pf"),
            "sort_type": sort_type,
            "sorting_no": sorting_no,
            "key_model_yn": "Y" if "Y" in flags else "N",
            "source_pf_url": source_pf_url or None,
            "category": _most_common(observations, "category"),
            "category_url": _most_common(observations, "category_url"),
        })

    output.sort(key=lambda row: (
        row["source_pf_url"] or "",
        row["sort_type"],
        row["sorting_no"],
        row["model_code"],
    ))
    metadata = {
        **base_metadata,
        "details_schema_version": DETAILS_SCHEMA_VERSION,
        "observation_count": len(output),
        "v5_collection_issue_count": issue_count,
        "key_model_conflicts": key_model_conflicts,
        "key_model_definition": "Y only when SKU equals the untouched initial card SKU",
    }
    annotate_sort_presence(output, metadata)
    return output, metadata


def checkpoint_is_v5(records):
    product_rows = [record for record in records if not record.get("status")]
    if not product_rows:
        return True
    fields_valid = all(
        record.get("details_schema_version") == DETAILS_SCHEMA_VERSION
        and record.get("sort_type") in {"recommended", "newest"}
        and record.get("sorting_no") is not None
        and record.get("key_model_yn") in {"Y", "N"}
        for record in product_rows
    )
    if not fields_valid:
        return False
    groups = {}
    for record in product_rows:
        key = (record.get("sort_type"), str(record.get("cardidx", "")))
        groups.setdefault(key, []).append(record)
    return all(
        any(record.get("key_model_yn") == "Y" for record in group)
        for group in groups.values()
    )


def run():
    return traversal.run(
        extract_card_options=extract_card_options,
        output_transform=project_v5_records,
        checkpoint_validator=checkpoint_is_v5,
        mode="pf-card-details-v5-sorting-key-model",
    )


if __name__ == "__main__":
    run()
