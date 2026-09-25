<div align="center">

# 뭐 먹으러 갈까?

**여럿이 모였을 때 "아무거나"로 끝나지 않도록.**

음식 사진을 한 장씩 넘기며 취향을 모으고, 서로 팔로우한 사람들과 함께 먹을 음식을 추천받는 웹 서비스입니다.

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0-D71F00)
![Tests](https://img.shields.io/badge/tests-29%20passed-2E7D32)
![Embeddings](https://img.shields.io/badge/embeddings-CNN%20%7C%20autoencoder-7B1FA2)
![License](https://img.shields.io/badge/license-MIT-blue)

</div>

---

## 목차

- [무엇을 하는 서비스인가](#무엇을-하는-서비스인가)
- [주요 기능](#주요-기능)
- [기술 스택](#기술-스택)
- [빠른 시작](#빠른-시작)
- [프로젝트 구조](#프로젝트-구조)
- [추천 알고리즘](#추천-알고리즘)
- [AI 모델 연결](#ai-모델-연결)
- [REST API](#rest-api)
- [테스트](#테스트)
- [자주 막히는 지점](#자주-막히는-지점)
- [배포](#배포)
- [로드맵](#로드맵)
- [라이선스](#라이선스)

---

## 무엇을 하는 서비스인가

점심시간마다 반복되는 "뭐 먹지 → 아무거나 → 결국 어제 그 집" 을 없애려고 만들었습니다.

1. **모은다** — 회원가입 후 음식 사진이 한 장씩 뜨면 `좋아요` / `보통` / `싫어요` / `못 먹어요` 중 하나를 고릅니다. 틴더처럼 넘기기만 하면 개인 취향 데이터가 쌓입니다.
2. **잇는다** — 인스타그램식 팔로우 구조에서, **서로 팔로우한 사이**에만 그룹 추천이 열립니다. 한쪽만 팔로우한 관계에서는 취향이 노출되지 않습니다.
3. **고른다** — 선택한 사람들의 취향 벡터를 가중 합으로 묶어, 모두가 만족할 음식 TOP-3 를 뽑습니다. 한 명이라도 못 먹는 음식은 후보에서 빠집니다.
4. **찾는다** — 추천된 음식을 파는 주변 식당을 카카오 로컬 API 로 검색합니다.

---

## 주요 기능

| 기능 | 설명 |
|---|---|
| 취향 스와이프 | 한 번 평가한 음식은 다시 나오지 않고, 다 보면 안내 문구로 마무리 |
| 4지선다 평가 | 좋아요 / 보통 / 싫어요 에 더해 **못 먹어요**(알레르기·종교·비선호)를 분리 |
| 맞팔로우 게이팅 | 서로 팔로우한 사이에서만 그룹 추천. 서버에서 재검증하므로 API 우회 불가 |
| 그룹 추천 | N명 지원. 거부권 규칙 + 공통 취향이 없을 때의 자동 폴백 |
| 주변 식당 | 브라우저 위치 권한 + 카카오 로컬. API 키는 서버에만 보관 |
| 이미지 임베딩 | CNN 으로 뽑은 사진 특징을 추천에 반영. 평가가 없는 음식의 콜드 스타트를 보완 |
| REST API | 모바일 앱을 붙일 수 있도록 화면과 데이터를 분리 (`/api/v1`) |
| 관리자 업로드 | 사진 일괄 등록. CLI 로 폴더 통째 임포트도 가능 |

---

## 기술 스택

**백엔드** Flask 3 (애플리케이션 팩토리 + 블루프린트) · SQLAlchemy 2.0 · Alembic · Flask-Login · Flask-WTF

**데이터베이스** SQLite (개발) / PostgreSQL (운영) — `DATABASE_URL` 만 바꾸면 코드 수정 없이 전환

**프론트엔드** Jinja2 + 순수 CSS. 프레임워크 없이 약 300줄, 외부 CSS 의존성 0

**인증** 세션 쿠키(웹) + JWT Bearer 토큰(API)

**머신러닝** 사전학습 ResNet18 (512차원 특징). 직접 학습한 오토인코더도 지원하며, 세 방식을 비교한 기록은 [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) 에 있습니다. 임베딩은 오프라인에서 계산해 `.npz` 로 저장하므로 **웹 서버에는 TensorFlow/PyTorch 가 필요 없습니다**

**테스트** pytest — 서비스 계층 단위 테스트 + 라우트 통합 테스트 29개

---

## 빠른 시작

> **필요 환경** Python 3.10 이상, Git

### 1. 내려받기

```bash
git clone https://github.com/dsguseong/Grand-Heart-Project.git
cd Grand-Heart-Project
```

### 2. 가상환경

<details open>
<summary><b>Git Bash / macOS / Linux</b></summary>

```bash
python -m venv .venv
source .venv/Scripts/activate    # Windows Git Bash
source .venv/bin/activate        # macOS / Linux
```
</details>

<details>
<summary><b>Windows PowerShell</b></summary>

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

실행 정책 오류가 나면 먼저:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
</details>

프롬프트 앞에 `(.venv)` 가 붙으면 성공입니다.

### 3. 패키지 설치

```bash
pip install -r requirements.txt
```

### 4. 환경변수

```bash
cp .env.example .env        # Windows PowerShell: copy .env.example .env
```

개발용은 그대로 두셔도 됩니다. 운영에 올릴 때는 `SECRET_KEY` 를 반드시 바꾸세요.

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. 데이터베이스

```bash
export FLASK_APP=run.py     # PowerShell: $env:FLASK_APP="run.py"  /  cmd: set FLASK_APP=run.py
flask db upgrade
```

### 6. 음식 사진 등록

데이터셋은 용량 때문에 저장소에 포함하지 않았습니다. `Data/KFoods/Foods` 경로를 지정해 주세요.

```bash
flask import-foods ./Data/KFoods/Foods
```

```
스캔 453장 / 등록 453장 / 건너뜀 0장
```

파일명은 `{카테고리}_{음식명}_{번호}.jpg` 규칙을 따릅니다. 예) `찌개_김치찌개1_0007.jpg` → 카테고리 `찌개`, 음식 `김치찌개`. 규칙에 맞지 않는 파일은 건너뛰고 어떤 파일이 빠졌는지 알려 줍니다.

### 7. 실행

```bash
flask demo-data --ratings 60    # 데모 계정 2개 (서로 팔로우 상태)
flask run --debug
```

브라우저에서 <http://127.0.0.1:5000> 접속 → **demo1 / demo1234** 로 로그인.

상단 **고르기** 로 취향을 모으고, **함께 먹기** 에서 demo2 를 선택해 추천을 받아 보세요.

<details>
<summary><b>본인 계정으로 시작하려면</b></summary>

```bash
flask create-user 아이디 이메일주소 --admin
```

`--admin` 을 붙이면 사진 등록 메뉴가 보입니다. 첫 번째로 가입한 사용자는 자동으로 관리자가 됩니다.
</details>

### CLI 명령어 모음

| 명령어 | 설명 |
|---|---|
| `flask db upgrade` | 마이그레이션 적용 |
| `flask init-db` | 마이그레이션 없이 테이블만 생성 |
| `flask import-foods <경로>` | 폴더의 음식 사진 일괄 등록 (`--limit N` 으로 개수 제한) |
| `flask create-user <아이디> <이메일>` | 사용자 생성 (`--admin` 으로 관리자) |
| `flask demo-data` | 데모 계정 2개 + 무작위 평가 생성 |
| `flask compute-embeddings` | 이미지 임베딩 계산 (`--backend resnet\|autoencoder\|histogram`) |
| `flask embedding-info` | 저장된 임베딩 상태 확인 |
| `flask similar <id>` | 생김새가 비슷한 음식 검색 |
| `flask import-embeddings <파일>` | Colab 등에서 계산한 임베딩 가져오기 (numpy 만 필요) |
| `flask shell` | 모델이 미리 로드된 파이썬 셸 |

---

## 프로젝트 구조

```
Grand-Heart-Project/
├── run.py                      개발 서버 진입점
├── config.py                   환경별 설정 (development / testing / production)
├── requirements.txt
├── .env.example
│
├── app/
│   ├── __init__.py             create_app() 애플리케이션 팩토리
│   ├── extensions.py           db · migrate · login · mail · csrf
│   ├── models.py               User · FoodItem · FoodImage · Preference · FoodExclusion
│   ├── cli.py                  커스텀 flask 명령어
│   │
│   ├── auth/                   가입 · 로그인 · 비밀번호 재설정
│   ├── main/                   홈 · 프로필 · 팔로우
│   ├── foods/                  스와이프 · 취향 · 제외 · 업로드
│   ├── recommend/              그룹 추천 · 주변 식당
│   ├── api/                    /api/v1 JSON 엔드포인트
│   ├── errors/                 403 · 404 · 413 · 500
│   │
│   ├── services/               ◀ 도메인 로직은 전부 여기
│   │   ├── preferences.py      다음 음식 선택, 평가 저장
│   │   ├── recommender.py      통계 + 임베딩 하이브리드 추천
│   │   ├── embeddings.py       취향 벡터, 유사도 (numpy 만 사용)
│   │   ├── images.py           파일명 파싱, 저장, 일괄 임포트
│   │   ├── mailer.py           메일 발송
│   │   └── places.py           카카오 로컬 API
│   │
│   ├── ml/                     ◀ 오프라인 전용 (서버 실행에 불필요)
│   │   ├── encoders.py         resnet / autoencoder / histogram
│   │   └── train_autoencoder.py  오토인코더 학습 (구조 버그 수정본)
│   │
│   ├── templates/
│   └── static/css/app.css
│
├── migrations/                 Alembic
├── tests/test_app.py           테스트 29개
├── notebooks/                  오토인코더 실험 원본 (Colab)
├── models/                     학습된 .h5 (gitignore)
├── scripts/colab_embeddings.py Colab 에서 임베딩 계산
└── docs/
    ├── EMBEDDINGS.md           AI 모델 연결 가이드
    └── EXPERIMENTS.md          임베딩 비교 실험
```

**설계 원칙** — 라우트는 요청을 받아 서비스 함수를 호출하는 일만 합니다. 계산은 전부 `services/` 안에 있어서 웹 컨텍스트 없이 단독 테스트가 가능합니다.

---

## 추천 알고리즘

### 1. 개인 취향 벡터

평가 점수 `좋아요 3 / 보통 2 / 싫어요 1` 을 `점수 - 2` 로 옮겨 **-1 ~ +1** 범위로 정규화하고, 카테고리별 평균을 냅니다.

```
demo1  →  { 나물: +0.40, 국: +0.22, 구이: +0.07, 면: -0.17, ... }
```

### 2. 가중 합

구성원들의 벡터를 가중 평균합니다. 가중치를 주지 않으면 `1/N` 동일 가중입니다.

```python
def weighted_sum(vectors, weights=None):
    if weights is None:
        weights = [1.0 / len(vectors)] * len(vectors)
    keys = set().union(*(v.keys() for v in vectors))   # 한쪽에만 있는 카테고리도 포함
    return {k: sum(v.get(k, 0.0) * w for v, w in zip(vectors, weights)) / sum(weights)
            for k in keys}
```

2명 고정이 아니라 **N명 일반화**되어 있고, 두 사람의 카테고리 구성이 달라도 잘리지 않습니다.

### 3. 거부권

다음 셋 중 하나라도 해당되면 후보에서 제외합니다.

- 구성원 한 명이라도 해당 **카테고리** 선호도가 0 이하
- 구성원 한 명이라도 **못 먹어요** 로 지정한 음식
- 구성원 한 명이라도 직접 **싫어요** 를 준 음식

### 4. 폴백

거부권을 적용한 결과 후보가 하나도 남지 않으면 — 즉 공통으로 좋아하는 카테고리가 없으면 — 오류를 내지 않고 평균 점수가 높은 순으로 결과를 냅니다. 화면에는 완화해서 추천했다는 안내가 함께 뜹니다.

### 5. 음식 선택

카테고리 점수만 쓰지 않고, 구성원이 그 음식을 직접 평가한 비율만큼 실제 평가 평균에 가중치를 줍니다.

```
score = 직접평가평균 × 커버리지 + 카테고리점수 × (1 - 커버리지)
```

**실행 예시** (demo1 + demo2)

```
1. 나물 가지볶음     +1.00   (2/2명이 직접 평가)
2. 나물 시금치나물   +0.65   (1/2명이 직접 평가)
3. 나물 고사리나물   +0.50   (2/2명이 직접 평가)

거부권으로 제외된 카테고리: 구이, 국, 기타, 김치, 떡, 만두, 면, 무침
```

### 6. 이미지 임베딩 (선택)

임베딩 파일이 있으면, 아무도 평가하지 않은 음식의 점수를 CNN 특징으로 보완합니다.

```
prior = w · 임베딩점수 + (1 - w) · 카테고리점수      # w = EMBEDDING_WEIGHT (기본 0.6)
score = 직접평가평균 × 커버리지 + prior × (1 - 커버리지)
```

임베딩 파일이 없으면 `w` 가 자동으로 0 이 되어 순수 통계 방식으로 동작합니다.
자세한 내용은 [AI 모델 연결](#ai-모델-연결).

---

## AI 모델 연결

추천은 **통계**와 **이미지 임베딩** 두 신호를 섞습니다. 임베딩은 선택 사항이고, 없으면 통계만으로 정상 동작합니다.

### 왜 미리 계산하나

```
[오프라인]  사진 → CNN → 벡터 → instance/embeddings.npz    TensorFlow/PyTorch 필요
[실행 중]   instance/embeddings.npz → numpy               numpy 만 있으면 됨
```

웹 서버가 모델을 들고 있을 필요가 없어 배포가 가볍고 응답이 빠릅니다.

### 백엔드

| 백엔드 | 설명 | 필요한 것 |
|---|---|---|
| `resnet` | ImageNet 사전학습 ResNet18 (512차원). 학습 불필요 | PyTorch |
| `autoencoder` | 직접 학습한 컨볼루션 오토인코더 | TensorFlow + 학습 |
| `histogram` | 색 히스토그램. **딥러닝 아님**, 배관 점검용 | Pillow (기본 포함) |

### 바로 해보기

```bash
# 1) 무거운 라이브러리 없이 파이프라인 확인
flask compute-embeddings --backend histogram
flask embedding-info
flask similar 1 --top 5

# 2) 사전학습 모델로 교체
pip install -r requirements-ml.txt
flask compute-embeddings --backend resnet

# 3) 직접 학습한 오토인코더로 교체
python -m app.ml.train_autoencoder --images ./Data/KFoods/Foods
flask compute-embeddings --backend autoencoder --model models/autoencoder.h5
```

### 세 방식을 비교했습니다

기준 음식 `구이 · 갈비구이` 에 대해 유사도 상위 항목을 확인한 결과입니다.

| 방식 | 비슷하다고 본 것 | 유사도 폭 | 평가 |
|---|---|---|---|
| 히스토그램 | 고사리나물, 만두, 미역국 | 0.926~0.902 | 색만 봄. 무의미 |
| 오토인코더 (직접 학습) | 미역줄기볶음, 물냉면, 감자전 | 0.454~0.387 | 학습 부족. 사실상 무작위 |
| **ResNet18 (사전학습)** | **보쌈, 총각김치, 주꾸미볶음** | **0.915~0.891** | **계열은 맞음. 변별력 부족** |

오토인코더는 416장(음식당 평균 2.8장)으로는 유의미한 임베딩을 얻지 못했습니다.
ResNet18 은 붉은 양념 계열의 고기·해산물을 찾아내 계열 구분은 되지만, 상위 항목이
사실상 동점이라 변별력이 충분하지는 않습니다. ImageNet 이 한식 반찬을 구분하도록
학습되지 않았기 때문입니다.

실험 과정과 판단 근거는 **[docs/EXPERIMENTS.md](docs/EXPERIMENTS.md)** 에 정리했습니다.

### 원본 노트북의 버그

기존 `Autoencoder_Colab/grand_heart_project.ipynb` 에는 인코더 층 연결이 끊기는 버그가 있었습니다.
`Conv2D(64, ...)(input_model)` — 직전 층이 아니라 원본 입력을 받아, 앞의 두 층이 그래프에서
통째로 끊겼습니다. 다운샘플링도 없어 `Dense` 한 층의 파라미터가 6,700만 개였습니다.

`app/ml/train_autoencoder.py` 에서 이를 수정했습니다. 자세한 진단은
**[docs/EMBEDDINGS.md](docs/EMBEDDINGS.md)**.

### 기대치

이미지 임베딩은 **생김새가 비슷한 음식**을 찾을 뿐, 맛이나 재료를 이해하지 못합니다.
김치찌개와 육개장은 둘 다 붉은 국물이라 가깝게 나오지만 취향은 갈립니다. 어떤 모델을
쓰더라도 이미지만으로는 넘을 수 없는 벽입니다.

그래서 임베딩의 역할을 **콜드 스타트 보완**으로 제한했습니다. 실제 평가가 있는 음식에는
평가 데이터가 점수를 지배하고, 아무도 평가하지 않은 음식에만 임베딩이 개입합니다.

---

## REST API

모바일 앱을 붙일 수 있도록 화면(HTML)과 데이터(JSON)를 분리했습니다. 인증은 Bearer 토큰입니다.

### 토큰 발급

```http
POST /api/v1/token
Content-Type: application/json

{ "username": "demo1", "password": "demo1234" }
```

```json
{
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 604800,
  "user": { "id": 2, "username": "demo1", "is_admin": false }
}
```

### 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/api/v1/token` | 토큰 발급 |
| `GET` | `/api/v1/me` | 내 정보 · 진행률 · 맞팔 목록 |
| `GET` | `/api/v1/foods/next` | 다음에 평가할 음식 |
| `POST` | `/api/v1/foods/{id}/vote` | 평가 (`like` / `soso` / `dislike` / `exclude`) |
| `GET` | `/api/v1/preferences` | 내 평가 · 제외 목록 |
| `POST` | `/api/v1/recommend` | 그룹 추천 |
| `GET` | `/api/v1/places/nearby` | 주변 식당 |

### 사용 예시

```bash
TOKEN=$(curl -s -X POST localhost:5000/api/v1/token \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo1","password":"demo1234"}' | jq -r .token)

curl localhost:5000/api/v1/foods/next -H "Authorization: Bearer $TOKEN"

curl -X POST localhost:5000/api/v1/recommend \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"member_ids":[3]}'
```

`/api/v1/recommend` 는 **맞팔로우 관계가 아닌 id 가 들어오면 403** 을 반환합니다. 클라이언트를 신뢰하지 않고 서버에서 다시 검증합니다.

---

## 테스트

```bash
pytest -q
```

```
............................. 29 passed
```

버그를 고칠 때마다 그 버그를 재현하는 테스트를 함께 남겼습니다.

| 영역 | 검증 내용 |
|---|---|
| 파일명 파싱 | 규칙 위반 파일에 예외 대신 `None` 반환 |
| 스와이프 | 같은 음식 재출현 없음, 전부 평가 후에도 크래시 없음 |
| 평가 | 중복 저장 없음, 허용되지 않은 점수 거부 |
| 추천 | 거부권 적용, 공통 카테고리 없을 때 폴백, 못 먹어요 반영, N명 일반화 |
| 팔로우 | 맞팔일 때만 그룹 추천, 자기 자신 팔로우 차단 |
| 라우트 | 신규 가입자 전 화면 200, 비관리자 업로드 403, 오픈 리다이렉트 차단 |
| API | 토큰 발급·검증, 맞팔 아닌 상대 요청 403 |
| 임베딩 | 취향 벡터 방향, 미평가 음식 예측, 파일 없을 때 통계 폴백, 자기 자신 제외 |

---

## 자주 막히는 지점

<details>
<summary><b><code>UnicodeDecodeError: 'cp949' codec can't decode...</code></b></summary>

한국어 Windows 에서 pip 가 UTF-8 파일을 cp949 로 읽으려다 실패하는 경우입니다. 현재 `requirements.txt` 는 ASCII 로만 작성되어 있어 발생하지 않지만, 다른 파일에서 같은 오류가 나면 해당 파일의 한글 주석을 제거하거나 인코딩을 확인해 주세요.
</details>

<details>
<summary><b><code>bash: .venvScriptsactivate: command not found</code></b></summary>

Git Bash 에서는 역슬래시(`\`)가 이스케이프 문자로 해석되어 사라집니다. 슬래시를 쓰고 `source` 를 붙이세요.

```bash
source .venv/Scripts/activate
```
</details>

<details>
<summary><b><code>Error: Could not locate a Flask application</code></b></summary>

`FLASK_APP` 이 설정되지 않았습니다. 터미널을 새로 열 때마다 다시 지정해야 합니다.

```bash
export FLASK_APP=run.py     # PowerShell: $env:FLASK_APP="run.py"
```
</details>

<details>
<summary><b>스와이프 화면에 "준비된 음식을 모두 봤습니다" 만 나옴</b></summary>

오류가 아니라 DB 에 음식이 없어서입니다. 6단계 `flask import-foods` 를 실행했는지 확인해 주세요.
</details>

<details>
<summary><b><code>flask: command not found</code></b></summary>

가상환경이 활성화되지 않았습니다. 프롬프트 앞에 `(.venv)` 가 붙어 있는지 확인하세요.
</details>

<details>
<summary><b>"주변 식당" 버튼을 눌러도 결과가 없음</b></summary>

`.env` 에 카카오 REST API 키가 필요합니다. [카카오 개발자센터](https://developers.kakao.com)에서 발급 후 `KAKAO_REST_API_KEY` 에 넣어 주세요. 키가 없어도 나머지 기능은 정상 동작합니다.
</details>

---

## 배포

```bash
export FLASK_CONFIG=production
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export DATABASE_URL=postgresql://user:password@host/dbname

flask db upgrade
gunicorn -w 4 -b 0.0.0.0:8000 "run:app"
```

**체크리스트**

- [ ] `SECRET_KEY` 를 임의의 긴 문자열로 교체 (기본값 사용 금지)
- [ ] SQLite → PostgreSQL 전환 (`DATABASE_URL`)
- [ ] `app/static/uploads/foods/` 를 볼륨으로 분리하거나 오브젝트 스토리지로 이전
- [ ] HTTPS 적용 (`SESSION_COOKIE_SECURE` 가 production 설정에서 자동 활성화)
- [ ] 비밀번호 재설정을 쓰려면 `MAIL_*` 설정

---

## 로드맵

- [x] 이미지 임베딩을 추천에 연결 (사전학습 CNN / 직접 학습 오토인코더)
- [ ] Food-101 파인튜닝 — 분류 학습 특징이 이 과제에 더 적합 ([근거](docs/EXPERIMENTS.md))
- [ ] precision@k 등 임베딩 평가 지표 도입 (현재는 눈으로 확인)
- [ ] 3명 이상 그룹의 가중치 설계 (현재는 전원 동일 가중)
- [ ] 추천 결과 기록 → "실제로 뭘 먹었는지" 피드백 루프
- [ ] 업로드 이미지 리사이징 및 WebP 변환
- [ ] React Native 또는 Flutter 클라이언트 (API 는 준비 완료)
- [ ] 소셜 로그인

---

## 문서

- [CHANGES.md](CHANGES.md) — v1 에서 v2 로 넘어오며 고친 문제. 기존 코드 인용과 함께 정리했습니다.
- [docs/EMBEDDINGS.md](docs/EMBEDDINGS.md) — 이미지 임베딩 설정, 오토인코더 학습, 원본 노트북 진단.
- [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) — 임베딩 세 방식 비교 실험과 채택 근거.

---

## 라이선스

[MIT](LICENSE)
