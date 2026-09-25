from flask import Blueprint

bp = Blueprint("recommend", __name__)

from app.recommend import routes  # noqa: E402,F401
