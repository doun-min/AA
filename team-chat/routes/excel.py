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


def _read_sheet_df(data, ext, sheet_name=None):
    if ext == "csv":
        return _read_csv_bytes(data)
    kwargs = {"dtype": str, "keep_default_na": False}
    if sheet_name is not None:
        kwargs["sheet_name"] = sheet_name
    return pd.read_excel(io.BytesIO(data), **kwargs)


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


@excel_bp.route("/sheets", methods=["POST"])
def sheet_names():
    _require_login()
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify(error="파일을 선택해주세요."), 400

    ext = _split_ext(upload.filename)
    if ext == "csv":
        return jsonify(is_excel=False, sheets=[])
    if ext not in ("xlsx", "xls"):
        return jsonify(error=f"지원하지 않는 파일 형식입니다: {upload.filename}"), 400

    try:
        sheets = pd.ExcelFile(io.BytesIO(upload.read())).sheet_names
    except Exception:
        return jsonify(error="시트 목록을 읽을 수 없습니다."), 400
    return jsonify(is_excel=True, sheets=list(sheets))


@excel_bp.route("/merge", methods=["POST"])
def merge():
    _require_login()
    files = request.files.getlist("files")
    if len(files) < 2:
        return jsonify(error="병합할 파일을 2개 이상 선택해주세요."), 400

    force = (request.form.get("force") or "").strip().lower() in ("1", "true")
    skip_missing = (request.form.get("skip_missing") or "").strip().lower() in ("1", "true")
    sheet_name = (request.form.get("sheet") or "").strip() or None

    file_infos = []
    for f in files:
        filename = f.filename or ""
        ext = _split_ext(filename)
        if ext not in ("csv", "xlsx", "xls"):
            return jsonify(error=f"지원하지 않는 파일 형식입니다: {filename}"), 400
        file_infos.append({"filename": filename, "ext": ext, "data": f.read()})

    base_is_excel = file_infos[0]["ext"] in ("xlsx", "xls")
    if base_is_excel and not sheet_name:
        return jsonify(error="병합할 시트를 선택해주세요."), 400

    # 첫 번째 파일 기준 시트명이 없는 엑셀 파일은 감지해 목록으로 알린다.
    # CSV 파일은 시트 개념이 없으므로(파일 전체가 하나의 표) 시트 검사 없이 그대로 포함한다.
    included = []
    missing_sheet_files = []
    for info in file_infos:
        if sheet_name and info["ext"] in ("xlsx", "xls"):
            try:
                sheets = pd.ExcelFile(io.BytesIO(info["data"])).sheet_names
            except Exception:
                return jsonify(error=f"'{info['filename']}' 파일을 읽을 수 없습니다."), 400
            if sheet_name not in sheets:
                missing_sheet_files.append(info["filename"])
                continue
        included.append(info)

    if missing_sheet_files and not skip_missing:
        return jsonify(
            error="missing_sheet",
            message=f"선택한 시트('{sheet_name}')가 없는 파일이 있습니다.",
            sheet=sheet_name,
            missing_files=missing_sheet_files,
        ), 409

    if len(included) < 2:
        return jsonify(error="병합할 수 있는 파일이 2개 미만입니다."), 400

    dfs = []
    headers = []
    for info in included:
        try:
            df = _read_sheet_df(info["data"], info["ext"], sheet_name)
        except ValueError as e:
            return jsonify(error=str(e)), 400
        dfs.append(df)
        headers.append({"filename": info["filename"], "columns": list(df.columns)})

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
