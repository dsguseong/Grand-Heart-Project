"""데이터 모델.

기존 구조와 가장 크게 달라진 점
-------------------------------
기존에는 User 테이블의 food_json / filter_food_json / preference_json 이라는
TEXT 컬럼에 파이썬 dict 를 통째로 json.dumps 해서 넣었습니다. 이 방식은

  * 회원가입 직후 값이 빈 문자열('')이라 json.loads('') 가 예외를 냅니다.
  * 음식이 추가되면 기존 사용자의 dict 에는 그 키가 없어 KeyError 가 납니다.
  * "이 음식을 좋아하는 사람" 같은 질의를 SQL 로 할 수 없습니다.
  * 동시 요청 시 dict 전체를 덮어쓰므로 평가가 유실됩니다.

그래서 Preference / FoodExclusion 테이블로 정규화했습니다.
음식 한 건에 대한 평가가 행 하나가 되므로 위 문제가 전부 사라집니다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import md5

import jwt
from flask import current_app
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint, func
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager


def utcnow() -> datetime:
    """타임존 인식 UTC. datetime.utcnow() 는 파이썬 3.12에서 deprecated 입니다."""
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """SQLite 는 타임존을 저장하지 않습니다.

    aware datetime 을 넣어도 읽을 때는 naive 로 돌아오므로, 그대로 빼면
    "can't subtract offset-naive and offset-aware datetimes" 가 납니다.
    DB에서 읽은 값은 항상 이 함수를 거쳐 비교하세요.
    """
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


# 선호도 점수 정의 (기획서 기준)
SCORE_DISLIKE = 1  # 싫어요
SCORE_SOSO = 2  # 보통
SCORE_LIKE = 3  # 좋아요
SCORE_LABELS = {SCORE_DISLIKE: "싫어요", SCORE_SOSO: "보통", SCORE_LIKE: "좋아요"}


followers = db.Table(
    "followers",
    db.Column("follower_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
    db.Column("followed_id", db.Integer, db.ForeignKey("user.id"), primary_key=True),
)


class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True, nullable=False)
    email = db.Column(db.String(120), index=True, unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    about_me = db.Column(db.String(140))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    last_seen = db.Column(db.DateTime(timezone=True), default=utcnow)

    preferences = db.relationship(
        "Preference", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )
    exclusions = db.relationship(
        "FoodExclusion", back_populates="user", lazy="dynamic", cascade="all, delete-orphan"
    )

    followed = db.relationship(
        "User",
        secondary=followers,
        primaryjoin=(followers.c.follower_id == id),
        secondaryjoin=(followers.c.followed_id == id),
        backref=db.backref("followers", lazy="dynamic"),
        lazy="dynamic",
    )

    # --- 비밀번호 ---
    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    # --- 팔로우 ---
    def follow(self, user: "User") -> None:
        if user.id != self.id and not self.is_following(user):
            self.followed.append(user)

    def unfollow(self, user: "User") -> None:
        if self.is_following(user):
            self.followed.remove(user)

    def is_following(self, user: "User") -> bool:
        if user.id is None:
            return False
        return self.followed.filter(followers.c.followed_id == user.id).count() > 0

    def is_followed_by(self, user: "User") -> bool:
        if user.id is None:
            return False
        return self.followers.filter(followers.c.follower_id == user.id).count() > 0

    def mutual_friends(self) -> list["User"]:
        """서로 팔로우 중인 사용자만 반환. 그룹 추천은 이 관계에서만 동작합니다."""
        return [u for u in self.followed.all() if u.is_following(self)]

    # --- 기타 ---
    def avatar(self, size: int = 80) -> str:
        digest = md5(self.email.lower().encode("utf-8")).hexdigest()
        return f"https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}"

    def rated_count(self) -> int:
        return self.preferences.count()

    # --- 토큰 (비밀번호 재설정 / API 인증 공용) ---
    def generate_token(self, purpose: str, expires_in: int = 600) -> str:
        payload = {
            "sub": str(self.id),
            "purpose": purpose,
            "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        }
        return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")

    @staticmethod
    def verify_token(token: str, purpose: str) -> "User | None":
        try:
            payload = jwt.decode(
                token, current_app.config["SECRET_KEY"], algorithms=["HS256"]
            )
        except jwt.PyJWTError:
            return None
        if payload.get("purpose") != purpose:
            return None
        try:
            user_id = int(payload["sub"])
        except (KeyError, TypeError, ValueError):
            return None
        return db.session.get(User, user_id)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, int(user_id))


class FoodItem(db.Model):
    """음식 종류. 예) 카테고리='찌개', 이름='김치찌개'.

    기존 코드는 이미지 파일명을 매번 split('_') 해서 카테고리/음식명을 뽑았습니다.
    파일명에 '_' 가 없으면 IndexError 로 500 이 났고, 같은 음식의 사진 여러 장이
    서로 다른 음식으로 취급됐습니다. 여기서는 한 번만 파싱해 테이블에 넣습니다.
    """

    __tablename__ = "food_item"
    __table_args__ = (UniqueConstraint("category", "name", name="uq_food_category_name"),)

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(40), index=True, nullable=False)
    name = db.Column(db.String(80), index=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    images = db.relationship(
        "FoodImage", back_populates="item", lazy="dynamic", cascade="all, delete-orphan"
    )
    preferences = db.relationship(
        "Preference", back_populates="item", lazy="dynamic", cascade="all, delete-orphan"
    )
    exclusions = db.relationship(
        "FoodExclusion", back_populates="item", lazy="dynamic", cascade="all, delete-orphan"
    )

    @property
    def label(self) -> str:
        return f"{self.category} · {self.name}"

    def cover(self) -> "FoodImage | None":
        return self.images.order_by(FoodImage.id).first()

    def __repr__(self) -> str:
        return f"<FoodItem {self.category}/{self.name}>"


class FoodImage(db.Model):
    """음식 사진. 파일은 디스크에 두고 DB에는 경로만 보관합니다.

    기존 코드는 원본 바이너리(imgdata)와 base64 문자열(rendered_data)을 둘 다
    DB에 저장했습니다. 같은 사진을 두 번, 그것도 base64는 원본보다 33% 크게
    저장하는 셈이라 SQLite 파일이 급격히 커지고 목록 조회가 느려집니다.
    """

    __tablename__ = "food_image"

    id = db.Column(db.Integer, primary_key=True)
    food_item_id = db.Column(
        db.Integer, db.ForeignKey("food_item.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename = db.Column(db.String(255), unique=True, nullable=False)
    original_name = db.Column(db.String(255))
    uploaded_at = db.Column(db.DateTime(timezone=True), default=utcnow)
    uploader_id = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"))

    item = db.relationship("FoodItem", back_populates="images")
    uploader = db.relationship("User")

    @property
    def url(self) -> str:
        from flask import url_for

        return url_for("static", filename=f"uploads/foods/{self.filename}")

    def __repr__(self) -> str:
        return f"<FoodImage {self.filename}>"


class Preference(db.Model):
    """사용자 한 명이 음식 하나에 남긴 평가. (좋아요 3 / 보통 2 / 싫어요 1)"""

    __tablename__ = "preference"
    __table_args__ = (UniqueConstraint("user_id", "food_item_id", name="uq_pref_user_item"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    food_item_id = db.Column(
        db.Integer, db.ForeignKey("food_item.id", ondelete="CASCADE"), index=True, nullable=False
    )
    score = db.Column(db.SmallInteger, nullable=False)
    rated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user = db.relationship("User", back_populates="preferences")
    item = db.relationship("FoodItem", back_populates="preferences")

    @property
    def label(self) -> str:
        return SCORE_LABELS.get(self.score, "?")

    def __repr__(self) -> str:
        return f"<Preference u{self.user_id} f{self.food_item_id} = {self.score}>"


class FoodExclusion(db.Model):
    """'못 먹어요'. 알레르기·종교·비선호 등으로 추천에서 완전히 빼는 음식."""

    __tablename__ = "food_exclusion"
    __table_args__ = (UniqueConstraint("user_id", "food_item_id", name="uq_excl_user_item"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False
    )
    food_item_id = db.Column(
        db.Integer, db.ForeignKey("food_item.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reason = db.Column(db.String(120))
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    user = db.relationship("User", back_populates="exclusions")
    item = db.relationship("FoodItem", back_populates="exclusions")

    def __repr__(self) -> str:
        return f"<FoodExclusion u{self.user_id} f{self.food_item_id}>"


def food_stats() -> dict:
    """대시보드용 집계."""
    return {
        "items": db.session.scalar(db.select(func.count(FoodItem.id))) or 0,
        "images": db.session.scalar(db.select(func.count(FoodImage.id))) or 0,
        "users": db.session.scalar(db.select(func.count(User.id))) or 0,
    }
