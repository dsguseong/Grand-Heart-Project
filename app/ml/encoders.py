"""임베딩 생성기 (오프라인 전용).

이 모듈은 `flask compute-embeddings` 를 실행할 때만 임포트됩니다.
웹 서버는 여기를 거치지 않으므로 TensorFlow / PyTorch 가 설치돼 있지 않아도
앱 전체가 정상 동작합니다.

백엔드 두 가지
--------------
autoencoder : 직접 학습한 컨볼루션 오토인코더(.h5)의 latent_space 층 출력.
              "우리가 만든 모델" 을 그대로 씁니다. TensorFlow 필요.
resnet      : ImageNet 사전학습 ResNet18 의 평균 풀링 특징(512차원).
              학습 없이 바로 동작. PyTorch + torchvision 필요.

둘 다 `encode_paths(paths) -> np.ndarray` 라는 같은 인터페이스를 따르므로
서로 바꿔 끼울 수 있습니다. 새 백엔드를 추가하려면 Encoder 를 상속해
BACKENDS 에 등록하기만 하면 됩니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np


class MissingDependency(RuntimeError):
    """필요한 ML 라이브러리가 설치되지 않았을 때."""


class Encoder(ABC):
    name: str = "base"
    dim: int = 0

    @abstractmethod
    def encode_paths(self, paths: list[Path]) -> np.ndarray:
        """이미지 경로 목록 -> (N, dim) 행렬."""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} dim={self.dim}>"


class AutoencoderEncoder(Encoder):
    """직접 학습한 오토인코더의 잠재 벡터.

    학습 스크립트(app/ml/train_autoencoder.py)가 만든 .h5 파일을 받아
    'latent_space' 층까지만 잘라낸 모델로 추론합니다.
    """

    name = "autoencoder"

    def __init__(self, model_path: Path, image_size: int = 256, batch_size: int = 16):
        try:
            from tensorflow.keras.models import Model, load_model
        except ImportError as exc:  # pragma: no cover - 환경 의존
            raise MissingDependency(
                "TensorFlow 가 필요합니다.  pip install 'tensorflow>=2.12'"
            ) from exc

        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"모델 파일이 없습니다: {model_path}\n"
                "먼저 학습하세요:  python -m app.ml.train_autoencoder --images <폴더>"
            )

        autoencoder = load_model(model_path, compile=False)
        try:
            latent = autoencoder.get_layer("latent_space")
        except ValueError as exc:
            names = [layer.name for layer in autoencoder.layers]
            raise ValueError(
                "모델에 'latent_space' 층이 없습니다. 층 이름: " + ", ".join(names)
            ) from exc

        self._model = Model(autoencoder.input, latent.output)
        self.dim = int(latent.output.shape[-1])
        self.image_size = image_size
        self.batch_size = batch_size

    def _load_batch(self, paths: list[Path]) -> np.ndarray:
        from tensorflow.keras.preprocessing.image import img_to_array, load_img

        arrays = []
        for path in paths:
            img = load_img(path, target_size=(self.image_size, self.image_size))
            arrays.append(img_to_array(img) / 255.0)
        return np.stack(arrays)

    def encode_paths(self, paths: list[Path]) -> np.ndarray:
        out = []
        for start in range(0, len(paths), self.batch_size):
            batch = paths[start : start + self.batch_size]
            out.append(self._model.predict(self._load_batch(batch), verbose=0))
        return np.vstack(out).astype(np.float32)


class ResNetEncoder(Encoder):
    """ImageNet 사전학습 ResNet18 의 512차원 특징.

    453장으로 오토인코더를 밑바닥부터 학습하는 것보다 임베딩 품질이 안정적이라,
    오토인코더를 학습하기 전의 기본값으로 씁니다.
    """

    name = "resnet"
    dim = 512

    def __init__(self, batch_size: int = 32):
        try:
            import torch
            from torchvision import models, transforms
        except ImportError as exc:  # pragma: no cover - 환경 의존
            raise MissingDependency(
                "PyTorch 가 필요합니다.\n"
                "  pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu"
            ) from exc

        self._torch = torch
        weights = models.ResNet18_Weights.IMAGENET1K_V1
        model = models.resnet18(weights=weights)
        model.fc = torch.nn.Identity()  # 분류층 제거 -> 512차원 특징
        model.eval()
        self._model = model
        self._transform = transforms.Compose(
            [
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
                ),
            ]
        )
        self.batch_size = batch_size

    def encode_paths(self, paths: list[Path]) -> np.ndarray:
        from PIL import Image

        out = []
        for start in range(0, len(paths), self.batch_size):
            batch_paths = paths[start : start + self.batch_size]
            tensors = []
            for path in batch_paths:
                with Image.open(path) as img:
                    tensors.append(self._transform(img.convert("RGB")))
            batch = self._torch.stack(tensors)
            with self._torch.no_grad():
                out.append(self._model(batch).cpu().numpy())
        return np.vstack(out).astype(np.float32)


class HistogramEncoder(Encoder):
    """색·밝기 히스토그램. Pillow 와 numpy 만 있으면 동작합니다.

    **딥러닝이 아닙니다.** TensorFlow 나 PyTorch 를 설치하기 전에
    임베딩 → 저장 → 추천으로 이어지는 배관이 제대로 도는지 확인하는 용도입니다.
    추천 품질을 기대하지 마시고, 실제 서비스에는 autoencoder 나 resnet 을 쓰세요.

    구성: RGB 채널별 32빈 히스토그램(96) + 4x4 격자 평균 밝기(16) = 112차원.
    """

    name = "histogram"
    dim = 112

    def __init__(self, bins: int = 32, grid: int = 4, batch_size: int = 32):
        self.bins = bins
        self.grid = grid
        self.dim = bins * 3 + grid * grid

    def _encode_one(self, path: Path) -> np.ndarray:
        from PIL import Image

        with Image.open(path) as img:
            rgb = np.asarray(img.convert("RGB").resize((128, 128)), dtype=np.float32) / 255.0

        parts = [
            np.histogram(rgb[:, :, c], bins=self.bins, range=(0.0, 1.0), density=True)[0]
            for c in range(3)
        ]
        gray = rgb.mean(axis=2)
        cell = gray.shape[0] // self.grid
        parts.append(
            np.array(
                [
                    gray[r * cell : (r + 1) * cell, c * cell : (c + 1) * cell].mean()
                    for r in range(self.grid)
                    for c in range(self.grid)
                ]
            )
        )
        return np.concatenate(parts).astype(np.float32)

    def encode_paths(self, paths: list[Path]) -> np.ndarray:
        return np.vstack([self._encode_one(p) for p in paths])


BACKENDS = {
    "autoencoder": AutoencoderEncoder,
    "resnet": ResNetEncoder,
    "histogram": HistogramEncoder,  # 배관 점검용 (딥러닝 아님)
}


def build_encoder(backend: str, **kwargs) -> Encoder:
    if backend not in BACKENDS:
        raise ValueError(
            f"알 수 없는 백엔드 '{backend}'. 사용 가능: {', '.join(BACKENDS)}"
        )
    return BACKENDS[backend](**kwargs)
