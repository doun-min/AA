"""Add sort-presence labels to completed PF v5 JSON without recrawling."""

import argparse
import json
from pathlib import Path

from collect_pf_card_details_v5 import annotate_sort_presence


def annotate_file(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError(f"{path}: records must be a list")
    metadata = data.setdefault("metadata", {})
    counts = annotate_sort_presence(records, metadata)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
    print(
        f"[done] {path} records={len(records)} "
        f"recommended_only={counts['recommended_only']} "
        f"newest_only={counts['newest_only']} both={counts['both']}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_files", nargs="+", type=Path)
    args = parser.parse_args()
    for path in args.json_files:
        annotate_file(path)


if __name__ == "__main__":
    main()
