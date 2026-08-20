import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = os.environ.get("CHAT_SECRET_KEY", "change-this-secret-key-for-internal-use")

DB_PATH = os.path.join(BASE_DIR, "chat.db")

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

# 관리자가 기간을 지정해 로그를 삭제할 때, 삭제 전 내용을 방별로 계속 이어서(append)
# 백업해두는 txt 파일 위치. 삭제 이력 전체가 시간순으로 한 파일에 쌓인다.
LOG_BACKUP_FOLDER = os.path.join(BASE_DIR, "log_backups")

ALLOWED_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "webp", "bmp",
    "pdf", "txt", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "zip", "csv", "hwp", "log",
}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}

# 로그인은 닉네임만 입력하는 방식이라 별도 계정 시스템이 없다.
# 관리자 권한은 users.role 컬럼(db.py)으로 관리하며, 관리자가 한 명도 없는 최초 기동 시에만
# 이 닉네임을 자동으로 admin으로 시딩한다(db._ensure_initial_admin).
INITIAL_ADMIN_NICKNAME = "test11"

GLOBAL_ROOM_NAME = "전체"
# 더 이상 새로 만들지 않는다 — 예전에 이미 생성된 방을 찾아 삭제 가능하게 풀어주는
# 1회성 마이그레이션(db.init_db)에서만 쓰인다.
SCHEDULE_ROOM_NAME = "일정공유"

# @전체 라고 멘션하면 방 참여자 전원에게 멘션한 것으로 처리한다 (sockets.py).
# 실제 닉네임과 충돌하면 안 되므로 로그인 시 이 이름은 예약어로 막는다 (routes/pages.py).
MENTION_ALL = "전체"

NICKNAME_MAX_LENGTH = 20
ROOM_NAME_MAX_LENGTH = 50

HOST = os.environ.get("CHAT_HOST", "0.0.0.0")
PORT = int(os.environ.get("CHAT_PORT", "5000"))

# 브라우저 알림(Notification API)은 secure context(https 또는 localhost)에서만 동작하므로
# 사설 IP로 접속하는 내부망 환경에서는 자체서명 인증서로 https를 켜야 한다.
CERT_FILE = os.path.join(BASE_DIR, "certs", "cert.pem")
KEY_FILE = os.path.join(BASE_DIR, "certs", "key.pem")
