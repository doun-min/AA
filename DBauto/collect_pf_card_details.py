"""Collect a minimal SKU-to-PF-name/color mapping from Samsung PF cards."""

import os
import re
import time
from collections import Counter

# One complete Recommended traversal is enough for PF card details.
os.environ.setdefault("SAMSUNG_SORTS", "recommended")
os.environ.setdefault("SAMSUNG_QV_AUDIT_N", "0")
_SITE = (os.environ.get("SAMSUNG_SITE", "us") or "us").strip().lower()
os.environ.setdefault("SAMSUNG_OUTPUT", f"pf_card_details_{_SITE}.json")
os.environ.setdefault("SAMSUNG_RESUME_DIR", f"pf_card_details_resume_{_SITE}_v4")

import collect_pf_cta_labels as traversal  # noqa: E402
import verify_samsung_smartphones as core  # noqa: E402


DETAILS_SCHEMA_VERSION = 4


def _clean_color_label(value):
    value = " ".join(str(value or "").split()).strip(" ,-:")
    if not value:
        return None
    if ":" in value:
        value = value.split(":", 1)[1].strip()
    value = re.sub(r"^(?:select|choose)\s+", "", value, flags=re.I)
    value = re.sub(r"\s*[,\-]?\s*selected$", "", value, flags=re.I)
    return value.strip() or None


def _node_text(node):
    try:
        return _clean_color_label(node.text_content())
    except Exception:
        return None


def _slide_color_label(slide, button):
    # The color-name span follows the customer-facing locale more reliably than
    # analytics attributes such as data-chip-value or an-la.
    for selector in (
        "span.option-selector-v2__color-name",
        "span.option-selector-v2__size-text",
        "span.blind",
        "span.hidden",
    ):
        nodes = slide.locator(selector)
        for index in range(nodes.count()):
            label = _node_text(nodes.nth(index))
            if label and label.casefold() != "selected":
                return label, "card-label"
    for attribute, source in (
        ("aria-label", "aria-label"),
        ("title", "title"),
        ("data-chip-value", "data-chip-value"),
        ("data-chip-code", "data-chip-code"),
        ("an-la", "an-la"),
    ):
        node = button if attribute in {"aria-label", "title", "an-la"} else slide
        label = _clean_color_label(node.get_attribute(attribute))
        if label:
            return label, source
    return None, None


def _slide_key(slide, button):
    for node, attributes in (
        (slide, ("data-chip-code", "data-chip-value", "data-modelcode")),
        (button, ("data-chip-code", "data-chip-value", "data-modelcode", "id")),
    ):
        for attribute in attributes:
            value = str(node.get_attribute(attribute) or "").strip()
            if value:
                return f"{attribute}:{value}".casefold()
    label, _source = _slide_color_label(slide, button)
    return f"label:{label}".casefold() if label else None


def _color_options(card):
    wrap = card.locator("div.option-selector-v2__wrap--color-chip")
    if wrap.count() == 0:
        return []
    slides = wrap.locator("div.option-selector-v2__swiper-slide")
    options = []
    for index in range(slides.count()):
        slide = slides.nth(index)
        button = slide.locator("button.option-selector-v2__color").first
        if button.count() == 0:
            continue
        label, source = _slide_color_label(slide, button)
        options.append(
            {
                "index": index,
                "key": _slide_key(slide, button),
                "label": label,
                "label_source": source,
                "button": button,
            }
        )
    return options


def _selected_color(card):
    options = _color_options(card)
    wrap = card.locator("div.option-selector-v2__wrap--color-chip")
    slides = wrap.locator("div.option-selector-v2__swiper-slide")
    for option in options:
        slide = slides.nth(option["index"])
        button = slide.locator("button.option-selector-v2__color").first
        slide_classes = str(slide.get_attribute("class") or "").casefold()
        selected = (
            "is-checked" in slide_classes
            or str(button.get_attribute("aria-checked") or "").casefold() == "true"
            or str(button.get_attribute("aria-selected") or "").casefold() == "true"
            or button.get_attribute("checked") is not None
        )
        if selected:
            label, source = _slide_color_label(slide, button)
            return {
                "index": option["index"],
                "key": _slide_key(slide, button),
                "label": label,
                "label_source": source,
            }
    return None


def _select_color(page, card, option):
    if not core._click_chip(page, option["button"]):
        return None
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        selected = _selected_color(card)
        if selected and (
            (option["key"] and selected["key"] == option["key"])
            or selected["index"] == option["index"]
        ):
            return selected
        page.wait_for_timeout(100)
    return None


def _variant_record(
    page,
    card,
    color_name,
    representative_sku,
    representative_color,
    prev_code=None,
    color_source=None,
):
    try:
        sku, source, mismatch = core.read_variant_sku(page, card, prev_code)
    except Exception as exc:  # one broken option must not drop the entire PF
        core._close_quick_view(page)
        return {
            "sku": None,
            "display_name_pf": traversal.read_pf_display_name(card),
            "product_color_pf": color_name,
            "representative_sku": representative_sku,
            "representative_color_pf": representative_color,
            "color_label_source": color_source,
            "color_selection_verified": True,
            "details_schema_version": DETAILS_SCHEMA_VERSION,
            "error": f"{type(exc).__name__}: {exc}",
        }

    # Variant controls can change the displayed size/capacity name. Read it
    # only after read_variant_sku has observed the updated model code.
    record = {
        "sku": sku,
        "display_name_pf": traversal.read_pf_display_name(card),
        "product_color_pf": color_name,
        "representative_sku": representative_sku,
        "representative_color_pf": representative_color,
        "color_label_source": color_source,
        "color_selection_verified": True,
        "details_schema_version": DETAILS_SCHEMA_VERSION,
    }
    # These audit fields stay in checkpoints but are removed from final records.
    if source:
        record["sku_source"] = source
    if mismatch:
        record["sku_audit_mismatch"] = mismatch
    return record


