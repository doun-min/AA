import os

from flask import Flask, abort, jsonify, redirect, request, session, url_for

import auth
import config
import db
from extensions import socketio


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

    @app.errorhandler(413)
    def upload_too_large(error):
        if request.path.startswith("/api/"):
            return jsonify(error="업로드 요청이 허용 크기를 초과했습니다."), 413
        return error

    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(config.LOG_BACKUP_FOLDER, exist_ok=True)
    db.init_db()

    @app.before_request
    def reject_revoked_session():
        if request.path.startswith("/static/uploads/"):
            abort(404)
        nickname = session.get("nickname")
        if nickname and not db.user_session_valid(nickname, session.get("session_token")):
            session.clear()
            if request.path.startswith("/api/") or request.path.startswith("/files/"):
                abort(401)
            if request.endpoint != "pages.login_page":
                return redirect(url_for("pages.login_page"))

    from routes.pages import pages_bp
    from routes.rooms import rooms_bp
    from routes.files import files_bp
    from routes.logs import logs_bp
    from routes.schedules import schedules_bp
    from routes.excel import excel_bp
    from routes.issues import issues_bp
    from routes.products import products_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(rooms_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(schedules_bp)
    app.register_blueprint(excel_bp)
    app.register_blueprint(issues_bp)
    app.register_blueprint(products_bp)

    @app.context_processor
    def inject_sidebar_context():
        # 사이드바(관리자 메뉴 노출 여부 포함)는 모든 페이지에서 공통으로 쓰이므로,
        # 각 라우트가 매번 is_admin을 넘기지 않아도 되도록 여기서 한 번에 주입한다.
        nickname = session.get("nickname")
        if not nickname:
            return {}
        rooms = (
            db.list_sidebar_rooms(nickname, request.view_args.get("room_id"))
            if request.endpoint == "pages.chat_page" else None
        )
        total = (
            rooms["total_unread"]
            if rooms else sum(db.get_unread_message_counts(nickname).values())
        )
        return {
            "sidebar_unread_total": total,
            "sidebar_rooms": rooms,
            "is_admin": auth.is_admin(nickname),
        }

    socketio.init_app(app, async_mode="threading")

    import sockets  # noqa: F401  (import 시점에 이벤트 핸들러가 socketio에 등록됨)

    return app


app = create_app()

if __name__ == "__main__":
    ssl_context = (config.CERT_FILE, config.KEY_FILE) if os.path.exists(config.CERT_FILE) else None
    socketio.run(
        app,
        host=config.HOST,
        port=config.PORT,
        debug=True,
        allow_unsafe_werkzeug=True,
        ssl_context=ssl_context,
    )
