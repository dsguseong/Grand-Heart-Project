# 이미지 임베딩 붙이기

이 문서는 **AI 모델을 실제로 추천에 연결하는 방법**을 설명합니다.

지금 상태에서 추천은 두 신호를 섞어 씁니다.

| 신호 | 출처 | 언제 쓰이나 |
|---|---|---|
| 통계 | 사용자가 남긴 평가의 카테고리별 평균 | 항상 |
| 이미지 임베딩 | CNN 이 뽑은 사진 특징 벡터 | 임베딩 파일이 있을 때 |

**임베딩 파일이 없으면 통계만으로 동작합니다.** 오류가 나지 않고, 기존과 완전히 동일하게 추천됩니다. 그래서 모델 없이도 앱을 먼저 띄워 보고, 나중에 붙일 수 있습니다.

---

## 왜 임베딩을 미리 계산해 두나

웹 서버가 TensorFlow 를 들고 있을 필요가 없게 하기 위해서입니다.

```
[오프라인]  사진 → 모델 → 벡터 → instance/embeddings.npz   ← TensorFlow/PyTorch 필요
[실행 중]   instance/embeddings.npz → numpy 로 읽기         ← numpy 만 있으면 됨
```

원본 노트북이 임베딩을 pickle 로 떨군 것과 같은 발상이고, 서빙 경로에서 모델 로딩을 완전히 걷어냈습니다. 덕분에 배포 이미지가 가벼워지고, 요청마다 모델을 태우지 않아 응답이 빠릅니다.

임베딩은 **음식 단위**입니다. 한 음식에 사진이 여러 장이면 벡터를 평균 내 대표 벡터로 씁니다.

---

## 백엔드 세 가지

### `resnet` — 사전학습 모델 (권장 시작점)

ImageNet 으로 학습된 ResNet18 의 512차원 특징을 씁니다. 학습이 필요 없습니다.

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
flask compute-embeddings --backend resnet
```

453장 기준 CPU 로 1~2분입니다.

### `autoencoder` — 직접 학습한 모델

팀이 설계한 컨볼루션 오토인코더입니다. 아래 [오토인코더 학습](#오토인코더-학습) 참고.

```bash
pip install 'tensorflow>=2.12'
python -m app.ml.train_autoencoder --images ./Data/KFoods/Foods
flask compute-embeddings --backend autoencoder --model models/autoencoder.h5
```

### `histogram` — 배관 점검용 (딥러닝 아님)

색·밝기 히스토그램입니다. Pillow 와 numpy 만 있으면 돌아갑니다.

```bash
flask compute-embeddings --backend histogram
```

무거운 라이브러리를 깔기 전에 **임베딩 → 저장 → 추천 경로가 제대로 도는지** 확인하는 용도입니다. 추천 품질은 기대하지 마세요. 실제로 돌려보면 이렇게 나옵니다.

```
기준: 구이 · 갈비구이
   1. 나물 · 고사리나물    유사도 +0.926
   2. 만두 · 만두         유사도 +0.910
   3. 국 · 미역국         유사도 +0.907
```

갈비구이와 고사리나물이 0.926 입니다. 색 분포만으로는 음식을 구분하지 못합니다. 제대로 된 모델이 왜 필요한지 보여주는 결과이기도 합니다.

---

## 내 PC에서 TensorFlow가 안 될 때

윈도우 + Anaconda 조합에서 TensorFlow DLL 로딩이 실패하는 경우가 있습니다.

```
ImportError: DLL load failed while importing _pywrap_tensorflow_internal
```

CPU가 AVX를 지원하고 VC++ 재배포 패키지도 최신인데 이 오류가 나면, 버전을 낮춰
보세요 (파이썬 3.11 기준).

```bash
pip uninstall -y tensorflow
pip install "tensorflow==2.15.1"
python -c "import tensorflow as tf; print(tf.__version__)"
```

그래도 안 되면 **계산만 Colab에서 하고 결과 파일만 받아오면 됩니다.**
내 PC에는 TensorFlow가 전혀 필요 없습니다.

### Colab에서

`scripts/colab_embeddings.py` 와 `models/autoencoder.h5` 를 업로드한 뒤:

```python
!python colab_embeddings.py \
    --model autoencoder.h5 \
    --images /content/Kfoods/Foods \
    --output embeddings_by_name.npz
