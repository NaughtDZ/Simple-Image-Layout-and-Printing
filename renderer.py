"""把排版结果绘制到 QPainter（预览与打印共用同一套绘制逻辑）。"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

from layout_engine import PageLayout
from page_settings import PageSettings

ImageProvider = Callable[[int], Optional[QImage]]


def _contain_rect(area: QRectF, iw: int, ih: int) -> QRectF:
    """把 (iw, ih) 的图片等比缩放到 area 内并居中，返回目标矩形。"""
    if iw <= 0 or ih <= 0 or area.isEmpty():
        return area
    scale = min(area.width() / iw, area.height() / ih)
    w = iw * scale
    h = ih * scale
    return QRectF(
        area.x() + (area.width() - w) / 2.0,
        area.y() + (area.height() - h) / 2.0,
        w,
        h,
    )


def draw_page(
    painter: QPainter,
    page: PageLayout,
    settings: PageSettings,
    provider: ImageProvider,
    scale: float = 1.0,
) -> None:
    """绘制一页。

    :param painter: 目标画笔（预览的 QPixmap 或打印机的 QPainter）
    :param page: 排版结果
    :param settings: 页面设置（含边框、边距）
    :param provider: 按图片下标返回 QImage 的回调
    :param scale: 逻辑放大倍数（打印高分辨率时 >1，用于把 pt 映射为设备像素）
    """
    pw, ph = settings.page_size_pt()
    _, _, ml, mt = settings.margins_pt()

    painter.save()
    painter.scale(scale, scale)

    # 页面背景（白色纸张）
    painter.fillRect(QRectF(0, 0, pw, ph), Qt.white)

    border_qcolor = QColor(settings.border_color_hex) if settings.border_enabled else QColor(0, 0, 0)

    for placed in page.images:
        cell = QRectF(ml + placed.x, mt + placed.y, placed.w, placed.h)
        img = provider(placed.index)
        if img is None or img.isNull():
            continue

        # 若启用边框，图片向四周缩进，把边框让出来
        b = settings.border_width_pt if settings.border_enabled else 0.0
        area = cell.adjusted(b, b, -b, -b)
        target = _contain_rect(area, img.width(), img.height())

        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawImage(target, img)

        if settings.border_enabled and b > 0:
            painter.setPen(QPen(border_qcolor, b, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(target)

    painter.restore()
