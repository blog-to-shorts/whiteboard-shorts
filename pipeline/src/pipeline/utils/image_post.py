"""생성 이미지 후처리.

whiteboard-animator는 '흰 배경 위의 잉크'를 선으로 따라 그린다.
이미지 모델이 거의 흰색(240~254)의 옅은 배경 얼룩이나 연한 회색·색을 섞으면
그 부분도 선으로 인식해 불필요한 획이 생기므로 미리 정리한다.
  - grayscale: 회색조로 변환 (흑백 화풍 유지, 컬러를 도입하면 끈다)
  - white_threshold: R·G·B가 모두 이 값 이상인 픽셀을 순백(255)으로 (0이면 끔)
"""
from pathlib import Path

import numpy as np
from PIL import Image


def postprocess(path: Path, grayscale: bool, white_threshold: int) -> None:
    if not grayscale and not white_threshold:
        return
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
    if grayscale:
        g = (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114).astype(np.int16)
        a = np.stack([g, g, g], axis=-1)
    if white_threshold:
        a[a.min(axis=-1) >= white_threshold] = 255
    Image.fromarray(a.clip(0, 255).astype("uint8")).save(path)