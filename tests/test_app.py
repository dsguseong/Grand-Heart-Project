"""회귀 테스트.

원래 tests.py 는 User/Post 모델만 직접 만들어 확인했고, 웹 요청은 한 번도
거치지 않았습니다. 실제로 500 이 나던 화면들(스와이프, 필터)은 테스트가
없어서 못 잡았습니다. 여기서는 라우트를 실제로 호출합니다.
"""

from pathlib import Path

import pytest

from app import create_app
from app.extensions import db
from app.models import (
    SCORE_DISLIKE,
    SCORE_LIKE,
    SCORE_SOSO,
    FoodImage,
    FoodItem,
    Preference,
    User,
)
from app.services.images import parse_food_name
from app.services.preferences import exclude_food, next_food_for, record_vote
from app.services.recommender import recommend_for_group, weighted_sum


@pytest.fixture
def app(tmp_path):
    app = create_app("testing")
    # 임베딩은 테스트마다 임시 폴더를 씁니다. 개발용 instance/embeddings.npz 를
    # 테스트가 덮어쓰거나 지우면 로컬에서 만들어 둔 임베딩이 날아갑니다.
    app.config["EMBEDDING_PATH"] = str(tmp_path / "embeddings.npz")
    with app.app_context():
        from app.services import embeddings as emb

        emb.clear_cache()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
        emb.clear_cache()


@pytest.fixture
def client(app):
    return app.test_client()


def make_user(username, admin=False):
    user = User(username=username, email=f"{username}@example.com", is_admin=admin)
    user.set_password("password123")
    db.session.add(user)
    db.session.commit()
    return user


def make_food(category, name, images=1):
    item = FoodItem(category=category, name=name)
    db.session.add(item)
    db.session.flush()
    for i in range(images):
        db.session.add(
            FoodImage(food_item_id=item.id, filename=f"{category}_{name}_{i}.jpg")
        )
    db.session.commit()
    return item


