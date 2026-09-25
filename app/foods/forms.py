"""폼.

주의: 버튼 값(action)이나 대상 id 를 WTForms HiddenField 로 두면서 템플릿에서
form.hidden_tag() 와 <input type="hidden"> 을 함께 쓰면 같은 이름의 필드가
두 번 전송되어 WTForms 가 빈 쪽을 읽습니다. 그래서 이 폼들은 CSRF 토큰만
담당하고, action/item_id 는 라우트에서 request.form 으로 직접 읽습니다.
"""

from flask_wtf import FlaskForm
from wtforms import SubmitField


class CsrfForm(FlaskForm):
    """CSRF 토큰만 있는 폼. 스와이프 투표·제외·삭제 버튼에 공통으로 씁니다."""

    submit = SubmitField("확인")


class UploadForm(FlaskForm):
    submit = SubmitField("등록")
