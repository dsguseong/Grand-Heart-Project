"""음식 이미지 등록.

기존 add_image() 의 파일명 파싱
------------------------------
    imgname = str(get_file).split("'")[1].split(".")[0]

FileStorage 객체를 str() 로 바꾼 결과(<FileStorage: '국_육개장1_0001.jpg' (...)>)
에서 따옴표를 기준으로 잘라 파일명을 얻고 있었습니다. 파일을 선택하지 않으면
빈 FileStorage 가 넘어와 IndexError, 파일명에 작은따옴표가 있어도 깨집니다.
FileStorage.filename 을 그대로 쓰고 secure_filename 으로 정리합니다.

파일명 규칙: {카테고리}_{음식명+변형번호}_{일련번호}.{확장자}
  예) 국_육개장1_0001.jpg -> 카테고리 '국', 음식 '육개장'
"""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path

from sqlalchemy import select
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import FoodImage, FoodItem

# 한글 파일명은 secure_filename 이 통째로 날려버리므로 확장자만 검사하고
# 저장 이름은 uuid 로 새로 만듭니다.
TRAILING_DIGITS = re.compile(r"\d+$")


def parse_food_name(filename: str) -> tuple[str, str] | None:
    """'국_육개장1_0001.jpg' -> ('국', '육개장'). 규칙에 안 맞으면 None."""
    stem = Path(filename).stem
    parts = stem.split("_")
    if len(parts) < 2:
        return None
    category = parts[0].strip()
    name = TRAILING_DIGITS.sub("", parts[1].strip()).strip()
    if not category or not name:
        return None
    return category, name


def allowed_file(filename: str, allowed: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def get_or_create_item(category: str, name: str) -> FoodItem:
    item = db.session.scalar(
        select(FoodItem).where(FoodItem.category == category, FoodItem.name == name)
    )
    if item is None:
        item = FoodItem(category=category, name=name)
        db.session.add(item)
        db.session.flush()  # id 확보
    return item


def _unique_filename(original: str) -> str:
    ext = Path(original).suffix.lower().lstrip(".") or "jpg"
    return f"{uuid.uuid4().hex}.{ext}"


def store_upload(file_storage, upload_dir: Path, uploader_id: int | None = None) -> FoodImage | None:
    """업로드된 파일 하나를 디스크에 저장하고 DB에 등록."""
    original = (file_storage.filename or "").strip()
    if not original:
        return None

    parsed = parse_food_name(original)
    if parsed is None:
        return None
    category, name = parsed

    upload_dir.mkdir(parents=True, exist_ok=True)
    stored = _unique_filename(original)
    file_storage.save(upload_dir / stored)

    item = get_or_create_item(category, name)
    image = FoodImage(
        food_item_id=item.id,
        filename=stored,
        original_name=secure_filename(original) or original,
        uploader_id=uploader_id,
    )
    db.session.add(image)
    return image


def import_directory(source: Path, upload_dir: Path, limit: int | None = None) -> dict:
    """Data/KFoods/Foods 같은 폴더를 통째로 가져옵니다(시드용)."""
    source = Path(source)
    if not source.is_dir():
        raise FileNotFoundError(f"폴더를 찾을 수 없습니다: {source}")

    upload_dir.mkdir(parents=True, exist_ok=True)
    existing = {
        row for row in db.session.scalars(select(FoodImage.original_name)).all() if row
    }

    added = skipped = 0
    files = sorted(p for p in source.iterdir() if p.is_file())
    for path in files:
        if limit is not None and added >= limit:
            break
        if path.name in existing:
            skipped += 1
            continue
        parsed = parse_food_name(path.name)
        if parsed is None:
            skipped += 1
            continue
        category, name = parsed
        stored = _unique_filename(path.name)
        shutil.copy2(path, upload_dir / stored)
        item = get_or_create_item(category, name)
        db.session.add(
            FoodImage(food_item_id=item.id, filename=stored, original_name=path.name)
        )
        added += 1

    db.session.commit()
    return {"added": added, "skipped": skipped, "scanned": len(files)}


def delete_image(image: FoodImage, upload_dir: Path) -> None:
    """DB 행과 디스크 파일을 함께 정리. 사진이 0장이 된 음식은 항목도 삭제."""
    item = image.item
    target = Path(upload_dir) / image.filename
    db.session.delete(image)
    db.session.flush()
    if item is not None and item.images.count() == 0:
        db.session.delete(item)
    db.session.commit()
    target.unlink(missing_ok=True)
