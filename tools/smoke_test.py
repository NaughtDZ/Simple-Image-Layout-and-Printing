"""离屏 GUI 冒烟测试：不显示窗口，验证从载入到渲染的完整链路。

运行：
    ./venv/Scripts/python.exe tools/smoke_test.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from layout_engine import compute_layout
from page_settings import PageSettings
from preview_widget import render_page_pixmap, update_preview
from renderer import draw_page


def make_test_images(tmp: Path, count: int) -> list[str]:
    """生成多张不同尺寸、不同颜色的 PNG 测试图。"""
    paths = []
    sizes = [(640, 480), (300, 500), (800, 300), (500, 500), (1200, 800),
             (400, 900), (700, 700), (350, 250), (1000, 400), (450, 650)]
    for i in range(count):
        w, h = sizes[i % len(sizes)]
        img = QImage(w, h, QImage.Format_RGB32)
        img.fill(QColor(i * 20 % 255, (i * 60) % 255, (i * 110) % 255))
        p = QPainter(img)
        p.setPen(Qt.white)
        p.drawText(QRectF(0, 0, w, h), f"img {i} {w}x{h}")
        p.end()
        path = str(tmp / f"test_{i}.png")
        assert img.save(path), f"保存测试图失败: {path}"
        paths.append(path)
    return paths


def main() -> int:
    app = QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        paths = make_test_images(tmp, 15)

        # 1) 载入图片信息
        from image_store import ImageItem, read_image_info
        items = [read_image_info(p) for p in paths]
        assert all(i is not None for i in items), "读取图片信息失败"
        items = [i for i in items if i]
        print(f"[OK] 读取 {len(items)} 张图片信息")

        # 2) 排版
        settings = PageSettings()
        aw, ah = settings.available_pt()
        gap_x = settings.gap_mm * (72.0 / 25.4)
        gap_y = settings.gap_v_mm * (72.0 / 25.4)
        aspects = [(i, it.ratio) for i, it in enumerate(items)]
        pages = compute_layout(aspects, aw, ah, gap_x, gap_y)
        assert pages and sum(len(p.images) for p in pages) == len(items)
        print(f"[OK] 排版 {len(pages)} 页, 共 {len(items)} 张")
        for pi, pg in enumerate(pages):
            print(f"      第{pi+1}页 {len(pg.images)} 张, 利用率 {pg.content_h/ah*100:.0f}%")

        # 3) 预览渲染（离屏）
        store = {it.path: it for it in items}
        from image_store import ImageStore
        istore = ImageStore(max_images=16)

        def provider(idx: int):
            return istore.load(items[idx].path)

        pm = render_page_pixmap(pages[0], settings, provider, 96.0 / 72.0)
        assert not pm.isNull()
        print(f"[OK] 预览渲染 {pm.width()}x{pm.height()} px")

        # 4) 预览视图场景更新（使用虚拟视图）
        from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QWidget
        from preview_widget import PreviewView
        view = PreviewView()
        update_preview(view, pages, settings, provider)
        assert view._scene.itemsBoundingRect().isValid()
        print(f"[OK] 预览场景更新, 场景范围 {view._scene.itemsBoundingRect().width():.0f}x{view._scene.itemsBoundingRect().height():.0f}")

        # 5) 模拟打印：绘制到 QImage（按打印机 300dpi 逻辑缩放）
        pw, ph = settings.page_size_pt()
        scale = 300.0 / 72.0
        out = QImage(int(pw * scale), int(ph * scale), QImage.Format_RGB32)
        out.fill(Qt.white)
        painter = QPainter(out)
        draw_page(painter, pages[0], settings, provider, scale)
        painter.end()
        assert not out.isNull()
        # 抽样检查页面非纯白（有内容）
        assert out.pixelColor(int(out.width() * 0.5), int(out.height() * 0.5)) != QColor(Qt.white)
        print(f"[OK] 打印绘制 {out.width()}x{out.height()}px (300dpi)")

    print("\n=== 冒烟测试全部通过 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