def login(client, username, password="password123"):
    return client.post(
        "/auth/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )


# --------------------------------------------------------------------------
# 파일명 파싱
# --------------------------------------------------------------------------
def test_parse_food_name_strips_variant_number():
    assert parse_food_name("국_육개장1_0001.jpg") == ("국", "육개장")
    assert parse_food_name("면_칼국수12_0070.JPG") == ("면", "칼국수")


def test_parse_food_name_rejects_bad_names():
    # 기존 코드는 여기서 IndexError 를 내고 500 을 띄웠습니다.
    assert parse_food_name("사진.jpg") is None
    assert parse_food_name("") is None
    assert parse_food_name("_") is None


# --------------------------------------------------------------------------
# 스와이프: 같은 음식이 다시 나오지 않고, 다 보면 크래시 없이 끝난다
# --------------------------------------------------------------------------
def test_swipe_never_repeats_and_ends_cleanly(app):
    user = make_user("kim")
    items = [make_food("찌개", f"김치찌개{i}") for i in range(3)]

    seen = []
    for _ in range(3):
        item = next_food_for(user)
        assert item is not None
        assert item.id not in seen  # 이미 평가한 음식이 또 나오면 안 됨
        seen.append(item.id)
        record_vote(user, item, SCORE_LIKE)

    # 남은 음식이 없을 때 기존 코드는 random.choice([]) 로 IndexError 였습니다.
    assert next_food_for(user) is None
    assert len(seen) == len({i.id for i in items})


def test_excluded_food_never_shows_again(app):
    user = make_user("lee")
    item = make_food("면", "칼국수")
    exclude_food(user, item)
    assert next_food_for(user) is None


def test_vote_is_idempotent(app):
    """같은 음식을 다시 평가해도 행이 하나만 남아야 합니다."""
    user = make_user("park")
    item = make_food("밥", "김밥")
    record_vote(user, item, SCORE_LIKE)
    record_vote(user, item, SCORE_DISLIKE)
    rows = db.session.scalars(
        db.select(Preference).where(Preference.user_id == user.id)
    ).all()
    assert len(rows) == 1
    assert rows[0].score == SCORE_DISLIKE


def test_invalid_score_rejected(app):
    user = make_user("choi")
    item = make_food("전", "파전")
    with pytest.raises(ValueError):
        record_vote(user, item, 99)


# --------------------------------------------------------------------------
# 추천
# --------------------------------------------------------------------------
def test_weighted_sum_handles_different_keys():
    """원본 알고리즘은 두 사용자의 카테고리가 다르면 뒤쪽을 잘라버렸습니다."""
    result = weighted_sum([{"국": 1.0, "면": -1.0}, {"국": 0.0, "밥": 1.0}])
    assert result["국"] == pytest.approx(0.5)
    assert result["면"] == pytest.approx(-0.5)
    assert result["밥"] == pytest.approx(0.5)


def test_weighted_sum_supports_more_than_two_users():
    result = weighted_sum([{"국": 1.0}, {"국": 1.0}, {"국": -1.0}])
    assert result["국"] == pytest.approx(1 / 3)


def test_group_recommendation_respects_veto(app):
    a, b = make_user("a"), make_user("b")
    stew = make_food("찌개", "김치찌개")
    noodle = make_food("면", "칼국수")

    record_vote(a, stew, SCORE_LIKE)
    record_vote(b, stew, SCORE_LIKE)
    record_vote(a, noodle, SCORE_LIKE)
    record_vote(b, noodle, SCORE_DISLIKE)  # b가 싫어함 -> 면 카테고리 제외

    result = recommend_for_group([a, b], top_n=3)
    names = [r.item.name for r in result.recommendations]
    assert "김치찌개" in names
    assert "칼국수" not in names
    assert "면" in result.vetoed_categories


def test_group_recommendation_falls_back_when_no_common_category(app):
    """공통 카테고리가 없어도 오류 없이 결과가 나와야 합니다(기획서 요구사항)."""
    a, b = make_user("a"), make_user("b")
    rice = make_food("밥", "김밥")
    soup = make_food("국", "미역국")
    record_vote(a, rice, SCORE_LIKE)
    record_vote(a, soup, SCORE_DISLIKE)
    record_vote(b, rice, SCORE_DISLIKE)
    record_vote(b, soup, SCORE_LIKE)

    result = recommend_for_group([a, b], top_n=3)
    assert result.relaxed is True
    assert result.notes  # 왜 완화했는지 안내가 있어야 함


def test_exclusion_blocks_group_recommendation(app):
    a, b = make_user("a"), make_user("b")
    item = make_food("찌개", "된장찌개")
    record_vote(a, item, SCORE_LIKE)
    record_vote(b, item, SCORE_LIKE)
    exclude_food(b, item)  # b가 못 먹음

    result = recommend_for_group([a, b], top_n=3)
    assert all(r.item.id != item.id for r in result.recommendations)


def test_recommendation_needs_two_people(app):
    a = make_user("solo")
    result = recommend_for_group([a], top_n=3)
    assert result.recommendations == []
    assert result.notes


# --------------------------------------------------------------------------
# 팔로우 / 맞팔로우
# --------------------------------------------------------------------------
def test_mutual_friends_only_when_both_follow(app):
    a, b = make_user("a"), make_user("b")
    a.follow(b)
    db.session.commit()
    assert a.mutual_friends() == []

    b.follow(a)
    db.session.commit()
    assert [u.username for u in a.mutual_friends()] == ["b"]


def test_cannot_follow_self(app):
    a = make_user("a")
    a.follow(a)
    db.session.commit()
    assert a.followed.count() == 0


# --------------------------------------------------------------------------
# 라우트 스모크 테스트
# --------------------------------------------------------------------------
def test_pages_render_for_new_user(client, app):
    """가입 직후 바로 스와이프/취향/제외 화면에 들어가도 500 이 나면 안 됩니다.

    기존 코드에서는 food_json 이 빈 문자열이라 json.loads('') 가
    JSONDecodeError 를 내며 이 시나리오가 무조건 깨졌습니다.
    """
    make_user("newbie")
    make_food("구이", "삼겹살")
    login(client, "newbie")

    for path in [
        "/",
        "/foods/swipe",
        "/foods/my-tastes",
        "/foods/exclusions",
        "/foods/catalog",
        "/recommend/",
        "/people",
    ]:
        response = client.get(path)
        assert response.status_code == 200, f"{path} -> {response.status_code}"


def test_login_required_redirects(client, app):
    response = client.get("/foods/swipe")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_upload_requires_admin(client, app):
    make_user("plain")
    login(client, "plain")
    assert client.get("/foods/upload").status_code == 403


def test_open_redirect_is_blocked(client, app):
    make_user("kim")
    response = client.post(
        "/auth/login",
        data={"username": "kim", "password": "password123"},
        query_string={"next": "http://evil.example.com/"},
    )
    assert "evil.example.com" not in response.headers.get("Location", "")


def test_vote_route_updates_preference(client, app):
    make_user("kim")
    item = make_food("탕", "삼계탕")
    login(client, "kim")
    response = client.post(
        f"/foods/vote/{item.id}", data={"action": "like"}, follow_redirects=True
    )
    assert response.status_code == 200
    pref = db.session.scalar(db.select(Preference).where(Preference.food_item_id == item.id))
    assert pref is not None and pref.score == SCORE_LIKE


def test_vote_rejects_unknown_action(client, app):
    make_user("kim")
    item = make_food("탕", "갈비탕")
    login(client, "kim")
    client.post(f"/foods/vote/{item.id}", data={"action": "탈취"}, follow_redirects=True)
    assert db.session.scalar(db.select(Preference)) is None


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------
def test_api_token_and_next_food(client, app):
    make_user("kim")
    make_food("죽", "전복죽")

    response = client.post("/api/v1/token", json={"username": "kim", "password": "password123"})
    assert response.status_code == 200
    token = response.get_json()["token"]

    headers = {"Authorization": f"Bearer {token}"}
    data = client.get("/api/v1/foods/next", headers=headers).get_json()
    assert data["item"]["name"] == "전복죽"

    item_id = data["item"]["id"]
    voted = client.post(
        f"/api/v1/foods/{item_id}/vote", json={"action": "like"}, headers=headers
    )
    assert voted.status_code == 200
    assert client.get("/api/v1/foods/next", headers=headers).get_json()["item"] is None


def test_api_rejects_bad_token(client, app):
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/api/v1/me").status_code == 401


def test_api_recommend_requires_mutual_follow(client, app):
    kim = make_user("kim")
    other = make_user("other")
    make_food("면", "잔치국수")
    kim.follow(other)  # 한쪽만 팔로우
    db.session.commit()

    token = client.post(
        "/api/v1/token", json={"username": "kim", "password": "password123"}
    ).get_json()["token"]
    response = client.post(
        "/api/v1/recommend",
        json={"member_ids": [other.id]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------
# 이미지 임베딩
# --------------------------------------------------------------------------
def _make_embeddings(app, mapping: dict[int, list[float]], backend="test"):
    """테스트용 임베딩 파일을 만들고 설정을 켭니다.

    실제 모델을 돌리지 않고 벡터를 직접 지정하므로 TensorFlow 없이
    추천 로직만 검증할 수 있습니다.
    """
    import numpy as np

    from app.services import embeddings as emb

    path = Path(app.config["EMBEDDING_PATH"])
    item_ids = list(mapping)
    vectors = np.array([mapping[i] for i in item_ids], dtype=np.float32)
    emb.clear_cache()
    emb.save_store(path, item_ids, vectors, backend)
    app.config["EMBEDDING_WEIGHT"] = 0.6
    return path


def test_taste_vector_reflects_likes_and_dislikes(app):
    from app.services import embeddings as emb

    user = make_user("kim")
    liked = make_food("구이", "삼겹살")
    disliked = make_food("회", "육회")

    _make_embeddings(app, {liked.id: [1.0, 0.0], disliked.id: [0.0, 1.0]})
    record_vote(user, liked, SCORE_LIKE)
    record_vote(user, disliked, SCORE_DISLIKE)

    taste = emb.taste_vector(user)
    assert taste is not None
    # 좋아한 쪽(+x)으로 기울고 싫어한 쪽(+y)에서 멀어져야 함
    assert taste[0] > 0 and taste[1] < 0
    assert abs(float((taste ** 2).sum()) - 1.0) < 1e-5  # 단위 벡터


def test_embedding_predicts_unrated_food(app):
    """평가한 적 없는 음식도 사진이 비슷하면 높은 점수를 받아야 합니다."""
    from app.services import embeddings as emb

    user = make_user("kim")
    liked = make_food("구이", "삼겹살")
    similar = make_food("구이", "목살")      # 좋아한 것과 비슷한 벡터
    different = make_food("회", "광어회")    # 반대 벡터

    _make_embeddings(
        app,
        {liked.id: [1.0, 0.0], similar.id: [0.95, 0.31], different.id: [-1.0, 0.0]},
    )
    record_vote(user, liked, SCORE_LIKE)

    scores = emb.affinity_for_items(user, [similar.id, different.id])
    assert scores[similar.id] > scores[different.id]
    assert scores[similar.id] > 0 > scores[different.id]


def test_taste_vector_none_without_embeddings(app):
    """임베딩 파일이 없으면 조용히 None. 예외가 나면 안 됩니다."""
    from app.services import embeddings as emb

    emb.clear_cache()
    user = make_user("kim")
    item = make_food("밥", "볶음밥")
    record_vote(user, item, SCORE_LIKE)

    assert emb.available() is False
    assert emb.taste_vector(user) is None
    assert emb.affinity_for_items(user, [item.id]) == {}


def test_recommendation_works_without_embeddings(app):
    """임베딩이 없어도 기존 통계 추천이 그대로 동작해야 합니다(하위 호환)."""
    from app.services import embeddings as emb

    emb.clear_cache()
    a, b = make_user("a"), make_user("b")
    item = make_food("찌개", "김치찌개")
    record_vote(a, item, SCORE_LIKE)
    record_vote(b, item, SCORE_LIKE)

    result = recommend_for_group([a, b], top_n=3)
    assert result.used_embeddings is False
    assert [r.item.name for r in result.recommendations] == ["김치찌개"]
    assert result.recommendations[0].embedding_score is None


def test_recommendation_uses_embeddings_when_available(app):
    """임베딩이 있으면 사용 표시가 뜨고 세부 점수가 채워져야 합니다."""
    a, b = make_user("a"), make_user("b")
    rated = make_food("구이", "삼겹살")
    unrated = make_food("구이", "목살")

    _make_embeddings(app, {rated.id: [1.0, 0.0], unrated.id: [0.94, 0.34]})
    record_vote(a, rated, SCORE_LIKE)
    record_vote(b, rated, SCORE_LIKE)

    result = recommend_for_group([a, b], top_n=3)
    assert result.used_embeddings is True
    by_name = {r.item.name: r for r in result.recommendations}
    assert by_name["목살"].embedding_score is not None
    assert "사진 유사도" in by_name["목살"].reason


def test_similar_items_excludes_itself(app):
    from app.services import embeddings as emb

    a = make_food("면", "칼국수")
    b = make_food("면", "잔치국수")
    c = make_food("회", "연어회")
    _make_embeddings(app, {a.id: [1.0, 0.0], b.id: [0.9, 0.44], c.id: [-1.0, 0.0]})

    results = emb.similar_items(a.id, top_n=5)
    ids = [i for i, _ in results]
    assert a.id not in ids            # 자기 자신 제외
    assert ids[0] == b.id             # 가장 비슷한 것이 먼저