```

`embeddings_by_name.npz` 를 다운로드합니다.

### 내 PC에서

```bash
flask import-embeddings embeddings_by_name.npz
flask embedding-info
```

DB의 음식 id는 Colab이 알 수 없으므로, 이 파일은 **음식 이름**(`카테고리_음식명`)을
키로 씁니다. `import-embeddings` 가 이름을 DB의 id로 연결합니다. numpy만 쓰므로
TensorFlow 없이 동작합니다.

이름이 맞지 않으면 어떤 이름이 어긋났는지 알려주니, 같은 사진 폴더로 계산했는지
확인하시면 됩니다.

---

## 확인 명령어

```bash
flask embedding-info          # 백엔드 · 음식 수 · 차원 · 가중치
flask similar 12 --top 10     # 12번 음식과 생김새가 비슷한 음식
flask import-embeddings <파일>  # 다른 곳에서 계산한 임베딩 가져오기
```

`similar` 는 원본 노트북의 유사 이미지 검색에 대응합니다. 노트북은 유클리드 거리를 썼는데, 여기서는 벡터를 단위 길이로 정규화해 두어 코사인 유사도로 계산합니다. 단위 벡터에서는 `‖a-b‖² = 2 - 2·cos` 이므로 **순위가 완전히 동일**하고, 내적 한 번이라 더 빠릅니다.

---

## 추천에 어떻게 반영되나

### 취향 벡터

사용자가 좋아요(+1) / 보통(0) / 싫어요(-1) 를 준 음식들의 벡터를 가중 평균합니다.

```
taste(u) = Σ (score_i - 2) · v_i  /  ‖ · ‖
```

"이 사람이 좋아하는 음식은 대체로 이렇게 생겼다" 를 나타내는 단위 벡터입니다. 새 음식과의 코사인 유사도가 곧 예측 선호도(-1 ~ +1)입니다.

### 최종 점수

```
prior = w · 임베딩점수 + (1 - w) · 카테고리점수        # w = EMBEDDING_WEIGHT (기본 0.6)
score = 직접평가평균 × 커버리지 + prior × (1 - 커버리지)
```

`커버리지` 는 구성원 중 그 음식을 실제로 평가한 비율입니다.

- **모두가 평가한 음식** → 실제 평가가 거의 전부를 차지. 임베딩은 개입하지 않습니다.
- **아무도 평가하지 않은 음식** → 임베딩 + 카테고리 통계로 점수를 냅니다.

**이미지 임베딩의 실질적 기여는 콜드 스타트 보완입니다.** 사람들이 이미 평가한 음식에는 실제 데이터가 훨씬 정확하니까요. 새로 등록한 음식이나 평가가 드문 음식에 의미 있는 점수를 매기는 것이 임베딩의 역할입니다.

### 가중치 조절

```bash
# .env
EMBEDDING_WEIGHT=0.6    # 0 이면 순수 통계, 1 이면 임베딩만
```

코드에서 직접 넘길 수도 있습니다.

```python
recommend_for_group(members, top_n=3, embedding_weight=0.0)   # 통계만
```

---

## 오토인코더 학습

### 원본 노트북의 문제

`Autoencoder_Colab/grand_heart_project.ipynb` 에는 구조적 버그가 있었습니다.

**1) 인코더 연결이 끊겨 있었습니다**

```python
encoder = Conv2D(32, ...)(input_model)     # ①
encoder = LeakyReLU()(encoder)
encoder = BatchNormalization()(encoder)

encoder = Conv2D(64, ...)(encoder)         # ②
encoder = LeakyReLU()(encoder)
encoder = BatchNormalization()(encoder)

