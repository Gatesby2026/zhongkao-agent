"""图片正立化（answer-card 流水线前置）。

手机拍的照片像素是横置的，靠 EXIF Orientation 标记告诉渲染器旋转；
但 qwen-vl-ocr / 腾讯云 / PIL 各自对 EXIF 处理不一致：
  - 腾讯云 OCR 内部按 EXIF 自动转正 → 返回正立坐标系 bbox
  - PIL Image.open 读**原始横置**像素，不应用 EXIF
  → bbox（正立系）套到横置像素上 → 裁切区域全错且方向歪
  → qwen-vl-ocr 看歪图 → 选择题涂卡识别错

对策：在进入任何 OCR / 裁切前，把图按 EXIF 真正旋转到位、烘焙进像素、
去掉 EXIF 标记，统一为正立 JPEG。已正立的图（无 EXIF）幂等不变。
"""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

try:                                  # HEIC 支持（iPhone 默认格式）
    import pillow_heif                # noqa
    pillow_heif.register_heif_opener()
    _HEIC_OK = True
except Exception:
    _HEIC_OK = False


def upright_image(src: Path) -> Image.Image:
    """打开任意图片，按 EXIF 旋转到位，返回 RGB PIL.Image（无 EXIF）。"""
    im = Image.open(src)
    im = ImageOps.exif_transpose(im)   # 关键：烘焙 EXIF 方向进像素
    if im.mode != "RGB":
        im = im.convert("RGB")
    return im


def normalize_bytes_to_upright_jpeg(raw: bytes, out_path: Path,
                                    max_dim: int = 3000,
                                    quality: int = 90) -> Path:
    """上传字节 → 正立 JPEG 落盘（去 EXIF，超大边缩放）。

    腾讯云 ImageBase64 ≤10MB / OCR 体验：限制最长边 ≤max_dim。
    """
    im = Image.open(io.BytesIO(raw))
    im = ImageOps.exif_transpose(im)
    if im.mode != "RGB":
        im = im.convert("RGB")
    w, h = im.size
    if max(w, h) > max_dim:
        s = max_dim / float(max(w, h))
        im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im.save(out_path, "JPEG", quality=quality)   # 不写 exif → 标记清除
    return out_path
