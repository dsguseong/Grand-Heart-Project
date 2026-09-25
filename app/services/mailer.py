"""메일 발송.

기존 app/email.py 는 send_email 을 **두 번** 정의했습니다. 파이썬은 나중 정의로
덮어쓰므로 동기 버전은 실행되지 않는 죽은 코드였고, 스레드에서 app 객체를
그대로 참조해 앱 컨텍스트가 깨질 여지도 있었습니다. 하나로 정리했습니다.
"""

from __future__ import annotations

from threading import Thread

from flask import current_app, render_template
from flask_mail import Message

from app.extensions import mail


def _send_async(app, msg: Message) -> None:
    with app.app_context():
        try:
            mail.send(msg)
        except Exception:  # 메일 실패가 요청을 죽이면 안 됨
            app.logger.exception("메일 발송 실패")


def send_email(subject, recipients, text_body, html_body, sender=None) -> None:
    app = current_app._get_current_object()
    if not app.config.get("MAIL_SERVER"):
        app.logger.info("MAIL_SERVER 미설정 - 메일을 건너뜁니다: %s", subject)
        app.logger.info("본문:\n%s", text_body)
        return
    msg = Message(
        subject,
        sender=sender or app.config.get("MAIL_DEFAULT_SENDER"),
        recipients=recipients,
    )
    msg.body = text_body
    msg.html = html_body
    Thread(target=_send_async, args=(app, msg)).start()


def send_password_reset_email(user) -> None:
    token = user.generate_token("reset-password", expires_in=600)
    send_email(
        "[뭐 먹으러 갈까?] 비밀번호 재설정",
        recipients=[user.email],
        text_body=render_template("email/reset_password.txt", user=user, token=token),
        html_body=render_template("email/reset_password.html", user=user, token=token),
    )
