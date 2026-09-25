"""애플리케이션 팩토리.

기존 구조는 app/__init__.py 안에서 `app = Flask(__name__)` 을 만들고 파일
맨 아래에서 `from app import routes, models, errors` 를 했습니다. 그러면
routes.py 가 다시 `from app import app` 을 하므로 순환 임포트가 되고,
테스트에서 설정을 바꿔 앱을 새로 만드는 것도 불가능합니다.
create_app(config) 팩토리로 바꿨습니다.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask

from config import get_config
from app.extensions import csrf, db, login_manager, mail, migrate


def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)  # SQLite ALTER TABLE 지원
    login_manager.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)

    from app.api import bp as api_bp
    from app.auth import bp as auth_bp
    from app.errors import bp as errors_bp
    from app.foods import bp as foods_bp
    from app.main import bp as main_bp
    from app.recommend import bp as recommend_bp

    app.register_blueprint(errors_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(foods_bp, url_prefix="/foods")
    app.register_blueprint(recommend_bp, url_prefix="/recommend")
    app.register_blueprint(api_bp, url_prefix="/api/v1")
    csrf.exempt(api_bp)  # API는 토큰 인증을 쓰므로 CSRF 대상 아님

    from app import cli

    cli.register(app)

    from app.models import SCORE_DISLIKE, SCORE_LIKE, SCORE_SOSO

    @app.context_processor
    def inject_globals():
        return {
            "SCORE_LIKE": SCORE_LIKE,
            "SCORE_SOSO": SCORE_SOSO,
            "SCORE_DISLIKE": SCORE_DISLIKE,
        }

    _configure_logging(app)
    return app


def _configure_logging(app: Flask) -> None:
    if app.debug or app.testing:
        return
    log_dir = Path(app.instance_path) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(log_dir / "app.log", maxBytes=1_000_000, backupCount=5)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s: %(message)s [%(pathname)s:%(lineno)d]")
    )
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info("뭐 먹으러 갈까? 서버 시작")
