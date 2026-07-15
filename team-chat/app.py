import os

from flask import Flask, session

import config
import db
from extensions import socketio


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

    os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)
    db.init_db()

    from routes.pages import pages_bp
    from routes.rooms import rooms_bp
    from routes.files import files_bp
    from routes.logs import logs_bp
    from routes.schedules import schedules_bp
    from routes.excel import excel_bp
    from routes.issues import issues_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(rooms_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(logs_bp)
    app.register_blueprint(schedules_bp)
    app.register_blueprint(excel_bp)
    app.register_blueprint(issues_bp)

    @app.context_processor
    def inject_sidebar_counts():
        nickname = session.get("nickname")
        if not nickname:
            return {}
        total = (
            sum(db.get_unread_mention_counts(nickname).values())
            + sum(db.get_unread_direct_message_counts(nickname).values())
        )
        return {"sidebar_mention_total": total}

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
