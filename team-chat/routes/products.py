from io import BytesIO

from flask import Blueprint, abort, jsonify, render_template, request, send_file, session
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell

import auth
import config
from product_catalog import COUNTRIES, SECTIONS, catalog_stats, product_detail, search_catalog


products_bp = Blueprint("products", __name__)


def require_api_login():
    if not session.get("nickname"):
        abort(401)


@products_bp.get("/products")
@auth.login_required
def page():
    return render_template("products.html",nickname=session["nickname"])


@products_bp.get("/api/products/stats")
def stats():
    require_api_login()
    return jsonify(catalog_stats(config.PRODUCT_DB_PATH))


def search_parameters():
    country = request.args.get("country", "").strip().lower()
    scope = request.args.get("scope", "basic")
    query = request.args.get("q", "").strip()
    if country and country not in COUNTRIES:
        abort(400)
    if scope not in {*SECTIONS, "all"} or len(query) > 200:
        abort(400)
    try:
        page_number = max(1, min(int(request.args.get("page",1)),100000))
    except ValueError:
        abort(400)
    return country, query, scope, page_number


@products_bp.get("/api/products")
def search():
    require_api_login()
    country,query,scope,page_number = search_parameters()
    return jsonify(search_catalog(config.PRODUCT_DB_PATH,country,query,scope,page_number))


@products_bp.get("/api/products/export")
def export():
    require_api_login()
    country,query,scope,_page_number = search_parameters()
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Products")
    fields = ["country","sku","name","model_name","color","category"]
    sheet.append(fields)
    page_number = 1
    while True:
        data = search_catalog(config.PRODUCT_DB_PATH,country,query,scope,page_number,page_size=1000)
        for item in data["items"]:
            cells = []
            for field in fields:
                cell = WriteOnlyCell(sheet,value=str(item.get(field) or ""))
                cell.data_type = "s"
                cells.append(cell)
            sheet.append(cells)
        if page_number*1000 >= data["total"]:
            break
        page_number += 1
    output = BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(output,as_attachment=True,download_name="product_search.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@products_bp.get("/api/products/<country>/<path:sku>")
def detail(country,sku):
    require_api_login()
    section = request.args.get("section","basic")
    if country not in COUNTRIES or section not in SECTIONS:
        abort(400)
    result = product_detail(config.PRODUCT_DB_PATH,country,sku.strip().upper(),section)
    if result is None:
        abort(404)
    return jsonify(result)
