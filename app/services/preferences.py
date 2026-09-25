"""취향 데이터 읽기/쓰기.

기존 random_show() 의 치명적 버그
---------------------------------
    filtered_list = [int(key) for key, value in cat_items_list if value == 0]
    random_img_id = random.choice(filtered_list)
    random_img_list.append(image_list[random_img_id])

filtered_list 에 들어 있는 값은 **DB의 이미지 id** 인데, 그것을 파이썬
**리스트 인덱스**로 그대로 썼습니다. id는 1부터, 인덱스는 0부터 시작하므로
항상 한 칸씩 밀린 엉뚱한 음식이 나오고, 이미지를 하나라도 삭제하면 완전히
어긋납니다. README에 적힌 "필터링 된 음식인데 랜덤 이미지에서 나타나는 현상"의
원인이 바로 이것입니다. 게다가 남은 음식이 없으면 random.choice([]) 가
IndexError 를 던져 500 페이지가 떴습니다.

여기서는 파이썬에서 인덱스 계산을 하지 않고, "아직 평가하지 않았고 제외하지도
않은 음식" 을 SQL 로 직접 골라옵니다. 남은 음식이 없으면 None 을 돌려주고
화면에서 안내 문구를 띄웁니다.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.extensions import db
from app.models import (
    SCORE_DISLIKE,
    SCORE_LIKE,
    SCORE_SOSO,
    FoodExclusion,
    FoodImage,
    FoodItem,
    Preference,
    User,
)

VALID_SCORES = {SCORE_DISLIKE, SCORE_SOSO, SCORE_LIKE}


def _rated_item_ids(user: User):
    return select(Preference.food_item_id).where(Preference.user_id == user.id)


def _excluded_item_ids(user: User):
    return select(FoodExclusion.food_item_id).where(FoodExclusion.user_id == user.id)


def next_food_for(user: User) -> FoodItem | None:
    """아직 평가하지 않았고 '못 먹어요'로 빼지도 않은 음식 하나를 무작위로."""
    stmt = (
        select(FoodItem)
        .where(FoodItem.id.not_in(_rated_item_ids(user)))
        .where(FoodItem.id.not_in(_excluded_item_ids(user)))
        .where(FoodItem.images.any())  # 사진이 없는 항목은 스와이프에서 제외
        .order_by(func.random())
        .limit(1)
    )
    return db.session.scalars(stmt).first()


def random_image_for(item: FoodItem) -> FoodImage | None:
    """같은 음식의 사진이 여러 장이면 매번 다른 장을 보여줍니다."""
    stmt = (
        select(FoodImage)
        .where(FoodImage.food_item_id == item.id)
        .order_by(func.random())
        .limit(1)
    )
    return db.session.scalars(stmt).first()


def record_vote(user: User, item: FoodItem, score: int) -> Preference:
    """평가 저장. 같은 음식을 다시 평가하면 덮어씁니다(중복 행이 생기지 않음)."""
    if score not in VALID_SCORES:
        raise ValueError(f"허용되지 않은 점수입니다: {score}")

    pref = db.session.scalar(
        select(Preference).where(
            Preference.user_id == user.id, Preference.food_item_id == item.id
        )
    )
    if pref is None:
        pref = Preference(user_id=user.id, food_item_id=item.id, score=score)
        db.session.add(pref)
    else:
        pref.score = score
    db.session.commit()
    return pref


def exclude_food(user: User, item: FoodItem, reason: str | None = None) -> FoodExclusion:
    """'못 먹어요' 처리. 이미 남긴 평가가 있으면 함께 지웁니다."""
    excl = db.session.scalar(
        select(FoodExclusion).where(
            FoodExclusion.user_id == user.id, FoodExclusion.food_item_id == item.id
        )
    )
    if excl is None:
        excl = FoodExclusion(user_id=user.id, food_item_id=item.id, reason=reason)
        db.session.add(excl)
    else:
        excl.reason = reason

    db.session.execute(
        db.delete(Preference).where(
            Preference.user_id == user.id, Preference.food_item_id == item.id
        )
    )
    db.session.commit()
    return excl


def unexclude_food(user: User, item: FoodItem) -> None:
    db.session.execute(
        db.delete(FoodExclusion).where(
            FoodExclusion.user_id == user.id, FoodExclusion.food_item_id == item.id
        )
    )
    db.session.commit()


def progress(user: User) -> dict:
    """스와이프 진행률."""
    total = db.session.scalar(select(func.count(FoodItem.id))) or 0
    rated = db.session.scalar(
        select(func.count(Preference.id)).where(Preference.user_id == user.id)
    ) or 0
    excluded = db.session.scalar(
        select(func.count(FoodExclusion.id)).where(FoodExclusion.user_id == user.id)
    ) or 0
    done = rated + excluded
    return {
        "total": total,
        "rated": rated,
        "excluded": excluded,
        "remaining": max(total - done, 0),
        "percent": round(done / total * 100) if total else 0,
    }


def rating_breakdown(user: User) -> dict[int, int]:
    rows = db.session.execute(
        select(Preference.score, func.count(Preference.id))
        .where(Preference.user_id == user.id)
        .group_by(Preference.score)
    ).all()
    counts = {SCORE_DISLIKE: 0, SCORE_SOSO: 0, SCORE_LIKE: 0}
    counts.update({score: n for score, n in rows})
    return counts
