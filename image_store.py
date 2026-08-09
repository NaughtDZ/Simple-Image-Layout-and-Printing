"""图片信息读取与解码缓存。"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize
from PySide6.QtGui import QImage, QImageIOHandler, QImageReader


@dataclass
class ImageItem:
    """一张待排版的图片（仅元信息，不持有解码数据）。"""

    path: str
    name: str
    width: int
    height: int

    @property
    def ratio(self) -> float:
        """宽高比 w / h。"""
        if self.height == 0:
            return 1.0
        return self.width / self.height


class ImageStore:
    """按路径缓存解码后的 QImage（LRU，限制张数，避免大图撑爆内存）。"""

    def __init__(self, max_images: int = 64):
        self._cache: OrderedDict[str, QImage] = OrderedDict()
        self._max = max_images

    def load(self, path: str) -> Optional[QImage]:
        """读取（或从缓存取回）某路径的完整图像，自动应用 EXIF 旋转。"""
        if path in self._cache:
            img = self._cache.pop(path)
            self._cache[path] = img  # 移到队尾（最近使用）
            return img

        reader = QImageReader(path)
        reader.setAutoTransform(True)
        img = reader.read()
        if img.isNull():
            return None

        self._cache[path] = img
        while len(self._cache) > self._max:
            self._cache.popitem(last=False)
        return img

    def clear(self) -> None:
        self._cache.clear()


def read_image_info(path: str) -> Optional[ImageItem]:
    """快速读取图片尺寸（只解析文件头，不解码全部像素），并处理 EXIF 旋转。"""
    reader = QImageReader(path)
    if not reader.canRead():
        return None
    size = reader.size()
    if size.isNull() or size.width() <= 0 or size.height() <= 0:
        return None

    tf = reader.transformation()
    if tf in (
        QImageIOHandler.Transformation.TransformationRotate90,
        QImageIOHandler.Transformation.TransformationRotate270,
    ):
        size = QSize(size.height(), size.width())

    name = Path(path).name
    return ImageItem(path=path, name=name, width=size.width(), height=size.height())


def supported_image_extensions() -> set[str]:
    """返回 Qt 支持的图片扩展名集合（小写，无点号）。"""
    ext = set()
    for fmt in QImageReader.supportedImageFormats():
        try:
            ext.add(bytes(fmt).decode("ascii").lower())
        except (UnicodeDecodeError, TypeError):
            continue
    return ext
