"""컨볼루션 오토인코더 학습.

원본 노트북(Autoencoder_Colab/grand_heart_project.ipynb)의 문제와 수정 내역
----------------------------------------------------------------------

**1) 인코더 연결이 끊겨 있었습니다 — 가장 큰 문제**

    encoder = Conv2D(32, ...)(input_model)     # ①
    encoder = LeakyReLU()(encoder)
    encoder = BatchNormalization()(encoder)

    encoder = Conv2D(64, ...)(encoder)         # ②
    encoder = LeakyReLU()(encoder)
    encoder = BatchNormalization()(encoder)

    encoder = Conv2D(64, ...)(input_model)     # ③ ← encoder 가 아니라 input_model
                                               #    ①②가 그래프에서 통째로 끊김

세 번째 Conv2D 의 입력이 직전 층이 아니라 원본 입력이었습니다. 결과적으로
실제 학습된 인코더는 **Conv2D 한 층** 뿐이었습니다.

**2) 다운샘플링이 전혀 없었습니다**

MaxPooling 도 strides 도 없어서 256×256 해상도가 그대로 유지됐습니다.
Flatten 하면 256·256·64 = 4,194,304 차원이고, 여기서 Dense(16) 으로 가면
그 한 층의 파라미터만 **6,700만 개**입니다. 이미지 453장으로 학습할 규모가
아닙니다(파라미터가 샘플보다 15만 배 많음).

**3) 잠재 차원이 16 이었습니다**

음식 사진의 색·질감·플레이팅을 담기에 너무 좁습니다.

**수정**

- 인코더를 제대로 연결하고 `strides=2` 로 단계마다 절반씩 줄입니다
  (256 → 128 → 64 → 32 → 16). Flatten 직전이 16·16·128 = 32,768 차원.
- 잠재 차원 기본값 128. `--latent-dim` 으로 조정 가능합니다.
- 데이터가 적으므로 좌우 반전·밝기 변화 증강을 켰습니다(원본은 주석 처리).
- `fit_generator` 는 TF 2.1 에서 deprecated → `fit`.
- `tqdm_notebook` 제거(주피터 밖에서 경고).

사용법
------
    # 로컬
    python -m app.ml.train_autoencoder --images ./Data/KFoods/Foods

    # Colab (GPU 권장, 453장 기준 수 분)
    !python -m app.ml.train_autoencoder --images /content/Kfoods/Foods --epochs 150

학습이 끝나면 models/autoencoder.h5 가 생깁니다. 그 파일로 임베딩을 만듭니다.

    flask compute-embeddings --backend autoencoder --model models/autoencoder.h5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_autoencoder(image_size: int = 256, channels: int = 3, latent_dim: int = 128):
    """인코더-디코더를 대칭으로 구성합니다."""
    from tensorflow.keras import backend as K
    from tensorflow.keras.layers import (
        Activation,
        BatchNormalization,
        Conv2D,
        Conv2DTranspose,
        Dense,
        Flatten,
        Input,
        LeakyReLU,
        Reshape,
    )
    from tensorflow.keras.models import Model

    inputs = Input(shape=(image_size, image_size, channels), name="image")

    # --- 인코더: 단계마다 해상도 절반, 채널 2배 ---
    x = inputs
    for filters in (32, 64, 128, 128):
        x = Conv2D(filters, (3, 3), strides=2, padding="same",
                   kernel_initializer="he_normal")(x)
        x = LeakyReLU(0.2)(x)
        x = BatchNormalization(axis=-1)(x)

    shape_before_flatten = K.int_shape(x)[1:]
    x = Flatten()(x)
    latent = Dense(latent_dim, name="latent_space")(x)

    # --- 디코더: 인코더를 거꾸로 ---
    y = Dense(int(shape_before_flatten[0] * shape_before_flatten[1] * shape_before_flatten[2]))(latent)
    y = Reshape(shape_before_flatten)(y)
    for filters in (128, 128, 64, 32):
        y = Conv2DTranspose(filters, (3, 3), strides=2, padding="same",
                            kernel_initializer="he_normal")(y)
        y = LeakyReLU(0.2)(y)
        y = BatchNormalization(axis=-1)(y)

    outputs = Conv2D(channels, (3, 3), padding="same", name="reconstruction")(y)
    outputs = Activation("sigmoid")(outputs)

    return Model(inputs, outputs, name="food_autoencoder")


def train(
    images_dir: Path,
    output: Path,
    image_size: int = 256,
    latent_dim: int = 128,
    batch_size: int = 16,
    epochs: int = 150,
    learning_rate: float = 1e-3,
    validation_split: float = 0.2,
) -> Path:
    try:
        from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
        from tensorflow.keras.optimizers import Adam
        from tensorflow.keras.preprocessing.image import ImageDataGenerator
    except ImportError:
        sys.exit("TensorFlow 가 필요합니다:  pip install 'tensorflow>=2.12'")

    images_dir = Path(images_dir)
    if not images_dir.is_dir():
        sys.exit(f"이미지 폴더를 찾을 수 없습니다: {images_dir}")

    # flow_from_directory 는 하위 폴더를 클래스로 봅니다.
    # 사진이 폴더 바로 아래에 있으면 부모를 넘기고 classes 로 지정합니다.
    has_subdirs = any(p.is_dir() for p in images_dir.iterdir())
    if has_subdirs:
        root, classes = images_dir, None
    else:
        root, classes = images_dir.parent, [images_dir.name]

    datagen = ImageDataGenerator(
        rescale=1.0 / 255,
        horizontal_flip=True,       # 데이터가 적으므로 증강을 켭니다
        brightness_range=(0.8, 1.2),
        zoom_range=0.1,
        validation_split=validation_split,
    )
    common = dict(
        directory=str(root),
        classes=classes,
        target_size=(image_size, image_size),
        batch_size=batch_size,
        class_mode="input",         # 입력 = 정답 (복원 학습)
    )
    train_set = datagen.flow_from_directory(subset="training", shuffle=True, **common)
    val_set = datagen.flow_from_directory(subset="validation", shuffle=False, **common)

    if train_set.n == 0:
        sys.exit(f"이미지를 찾지 못했습니다: {images_dir}")

    model = build_autoencoder(image_size, 3, latent_dim)
    model.compile(loss="mse", optimizer=Adam(learning_rate=learning_rate))
    model.summary()

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    model.fit(
        train_set,
        epochs=epochs,
        validation_data=val_set,
        callbacks=[
            ModelCheckpoint(str(output), monitor="val_loss", save_best_only=True, verbose=1),
            EarlyStopping(monitor="val_loss", patience=20, restore_best_weights=True),
            ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=8, min_lr=1e-6),
        ],
    )

    model.save(output)
    print(f"\n저장 완료: {output}")
    print("다음 단계:")
    print(f"  flask compute-embeddings --backend autoencoder --model {output}")
    return output


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="음식 이미지 오토인코더 학습")
    parser.add_argument("--images", required=True, help="음식 사진 폴더 (예: ./Data/KFoods/Foods)")
    parser.add_argument("--output", default="models/autoencoder.h5")
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--latent-dim", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--epochs", type=int, default=150)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    args = parser.parse_args(argv)

    train(
        images_dir=Path(args.images),
        output=Path(args.output),
        image_size=args.image_size,
        latent_dim=args.latent_dim,
        batch_size=args.batch_size,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
    )


if __name__ == "__main__":
    main()