encoder = Conv2D(64, ...)(input_model)     # ③ ← encoder 가 아니라 input_model
```

세 번째 `Conv2D` 의 입력이 직전 층이 아니라 원본 입력입니다. ①②가 그래프에서 통째로 끊기고, 실제 학습된 인코더는 **Conv2D 한 층** 뿐이었습니다.

**2) 다운샘플링이 없었습니다**

`MaxPooling` 도 `strides` 도 없어 256×256 해상도가 그대로 유지됩니다. Flatten 하면 256·256·64 = 4,194,304 차원이고, 여기서 `Dense(16)` 으로 가면 그 한 층의 파라미터만 **6,700만 개**입니다. 사진 453장으로 학습할 규모가 아닙니다.

**3) 잠재 차원 16**

음식 사진의 색·질감·플레이팅을 담기에 너무 좁습니다.

### 수정한 구조

`app/ml/train_autoencoder.py` 에 다음을 반영했습니다.

- 인코더를 제대로 연결하고 `strides=2` 로 단계마다 절반씩 축소 (256 → 128 → 64 → 32 → 16)
- 잠재 차원 기본 128 (`--latent-dim` 으로 조정)
- 데이터가 적으므로 좌우 반전·밝기·줌 증강 활성화 (원본은 주석 처리되어 있었습니다)
- `fit_generator` → `fit` (TF 2.1 에서 deprecated)
- `ReduceLROnPlateau` 추가

### 학습하기

**Colab (권장)** — GPU 로 453장이면 몇 분입니다.

```python
!git clone https://github.com/dsguseong/Grand-Heart-Project.git
%cd Grand-Heart-Project
!unzip -q Data/KFoods.zip -d /content/Kfoods
!python -m app.ml.train_autoencoder --images /content/Kfoods/Foods --epochs 150
```

학습이 끝나면 `models/autoencoder.h5` 를 내려받아 프로젝트의 `models/` 에 넣으세요.

**로컬**

```bash
pip install 'tensorflow>=2.12'
python -m app.ml.train_autoencoder --images ./Data/KFoods/Foods --epochs 150
```

주요 옵션:

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--images` | (필수) | 음식 사진 폴더 |
| `--output` | `models/autoencoder.h5` | 저장 경로 |
| `--latent-dim` | 128 | 잠재 벡터 차원 |
| `--image-size` | 256 | 입력 해상도 |
| `--epochs` | 150 | EarlyStopping 이 있으므로 넉넉히 줘도 됩니다 |

### 임베딩 만들기

```bash
flask compute-embeddings --backend autoencoder --model models/autoencoder.h5
flask embedding-info
```

---

## 기대치에 대해

솔직하게 적어둡니다.

**생김새가 비슷하다고 맛 취향이 비슷하지는 않습니다.** 김치찌개와 육개장은 둘 다 빨간 국물이라 임베딩이 가깝게 나오지만, 한쪽만 좋아하는 사람은 많습니다. 이미지 임베딩은 "비슷하게 생긴 음식" 을 찾을 뿐, 맛이나 재료를 이해하지 못합니다.

**453장은 오토인코더를 밑바닥부터 학습하기에 적은 양입니다.** 수정한 구조로도 임베딩 품질이 `resnet` 백엔드보다 낫기는 어려울 수 있습니다. 사전학습 모델은 수백만 장으로 학습된 특징을 이미 갖고 있기 때문입니다.

그래서 두 백엔드를 모두 지원합니다.

- 직접 만든 모델을 쓰는 것이 목적이면 → `autoencoder`
- 추천 품질이 목적이면 → `resnet`
- 둘을 비교해 보는 것도 좋습니다. `flask similar` 로 같은 음식에 대해 어느 쪽이 납득 가는 결과를 내는지 보면 차이가 드러납니다.

**더 나은 방향** 이 궁금하시면, 음식 분류 데이터셋(Food-101 등)으로 파인튜닝한 모델이 이 과제에는 가장 적합합니다. 분류 학습을 거치면 "같은 음식끼리 가깝게" 모이도록 특징이 정렬되기 때문입니다. 오토인코더는 복원이 목적이라 그런 정렬이 보장되지 않습니다.

---

## 새 백엔드 추가하기

`app/ml/encoders.py` 에서 `Encoder` 를 상속하고 `BACKENDS` 에 등록하면 끝입니다.

```python
class MyEncoder(Encoder):
    name = "mine"
    dim = 256

    def encode_paths(self, paths: list[Path]) -> np.ndarray:
        ...  # (N, 256) 반환

BACKENDS["mine"] = MyEncoder
```

나머지(저장 형식, 취향 벡터 계산, 추천 반영, 화면 표시)는 전부 그대로 동작합니다.
