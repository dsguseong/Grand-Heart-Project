"""flask 커스텀 명령어."""

from __future__ import annotations

import random
from pathlib import Path

import click
from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import SCORE_DISLIKE, SCORE_LIKE, SCORE_SOSO, FoodItem, User
from app.services import embeddings as emb
from app.services import images as image_service
from app.services.preferences import record_vote


def register(app):
    @app.cli.command("init-db")
    def init_db():
        """테이블을 만듭니다(마이그레이션 대신 빠르게 시작할 때)."""
        db.create_all()
        click.echo("테이블을 생성했습니다.")

    @app.cli.command("import-foods")
    @click.argument("source", type=click.Path(exists=True, file_okay=False))
    @click.option("--limit", type=int, default=None, help="가져올 최대 장수")
    def import_foods(source, limit):
        """음식 이미지 폴더를 DB로 가져옵니다.

        예) flask import-foods ./Data/KFoods/Foods
        """
        result = image_service.import_directory(
            Path(source), Path(current_app.config["UPLOAD_FOLDER"]), limit=limit
        )
        click.echo(
            f"스캔 {result['scanned']}장 / 등록 {result['added']}장 / 건너뜀 {result['skipped']}장"
        )

    @app.cli.command("create-user")
    @click.argument("username")
    @click.argument("email")
    @click.password_option()
    @click.option("--admin", is_flag=True, help="관리자로 생성")
    def create_user(username, email, password, admin):
        """사용자를 만듭니다."""
        if db.session.scalar(select(User).where(User.username == username)):
            raise click.ClickException("이미 있는 아이디입니다.")
        user = User(username=username, email=email.lower(), is_admin=admin)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"{username} 생성 완료(admin={admin})")

    @app.cli.command("demo-data")
    @click.option("--ratings", type=int, default=40, help="사용자당 평가 수")
    def demo_data(ratings):
        """데모용 사용자 2명과 무작위 평가를 만듭니다."""
        items = db.session.scalars(select(FoodItem)).all()
        if not items:
            raise click.ClickException("먼저 import-foods 로 음식을 넣어 주세요.")

        people = []
        for name in ("demo1", "demo2"):
            user = db.session.scalar(select(User).where(User.username == name))
            if user is None:
                user = User(username=name, email=f"{name}@example.com")
                user.set_password("demo1234")
                db.session.add(user)
                db.session.commit()
            people.append(user)

        people[0].follow(people[1])
        people[1].follow(people[0])
        db.session.commit()

        for user in people:
            for item in random.sample(items, min(ratings, len(items))):
                record_vote(user, item, random.choice([SCORE_LIKE, SCORE_SOSO, SCORE_DISLIKE]))
        click.echo("demo1 / demo2 생성 완료 (비밀번호: demo1234), 서로 팔로우 상태입니다.")

    @app.cli.command("compute-embeddings")
    @click.option(
        "--backend",
        type=click.Choice(["autoencoder", "resnet", "histogram"]),
        default="resnet",
        help="autoencoder: 직접 학습한 .h5 / resnet: 사전학습 모델 / histogram: 배관 점검용",
    )
    @click.option("--model", "model_path", default="models/autoencoder.h5",
                  help="--backend autoencoder 일 때 쓸 .h5 경로")
    @click.option("--image-size", type=int, default=256)
    @click.option("--batch-size", type=int, default=16)
    def compute_embeddings(backend, model_path, image_size, batch_size):
        """음식 사진의 이미지 임베딩을 계산해 저장합니다.

        음식 하나에 사진이 여러 장이면 벡터를 평균 내 그 음식의 대표 벡터로 씁니다.
        결과는 instance/embeddings.npz 에 저장되고, 웹 서버는 이 파일만 읽습니다
        (서버 실행에는 TensorFlow/PyTorch 가 필요 없습니다).
        """
        import numpy as np

        from app.ml.encoders import MissingDependency, build_encoder

        upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
        items = db.session.scalars(select(FoodItem)).all()
        if not items:
            raise click.ClickException("먼저 import-foods 로 음식을 넣어 주세요.")

        kwargs = {"batch_size": batch_size}
        if backend == "autoencoder":
            kwargs.update(model_path=Path(model_path), image_size=image_size)
        try:
            encoder = build_encoder(backend, **kwargs)
        except (MissingDependency, FileNotFoundError, ValueError) as exc:
            raise click.ClickException(str(exc))

        click.echo(f"백엔드: {backend} (차원 {encoder.dim or '?'})")

        item_ids, vectors, skipped = [], [], 0
        with click.progressbar(items, label="임베딩 계산") as bar:
            for item in bar:
                paths = [
                    upload_dir / image.filename
                    for image in item.images
                    if (upload_dir / image.filename).exists()
                ]
                if not paths:
                    skipped += 1
                    continue
                try:
                    # 같은 음식의 사진이 여러 장이면 평균이 대표 벡터
                    matrix = encoder.encode_paths(paths)
                except Exception as exc:
                    click.echo(f"  건너뜀: {item.label} ({exc})")
                    skipped += 1
                    continue
                item_ids.append(item.id)
                vectors.append(matrix.mean(axis=0))

        if not item_ids:
            raise click.ClickException("임베딩을 하나도 만들지 못했습니다.")

        path = Path(current_app.config.get("EMBEDDING_PATH") or emb.default_path())
        store = emb.save_store(path, item_ids, np.vstack(vectors), backend)
        click.echo(
            f"저장 완료: {path}  (음식 {len(store)}종 / 차원 {store.dim} / 건너뜀 {skipped})"
        )

    @app.cli.command("embedding-info")
    def embedding_info():
        """저장된 임베딩 상태를 확인합니다."""
        data = emb.info()
        if not data["available"]:
            click.echo("임베딩이 없습니다. 추천은 통계 방식으로 동작합니다.")
            click.echo("  flask compute-embeddings --backend resnet")
            return
        click.echo(
            f"백엔드 {data['backend']} / 음식 {data['count']}종 / 차원 {data['dim']}"
        )
        click.echo(f"추천 가중치(EMBEDDING_WEIGHT): {current_app.config['EMBEDDING_WEIGHT']}")

    @app.cli.command("similar")
    @click.argument("item_id", type=int)
    @click.option("--top", type=int, default=10)
    def similar(item_id, top):
        """생김새가 비슷한 음식을 찾습니다(노트북의 유사 이미지 검색에 대응)."""
        target = db.session.get(FoodItem, item_id)
        if target is None:
            raise click.ClickException(f"음식 id {item_id} 를 찾을 수 없습니다.")
        results = emb.similar_items(item_id, top_n=top)
        if not results:
            raise click.ClickException(
                "임베딩이 없습니다. 먼저 flask compute-embeddings 를 실행하세요."
            )
        click.echo(f"기준: {target.label}\n")
        for rank, (other_id, score) in enumerate(results, 1):
            other = db.session.get(FoodItem, other_id)
            click.echo(f"  {rank:2}. {other.label:24} 유사도 {score:+.3f}")

    @app.cli.command("import-embeddings")
    @click.argument("source", type=click.Path(exists=True, dir_okay=False))
    def import_embeddings(source):
        """다른 곳(Colab 등)에서 계산한 임베딩 파일을 가져옵니다."""
        import numpy as np

        data = np.load(source, allow_pickle=False)
        if "names" not in data or "vectors" not in data:
            raise click.ClickException("형식이 맞지 않습니다. names 와 vectors 배열이 필요합니다.")

        names = [str(n) for n in data["names"]]
        vectors = data["vectors"].astype("float32")
        backend = str(data["backend"]) if "backend" in data else "imported"

        index = {
            f"{item.category}_{item.name}": item.id
            for item in db.session.scalars(select(FoodItem)).all()
        }
        if not index:
            raise click.ClickException("먼저 import-foods 로 음식을 넣어 주세요.")

        item_ids, matched, missing = [], [], []
        for name, vector in zip(names, vectors):
            item_id = index.get(name)
            if item_id is None:
                missing.append(name)
                continue
            item_ids.append(item_id)
            matched.append(vector)

        if not item_ids:
            raise click.ClickException(
                "이름이 하나도 맞지 않습니다.\n"
                f"  파일의 이름 예시: {', '.join(names[:3])}\n"
                f"  DB의 이름 예시:   {', '.join(list(index)[:3])}"
            )

        path = Path(current_app.config.get("EMBEDDING_PATH") or emb.default_path())
        store = emb.save_store(path, item_ids, np.vstack(matched), backend)
        click.echo(f"저장 완료: {path}  (음식 {len(store)}종 / 차원 {store.dim} / 백엔드 {backend})")
        if missing:
            click.echo(f"DB에 없어 건너뛴 음식 {len(missing)}종: {', '.join(missing[:5])}...")