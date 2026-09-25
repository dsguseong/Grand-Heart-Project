"""이미지 임베딩 기반 취향 추론 (실행 시점).

설계 의도
---------
임베딩은 **미리 계산해서 파일로 저장**하고, 웹 서버는 numpy 로 읽기만 합니다.
그래서 Flask 앱을 돌리는 데 TensorFlow 나 PyTorch 가 필요 없습니다.
무거운 라이브러리는 `flask compute-embeddings` 를 실행하는 개발 머신이나
Colab 에만 있으면 됩니다. 원본 노트북이 임베딩을 pickle 로 떨군 것과 같은
발상이고, 다만 서빙 경로에서 모델 로딩을 완전히 걷어냈습니다.

취향 벡터
---------
사용자가 좋아요(+1) / 보통(0) / 싫어요(-1)를 준 음식들의 임베딩을
가중 평균해 "이 사람이 좋아하는 음식은 대체로 이렇게 생겼다" 벡터를 만듭니다.
새 음식과의 코사인 유사도가 곧 예측 선호도입니다.

    taste(u) = Σ (score_i - 2) · v_i  /  ‖ · ‖
    affinity(u, j) = cos(taste(u), v_j) ∈ [-1, 1]

한계를 분명히 해두면, 이 값은 **생김새가 얼마나 비슷한가**이지 맛이 아닙니다.
김치찌개와 육개장은 둘 다 빨간 국물이라 가깝게 나오지만 취향은 갈릴 수
있습니다. 그래서 추천에서는 실제 평가가 있으면 그쪽을 우선하고, 임베딩은
아무도 평가하지 않은 음식을 메우는 용도로만 씁니다(콜드 스타트 보완).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import Preference, User

NEUTRAL = 2
_LOCK = threading.Lock()
_CACHE: dict[str, "EmbeddingStore"] = {}


@dataclass
class EmbeddingStore:
    """음식 id → 단위 벡터. 정규화되어 있으므로 내적이 곧 코사인 유사도입니다."""

    item_ids: np.ndarray  # (N,) int64
    vectors: np.ndarray  # (N, D) float32, L2 정규화됨
    backend: str
    dim: int

    def __post_init__(self):
        self._index = {int(i): n for n, i in enumerate(self.item_ids)}

    def __len__(self) -> int:
        return len(self.item_ids)

    def has(self, item_id: int) -> bool:
        return int(item_id) in self._index

    def vector(self, item_id: int) -> np.ndarray | None:
        pos = self._index.get(int(item_id))
        return None if pos is None else self.vectors[pos]

    def vectors_for(self, item_ids) -> tuple[np.ndarray, list[int]]:
        """요청한 id 중 임베딩이 있는 것만 (벡터, id목록) 으로 반환."""
        rows, found = [], []
        for item_id in item_ids:
            pos = self._index.get(int(item_id))
            if pos is not None:
                rows.append(self.vectors[pos])
                found.append(int(item_id))
        if not rows:
            return np.empty((0, self.dim), dtype=np.float32), []
        return np.vstack(rows), found


def default_path() -> Path:
    """임베딩 파일 위치. EMBEDDING_PATH 설정이 있으면 그쪽을 씁니다.

    테스트가 개발용 instance/ 의 임베딩을 덮어쓰거나 지우지 않도록,
    설정으로 경로를 갈아끼울 수 있게 해 둡니다.
    """
    configured = current_app.config.get("EMBEDDING_PATH")
    if configured:
        return Path(configured)
    return Path(current_app.instance_path) / "embeddings.npz"


def l2_normalize(matrix: np.ndarray, axis: int = -1) -> np.ndarray:
    norm = np.linalg.norm(matrix, axis=axis, keepdims=True)
    norm = np.where(norm == 0, 1.0, norm)
    return (matrix / norm).astype(np.float32)


def save_store(
    path: Path, item_ids: list[int], vectors: np.ndarray, backend: str
) -> EmbeddingStore:
    vectors = l2_normalize(np.asarray(vectors, dtype=np.float32))
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        item_ids=np.asarray(item_ids, dtype=np.int64),
        vectors=vectors,
        backend=np.array(backend),
    )
    clear_cache()
    return EmbeddingStore(
        item_ids=np.asarray(item_ids, dtype=np.int64),
        vectors=vectors,
        backend=backend,
        dim=vectors.shape[1],
    )


def load_store(path: Path | None = None) -> EmbeddingStore | None:
    """임베딩 파일을 읽어 캐시합니다. 파일이 없으면 None (통계 방식으로 동작)."""
    path = Path(path or default_path())
    key = str(path)

    with _LOCK:
        cached = _CACHE.get(key)
        if cached is not None:
            return cached

        if not path.exists():
            return None
        try:
            data = np.load(path, allow_pickle=False)
            vectors = l2_normalize(data["vectors"].astype(np.float32))
            store = EmbeddingStore(
                item_ids=data["item_ids"].astype(np.int64),
                vectors=vectors,
                backend=str(data["backend"]) if "backend" in data else "unknown",
                dim=int(vectors.shape[1]),
            )
        except Exception:
            current_app.logger.exception("임베딩 파일을 읽지 못했습니다: %s", path)
            return None

        _CACHE[key] = store
        return store


def clear_cache() -> None:
    with _LOCK:
        _CACHE.clear()


def available() -> bool:
    return load_store() is not None


def info() -> dict:
    store = load_store()
    if store is None:
        return {"available": False, "count": 0, "dim": 0, "backend": None}
    return {
        "available": True,
        "count": len(store),
        "dim": store.dim,
        "backend": store.backend,
    }


def taste_vector(user: User, store: EmbeddingStore | None = None) -> np.ndarray | None:
    """사용자의 평가로부터 취향 벡터를 만듭니다. 평가가 없거나 전부 '보통'이면 None."""
    store = store or load_store()
    if store is None:
        return None

    rows = db.session.execute(
        select(Preference.food_item_id, Preference.score).where(
            Preference.user_id == user.id
        )
    ).all()
    if not rows:
        return None

    acc = np.zeros(store.dim, dtype=np.float32)
    weight_total = 0.0
    for item_id, score in rows:
        vec = store.vector(item_id)
        if vec is None:
            continue
        w = float(score) - NEUTRAL  # +1 / 0 / -1
        if w == 0:
            continue
        acc += w * vec
        weight_total += abs(w)

    if weight_total == 0:
        return None

    norm = float(np.linalg.norm(acc))
    if norm == 0:  # 좋아요와 싫어요가 정확히 상쇄된 경우
        return None
    return (acc / norm).astype(np.float32)


def affinity_for_items(
    user: User, item_ids, store: EmbeddingStore | None = None
) -> dict[int, float]:
    """음식별 예측 선호도. -1 ~ +1. 임베딩이 없는 음식은 결과에서 빠집니다."""
    store = store or load_store()
    if store is None:
        return {}

    taste = taste_vector(user, store)
    if taste is None:
        return {}

    matrix, found = store.vectors_for(item_ids)
    if not found:
        return {}

    scores = matrix @ taste  # 둘 다 단위 벡터이므로 내적 = 코사인 유사도
    return {item_id: float(s) for item_id, s in zip(found, scores)}


def similar_items(item_id: int, top_n: int = 10) -> list[tuple[int, float]]:
    """생김새가 비슷한 음식. 노트북의 유클리드 거리 검색에 대응합니다.

    단위 벡터에서는 코사인 유사도와 유클리드 거리의 순서가 동일하므로
    (‖a-b‖² = 2 - 2·cos), 더 빠른 내적으로 계산합니다.
    """
    store = load_store()
    if store is None:
        return []
    vec = store.vector(item_id)
    if vec is None:
        return []

    scores = store.vectors @ vec
    order = np.argsort(-scores)
    out = []
    for pos in order:
        candidate = int(store.item_ids[pos])
        if candidate == int(item_id):
            continue
        out.append((candidate, float(scores[pos])))
        if len(out) >= top_n:
            break
    return out
