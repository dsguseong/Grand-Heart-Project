"""그룹 추천 (Weighted Sum).

원본 Weighted_Sum/Weighted_Sum_Algorithm.py 는 딕셔너리 두 개를 하드코딩해
결과를 눈으로 확인하는 스크립트였고, 다음 문제가 있었습니다.

  * 사용자가 정확히 2명일 때만 동작 (list(User.values())[0], [1] 로 접근)
  * user2 의 길이를 user1 의 키 개수로 잘라 씀 -> 카테고리가 다르면 잘림
  * 결과가 점수 리스트라서 어떤 카테고리인지 알 수 없음 (sorted 로 값만 정렬)
  * 예외 카테고리를 구하는 common() 이 계산만 하고 결과에 반영되지 않음

여기서는 N명으로 일반화하고, 팀이 메모에 적어둔 두 가지 예외 규칙을 실제로
적용합니다.

  1. 한 명이라도 '못 먹어요'로 뺀 음식은 무조건 후보에서 제외한다(거부권).
  2. 공통으로 선호하는 카테고리가 하나도 없어도 오류 없이 TOP-N 을 낸다
     (엄격 규칙으로 후보가 비면 완화 규칙으로 자동 폴백).

점수 정의
---------
평가 점수 1/2/3 을 -1/0/+1 로 옮겨 씁니다(중앙값 2 = 보통 = 0).
카테고리 선호도 = 그 카테고리에서 받은 평균값 ∈ [-1, 1].
그룹 점수 = 구성원 선호도의 가중 평균. 가중치를 주지 않으면 1/N 로
동일 가중이 되어 원본 알고리즘 `(x + y) * (1/len(User))` 와 같아집니다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select

from app.extensions import db
from app.models import FoodExclusion, FoodItem, Preference, User
from app.services import embeddings as emb

NEUTRAL = 2  # '보통' 을 기준점으로


@dataclass
class Recommendation:
    item: FoodItem
    score: float
    per_user: dict[str, float | None] = field(default_factory=dict)
    reason: str = ""
    category_score: float = 0.0
    embedding_score: float | None = None  # 임베딩이 없으면 None


@dataclass
class GroupResult:
    members: list[User]
    category_scores: dict[str, float]
    recommendations: list[Recommendation]
    vetoed_categories: list[str]
    relaxed: bool = False  # 엄격 규칙으로 후보가 없어 완화했는지
    notes: list[str] = field(default_factory=list)
    used_embeddings: bool = False  # 이미지 임베딩이 점수에 반영됐는지


def category_affinity(user: User) -> dict[str, float]:
    """사용자의 카테고리별 선호도. -1(싫어요) ~ +1(좋아요)."""
    rows = db.session.execute(
        select(FoodItem.category, func.avg(Preference.score), func.count(Preference.id))
        .join(Preference, Preference.food_item_id == FoodItem.id)
        .where(Preference.user_id == user.id)
        .group_by(FoodItem.category)
    ).all()
    return {category: float(avg) - NEUTRAL for category, avg, _n in rows}


def category_sample_size(user: User) -> dict[str, int]:
    rows = db.session.execute(
        select(FoodItem.category, func.count(Preference.id))
        .join(Preference, Preference.food_item_id == FoodItem.id)
        .where(Preference.user_id == user.id)
        .group_by(FoodItem.category)
    ).all()
    return {category: int(n) for category, n in rows}


def weighted_sum(
    vectors: list[dict[str, float]], weights: list[float] | None = None
) -> dict[str, float]:
    """N개의 선호도 벡터를 가중 평균. 한 명에게만 있는 카테고리는 0으로 채웁니다."""
    if not vectors:
        return {}
    if weights is None:
        weights = [1.0 / len(vectors)] * len(vectors)
    if len(weights) != len(vectors):
        raise ValueError("weights 길이가 vectors 와 다릅니다.")

    total_weight = sum(weights) or 1.0
    keys = set().union(*(v.keys() for v in vectors))
    return {
        key: sum(vec.get(key, 0.0) * w for vec, w in zip(vectors, weights)) / total_weight
        for key in keys
    }


def _excluded_item_ids(members: list[User]) -> set[int]:
    """구성원 중 한 명이라도 '못 먹어요'로 뺀 음식 id."""
    if not members:
        return set()
    rows = db.session.scalars(
        select(FoodExclusion.food_item_id).where(
            FoodExclusion.user_id.in_([m.id for m in members])
        )
    ).all()
    return set(rows)


def _item_scores(members: list[User], item_ids: list[int]) -> dict[int, dict[int, int]]:
    """{food_item_id: {user_id: score}}"""
    if not members or not item_ids:
        return {}
    rows = db.session.execute(
        select(Preference.food_item_id, Preference.user_id, Preference.score).where(
            Preference.user_id.in_([m.id for m in members]),
            Preference.food_item_id.in_(item_ids),
        )
    ).all()
    out: dict[int, dict[int, int]] = {}
    for item_id, user_id, score in rows:
        out.setdefault(item_id, {})[user_id] = score
    return out


def recommend_for_group(
    members: list[User],
    top_n: int = 3,
    veto_threshold: float = 0.0,
    embedding_weight: float | None = None,
) -> GroupResult:
    """그룹에 맞는 음식 TOP-N.

    veto_threshold: 구성원 한 명이라도 카테고리 선호도가 이 값 이하이면
        그 카테고리를 후보에서 뺍니다(원본의 '예외 카테고리' 규칙).
    embedding_weight: 아무도 평가하지 않은 음식의 점수를 낼 때 이미지 임베딩을
        얼마나 믿을지(0~1). None 이면 설정값을 씁니다. 임베딩 파일이 없으면
        자동으로 0 이 되어 기존 통계 방식과 완전히 동일하게 동작합니다.
    """
    members = [m for m in members if m is not None]
    notes: list[str] = []

    if len(members) < 2:
        return GroupResult(members, {}, [], [], notes=["추천에는 2명 이상이 필요합니다."])

    vectors = [category_affinity(m) for m in members]
    silent = [m.username for m, v in zip(members, vectors) if not v]
    if silent:
        notes.append(f"아직 취향 데이터가 없는 사용자: {', '.join(silent)}")

    group_scores = weighted_sum(vectors)
    if not group_scores:
        return GroupResult(
            members, {}, [], [], notes=notes + ["구성원 모두 평가 기록이 없습니다."]
        )

    # 1) 거부권 규칙: 한 명이라도 싫어하는 카테고리는 제외
    vetoed = sorted(
        {
            category
            for category in group_scores
            for vec in vectors
            if vec.get(category, 0.0) <= veto_threshold
        }
    )
    allowed = {c: s for c, s in group_scores.items() if c not in vetoed}

    relaxed = False
    if not allowed:
        # 2) 폴백: 겹치는 카테고리가 하나도 없어도 결과는 낸다
        relaxed = True
        allowed = dict(group_scores)
        notes.append("모두가 함께 좋아하는 카테고리가 없어, 평균 점수가 높은 순으로 추천합니다.")

    ranked_categories = sorted(allowed, key=lambda c: (-allowed[c], c))

    # 3) 카테고리 안에서 실제 음식 고르기
    excluded_ids = _excluded_item_ids(members)
    candidates = db.session.scalars(
        select(FoodItem)
        .where(FoodItem.category.in_(ranked_categories))
        .where(FoodItem.images.any())
    ).all()
    candidates = [c for c in candidates if c.id not in excluded_ids]

    scores_by_item = _item_scores(members, [c.id for c in candidates])
    member_ids = [m.id for m in members]
    name_by_id = {m.id: m.username for m in members}

    # 4) 이미지 임베딩(있으면). 평가가 없는 음식의 점수를 메우는 데 씁니다.
    if embedding_weight is None:
        embedding_weight = _default_embedding_weight()
    embedding_scores = _group_embedding_scores(
        members, [c.id for c in candidates]
    ) if embedding_weight > 0 else {}
    used_embeddings = bool(embedding_scores)
    if embedding_weight > 0 and not used_embeddings:
        embedding_weight = 0.0

    scored: list[Recommendation] = []
    for item in candidates:
        raw = scores_by_item.get(item.id, {})
        # 한 명이라도 직접 '싫어요'를 준 음식은 뺀다
        if any(raw.get(uid) == 1 for uid in member_ids):
            continue

        per_user = {
            name_by_id[uid]: (raw[uid] - NEUTRAL) if uid in raw else None for uid in member_ids
        }
        rated = [v for v in per_user.values() if v is not None]
        category_score = allowed.get(item.category, 0.0)
        embedding_score = embedding_scores.get(item.id)

        # 평가가 없는 음식의 사전 점수 = 카테고리 통계 + 이미지 임베딩 혼합
        if embedding_score is not None and embedding_weight > 0:
            prior = embedding_weight * embedding_score + (1 - embedding_weight) * category_score
        else:
            prior = category_score

        if rated:
            # 직접 평가가 있으면 그쪽을 우선하고, 나머지 비율만 사전 점수로 보간
            direct = sum(rated) / len(rated)
            coverage = len(rated) / len(member_ids)
            score = direct * coverage + prior * (1 - coverage)
            reason = f"{len(rated)}/{len(member_ids)}명이 직접 평가"
        else:
            score = prior
            if embedding_score is not None and embedding_weight > 0:
                reason = f"사진 유사도 + '{item.category}' 카테고리 선호도"
            else:
                reason = f"'{item.category}' 카테고리 선호도 기반"

        scored.append(
            Recommendation(
                item=item,
                score=round(score, 3),
                per_user=per_user,
                reason=reason,
                category_score=round(category_score, 3),
                embedding_score=round(embedding_score, 3) if embedding_score is not None else None,
            )
        )

    scored.sort(key=lambda r: (-r.score, r.item.category, r.item.name))

    return GroupResult(
        members=members,
        category_scores={c: round(allowed[c], 3) for c in ranked_categories},
        recommendations=scored[:top_n],
        vetoed_categories=vetoed,
        relaxed=relaxed,
        notes=notes,
        used_embeddings=used_embeddings,
    )


def _default_embedding_weight() -> float:
    """설정값. 앱 컨텍스트 밖(단위 테스트 등)에서는 0."""
    try:
        from flask import current_app

        return float(current_app.config.get("EMBEDDING_WEIGHT", 0.6))
    except Exception:
        return 0.0


def _group_embedding_scores(members: list[User], item_ids: list[int]) -> dict[int, float]:
    """구성원별 임베딩 선호도를 구해 가중 합합니다.

    카테고리 점수와 같은 방식(1/N 동일 가중)으로 묶어, 두 신호가 같은
    -1 ~ +1 스케일에서 비교되도록 맞춥니다.
    임베딩 파일이 없거나 취향 벡터를 만들 수 없으면 빈 dict 을 돌려주고,
    호출부는 기존 통계 방식으로 그대로 동작합니다.
    """
    if not emb.available() or not item_ids:
        return {}

    per_member = [emb.affinity_for_items(m, item_ids) for m in members]
    per_member = [d for d in per_member if d]
    if not per_member:
        return {}

    weight = 1.0 / len(per_member)
    totals: dict[int, float] = {}
    for scores in per_member:
        for item_id, value in scores.items():
            totals[item_id] = totals.get(item_id, 0.0) + value * weight
    return totals
