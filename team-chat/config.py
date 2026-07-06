import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SECRET_KEY = os.environ.get("CHAT_SECRET_KEY", "change-this-secret-key-for-internal-use")

DB_PATH = os.path.join(BASE_DIR, "chat.db")

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

ALLOWED_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "webp", "bmp",
    "pdf", "txt", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "zip", "csv", "hwp", "log",
}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}

# 로그인은 닉네임만 입력하는 방식이라 별도 계정 시스템이 없다.
# 여기 등록된 닉네임으로 로그인하면 자동으로 슈퍼관리자 권한이 부여된다.
SUPERADMIN_NAMES = {"admin", "관리자"}

GLOBAL_ROOM_NAME = "전체"

NICKNAME_MAX_LENGTH = 20
ROOM_NAME_MAX_LENGTH = 50

HOST = os.environ.get("CHAT_HOST", "0.0.0.0")
PORT = int(os.environ.get("CHAT_PORT", "5000"))
