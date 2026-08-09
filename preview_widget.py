"""实时预览控件：基于 QGraphicsView，支持滚轮缩放、拖拽平移与双击适应。"""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

from layout_engine import PageLayout
from page_settings import PageSettings
from renderer import draw_page

# 预览渲染使用的像素密度（每英寸像素数）。72dpi 下 1pt = 1px，
# 这里取 96 只是让预览页在屏幕上显得更大、更接近 100% 视觉。
PREVIEW_DPI = 96


class PreviewView(QGraphicsView):
    """预览视图。滚轮缩放、左键拖拽平移、双击适应窗口。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor(0x37, 0x3B, 0x40))

    def fit_all(self) -> None:
        """缩放以显示全部页面。"""
        rect = self._scene.itemsBoundingRect()
        if not rect.isEmpty():
            self.fitInView(rect, Qt.KeepAspectRatio)

    def reset_zoom(self) -> None:
        """重置为 1:1 显示（按预览渲染分辨率）。"""
        self.resetTransform()

    def wheelEvent(self, event):
        factor = 1.1 if event.angleDelta().y() > 0 else 1 / 1.1
        self.scale(factor, factor)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.fit_all()
        event.accept()


def render_page_pixmap(
    page: PageLayout,
    settings: PageSettings,
    provider,
    scale: float,
) -> QPixmap:
    """把一页离屏渲染成 QPixmap，供预览场景显示。"""
    pw, ph = settings.page_size_pt()
    px_w = max(1, int(pw * scale))
    px_h = max(1, int(ph * scale))
    pm = QPixmap(px_w, px_h)
    pm.fill(Qt.white)
    painter = QPainter(pm)
    try:
        draw_page(painter, page, settings, provider, scale)
    finally:
        painter.end()
    return pm


def update_preview(
    view: PreviewView,
    pages: List[PageLayout],
    settings: PageSettings,
    provider,
) -> None:
    """把多页排版结果渲染进预览场景。"""
    scene = view._scene
    scene.clear()

    if not pages:
        hint = scene.addText("拖入图片开始排版…", QFont("Microsoft YaHei", 18))
        hint.setDefaultTextColor(QColor("#9aa0a6"))
        hint.setPos(24, 24)
        return

    scale = PREVIEW_DPI / 72.0
    pad = 28
    y = pad
    for page in pages:
        pm = render_page_pixmap(page, settings, provider, scale)
        item = QGraphicsPixmapItem(pm)
        item.setPos(pad, y)
        scene.addItem(item)
        y += pm.height() + pad

    view.fit_all()
