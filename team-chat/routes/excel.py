import io

import pandas as pd
from flask import Blueprint, abort, jsonify, request, send_file, session

excel_bp = Blueprint("excel_api", __name__, url_prefix="/api/excel")

CSV_ENCODINGS = ("utf-8-sig", "utf-8", "cp949")


def _require_login():
    nickname = session.get("nickname")
    if not nickname:
        abort(401)
    return nickname


def _split_ext(filename):
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _read_csv_bytes(data):
    last_error = None
    for enc in CSV_ENCODINGS:
        try:
            return pd.read_csv(io.BytesIO(data), dtype=str, keep_default_na=False, encoding=enc)
        except (UnicodeDecodeError, UnicodeError) as e:
            last_error = e
            continue
    raise ValueError(f"CSV 인코딩을 인식할 수 없습니다: {last_error}")


def _read_df(file_storage):
    filename = file_storage.filename or ""
    ext = _split_ext(filename)
    data = file_storage.read()
    if ext == "csv":
        df = _read_csv_bytes(data)
    elif ext in ("xlsx", "xls"):
        df = pd.read_excel(io.BytesIO(data), dtype=str, keep_default_na=False)
    else:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {filename}")
    return df, ext, filename


def _base_name(filename):
    return filename.rsplit(".", 1)[0] if "." in filename else filename


@excel_bp.route("/convert", methods=["POST"])
def convert():
    _require_login()
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify(error="변환할 파일을 선택해주세요."), 400

    try:
        df, ext, filename = _read_df(upload)
    except ValueError as e:
        return jsonify(error=str(e)), 400

    base = _base_name(filename)
    if ext == "csv":
        out = io.BytesIO()
        df.to_excel(out, index=False, engine="openpyxl")
        out.seek(0)
        return send_file(
            out,
            as_attachment=True,
            download_name=f"{base}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
    out = io.BytesIO(csv_bytes)
    return send_file(out, as_attachment=True, download_name=f"{base}.csv", mimetype="text/csv")


@excel_bp.route("/merge", methods=["POST"])
def merge():
    _require_login()
    files = request.files.getlist("files")
    if len(files) < 2:
        return jsonify(error="병합할 파일을 2개 이상 선택해주세요."), 400

    force = (request.form.get("force") or "").strip().lower() in ("1", "true")

    dfs = []
    headers = []
    for f in files:
        try:
            df, ext, filename = _read_df(f)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        dfs.append(df)
        headers.append({"filename": filename, "columns": list(df.columns)})

    base_columns = headers[0]["columns"]
    mismatches = [h for h in headers[1:] if h["columns"] != base_columns]

    if mismatches and not force:
        return jsonify(
            error="header_mismatch",
            message="파일 간 헤더가 일치하지 않습니다.",
            base_file=headers[0]["filename"],
            base_header=base_columns,
            mismatches=mismatches,
        ), 409

    col_count = len(base_columns)
    for h in headers:
        if len(h["columns"]) != col_count:
            return jsonify(
                error=f"'{h['filename']}' 파일의 컬럼 개수({len(h['columns'])}개)가 "
                f"'{headers[0]['filename']}' 파일({col_count}개)과 달라 병합할 수 없습니다."
            ), 400

    aligned = []
    for df in dfs:
        df = df.copy()
        df.columns = base_columns
        aligned.append(df)
    merged = pd.concat(aligned, ignore_index=True)

    out = io.BytesIO()
    merged.to_excel(out, index=False, engine="openpyxl")
    out.seek(0)
    return send_file(
        out,
        as_attachment=True,
        download_name="merged.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
