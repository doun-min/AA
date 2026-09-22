"""Collect exact-SKU CTA labels from Samsung PF cards.

This is the lightweight companion to verify_samsung_smartphones.py. It keeps
the proven PF discovery, infinite-scroll, option-selection, and CTA selectors,
but omits price/review/image and sorting_no verification fields.
"""

import json
import os
import re
import sys
import time

# CTA verification needs one complete ordering, not two sorting snapshots.
os.environ.setdefault("SAMSUNG_SORTS", "recommended")
os.environ.setdefault("SAMSUNG_QV_AUDIT_N", "0")

import verify_samsung_smartphones as core  # noqa: E402
from playwright.sync_api import TimeoutError as PWTimeout  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


PF_CONTAINER_SELECTOR = ".js-pfv2-finder, .pd21-product-finder"
PF_DETECT_TIMEOUT_MS = int(os.environ.get("SAMSUNG_PF_DETECT_TIMEOUT_MS", "5000"))
VIRTUAL_MAX_PASSES = int(os.environ.get("SAMSUNG_VIRTUAL_MAX_PASSES", "500"))
VIRTUAL_STABLE_PASSES = int(os.environ.get("SAMSUNG_VIRTUAL_STABLE_PASSES", "5"))


def _clean_display_name(value):
    return " ".join(str(value or "").split()) or None


def _display_name_is_truncated(value):
    return bool(re.search(r"(?:\.{3}|\u2026)", value or ""))


def select_pf_display_name(candidates):
    """Prefer a complete PF name while retaining a truncated last resort."""
    truncated_fallback = None
    for raw_value in candidates:
        lines = []
        for line in str(raw_value or "").splitlines():
            line = _clean_display_name(line)
            if line and line not in lines:
                lines.append(line)
        if not lines:
            continue

        first = lines[0]
        if not _display_name_is_truncated(first):
            return first
        truncated_fallback = truncated_fallback or first

        # Some cards render a shortened visible line and an accessibility copy
        # of the complete name directly below it. Only accept a later line when
        # it begins with the same name prefix, not when it is a marketing tagline.
        prefix = re.split(r"(?:\.{3}|\u2026)", first, maxsplit=1)[0].strip()
        prefix = prefix[: min(len(prefix), 32)].casefold()
        for line in lines[1:]:
            if (
                prefix
                and line.casefold().startswith(prefix)
                and not _display_name_is_truncated(line)
            ):
                return line
    return truncated_fallback


def _without_model_suffix(value, model_codes):
    value = _clean_display_name(value)
    for model_code in sorted(set(model_codes), key=len, reverse=True):
        value = re.sub(
            rf"(?:[.\s|:-]+)?{re.escape(model_code)}\s*$",
            "",
            value or "",
            flags=re.I,
        ).strip(" .|:-")
    return value or None


def read_pf_display_name(card):
    """Read the complete name shown by a PF card across US/CA/CA-FR DOMs."""
    name_wrap = core.first_or_none(card, "div.pd21-product-card__name-wrap")
    name_link = core.first_or_none(
        card, "a.pd21-product-card__name, a.pd21-product-card__image-cta"
    )
    titled = core.first_or_none(
        card,
        "div.pd21-product-card__name-wrap [title], "
        "a.pd21-product-card__name[title]",
    )

    visible = name_wrap.inner_text() if name_wrap else None
    # CSS line-clamp does not shorten textContent. If the server emitted a
    # literal ellipsis, CA/CA-FR usually preserve the full name in aria-label,
    # while US exposes it as the analytics product-name parameter (pn).
    text_content = name_wrap.text_content() if name_wrap else None
    title = (
        (name_wrap.get_attribute("title") if name_wrap else None)
        or (titled.get_attribute("title") if titled else None)
        or (name_link.get_attribute("title") if name_link else None)
    )
    aria_label = (
        (name_wrap.get_attribute("aria-label") if name_wrap else None)
        or (name_link.get_attribute("aria-label") if name_link else None)
    )
    aria_label = _without_model_suffix(aria_label, core._card_codes(card))
    analytics_name = core._feedback_params(card).get("pn")

    return select_pf_display_name(
        (visible, title, aria_label, analytics_name, text_content)
    )


def _checkpoint_has_display_names(records):
    product_rows = [record for record in records if not record.get("status")]
    return not product_rows or all(
        "display_name_PF" in record or "display_name_pf" in record
        for record in product_rows
    )


