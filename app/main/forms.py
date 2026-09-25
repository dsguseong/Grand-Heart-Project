from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, Regexp, ValidationError

from app.extensions import db
from app.models import User


class EmptyForm(FlaskForm):
    """CSRF 토큰만 필요한 POST 버튼(팔로우/언팔로우 등)용."""

    submit = SubmitField("확인")


class EditProfileForm(FlaskForm):
    username = StringField(
        "아이디",
        validators=[
            DataRequired("아이디를 입력하세요."),
            Length(3, 64),
            Regexp(r"^[A-Za-z0-9_.가-힣]+$", message="한글, 영문, 숫자, _ . 만 쓸 수 있습니다."),
        ],
    )
    about_me = TextAreaField("소개", validators=[Length(0, 140)])
    submit = SubmitField("저장")

    def __init__(self, original_username, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, field):
        if field.data == self.original_username:
            return
        if db.session.scalar(db.select(User).where(User.username == field.data)):
            raise ValidationError("이미 사용 중인 아이디입니다.")
