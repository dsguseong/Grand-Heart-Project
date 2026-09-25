# 무엇을 왜 바꿨나

기존 저장소 코드를 점검하면서 찾은 문제와 조치를 한 건씩 적었습니다.
"기존 코드" 는 [dsguseong/Grand-Heart-Project](https://github.com/dsguseong/Grand-Heart-Project)
기준입니다.

---

## 1. 최신 환경에서 앱이 아예 뜨지 않던 문제

### 1-1. 삭제된 함수 임포트

```python
# app/routes.py
from werkzeug.urls import url_parse
```

`url_parse` 는 Werkzeug 2.1 에서 제거됐습니다. 지금 버전에서는 임포트 단계에서
`ImportError` 가 나 서버가 시작조차 되지 않습니다.

→ 표준 라이브러리 `urllib.parse.urlsplit` 으로 교체했습니다.
   (`app/auth/routes.py` 의 `_safe_next`)

### 1-2. paginate 호출 방식

```python
posts = user.posts.order_by(Post.timestamp.desc()).paginate(
    page, app.config['POSTS_PER_PAGE'], False)
```

Flask-SQLAlchemy 3.x 부터 `paginate()` 는 위치 인자를 받지 않습니다.

→ `db.paginate(stmt, page=page, per_page=..., error_out=False)` 로 바꿨습니다.

### 1-3. requirements.txt

200개가 넘는 패키지가 들어 있었고 그중에는

| 패키지 | 문제 |
|---|---|
| `pywin32`, `pywinpty`, `wincertstore` | 윈도우 전용. 리눅스·맥에서 설치 실패 |
| `tensorflow-gpu==2.5.0rc2` | 웹앱 실행과 무관. 최신 파이썬에서 설치 불가 |
| `jupyter`, `discord.py`, `pygame`, `eli5`, `PDPbox` | 이 프로젝트와 관련 없음 |

가 있어서 `pip install -r requirements.txt` 자체가 대부분의 환경에서 실패했습니다.

→ 실행에 실제로 필요한 12개만 남기고, 버전은 핀 고정 대신 호환 범위로 지정했습니다.
   모델 학습은 Colab 노트북에서 하므로 여기 넣지 않습니다.

---

## 2. 랜덤 음식이 엉뚱하게 나오던 버그

README 의 "필터링 된 음식인데 랜덤 이미지에서 나타나는 현상 발생 - 수정중" 의 원인입니다.

```python
# app/routes.py  random_show()
cat_dict = json.loads(...filter_food_json)
cat_items_list = list(cat_dict.items())
filtered_list = [int(key) for key, value in cat_items_list if value == 0]
random_img_id = random.choice(filtered_list)
random_img_list.append(image_list[random_img_id])   # ← 여기
```

`filtered_list` 에 들어 있는 값은 **DB 의 이미지 id** 입니다.
그런데 마지막 줄에서 그것을 **파이썬 리스트 인덱스**로 그대로 썼습니다.

- id 는 1부터, 인덱스는 0부터 시작 → 항상 한 칸 밀린 음식이 나옵니다.
- 사진을 하나라도 삭제하면 id 와 인덱스의 간격이 벌어져 완전히 어긋납니다.
- `id == len(image_list)` 인 경우 `IndexError` 로 500.
- 남은 음식이 없으면 `random.choice([])` 가 `IndexError` → 역시 500.

→ 파이썬에서 인덱스 계산을 하지 않습니다.
   "아직 평가하지 않았고 제외하지도 않은 음식" 을 SQL 로 직접 고릅니다.
   (`app/services/preferences.py` 의 `next_food_for`)

```python
select(FoodItem)
  .where(FoodItem.id.not_in(_rated_item_ids(user)))
  .where(FoodItem.id.not_in(_excluded_item_ids(user)))
  .where(FoodItem.images.any())
  .order_by(func.random()).limit(1)
```

남은 음식이 없으면 `None` 을 돌려주고 화면에 "준비된 음식을 모두 봤습니다" 를 띄웁니다.

테스트: `test_swipe_never_repeats_and_ends_cleanly`, `test_excluded_food_never_shows_again`

---

## 3. 회원가입 직후 무조건 깨지던 경로

```python
# app/models.py
food_json = db.Column(db.Text(), default='')
filter_food_json = db.Column(db.Text(), default='')
preference_json = db.Column(db.Text(), default='')
```

기본값이 빈 문자열인데, 값을 채우는 코드는 `/filter` 라우트 안에만 있었습니다.
가입한 사용자가 `/filter` 를 거치지 않고 바로 `/random_show` 에 들어가면

```python
json.loads('')   # json.decoder.JSONDecodeError
```

로 500 이 났습니다. 첫 사용자가 가장 먼저 부딪히는 화면이 이것입니다.

→ JSON 컬럼 자체를 없앴습니다. 아래 4번 참고.

테스트: `test_pages_render_for_new_user`

---

## 4. JSON 문자열 컬럼 → 정규화 테이블

기존에는 사용자 한 명의 취향 전체를 `User` 테이블의 TEXT 컬럼 세 개에
`json.dumps` 로 통째로 넣었습니다. 여기서 생기는 문제가 셋 더 있습니다.

**(a) 음식이 추가되면 기존 사용자가 깨집니다.**
`cat_dict[food_category] += 1` 은 그 사용자의 dict 에 해당 키가 없으면 `KeyError` 입니다.
사진을 새로 올린 뒤 기존 회원이 평가하면 500 이 납니다.

**(b) 질의를 할 수 없습니다.**
"이 음식을 좋아하는 사람" "카테고리별 평균" 같은 걸 SQL 로 못 구하고,
전체 사용자를 파이썬으로 읽어 파싱해야 합니다.

**(c) 동시 요청에서 평가가 유실됩니다.**
두 요청이 같은 dict 를 읽어 각각 수정한 뒤 통째로 덮어쓰면 하나가 사라집니다.

→ 평가 한 건 = 행 하나로 정규화했습니다.

| 기존 | 지금 |
|---|---|
| `User.food_json` (카테고리별 좋아요 수) | 계산해서 씁니다 — `recommender.category_affinity()` |
| `User.preference_json` (음식별 0~3) | `Preference(user_id, food_item_id, score)` |
| `User.filter_food_json` (이미지별 0/1) | `FoodExclusion(user_id, food_item_id, reason)` |

`Preference` 에는 `UniqueConstraint(user_id, food_item_id)` 를 걸어
같은 음식을 다시 평가해도 행이 하나만 남습니다.

테스트: `test_vote_is_idempotent`

---

## 5. 이미지를 두 번 저장하던 문제

```python
newFile = Image(imgname=imgname,
                imgdata=data,              # 원본 바이너리
                rendered_data=render_file) # 같은 이미지의 base64 문자열
```

같은 사진을 원본과 base64 로 **두 번** 저장하고 있었습니다.
base64 는 원본보다 약 33% 크므로 DB 에 원본의 2.33배가 들어갑니다.
목록 페이지가 모든 이미지 바이트를 메모리로 읽어오는 것도 여기서 옵니다.

→ 파일은 `app/static/uploads/foods/` 에 두고 DB 에는 파일명만 저장합니다.
   웹서버가 정적 파일로 바로 내보내므로 훨씬 빠르고, 브라우저 캐시도 걸립니다.

---

## 6. 파일명 파싱

```python
imgname = str(get_file).split("'")[1].split(".")[0]
```

`FileStorage` 객체를 `str()` 로 바꾼 결과
(`<FileStorage: '국_육개장1_0001.jpg' ('image/jpeg')>`)에서 따옴표를 잘라
파일명을 꺼내고 있었습니다.

- 파일을 선택하지 않으면 빈 `FileStorage` 가 넘어와 `[1]` 에서 `IndexError`
- 파일명에 작은따옴표가 있으면 엉뚱하게 잘림
- repr 형식은 Werkzeug 내부 구현이라 언제든 바뀔 수 있음

또 카테고리·음식명을 매번 `split('_')` 해서 뽑았는데, `_` 가 없는 파일명에서는
`splitted[1]` 이 `IndexError` 였습니다. `/filter/delete` 도 같은 문제가 있어서
검색창에 `_` 없는 글자를 치면 500 이 났습니다.

→ `FileStorage.filename` 을 쓰고, 파싱은 등록할 때 한 번만 합니다.
   규칙에 맞지 않으면 예외 대신 `None` 을 돌려주고 "이 파일은 건너뛰었다" 고 알려 줍니다.
   (`app/services/images.py` 의 `parse_food_name`)

테스트: `test_parse_food_name_rejects_bad_names`

---

## 7. 순환 임포트 / 앱 팩토리

```python
# app/__init__.py 맨 아래
from app import routes, models, errors

# app/routes.py 맨 위
from app import app, db
```

`app` → `routes` → `app` 의 순환 임포트입니다. 지금은 파이썬이 봐주고 있지만
임포트 순서에 의존하는 취약한 구조이고, 무엇보다 **설정을 바꿔 앱을 새로 만들 수 없습니다.**
테스트에서 인메모리 DB 를 쓰려면 앱을 다시 만들어야 하는데 그게 불가능합니다.

→ `create_app(config_name)` 팩토리 + 블루프린트로 바꿨습니다.
   확장 객체는 `app/extensions.py` 한 곳에 모았습니다.

---

## 8. 템플릿 블록 이름 충돌

`base.html` 은 `bootstrap/base.html` 을 상속하면서 이렇게 되어 있었습니다.

```jinja
{% block content %}
    <div class="container">
        ... 플래시 메시지 ...
        {% block app_content %}{% endblock %}
    </div>
{% endblock %}
```

그런데 자식 템플릿 12개 중 10개가 `{% block content %}` 를 덮어썼습니다.
그러면 그 안에 있던 컨테이너와 **플래시 메시지가 통째로 사라집니다.**
`register.html` 과 `404.html` 만 `app_content` 를 제대로 썼습니다.

즉 로그인 실패 시 `flash('Invalid username or password')` 는 저장은 되지만
화면에 절대 표시되지 않았습니다.

→ Flask-Bootstrap 을 걷어내고 블록을 `content` 하나로 통일했습니다.
   Flask-Bootstrap 은 관리가 끊긴 패키지이고, 템플릿에는 부트스트랩 3 을 쓰면서
   `offset-md-2`, `form-control-lg`, `btn-info btn-lg` 같은 부트스트랩 4/5 클래스가
   섞여 있어 실제로는 적용되지 않는 클래스가 많았습니다.

---

## 9. 함수 중복 정의

```python
# app/email.py
def send_email(subject, sender, recipients, text_body, html_body):   # ① 동기
    ...
    mail.send(msg)

def send_async_email(app, msg): ...

def send_email(subject, sender, recipients, text_body, html_body):   # ② 비동기
    ...
    Thread(target=send_async_email, args=(app, msg)).start()
```

파이썬은 나중 정의로 덮어쓰므로 ① 은 실행되지 않는 죽은 코드입니다.

→ 하나로 정리하고, `MAIL_SERVER` 가 설정되지 않았으면 예외를 내는 대신
   재설정 링크를 로그에 찍습니다. 메일 서버 없이도 개발할 수 있습니다.

---

## 10. 보안

| 기존 | 문제 | 조치 |
|---|---|---|
| `add_image()` | `@login_required` 도 관리자 검사도 없음 → 누구나 음식 업로드 | `@admin_required` |
| `@app.route('/upload/<int:image_id>')` | **GET 으로 삭제**. 링크를 누르거나 크롤러가 긁으면 지워짐 | POST + CSRF |
| `/random_show/prefer/<name>` | `methods=['GET','POST']` → 주소만 쳐도 평가 저장 | POST 전용 + CSRF |
| 평가 대상을 이름 문자열로 전달 | URL 조작 가능, 이름이 겹치면 오작동 | 음식 id 로 지정 |
| `url_parse(next_page).netloc != ''` | 스킴 없는 `//evil.com` 형태를 놓칠 여지 | `urlsplit` + `startswith('/')` 검사 |
| 비밀번호 길이 제한 없음 | | 8자 이상 |
| 로그인 실패 메시지 | 아이디 존재 여부가 드러남 | 통합 메시지 |
| 재설정 요청 | 가입 여부가 드러남 | 항상 같은 안내 |

테스트: `test_upload_requires_admin`, `test_open_redirect_is_blocked`

---

## 11. Weighted Sum 알고리즘

`Weighted_Sum/Weighted_Sum_Algorithm.py` 는 값을 눈으로 확인하는 스크립트였고
다음 문제가 있었습니다.

```python
user1 = [list(list(User.values())[0].values())[i] for i in range(len(list(User.values())[0].keys()))]
user2 = [list(list(User.values())[1].values())[i] for i in range(len(list(User.values())[0].keys()))]
result = [(x + y) * (1 / len(User)) for x, y in zip(user1, user2)]
```

- **사용자가 정확히 2명일 때만** 동작합니다 (`[0]`, `[1]` 로 직접 접근).
- `user2` 의 길이를 **user1 의 키 개수**로 잘라 씁니다. 두 사람의 카테고리 구성이
  다르면 뒤쪽이 잘리고, dict 순서에 따라 서로 다른 카테고리끼리 더해집니다.
- 결과가 점수 리스트라 **어떤 카테고리인지 알 수 없습니다** (`sorted(result)` 는 값만 정렬).
- 예외 카테고리를 구하는 `common()` 은 계산만 하고 결과에 반영되지 않습니다.

→ `app/services/recommender.py` 로 옮기고 N명으로 일반화했습니다.

```python
def weighted_sum(vectors, weights=None):
    if weights is None:
        weights = [1.0 / len(vectors)] * len(vectors)
    keys = set().union(*(v.keys() for v in vectors))     # 한쪽에만 있는 키도 포함
    return {k: sum(v.get(k, 0.0) * w for v, w in zip(vectors, weights)) / sum(weights)
            for k in keys}
```

가중치를 주지 않으면 `1/N` 동일 가중이라 원래 의도와 같은 값이 나오고,
카테고리가 달라도 잘리지 않으며, 결과가 `{카테고리: 점수}` 라 어떤 음식인지 알 수 있습니다.

메모에 적혀 있던 두 예외 규칙도 실제로 구현했습니다.

1. 한 명이라도 싫어하는 카테고리 / 못 먹는 음식은 제외 (거부권)
2. 그렇게 해서 후보가 하나도 없으면 오류 없이 완화 규칙으로 폴백

테스트: `test_weighted_sum_handles_different_keys`,
`test_weighted_sum_supports_more_than_two_users`,
`test_group_recommendation_respects_veto`,
`test_group_recommendation_falls_back_when_no_common_category`

---

## 12. 타임존

```python
last_seen = db.Column(db.DateTime, default=datetime.utcnow)
```

`datetime.utcnow()` 는 파이썬 3.12 에서 deprecated 이고, 타임존 정보가 없는
naive datetime 을 만듭니다. aware datetime 과 섞으면
`TypeError: can't subtract offset-naive and offset-aware datetimes` 가 납니다.

SQLite 는 타임존을 저장하지 않으므로 aware 값을 넣어도 읽을 때는 naive 로 돌아옵니다.
이 프로젝트를 다시 만들면서 실제로 이 오류를 만났고, 그래서 DB 에서 읽은 값은
항상 `as_utc()` 를 거쳐 비교하도록 했습니다. (`app/models.py`)

---

## 13. 요청마다 무조건 커밋

```python
@app.before_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
```

정적 파일 요청을 포함해 모든 요청마다 DB 쓰기가 일어납니다.

→ 마지막 갱신으로부터 60초가 지났을 때만 커밋합니다.

---

## 14. 저장소 위생

| 항목 | 문제 |
|---|---|
| `venv/` (16MB) | 가상환경이 통째로 커밋. `Scripts/` 가 있는 걸 보면 윈도우용이라 다른 OS 에서는 못 씁니다 |
| `Data/KFoods.zip` (73MB) | 압축 해제본 `Data/KFoods/` 와 중복 |
| `app.db` | 로컬 DB 커밋. 개인 계정·평가가 들어갑니다 |
| `__pycache__/` | 컴파일 캐시 커밋 |
| `.gitignore` 없음 | 위 문제들의 원인 |
| `app/copy,html` | 0바이트, 파일명에 쉼표 |
| `grand_heart_project` | 루트의 1바이트 파일 |
| `logs/` | 빈 폴더 |

→ `.gitignore` 를 추가하고 잔여 파일을 정리했습니다.
   이미 커밋된 것을 저장소에서 빼려면:

```bash
git rm -r --cached venv __pycache__ app.db "app/copy,html" grand_heart_project
git rm --cached Data/KFoods.zip        # 필요하면 Git LFS 나 외부 스토리지로
git commit -m "커밋에서 제외: 가상환경, 로컬 DB, 캐시, 잔여 파일"
```

---

## 15. 마이그레이션 정리

`migrations/versions/` 에 `followers` 라는 이름이 붙은 리비전이 셋 있었습니다.

```
3db9faaa854b_follwers.py     (오타)
8907431167e2_followers.py
a70e12dc13dc_followers.py
70bfe5fb23aa_.py             (메시지 없음)
```

체인은 이어져 있지만 같은 작업을 여러 번 시도한 흔적이라 나중에 되짚기 어렵습니다.

→ 스키마가 완전히 바뀌었으므로 초기 마이그레이션 하나로 새로 만들었습니다.
   `render_as_batch=True` 를 켜 두어 SQLite 에서도 컬럼 변경이 됩니다.

---

## 16. 빼거나 새로 넣은 기능

**뺀 것**

- `Post` 모델과 마이크로블로그 화면 (index 피드, `_post.html`, `explore`).
  Miguel Grinberg 튜토리얼의 잔재이고 기획서의 음식 추천과 무관합니다.
  홈은 취향 진행률과 함께 먹을 사람을 보여주는 대시보드로 바꿨습니다.
  **다시 넣고 싶으시면 말씀해 주세요.**
- `models.py` 의 `association_table` (친구 추가). 정의만 있고 쓰이지 않았으며,
  마이그레이션에도 없어 테이블이 실제로 만들어지지도 않았습니다.
  맞팔로우로 같은 목적을 달성하므로 뺐습니다.
- `image_multi_upload_randomshow/` 폴더. 앱에 이미 반영된 실험 코드의 사본입니다.

**새로 넣은 것**

- "못 먹어요" 버튼 — 기획서의 4지선다(좋아요/싫어요/못먹어요/보통)에 있었는데
  스와이프 화면에는 3개만 있었습니다.
- 맞팔로우 기반 그룹 추천 화면
- `/api/v1` JSON API (앱용)
- 주변 식당 검색 (카카오 로컬)
- `flask import-foods` — 폴더 통째로 등록. 웹에서 453장을 손으로 올릴 필요가 없습니다.
- 테스트 23개

---

## 17. 오토인코더 — 실제로 연결

v2 초기 버전에서는 추천이 통계(카테고리 평균)만으로 동작했고, 오토인코더는 연결되지
않은 상태였습니다. 이번에 실제로 붙였습니다.

### 원본 노트북 진단

`Autoencoder_Colab/grand_heart_project.ipynb` (코드 셀 23개)를 읽어 보니 두 가지
구조적 문제가 있었습니다.

**(a) 인코더 층 연결이 끊겨 있었습니다**

```python
encoder = Conv2D(32, ...)(input_model)     # ①
encoder = LeakyReLU()(encoder)
encoder = BatchNormalization()(encoder)

encoder = Conv2D(64, ...)(encoder)         # ②
encoder = LeakyReLU()(encoder)
encoder = BatchNormalization()(encoder)

encoder = Conv2D(64, ...)(input_model)     # ③ ← encoder 가 아니라 input_model
```

세 번째 `Conv2D` 의 입력이 직전 층이 아니라 원본 입력입니다. ①②가 계산 그래프에서
통째로 끊기고, 실제 학습된 인코더는 **Conv2D 한 층** 이었습니다.

**(b) 다운샘플링이 전혀 없었습니다**

`MaxPooling` 도 `strides` 도 없어 256×256 해상도가 그대로 유지됩니다.
`Flatten()` 하면 256·256·64 = 4,194,304 차원이고, 여기서 `Dense(16)` 으로 가면
그 한 층의 파라미터만 **6,700만 개**입니다. 사진 453장으로 학습할 규모가 아닙니다
(파라미터가 샘플보다 약 15만 배 많음).

또한 노트북의 뒷부분은 추천이 아니라 **유사 이미지 검색**입니다. 사진 하나를 넣으면
유클리드 거리로 가까운 20장을 뽑고 파일명 문자열 유사도로 재정렬합니다.
사용자도, 평가 점수도, 취향도 이 흐름에 들어오지 않습니다.

### 조치

| 항목 | 내용 |
|---|---|
| `app/ml/train_autoencoder.py` | 인코더를 제대로 연결하고 `strides=2` 로 단계별 축소(256→128→64→32→16). 잠재 차원 128. 증강 활성화. `fit_generator` → `fit` |
| `app/ml/encoders.py` | 백엔드 3종을 같은 인터페이스로: `autoencoder`(.h5), `resnet`(사전학습), `histogram`(배관 점검용) |
| `app/services/embeddings.py` | 취향 벡터와 코사인 유사도. **numpy 만 사용** — 웹 서버에 TensorFlow 불필요 |
| `app/services/recommender.py` | 통계 + 임베딩 하이브리드. 임베딩이 없으면 자동으로 통계 방식으로 폴백 |
| CLI | `compute-embeddings`, `embedding-info`, `similar` |

### 설계 판단: 임베딩은 미리 계산해 파일로

```
[오프라인]  사진 → CNN → 벡터 → instance/embeddings.npz
[실행 중]   instance/embeddings.npz → numpy 로 읽기
```

원본 노트북이 임베딩을 pickle 로 떨군 것과 같은 발상이고, 서빙 경로에서 모델 로딩을
완전히 걷어냈습니다. 덕분에 `requirements.txt` 에 TensorFlow 를 넣지 않아도 되고
(`requirements-ml.txt` 로 분리), 배포 이미지가 가벼워집니다.

### 점수 결합

```
prior = w · 임베딩점수 + (1 - w) · 카테고리점수      # w = EMBEDDING_WEIGHT (기본 0.6)
score = 직접평가평균 × 커버리지 + prior × (1 - 커버리지)
```

실제 평가가 있는 음식에는 평가 데이터를 우선하고, 임베딩은 **아무도 평가하지 않은
음식의 콜드 스타트를 메우는 데만** 기여합니다. 사람들이 이미 평가한 음식에는 실제
데이터가 훨씬 정확하기 때문입니다.

### 테스트 중 발견한 버그

테스트 픽스처가 `instance/embeddings.npz` 를 삭제하도록 작성했더니, pytest 를 돌릴
때마다 개발용으로 만들어 둔 임베딩이 날아갔습니다. `EMBEDDING_PATH` 설정을 추가하고
테스트는 `tmp_path` 를 쓰도록 고쳤습니다. (`test_app.py` 의 `app` 픽스처)

### 한계

이미지 임베딩은 **생김새**를 볼 뿐 맛이나 재료를 이해하지 못합니다. 김치찌개와 육개장은
둘 다 빨간 국물이라 가깝게 나오지만 취향은 갈립니다.

`histogram` 백엔드로 실제 돌려본 결과가 이 한계를 잘 보여줍니다.

```
기준: 구이 · 갈비구이
   1. 나물 · 고사리나물    유사도 +0.926
   2. 만두 · 만두         유사도 +0.910
```

색 분포만으로는 음식을 구분하지 못합니다. 그래서 `histogram` 은 파이프라인 점검용으로만
표시해 두었고, 실제로는 `resnet` 이나 `autoencoder` 를 쓰도록 안내합니다.

453장은 오토인코더를 밑바닥부터 학습하기에 적은 양이라, 수정한 구조로도 사전학습
ResNet 보다 나은 임베딩을 얻기는 어려울 수 있습니다. 두 백엔드를 모두 지원하는 이유입니다.
자세한 내용은 [docs/EMBEDDINGS.md](docs/EMBEDDINGS.md).

---

## 실제 검증 결과

기존 저장소의 `Data/KFoods/Foods` 에서 사진 200장(음식 67종)을 넣고
서버를 띄워 전 화면을 돌려봤습니다.

```
pytest                     29 passed
전 화면 순회               13개 경로 모두 200
투표 4종(좋아요/보통/싫어요/못먹어요)  모두 200
그룹 추천                  200, 추천 3건
없는 주소                  404
비관리자 업로드            403
API 3종                    200
임베딩 파이프라인          음식 67종 / 112차원 생성, 유사 검색·하이브리드 추천 동작
서버 로그 traceback        0건
```

그룹 추천 실제 출력 예시 (demo1 + demo2):

```
1. 나물 가지볶음     +1.00  (2/2명이 직접 평가)
2. 나물 시금치나물   +0.65  (1/2명이 직접 평가)
3. 나물 고사리나물   +0.50  (2/2명이 직접 평가)
거부권으로 제외된 카테고리: 구이, 국, 기타, 김치, 떡, 만두, 면, 무침
```

---

## 남은 일

- Food-101 등 음식 분류 데이터로 파인튜닝한 모델 비교 (분류 학습 특징이 이 과제에 더 적합할 가능성)
- 3명 이상 그룹에서의 가중치 설계 (지금은 전원 동일 가중)
- 추천 결과 기록 → "그래서 뭘 먹었는지" 피드백 루프
- 사진 리사이징 (지금은 원본을 그대로 서빙합니다)
