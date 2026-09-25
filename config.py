"""애플리케이션 설정.

모든 값은 환경변수(.env)로 덮어쓸 수 있습니다.
운영 환경에서는 SECRET_KEY를 반드시 지정하세요.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    # --- 기본 ---
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-only-change-me"
    ITEMS_PER_PAGE = int(os.environ.get("ITEMS_PER_PAGE", 20))

    # --- 데이터베이스 ---
    # Heroku 등이 주는 postgres:// 스킴은 SQLAlchemy 2.x에서 인식하지 않으므로 보정
    _db_url = os.environ.get("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'instance' / 'app.db'}"
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- 업로드 ---
    UPLOAD_FOLDER = BASE_DIR / "app" / "static" / "uploads" / "foods"
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "gif"}
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_MB", 32)) * 1024 * 1024

    # --- 메일(비밀번호 재설정) ---
    MAIL_SERVER = os.environ.get("MAIL_SERVER")
    MAIL_PORT = int(os.environ.get("MAIL_PORT") or 25)
    MAIL_USE_TLS = _as_bool(os.environ.get("MAIL_USE_TLS"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "no-reply@grandheart.local")
    ADMINS = [e for e in os.environ.get("ADMINS", "").split(",") if e]

    # --- 추천 ---
    RECOMMEND_TOP_N = int(os.environ.get("RECOMMEND_TOP_N", 3))

    # --- 이미지 임베딩 ---
    # 아무도 평가하지 않은 음식의 점수를 낼 때 이미지 임베딩을 얼마나 믿을지(0~1).
    # 0 이면 순수 통계 방식. 임베딩 파일이 없으면 이 값과 무관하게 통계로 동작합니다.
    EMBEDDING_WEIGHT = float(os.environ.get("EMBEDDING_WEIGHT", 0.6))
    EMBEDDING_PATH = os.environ.get("EMBEDDING_PATH")  # 비우면 instance/embeddings.npz

    # --- 주변 식당(카카오 로컬 API) ---
    KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY")
    PLACES_RADIUS_M = int(os.environ.get("PLACES_RADIUS_M", 1500))

    # --- API 토큰 ---
    API_TOKEN_TTL = int(os.environ.get("API_TOKEN_TTL", 60 * 60 * 24 * 7))


class DevelopmentConfig(Config):
    DEBUG = True


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"  # 메모리 DB
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "testing"
    EMBEDDING_WEIGHT = 0.0


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    name = name or os.environ.get("FLASK_CONFIG", "development")
    return CONFIGS.get(name, DevelopmentConfig)
