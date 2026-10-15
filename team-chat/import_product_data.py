"""Import local structured workbooks and JSONL files; no file upload/network."""

import argparse
from pathlib import Path
import json

import config
from product_catalog import COUNTRIES, import_country


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).parent.parent / "DBauto")
    parser.add_argument("--countries", default="us,ca,ca_fr")
    parser.add_argument("--db", type=Path, default=Path(config.PRODUCT_DB_PATH))
    args = parser.parse_args()
    countries = [c.strip().lower().replace("-","_") for c in args.countries.split(",") if c.strip()]
    if not countries or any(c not in COUNTRIES for c in countries):
        parser.error("--countries must contain us,ca,ca_fr")
    sources = []
    for country in countries:
        suffix = country.replace("_","-")
        workbook = args.data_dir / f"structured-{suffix}.xlsx"
        long_file = args.data_dir / f"long-values-{suffix}.jsonl"
        if not workbook.is_file() or not long_file.is_file():
            parser.error(f"Source missing: {workbook} / {long_file}")
        sources.append((country,workbook,long_file))
    for country,workbook,long_file in sources:
        result = import_country(args.db,country,workbook,long_file)
        print("[done] " + json.dumps(result),flush=True)
    print(f"[database] {args.db.resolve()} size={args.db.stat().st_size/1048576:.1f}MB")


if __name__ == "__main__":
    main()
