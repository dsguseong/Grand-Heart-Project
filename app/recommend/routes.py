from flask import current_app, flash, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.models import User
from app.recommend import bp
from app.services.places import search_nearby
from app.services.recommender import category_affinity, recommend_for_group


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    """그룹 추천.

    기획대로 '서로 팔로우한 사이'에서만 동작합니다.
    한쪽만 팔로우한 상대는 목록에 나타나지 않습니다.
    """
    friends = current_user.mutual_friends()
    friend_ids = {f.id for f in friends}

    selected_ids = (
        {int(v) for v in request.form.getlist("members") if v.isdigit()}
        if request.method == "POST"
        else set()
    )
    # 목록에 없는 id 를 폼에 끼워 넣어도 무시합니다.
    selected_ids &= friend_ids

    result = None
    if request.method == "POST":
        if not selected_ids:
            flash("함께 먹을 사람을 한 명 이상 골라 주세요.", "warning")
        else:
            members = [current_user._get_current_object()] + db.session.scalars(
                select(User).where(User.id.in_(selected_ids))
            ).all()
            result = recommend_for_group(members, top_n=current_app.config["RECOMMEND_TOP_N"])

    return render_template(
        "recommend/index.html",
        title="함께 먹을 음식",
        friends=friends,
        selected_ids=selected_ids,
        result=result,
        my_affinity=category_affinity(current_user),
    )


@bp.route("/nearby")
@login_required
def nearby():
    """음식 이름으로 주변 식당 검색. 좌표는 브라우저 geolocation 에서 받습니다."""
    keyword = (request.args.get("keyword") or "").strip()
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    if not keyword or lat is None or lng is None:
        return jsonify(ok=False, places=[], message="검색어와 위치가 필요합니다."), 400
    return jsonify(search_nearby(keyword, lat, lng))
