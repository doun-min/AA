from flask import Blueprint, abort, jsonify, request, session

import auth
import db
from extensions import socketio

issues_bp = Blueprint("issues_api", __name__, url_prefix="/api")


def _require_login():
    nickname = session.get("nickname")
    if not nickname:
        abort(401)
    return nickname


def _require_admin():
    nickname = _require_login()
    if not auth.is_superadmin(nickname):
        abort(403)
    return nickname


@issues_bp.route("/subjects", methods=["GET"])
def list_subjects():
    _require_login()
    return jsonify(subjects=db.list_subjects())


@issues_bp.route("/subjects", methods=["POST"])
def create_subject():
    _require_login()
    name = ((request.get_json(silent=True) or {}).get("name") or "").strip()
    if not name:
        return jsonify(error="주제 이름을 입력해주세요."), 400
    subject = db.create_subject(name)
    socketio.emit("subject_updated", {"subject": subject})
    return jsonify(subject=subject), 201


@issues_bp.route("/subjects/<int:subject_id>/archive", methods=["POST"])
def archive_subject(subject_id):
    _require_admin()
    if not db.get_subject(subject_id):
        abort(404)
    subject = db.set_subject_status(subject_id, "archived")
    socketio.emit("subject_updated", {"subject": subject})
    return jsonify(subject=subject)


@issues_bp.route("/subjects/<int:subject_id>/activate", methods=["POST"])
def activate_subject(subject_id):
    _require_admin()
    if not db.get_subject(subject_id):
        abort(404)
    subject = db.set_subject_status(subject_id, "active")
    socketio.emit("subject_updated", {"subject": subject})
    return jsonify(subject=subject)


@issues_bp.route("/issue_fields", methods=["GET"])
def list_issue_fields():
    _require_login()
    return jsonify(fields=db.list_issue_fields())


@issues_bp.route("/issue_fields", methods=["POST"])
def create_issue_field():
    _require_admin()
    label = ((request.get_json(silent=True) or {}).get("label") or "").strip()
    if not label:
        return jsonify(error="필드 이름을 입력해주세요."), 400
    try:
        field = db.create_issue_field(label)
    except Exception:
        return jsonify(error="이미 존재하는 필드 이름입니다."), 400
    socketio.emit("issue_field_created", {"field": field})
    return jsonify(field=field), 201


def _parse_custom_fields(body):
    raw = body.get("custom_fields")
    if not isinstance(raw, dict):
        return {}
    return {str(k): ("" if v is None else str(v)) for k, v in raw.items()}


@issues_bp.route("/issues", methods=["GET"])
def list_issues():
    _require_login()
    subject_id = request.args.get("subject_id", type=int)
    reporter = (request.args.get("reporter") or "").strip() or None
    return jsonify(issues=db.list_issues(subject_id=subject_id, reporter=reporter))


@issues_bp.route("/issues/<int:issue_id>", methods=["GET"])
def get_issue(issue_id):
    _require_login()
    issue = db.get_issue(issue_id)
    if not issue:
        abort(404)
    return jsonify(issue=issue)


@issues_bp.route("/issues", methods=["POST"])
def create_issue():
    nickname = _require_login()
    body = request.get_json(silent=True) or {}
    subject_id = body.get("subject_id")
    subject = db.get_subject(subject_id) if subject_id else None
    if not subject:
        return jsonify(error="주제를 선택해주세요."), 400
    if subject["status"] != "active":
        return jsonify(error="아카이브된 주제에는 이슈를 등록할 수 없습니다."), 400

    tc_num = (body.get("tc_num") or "").strip()
    issue_body = (body.get("body") or "").strip()
    steps = (body.get("steps_to_reproduce") or "").strip()
    if not issue_body:
        return jsonify(error="Defect 내용을 입력해주세요."), 400

    issue = db.create_issue(
        subject_id, tc_num, issue_body, steps, nickname, _parse_custom_fields(body)
    )
    socketio.emit("issue_created", {"issue": issue})
    return jsonify(issue=issue), 201


@issues_bp.route("/issues/<int:issue_id>", methods=["PUT"])
def update_issue(issue_id):
    _require_login()
    existing = db.get_issue(issue_id)
    if not existing:
        abort(404)

    body = request.get_json(silent=True) or {}
    subject_id = body.get("subject_id")
    subject = db.get_subject(subject_id) if subject_id else None
    if not subject:
        return jsonify(error="주제를 선택해주세요."), 400

    tc_num = (body.get("tc_num") or "").strip()
    issue_body = (body.get("body") or "").strip()
    steps = (body.get("steps_to_reproduce") or "").strip()
    if not issue_body:
        return jsonify(error="Defect 내용을 입력해주세요."), 400

    issue = db.update_issue(
        issue_id, subject_id, tc_num, issue_body, steps, _parse_custom_fields(body)
    )
    socketio.emit("issue_updated", {"issue": issue})
    return jsonify(issue=issue)


@issues_bp.route("/issues/<int:issue_id>", methods=["DELETE"])
def delete_issue(issue_id):
    _require_login()
    if not db.get_issue(issue_id):
        abort(404)
    db.delete_issue(issue_id)
    socketio.emit("issue_deleted", {"issue_id": issue_id})
    return "", 204
