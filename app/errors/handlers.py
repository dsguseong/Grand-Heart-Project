"""에러 핸들러.

app_errorhandler 를 써야 블루프린트 전체(=앱 전역)에 적용됩니다.
errorhandler 만 쓰면 이 블루프린트 안에서 난 에러에만 걸립니다.
"""

from flask import jsonify, render_template, request

from app.errors import bp
from app.extensions import db


def _wants_json() -> bool:
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


@bp.app_errorhandler(403)
def forbidden(error):
    if _wants_json():
        return jsonify(error="forbidden"), 403
    return render_template("errors/403.html"), 403


@bp.app_errorhandler(404)
def not_found(error):
    if _wants_json():
        return jsonify(error="not_found"), 404
    return render_template("errors/404.html"), 404


@bp.app_errorhandler(413)
def too_large(error):
    if _wants_json():
        return jsonify(error="file_too_large"), 413
    return render_template("errors/413.html"), 413


@bp.app_errorhandler(500)
def internal_error(error):
    db.session.rollback()
    if _wants_json():
        return jsonify(error="internal_server_error"), 500
    return render_template("errors/500.html"), 500
