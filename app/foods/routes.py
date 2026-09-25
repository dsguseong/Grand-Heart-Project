from functools import wraps
from pathlib import Path

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select

from app.extensions import db
from app.foods import bp
from app.foods.forms import CsrfForm, UploadForm
from app.models import (
    SCORE_DISLIKE,
    SCORE_LIKE,
    SCORE_SOSO,
    FoodExclusion,
    FoodImage,
    FoodItem,
    Preference,
)
from app.services import images as image_service
from app.services.preferences import (
    exclude_food,
    next_food_for,
    progress,
    random_image_for,
    record_vote,
    unexclude_food,
)


def admin_required(view):
    """음식 업로드는 관리자만. 기존 코드에는 이 검사가 아예 없었습니다."""

    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapper


def _upload_dir() -> Path:
    return Path(current_app.config["UPLOAD_FOLDER"])


def _get_item_or_404(item_id: int) -> FoodItem:
    item = db.session.get(FoodItem, item_id)
    if item is None:
        abort(404)
    return item


@bp.route("/swipe")
@login_required
def swipe():
    item = next_food_for(current_user)
    image = random_image_for(item) if item else None
    return render_template(
        "foods/swipe.html",
        title="오늘의 음식",
        item=item,
        image=image,
        form=CsrfForm(),
        progress=progress(current_user),
    )


@bp.route("/vote/<int:item_id>", methods=["POST"])
@login_required
def vote(item_id):
    """평가 저장.

    기존 코드는 /random_show/prefer/<이름> 을 GET+POST 로 열어두어 주소만
    입력해도 평가가 저장됐습니다(부수효과가 있는 GET). POST 전용 + CSRF 로
    바꾸고, 대상은 이름 문자열이 아니라 음식 id 로 지정합니다.
    """
    if not CsrfForm().validate_on_submit():
        flash("요청이 만료되었습니다. 다시 시도해 주세요.", "warning")
        return redirect(url_for("foods.swipe"))

    item = _get_item_or_404(item_id)
    action = request.form.get("action")

    if action == "exclude":
        exclude_food(current_user, item)
        flash(f"'{item.name}' 은(는) 앞으로 추천에서 빼겠습니다.", "info")
    else:
        score_map = {"like": SCORE_LIKE, "soso": SCORE_SOSO, "dislike": SCORE_DISLIKE}
        if action not in score_map:
            flash("알 수 없는 요청입니다.", "danger")
            return redirect(url_for("foods.swipe"))
        record_vote(current_user, item, score_map[action])

    return redirect(url_for("foods.swipe"))


@bp.route("/my-tastes")
@login_required
def my_tastes():
    page = request.args.get("page", 1, type=int)
    stmt = (
        select(Preference)
        .where(Preference.user_id == current_user.id)
        .order_by(Preference.score.desc(), Preference.rated_at.desc())
    )
    pagination = db.paginate(stmt, page=page, per_page=30, error_out=False)
    return render_template(
        "foods/my_tastes.html",
        title="내 취향",
        preferences=pagination.items,
        pagination=pagination,
        progress=progress(current_user),
        form=CsrfForm(),
    )


@bp.route("/exclusions", methods=["GET", "POST"])
@login_required
def exclusions():
    """'못 먹어요' 목록 관리.

    기존 /filter 페이지는 텍스트 입력에 '카테고리_음식명' 을 직접 치게 했고,
    '_' 가 없으면 splitted[1] 에서 IndexError 로 500 이 났습니다.
    목록에서 고르는 방식으로 바꿔 잘못된 입력 자체가 불가능하게 했습니다.
    """
    form = CsrfForm()
    if form.validate_on_submit():
        item_id = request.form.get("item_id", type=int)
        if item_id is None:
            abort(400)
        item = _get_item_or_404(item_id)
        if request.form.get("action") == "remove":
            unexclude_food(current_user, item)
            flash(f"'{item.name}' 을(를) 다시 추천 대상에 넣었습니다.", "info")
        else:
            exclude_food(current_user, item, reason=request.form.get("reason") or None)
            flash(f"'{item.name}' 을(를) 추천에서 뺐습니다.", "info")
        return redirect(url_for("foods.exclusions"))

    excluded = db.session.scalars(
        select(FoodExclusion)
        .where(FoodExclusion.user_id == current_user.id)
        .order_by(FoodExclusion.created_at.desc())
    ).all()
    excluded_ids = {e.food_item_id for e in excluded}

    q = (request.args.get("q") or "").strip()
    stmt = select(FoodItem).order_by(FoodItem.category, FoodItem.name)
    if q:
        stmt = stmt.where(db.or_(FoodItem.name.ilike(f"%{q}%"), FoodItem.category.ilike(f"%{q}%")))
    catalog = [i for i in db.session.scalars(stmt.limit(200)).all() if i.id not in excluded_ids]

    return render_template(
        "foods/exclusions.html",
        title="못 먹는 음식",
        excluded=excluded,
        catalog=catalog,
        q=q,
        form=form,
    )


@bp.route("/catalog")
@login_required
def catalog():
    page = request.args.get("page", 1, type=int)
    q = (request.args.get("q") or "").strip()
    stmt = select(FoodItem).order_by(FoodItem.category, FoodItem.name)
    if q:
        stmt = stmt.where(db.or_(FoodItem.name.ilike(f"%{q}%"), FoodItem.category.ilike(f"%{q}%")))
    pagination = db.paginate(stmt, page=page, per_page=24, error_out=False)
    return render_template(
        "foods/catalog.html",
        title="음식 목록",
        items=pagination.items,
        pagination=pagination,
        q=q,
    )


@bp.route("/upload", methods=["GET", "POST"])
@admin_required
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        allowed = current_app.config["ALLOWED_IMAGE_EXTENSIONS"]
        added, rejected = 0, []
        for storage in request.files.getlist("images"):
            name = (storage.filename or "").strip()
            if not name:
                continue
            if not image_service.allowed_file(name, allowed):
                rejected.append(f"{name} (지원하지 않는 형식)")
                continue
            if image_service.store_upload(storage, _upload_dir(), uploader_id=current_user.id):
                added += 1
            else:
                rejected.append(f"{name} (파일명 규칙 불일치)")
        db.session.commit()

        if added:
            flash(f"{added}장을 등록했습니다.", "success")
        if rejected:
            flash("등록하지 못한 파일: " + ", ".join(rejected[:10]), "warning")
        if not added and not rejected:
            flash("선택된 파일이 없습니다.", "warning")
        return redirect(url_for("foods.upload"))

    recent = db.session.scalars(
        select(FoodImage).order_by(FoodImage.id.desc()).limit(24)
    ).all()
    total_items = db.session.scalar(select(db.func.count(FoodItem.id))) or 0
    total_images = db.session.scalar(select(db.func.count(FoodImage.id))) or 0
    return render_template(
        "foods/upload.html",
        title="음식 사진 등록",
        form=form,
        recent=recent,
        total_items=total_items,
        total_images=total_images,
    )


@bp.route("/image/<int:image_id>/delete", methods=["POST"])
@admin_required
def delete_image(image_id):
    """삭제는 POST 로만.

    기존 코드는 @app.route('/upload/<int:image_id>') 로 GET 삭제를 허용했고,
    같은 접두사의 /upload 목록 라우트와 뒤섞여 있었습니다.
    """
    if not CsrfForm().validate_on_submit():
        abort(400)
    image = db.session.get(FoodImage, image_id)
    if image is None:
        abort(404)
    image_service.delete_image(image, _upload_dir())
    flash("사진을 삭제했습니다.", "info")
    return redirect(url_for("foods.upload"))
