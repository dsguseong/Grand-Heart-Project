from flask import Blueprint

bp = Blueprint("foods", __name__)

from app.foods import routes  # noqa: E402,F401
