from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.main import bp
from app.main.forms import EditProfileForm, EmptyForm
from app.models import SCORE_LIKE, FoodItem, Preference, User, as_utc, food_stats, utcnow
from app.services.preferences import progress, rating_breakdown


@bp.before_app_request
def touch_last_seen():
    """마지막 접속 시각 갱신.

    기존 코드는 요청마다 무조건 db.session.commit() 을 호출했습니다.
    로그인하지 않은 요청에서도 커밋이 일어나 불필요한 쓰기가 생기므로,
    값이 실제로 바뀌었을 때만 커밋합니다.
    """
    if current_user.is_authenticated:
        now = utcnow()
        last = as_utc(current_user.last_seen)
        if last is None or (now - last).total_seconds() > 60:
            current_user.last_seen = now
            db.session.commit()


@bp.route("/")
@bp.route("/index")
@login_required
def index():
    return render_template(
        "main/index.html",
        title="홈",
        progress=progress(current_user),
        breakdown=rating_breakdown(current_user),
        friends=current_user.mutual_friends(),
        stats=food_stats(),
    )


@bp.route("/people")
@login_required
def people():
    """다른 사용자 찾기. 서로 팔로우해야 그룹 추천이 열립니다."""
    q = (request.args.get("q") or "").strip()
    page = request.args.get("page", 1, type=int)
    stmt = select(User).where(User.id != current_user.id).order_by(User.username)
    if q:
        stmt = stmt.where(User.username.ilike(f"%{q}%"))
    pagination = db.paginate(stmt, page=page, per_page=20, error_out=False)
    return render_template(
        "main/people.html",
        title="사람 찾기",
        users=pagination.items,
        pagination=pagination,
        q=q,
        form=EmptyForm(),
    )


@bp.route("/user/<username>")
@login_required
def user(username):
    target = db.session.scalar(select(User).where(User.username == username))
    if target is None:
        abort(404)
    top_likes = db.session.scalars(
        select(FoodItem)
        .join(Preference, Preference.food_item_id == FoodItem.id)
        .where(Preference.user_id == target.id, Preference.score == SCORE_LIKE)
        .order_by(Preference.rated_at.desc())
        .limit(12)
    ).all()
    return render_template(
        "main/user.html",
        title=f"{target.username} 님",
        user=target,
        form=EmptyForm(),
        progress=progress(target),
        top_likes=top_likes,
        is_mutual=target.is_following(current_user) and current_user.is_following(target),
    )


@bp.route("/edit-profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    form = EditProfileForm(current_user.username)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.about_me = form.about_me.data
        db.session.commit()
        flash("프로필을 저장했습니다.", "success")
        return redirect(url_for("main.user", username=current_user.username))
    if request.method == "GET":
        form.username.data = current_user.username
        form.about_me.data = current_user.about_me
    return render_template("main/edit_profile.html", title="프로필 수정", form=form)


@bp.route("/follow/<username>", methods=["POST"])
@login_required
def follow(username):
    form = EmptyForm()
    if not form.validate_on_submit():
        return redirect(url_for("main.people"))
    target = db.session.scalar(select(User).where(User.username == username))
    if target is None:
        flash(f"{username} 님을 찾을 수 없습니다.", "danger")
        return redirect(url_for("main.people"))
    if target.id == current_user.id:
        flash("자기 자신은 팔로우할 수 없습니다.", "warning")
        return redirect(url_for("main.user", username=username))
    current_user.follow(target)
    db.session.commit()
    if target.is_following(current_user):
        flash(f"{username} 님과 서로 팔로우가 되었습니다. 이제 함께 추천을 받을 수 있어요.", "success")
    else:
        flash(f"{username} 님을 팔로우했습니다. 상대도 팔로우하면 함께 추천을 받습니다.", "info")
    return redirect(url_for("main.user", username=username))


@bp.route("/unfollow/<username>", methods=["POST"])
@login_required
def unfollow(username):
    form = EmptyForm()
    if not form.validate_on_submit():
        return redirect(url_for("main.people"))
    target = db.session.scalar(select(User).where(User.username == username))
    if target is None:
        flash(f"{username} 님을 찾을 수 없습니다.", "danger")
        return redirect(url_for("main.people"))
    if target.id == current_user.id:
        flash("자기 자신은 언팔로우할 수 없습니다.", "warning")
        return redirect(url_for("main.user", username=username))
    current_user.unfollow(target)
    db.session.commit()
    flash(f"{username} 님 팔로우를 해제했습니다.", "info")
    return redirect(url_for("main.user", username=username))
