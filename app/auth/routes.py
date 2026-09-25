from urllib.parse import urlsplit

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.auth import bp
from app.auth.forms import (
    LoginForm,
    RegistrationForm,
    ResetPasswordForm,
    ResetPasswordRequestForm,
)
from app.extensions import db
from app.models import User, utcnow
from app.services.mailer import send_password_reset_email


def _safe_next(target: str | None) -> str:
    """오픈 리다이렉트 방지.

    기존 코드의 `from werkzeug.urls import url_parse` 는 Werkzeug 2.1 에서
    삭제돼 최신 버전에서는 ImportError 로 앱이 아예 뜨지 않습니다.
    표준 라이브러리 urllib.parse.urlsplit 으로 대체했습니다.
    """
    if not target:
        return url_for("main.index")
    parts = urlsplit(target)
    if parts.netloc or parts.scheme or not target.startswith("/"):
        return url_for("main.index")
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).where(User.username == form.username.data))
        if user is None or not user.check_password(form.password.data):
            flash("아이디 또는 비밀번호가 맞지 않습니다.", "danger")
            return redirect(url_for("auth.login"))
        login_user(user, remember=form.remember_me.data)
        user.last_seen = utcnow()
        db.session.commit()
        return redirect(_safe_next(request.args.get("next")))
    return render_template("auth/login.html", title="로그인", form=form)


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("로그아웃했습니다.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data.lower())
        user.set_password(form.password.data)
        # 첫 사용자를 관리자로 지정 (음식 업로드 권한)
        if db.session.scalar(db.select(db.func.count(User.id))) == 0:
            user.is_admin = True
        db.session.add(user)
        db.session.commit()
        flash("가입이 끝났습니다. 로그인 후 음식 취향을 골라 보세요.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/register.html", title="회원가입", form=form)


@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).where(User.email == form.email.data.lower()))
        if user:
            send_password_reset_email(user)
        # 가입 여부를 알려주지 않기 위해 항상 같은 안내를 보여줍니다.
        flash("메일을 보냈습니다. 받은편지함을 확인하세요.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_request.html", title="비밀번호 재설정", form=form)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))
    user = User.verify_token(token, "reset-password")
    if user is None:
        flash("링크가 만료되었거나 올바르지 않습니다. 다시 요청하세요.", "danger")
        return redirect(url_for("auth.reset_password_request"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash("비밀번호를 바꿨습니다.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", title="새 비밀번호", form=form)
