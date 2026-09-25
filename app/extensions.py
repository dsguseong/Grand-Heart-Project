"""확장 객체를 한 곳에 모아 순환 임포트를 없앱니다.

기존 코드는 app/__init__.py 에서 app 객체를 만들고 맨 아래에서
`from app import routes` 를 하는 구조라 routes -> app -> routes 로
순환 임포트가 생겼습니다. 팩토리 패턴 + 이 모듈로 해결합니다.
"""

from flask_login import LoginManager
from flask_mail import Mail
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
mail = Mail()
csrf = CSRFProtect()

login_manager.login_view = "auth.login"
login_manager.login_message = "로그인이 필요한 페이지입니다."
login_manager.login_message_category = "info"