def extract_card_options(page, card, _sort_type, _sorting_no):
    """Return one minimal record for every color/capacity option SKU."""
    records = []
    default_selection = _selected_color(card)
    default_color = default_selection.get("label") if default_selection else None
    default_source = (
        default_selection.get("label_source") if default_selection else None
    )
    codes = core._card_codes(card)
    representative_sku = max(set(codes), key=codes.count) if codes else None
    prev_code = representative_sku

    if core.DEFAULT_ONLY:
        if _color_options(card) and not default_selection:
            return [
                {
                    "sku": None,
                    "display_name_pf": traversal.read_pf_display_name(card),
                    "product_color_pf": None,
                    "representative_sku": representative_sku,
                    "representative_color_pf": None,
                    "color_selection_verified": False,
                    "details_schema_version": DETAILS_SCHEMA_VERSION,
                    "error": "default color selection could not be confirmed",
                }
            ]
        return [
            _variant_record(
                page,
                card,
                default_color,
                representative_sku,
                default_color,
                prev_code,
                default_source,
            )
        ]

    colors = _color_options(card)
    if not colors:
        colors = [{"label": None, "label_source": None, "button": None}]
    for option in colors:
        color_name = option.get("label")
        color_source = option.get("label_source")
        if option.get("button") is not None:
            selected = _select_color(page, card, option)
            if not selected:
                records.append(
                    {
                        "sku": None,
                        "display_name_pf": traversal.read_pf_display_name(card),
                        "product_color_pf": None,
                        "attempted_color_pf": color_name,
                        "representative_sku": representative_sku,
                        "representative_color_pf": default_color,
                        "color_selection_verified": False,
                        "details_schema_version": DETAILS_SCHEMA_VERSION,
                        "error": "color selection could not be confirmed",
                    }
                )
                continue
            color_name = selected.get("label")
            color_source = selected.get("label_source")

        capacities = core._chip_options(
            card, "option-selector-v2__wrap--capacity", "option-selector-v2__size"
        ) or [(None, None)]
        for _capacity, capacity_button in capacities:
            if core.MAX_COMBOS and len(records) >= core.MAX_COMBOS:
                return records
            if capacity_button is not None:
                core._click_chip(page, capacity_button)

            record = _variant_record(
                page,
                card,
                color_name,
                representative_sku,
                default_color,
                prev_code,
                color_source,
            )
            if record.get("sku"):
                prev_code = record["sku"]
            records.append(record)
    return records


def _most_common(records, key):
    values = [record.get(key) for record in records if record.get(key)]
    return Counter(values).most_common(1)[0][0] if values else None


def project_minimal_records(records):
    """Collapse repeated PF appearances to exactly three fields per SKU."""
    grouped = {}
    issue_count = 0
    for record in records:
        sku = str(record.get("sku") or "").strip().upper()
        if not sku:
            issue_count += bool(record.get("status") or record.get("error"))
            continue
        grouped.setdefault(sku, []).append(record)

    output = []
    name_conflicts = []
    color_conflicts = []
    representative_color_resolved = []
    majority_color_resolved = []
    unresolved_color_conflicts = []
    for sku, sku_records in grouped.items():
        names = {record.get("display_name_pf") for record in sku_records}
        colors = {record.get("product_color_pf") for record in sku_records}
        names.discard(None)
        colors.discard(None)
        if len(names) > 1:
            name_conflicts.append(sku)
        if len(colors) > 1:
            color_conflicts.append(sku)
            color_counts = Counter(
                record.get("product_color_pf")
                for record in sku_records
                if record.get("product_color_pf")
                and record.get("color_selection_verified", True)
            )
            ranked = color_counts.most_common()
            if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
                resolved_color = ranked[0][0]
                majority_color_resolved.append(sku)
                representative_records = []
            else:
                resolved_color = None
                representative_records = [
                    record
                    for record in sku_records
                    if str(record.get("representative_sku") or "").strip().upper()
                    == sku
                    and record.get("representative_color_pf") in color_counts
                ]
                resolved_color = _most_common(
                    representative_records, "representative_color_pf"
                )
                if resolved_color:
                    representative_color_resolved.append(sku)
                else:
                    unresolved_color_conflicts.append(sku)
        else:
            resolved_color = _most_common(sku_records, "product_color_pf")
        output.append(
            {
                "sku": sku,
                "display_name_pf": _most_common(sku_records, "display_name_pf"),
                "product_color_pf": resolved_color,
            }
        )

    metadata = {
        "raw_record_count": len(records),
        "unique_skus": len(output),
        "collection_issue_count": issue_count,
        "display_name_conflict_skus": name_conflicts,
        "product_color_conflict_skus": color_conflicts,
        "representative_color_resolved_skus": representative_color_resolved,
        "majority_color_resolved_skus": majority_color_resolved,
        "unresolved_color_conflict_skus": unresolved_color_conflicts,
    }
    return output, metadata


def checkpoint_is_details_only(records):
    """Reject checkpoints produced before verified, post-click color labels."""
    product_rows = [record for record in records if not record.get("status")]
    return not product_rows or all(
        record.get("details_schema_version") == DETAILS_SCHEMA_VERSION
        and "display_name_pf" in record
        and "product_color_pf" in record
        and "color_selection_verified" in record
        for record in product_rows
    )


def run():
    return traversal.run(
        extract_card_options=extract_card_options,
        output_transform=project_minimal_records,
        checkpoint_validator=checkpoint_is_details_only,
        mode="pf-card-details-only",
    )


if __name__ == "__main__":
    run()
