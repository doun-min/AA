#!/usr/bin/env python3
"""CSV <-> 엑셀 변환용 독립 스크립트 (team-chat 웹앱과 무관, 파일 크기 제한 없음).

team-chat/routes/excel.py의 변환 로직(CSV 인코딩 자동 감지, BOM 포함 CSV 출력)과
동일하게 동작하지만 Flask를 거치지 않아 MAX_CONTENT_LENGTH(50MB) 제한이 없다.

사용법:
    python3 excel_convert.py <입력파일> [출력파일]

출력파일을 생략하면 같은 폴더에 확장자만 바꿔서 저장한다.
"""
import sys
from pathlib import Path

import pandas as pd

CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp949")
EXCEL_MAX_ROWS = 1_048_576  # xlsx 포맷 자체의 시트당 최대 행 수(헤더 포함)


def read_csv_any_encoding(path):
    last_error = None
    for enc in CSV_ENCODINGS:
        try:
            return pd.read_csv(path, dtype=str, keep_default_na=False, encoding=enc)
        except (UnicodeDecodeError, UnicodeError) as e:
            last_error = e
            continue
    raise ValueError(f"CSV 인코딩을 인식할 수 없습니다: {last_error}")


def convert(input_path: Path, output_path: Path):
    ext = input_path.suffix.lower().lstrip(".")

    if ext == "csv":
        print(f"[1/2] CSV 읽는 중: {input_path} ({input_path.stat().st_size / 1024 / 1024:.1f} MB)")
        df = read_csv_any_encoding(input_path)
        row_count = len(df)
        print(f"      {row_count:,}행 x {len(df.columns)}열 읽음")
        if row_count + 1 > EXCEL_MAX_ROWS:
            raise ValueError(
                f"행 수({row_count:,})가 엑셀 시트 최대 행 수({EXCEL_MAX_ROWS:,})를 초과합니다. "
                "엑셀 하나로는 담을 수 없어서 파일을 나누거나 CSV로 유지해야 합니다."
            )
        print(f"[2/2] 엑셀로 저장 중: {output_path}")
        df.to_excel(output_path, index=False, engine="openpyxl")
    elif ext in ("xlsx", "xls"):
        print(f"[1/2] 엑셀 읽는 중: {input_path} ({input_path.stat().st_size / 1024 / 1024:.1f} MB)")
        df = pd.read_excel(input_path, dtype=str, keep_default_na=False)
        print(f"      {len(df):,}행 x {len(df.columns)}열 읽음")
        print(f"[2/2] CSV로 저장 중: {output_path}")
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
    else:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {input_path.name} (csv/xlsx/xls만 지원)")

    print(f"완료: {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_path = Path(sys.argv[1]).expanduser().resolve()
    if not input_path.exists():
        print(f"파일을 찾을 수 없습니다: {input_path}")
        sys.exit(1)

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2]).expanduser().resolve()
    else:
        ext = input_path.suffix.lower().lstrip(".")
        target_ext = ".xlsx" if ext == "csv" else ".csv"
        output_path = input_path.with_suffix(target_ext)

    try:
        convert(input_path, output_path)
    except ValueError as e:
        print(f"변환 실패: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
