"""JSON API (/api/v1).

기획서에 있는 '구글플레이 앱으로도 동작' 을 위해 화면(HTML)과 데이터(JSON)를
분리해 두었습니다. 앱은 이 엔드포인트만 호출하면 되고, 웹 화면 코드를 건드릴
필요가 없습니다. 인증은 세션 쿠키 대신 Bearer 토큰을 씁니다.
"""

from __future__ import annotations

from functools import wraps

from flask import current_app, g, jsonify, request
from sqlalchemy import select

from app.api import bp
from app.extensions import db
from app.models import (
    SCORE_DISLIKE,
    SCORE_LIKE,
    SCORE_SOSO,
    FoodExclusion,
    FoodItem,
    Preference,
    User,
)
from app.services.places import search_nearby
from app.services.preferences import (
    exclude_food,
    next_food_for,
    progress,
    random_image_for,
    record_vote,
)
from app.services.recommender import recommend_for_group

ACTION_SCORES = {"like": SCORE_LIKE, "soso": SCORE_SOSO, "dislike": SCORE_DISLIKE}


def token_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify(error="missing_token"), 401
        user = User.verify_token(header[7:], "api")
        if user is None:
            return jsonify(error="invalid_token"), 401
        g.current_user = user
        return view(*args, **kwargs)

    return wrapper


def _item_json(item: FoodItem, image=None) -> dict:
    return {
        "id": item.id,
        "category": item.category,
        "name": item.name,
        "image_url": image.url if image else None,
    }


@bp.post("/token")
def issue_token():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    user = db.session.scalar(select(User).where(User.username == username))
    if user is None or not user.check_password(password):
        return jsonify(error="invalid_credentials"), 401
    ttl = current_app.config["API_TOKEN_TTL"]
    return jsonify(
        token=user.generate_token("api", expires_in=ttl),
        expires_in=ttl,
        user={"id": user.id, "username": user.username, "is_admin": user.is_admin},
    )


@bp.get("/me")
@token_required
def me():
    user = g.current_user
    return jsonify(
        id=user.id,
        username=user.username,
        about_me=user.about_me,
        progress=progress(user),
        friends=[{"id": f.id, "username": f.username} for f in user.mutual_friends()],
    )


@bp.get("/foods/next")
@token_required
def next_food():
    item = next_food_for(g.current_user)
    if item is None:
        return jsonify(
            item=None, message="평가할 음식을 모두 봤습니다.", progress=progress(g.current_user)
        )
    image = random_image_for(item)
    return jsonify(item=_item_json(item, image), progress=progress(g.current_user))


@bp.post("/foods/<int:item_id>/vote")
@token_required
def vote(item_id):
    item = db.session.get(FoodItem, item_id)
    if item is None:
        return jsonify(error="not_found"), 404

    data = request.get_json(silent=True) or {}
    action = data.get("action")

    if action == "exclude":
        exclude_food(g.current_user, item)
    elif action in ACTION_SCORES:
        record_vote(g.current_user, item, ACTION_SCORES[action])
    else:
        return jsonify(error="invalid_action", allowed=[*ACTION_SCORES, "exclude"]), 400

    return jsonify(ok=True, progress=progress(g.current_user))


@bp.get("/preferences")
@token_required
def my_preferences():
    rows = db.session.scalars(
        select(Preference).where(Preference.user_id == g.current_user.id)
    ).all()
    excluded = db.session.scalars(
        select(FoodExclusion).where(FoodExclusion.user_id == g.current_user.id)
    ).all()
    return jsonify(
        preferences=[
            {
                "item_id": p.food_item_id,
                "name": p.item.name,
                "category": p.item.category,
                "score": p.score,
            }
            for p in rows
        ],
        exclusions=[{"item_id": e.food_item_id, "name": e.item.name} for e in excluded],
    )


@bp.post("/recommend")
@token_required
def recommend():
    data = request.get_json(silent=True) or {}
    requested = {int(v) for v in data.get("member_ids", []) if str(v).isdigit()}
    friends = {f.id: f for f in g.current_user.mutual_friends()}

    unknown = requested - friends.keys()
    if unknown:
        return jsonify(error="not_mutual_followers", ids=sorted(unknown)), 403
    if not requested:
        return jsonify(error="member_ids_required"), 400

    members = [g.current_user] + [friends[i] for i in requested]
    result = recommend_for_group(members, top_n=current_app.config["RECOMMEND_TOP_N"])
    return jsonify(
        members=[m.username for m in result.members],
        category_scores=result.category_scores,
        vetoed_categories=result.vetoed_categories,
        relaxed=result.relaxed,
        notes=result.notes,
        recommendations=[
            {
                "item": _item_json(r.item, r.item.cover()),
                "score": r.score,
                "reason": r.reason,
                "per_user": r.per_user,
            }
            for r in result.recommendations
        ],
    )


@bp.get("/places/nearby")
@token_required
def places_nearby():
    keyword = (request.args.get("keyword") or "").strip()
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    if not keyword or lat is None or lng is None:
        return jsonify(ok=False, places=[], message="keyword, lat, lng 가 필요합니다."), 400
    return jsonify(search_nearby(keyword, lat, lng))
