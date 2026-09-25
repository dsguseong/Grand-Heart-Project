from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Regexp,
    ValidationError,
)

from app.extensions import db
from app.models import User


class LoginForm(FlaskForm):
    username = StringField("아이디", validators=[DataRequired("아이디를 입력하세요.")])
    password = PasswordField("비밀번호", validators=[DataRequired("비밀번호를 입력하세요.")])
    remember_me = BooleanField("로그인 상태 유지")
    submit = SubmitField("로그인")


class RegistrationForm(FlaskForm):
    username = StringField(
        "아이디",
        validators=[
            DataRequired("아이디를 입력하세요."),
            Length(3, 64, message="3자 이상 64자 이하로 입력하세요."),
            Regexp(r"^[A-Za-z0-9_.가-힣]+$", message="한글, 영문, 숫자, _ . 만 쓸 수 있습니다."),
        ],
    )
    email = StringField(
        "이메일", validators=[DataRequired("이메일을 입력하세요."), Email("이메일 형식이 아닙니다.")]
    )
    password = PasswordField(
        "비밀번호",
        validators=[DataRequired("비밀번호를 입력하세요."), Length(8, message="8자 이상으로 정하세요.")],
    )
    password2 = PasswordField(
        "비밀번호 확인",
        validators=[DataRequired("한 번 더 입력하세요."), EqualTo("password", "비밀번호가 서로 다릅니다.")],
    )
    submit = SubmitField("가입하기")

    def validate_username(self, field):
        if db.session.scalar(db.select(User).where(User.username == field.data)):
            raise ValidationError("이미 사용 중인 아이디입니다.")

    def validate_email(self, field):
        if db.session.scalar(db.select(User).where(User.email == field.data.lower())):
            raise ValidationError("이미 가입된 이메일입니다.")


class ResetPasswordRequestForm(FlaskForm):
    email = StringField("가입한 이메일", validators=[DataRequired(), Email()])
    submit = SubmitField("재설정 링크 받기")


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "새 비밀번호", validators=[DataRequired(), Length(8, message="8자 이상으로 정하세요.")]
    )
    password2 = PasswordField(
        "새 비밀번호 확인", validators=[DataRequired(), EqualTo("password", "비밀번호가 서로 다릅니다.")]
    )
    submit = SubmitField("비밀번호 변경")