def _write_json(path, data):
    """Atomically update a checkpoint so Ctrl+C cannot leave truncated JSON."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def _wait_for_pf_fast(page):
    """Return quickly for PDP/menu links while allowing lazy PF grids to start."""
    if page.locator(core.CARD_SELECTOR).count():
        return True

    try:
        page.wait_for_selector(PF_CONTAINER_SELECTOR, timeout=PF_DETECT_TIMEOUT_MS)
    except PWTimeout:
        return False

    core._trigger_lazy_load(page)
    return page.locator(core.CARD_SELECTOR).count() > 0


def _minimal_variant_record(
    page,
    card,
    sort_type,
    sorting_no,
    color_name,
    capacity,
    is_default,
    display_name_pf,
    prev_code=None,
):
    sku = source = None
    mismatch = None
    error = None
    try:
        sku, source, mismatch = core.read_variant_sku(page, card, prev_code)
    except Exception as exc:  # one broken option must not drop the PF
        error = f"{type(exc).__name__}: {exc}"
        core._close_quick_view(page)

    cta = core.read_pf_cta(card)
    model_code = core.read_card_modelcode(card)
    record = {
        "sku": sku,
        "sku_source": source,
        "model_code": model_code,
        "modelcode": model_code,
        "sort_type": sort_type,
        "sorting_no": sorting_no,
        "is_default": is_default,
        "display_name_PF": display_name_pf,
        "product_color": color_name,
        "capacity": capacity,
        **cta,
    }
    if mismatch:
        record["sku_audit_mismatch"] = mismatch
    if error:
        record["error"] = error
    return record


def _extract_card_options(page, card, sort_type, sorting_no):
    records = []
    display_name_pf = read_pf_display_name(card)
    default_color = core._checked_chip_value(
        card, "option-selector-v2__wrap--color-chip"
    )
    default_capacity = core._checked_chip_value(
        card, "option-selector-v2__wrap--capacity"
    )

    codes = core._card_codes(card)
    prev_code = max(set(codes), key=codes.count) if codes else None

    if core.DEFAULT_ONLY:
        return [
            _minimal_variant_record(
                page,
                card,
                sort_type,
                sorting_no,
                default_color,
                default_capacity,
                True,
                display_name_pf,
            )
        ]

    colors = core._chip_options(
        card, "option-selector-v2__wrap--color-chip", "option-selector-v2__color"
    ) or [(None, None)]

    for color_name, color_button in colors:
        if color_button is not None:
            core._click_chip(page, color_button)

        capacities = core._chip_options(
            card, "option-selector-v2__wrap--capacity", "option-selector-v2__size"
        ) or [(None, None)]

        for capacity, capacity_button in capacities:
            if core.MAX_COMBOS and len(records) >= core.MAX_COMBOS:
                return records
            if capacity_button is not None:
                core._click_chip(page, capacity_button)

            record = _minimal_variant_record(
                page,
                card,
                sort_type,
                sorting_no,
                color_name,
                capacity,
                color_name == default_color and capacity == default_capacity,
                display_name_pf,
                prev_code=prev_code,
            )
            if record.get("sku"):
                prev_code = record["sku"]
            records.append(record)
    return records


def _card_snapshots(page):
    """Return stable identities for the cards currently mounted in the DOM."""
    return page.locator(core.CARD_SELECTOR).evaluate_all(
        """(cards) => cards.map((card, domIndex) => {
            const compare = card.querySelector('input.pd21-product-card__compare-checkbox');
            const link = card.querySelector(
                'a.pd21-product-card__image-cta, a.pd21-product-card__name'
            );
            return {
                cardidx: card.getAttribute('data-cardidx'),
                productidx: card.getAttribute('data-productidx'),
                model: compare?.getAttribute('data-model-code') ||
                    compare?.getAttribute('data-modelcode') ||
                    link?.getAttribute('data-modelcode') || '',
                href: link?.getAttribute('href') || '',
                domIndex,
            };
        })"""
    )


def _snapshot_key(snapshot):
    if snapshot.get("cardidx") not in (None, ""):
        return f"cardidx:{snapshot['cardidx']}"
    if snapshot.get("productidx") not in (None, ""):
        return f"productidx:{snapshot['productidx']}"
    if snapshot.get("model"):
        return f"model:{snapshot['model']}"
    if snapshot.get("href"):
        return f"href:{snapshot['href']}"
    return f"dom:{snapshot.get('domIndex', 0)}"


def _snapshot_locator(page, snapshot):
    cardidx = snapshot.get("cardidx")
    if cardidx not in (None, ""):
        value = str(cardidx).replace('"', '\\"')
        return page.locator(f'{core.CARD_SELECTOR}[data-cardidx="{value}"]').first
    productidx = snapshot.get("productidx")
    if productidx not in (None, ""):
        value = str(productidx).replace('"', '\\"')
        return page.locator(f'{core.CARD_SELECTOR}[data-productidx="{value}"]').first
    return page.locator(core.CARD_SELECTOR).nth(snapshot.get("domIndex", 0))


def _visible_pf_view_more(page):
    candidates = page.locator(core.VIEW_MORE_SELECTOR)
    for index in range(candidates.count()):
        candidate = candidates.nth(index)
        try:
            classes = (candidate.get_attribute("class") or "").casefold()
            label = " ".join(candidate.inner_text().casefold().split())
            if "learn-more" in classes or label.startswith("en savoir plus"):
                continue
            if candidate.is_visible() and candidate.evaluate(
                "el => Boolean(el.closest('.js-pfv2-finder, .pd21-product-finder'))"
            ):
                return candidate
        except Exception:
            continue
    return None


def _advance_virtual_pf(page, previous_signature):
    """Advance a virtualized PF and report whether its viewport changed."""
    view_more = _visible_pf_view_more(page)
    if view_more is not None:
        try:
            print(
                "[scroll-action] click view-more "
                f"text={view_more.inner_text().strip()!r} "
                f"class={(view_more.get_attribute('class') or '')!r}",
                file=sys.stderr,
                flush=True,
            )
        except Exception:
            pass
        try:
            view_more.scroll_into_view_if_needed(timeout=2000)
            view_more.click(timeout=5000)
        except Exception:
            try:
                view_more.evaluate("el => el.click()")
            except Exception:
                pass

        # CA-FR replaces or appends the rendered batch asynchronously. Moving
        # its internal scroller during that replacement can leave the virtual
        # viewport blank, so a View More click and scrolling are separate steps.
        for _ in range(25):
            page.wait_for_timeout(400)
            try:
                signature = tuple(_snapshot_key(item) for item in _card_snapshots(page))
            except Exception:
                signature = ()
            if signature and signature != previous_signature:
                return True, False, _visible_pf_view_more(page) is not None
        return False, False, _visible_pf_view_more(page) is not None

    cards = page.locator(core.CARD_SELECTOR)
    at_bottom = False
    if cards.count():
        try:
            state = cards.last.evaluate(
                """(card) => {
                    card.scrollIntoView({block: 'end'});
                    const before = window.scrollY;
                    window.scrollBy(0, Math.max(window.innerHeight * 0.65, 600));
                    return {
                        atBottom: window.scrollY + window.innerHeight >=
                            document.documentElement.scrollHeight - 4,
                        moved: window.scrollY !== before,
                    };
                }"""
            )
            at_bottom = bool(state and state.get("atBottom"))
        except Exception:
            page.mouse.wheel(0, 1000)

    changed = False
    for _ in range(15):
        page.wait_for_timeout(400)
        try:
            signature = tuple(_snapshot_key(item) for item in _card_snapshots(page))
        except Exception:
            signature = ()
        if signature and signature != previous_signature:
            changed = True
            break
    return changed, at_bottom, view_more is not None


def _record_identity(record):
    sku = (record.get("sku") or record.get("model_code") or "").strip().upper()
    return (
        sku,
        str(record.get("cardidx", "")),
        str(record.get("product_color") or record.get("product_color_pf") or ""),
        str(record.get("capacity", "")),
    )


def _extract_pf_virtual(
    page,
    sort_type,
    progress=None,
    partial_path=None,
    initial_records=None,
    context=None,
    extract_card_options=None,
):
    """Collect a CA-FR virtual grid before each rendered batch is discarded."""
    context = context or {}
    target_cards = core._pf_result_count(page)
    if core.MAX_CARDS and target_cards:
        target_cards = min(target_cards, core.MAX_CARDS)
    if progress and target_cards:
        progress.set_cards(target_cards)

    initial_records = [
        dict(record) for record in (initial_records or []) if not record.get("status")
    ]
    records = [
        record for record in initial_records
        if str(record.get("sort_type") or "").casefold() == str(sort_type).casefold()
    ]
    other_sort_records = [
        record for record in initial_records
        if str(record.get("sort_type") or "").casefold() != str(sort_type).casefold()
    ]
    processed = {
        f"cardidx:{record['cardidx']}"
        for record in records
        if record.get("cardidx") not in (None, "")
    }
    identities = {_record_identity(record) for record in records}
    attempts = {}
    stable_passes = 0
    complete = False

    for batch in range(1, VIRTUAL_MAX_PASSES + 1):
        snapshots = _card_snapshots(page)
        signature = tuple(_snapshot_key(item) for item in snapshots)
        new_cards = 0

        for snapshot in snapshots:
            key = _snapshot_key(snapshot)
            if key in processed or attempts.get(key, 0) >= 3:
                continue
            if core.MAX_CARDS and len(processed) >= core.MAX_CARDS:
                complete = True
                break

            attempts[key] = attempts.get(key, 0) + 1
            card = _snapshot_locator(page, snapshot)
            try:
                if card.count() == 0:
                    raise RuntimeError("card was unmounted before extraction")
                try:
                    sorting_no = int(snapshot.get("cardidx")) + 1
                except (TypeError, ValueError):
                    sorting_no = len(processed) + 1
                extractor = extract_card_options or _extract_card_options
                card_records = extractor(
                    page,
                    card,
                    sort_type,
                    sorting_no,
                )
                if not any(
                    record.get("sku") or record.get("model_code")
                    for record in card_records
                ):
                    raise RuntimeError("card identity disappeared during extraction")
            except Exception as exc:
                print(
                    f"[card-retry] key={key} attempt={attempts[key]}/3 "
                    f"error={type(exc).__name__}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                core._close_quick_view(page)
                continue

            try:
                cardidx = int(snapshot.get("cardidx"))
            except (TypeError, ValueError):
                cardidx = snapshot.get("cardidx") or snapshot.get("productidx")
            for record in card_records:
                record["cardidx"] = cardidx
                record["pf_load_complete"] = False
                record.update(context)
                identity = _record_identity(record)
                if identity not in identities:
                    identities.add(identity)
                    records.append(record)
            processed.add(key)
            new_cards += 1

        if partial_path and new_cards:
            _write_json(partial_path, other_sort_records + records)

        print(
            f"[scroll] batch={batch} visible={len(snapshots)} "
            f"cards_seen={len(processed)}/{target_cards or '?'} "
            f"skus={len(records)} new_cards={new_cards}",
            file=sys.stderr,
            flush=True,
        )

        if target_cards and len(processed) >= target_cards:
            complete = True
            break
        if core.MAX_CARDS and len(processed) >= core.MAX_CARDS:
            complete = True
            break

        changed, at_bottom, had_view_more = _advance_virtual_pf(page, signature)
        if new_cards or changed:
            stable_passes = 0
        else:
            stable_passes += 1
        if (
            stable_passes >= VIRTUAL_STABLE_PASSES
        ):
            complete = target_cards is None and at_bottom and not had_view_more
            break

    for record in records:
        record["pf_load_complete"] = complete
    if partial_path:
        _write_json(partial_path, other_sort_records + records)
    return records, complete, len(processed), target_cards


def _scan_category(
    page,
    category,
    progress=None,
    partial_path=None,
    initial_records=None,
    extract_card_options=None,
):
    core.navigate_to_category(page, category)
    canonical = category.get("canon") or core._canon_url(category.get("href"))
    source_menus = [
        f'{source["l0"]}>{source["l1"]}' for source in category.get("sources", [])
    ]
    if not _wait_for_pf_fast(page):
        return (
            [
                {
                    "category": category["name"],
                    "category_url": category.get("href"),
                    "source_pf_url": canonical,
                    "source_menus": source_menus,
                    "status": "skipped: no product-finder grid",
                }
            ],
            True,
        )

    output = []
    resume_records = [
        dict(record) for record in (initial_records or []) if not record.get("status")
    ]
    complete = True
    context = {
        "category": category["name"],
        "category_url": category.get("href"),
        "source_pf_url": canonical,
        "source_menus": source_menus,
    }
    for sort_name, sort_code in core.SORT_SEQUENCE:
        try:
            applied = core.set_sort(page, sort_name, sort_code)
        except PWTimeout:
            applied = None
        if not applied:
            complete = False
            output.append(
                {
                    **context,
                    "status": f"incomplete: sort unavailable ({sort_code})",
                }
            )
            continue

        combined_initial = {}
        for record in resume_records + [row for row in output if not row.get("status")]:
            identity = (
                str(record.get("sort_type") or "").casefold(),
                str(record.get("source_pf_url") or canonical),
                str(record.get("cardidx", "")),
                _record_identity(record),
            )
            combined_initial[identity] = record

        extracted, sort_complete, seen, target = _extract_pf_virtual(
            page,
            applied,
            progress=progress,
            partial_path=partial_path,
            initial_records=list(combined_initial.values()),
            context=context,
            extract_card_options=extract_card_options,
        )
        complete = complete and sort_complete
        output.extend(extracted)
        if not sort_complete:
            output.append(
                {
                    **context,
                    "status": (
                        f"incomplete: incremental PF cards_seen={seen} "
                        f"target={target or 'unknown'}"
                    ),
                }
            )
    if not output:
        return ([{**context, "status": "incomplete: no records extracted"}], False)
    return output, complete


def run(
    extract_card_options=None,
    output_transform=None,
    checkpoint_validator=None,
    mode="cta-and-pf-card-details",
):
    log = lambda message: print(message, file=sys.stderr, flush=True)
    checkpoint_validator = checkpoint_validator or _checkpoint_has_display_names
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 900}, user_agent=core.USER_AGENT
        )
        page.goto(core.BASE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        core.dismiss_consent(page)

        categories = core.discover_all_categories(page)
        log(
            f"[info] mode={mode.upper().replace('-', '_')} site={core.SITE} "
            f"sorts={','.join(code for _, code in core.SORT_SEQUENCE)} "
            f"unique PF candidates={len(categories)}"
        )
        progress = core.Progress(len(categories))

        for index, category in enumerate(categories, 1):
            checkpoint = core._ckpt_path(category) if core.RESUME_DIR else None
            partial = checkpoint + ".partial" if checkpoint else None
            if checkpoint and os.path.exists(checkpoint):
                try:
                    with open(checkpoint, encoding="utf-8") as file:
                        records = json.load(file)
                    if not checkpoint_validator(records):
                        log(
                            f"[resume-stale] PF {index}/{len(categories)} "
                            f"{category['canon']} missing display_name_PF; rescanning"
                        )
                        records = None
                    if records is None:
                        raise ValueError("old checkpoint schema")
                    results.extend(records)
                    progress.done += 1
                    log(
                        f"[resume] PF {index}/{len(categories)} "
                        f"{category['canon']} <- checkpoint ({len(records)})"
                    )
                    continue
                except (OSError, ValueError):
                    pass

            initial_records = []
            if partial and os.path.exists(partial):
                try:
                    with open(partial, encoding="utf-8") as file:
                        initial_records = json.load(file)
                    if not checkpoint_validator(initial_records):
                        log(
                            f"[partial-stale] PF {index}/{len(categories)} "
                            f"{category['canon']} missing display_name_PF; restarting"
                        )
                        initial_records = []
                    log(
                        f"[partial] PF {index}/{len(categories)} "
                        f"{category['canon']} existing_records={len(initial_records)}"
                    )
                except (OSError, ValueError):
                    initial_records = []

            progress.start_pf(index, category)
            try:
                records, complete = _scan_category(
                    page,
                    category,
                    progress=progress,
                    partial_path=partial,
                    initial_records=initial_records,
                    extract_card_options=extract_card_options,
                )
                if complete:
                    status = "ok" if any(not row.get("status") for row in records) else "skip"
                else:
                    status = "incomplete"
            except Exception as exc:
                records = [
                    {
                        "category": category["name"],
                        "category_url": category.get("href"),
                        "source_pf_url": category["canon"],
                        "status": f"error: {type(exc).__name__}: {exc}",
                    }
                ]
                complete = False
                status = "error"

            if checkpoint:
                if complete:
                    _write_json(checkpoint, records)
                    if partial and os.path.exists(partial):
                        os.remove(partial)
                elif partial:
                    partial_records = [row for row in records if not row.get("status")]
                    if partial_records:
                        _write_json(partial, partial_records)
            if complete:
                results.extend(records)
            else:
                results.extend(row for row in records if row.get("status"))
            progress.end_pf(status, len(records))

        browser.close()

    output_records = results
    extra_metadata = {}
    if output_transform:
        output_records, extra_metadata = output_transform(results)
    output = {
        "records": output_records,
        "metadata": {
            "mode": mode,
            "site": core.SITE,
            "sorts": [code for _, code in core.SORT_SEQUENCE],
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            **extra_metadata,
        },
    }
    output_path = os.environ.get("SAMSUNG_OUTPUT") or f"pf_cta_{core.SITE}.json"
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)
    log(f"[done] records={len(output_records)} output={output_path}")
    return output


if __name__ == "__main__":
    run()
