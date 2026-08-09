"""页面设置：纸张、方向、边距、间距与边框。"""

from __future__ import annotations

from dataclasses import dataclass

# 1 毫米对应的磅数（pt，1/72 英寸）
MM_TO_PT = 72.0 / 25.4

# 纸张名称 -> (宽 mm, 高 mm)，纵向基准
PAPER_SIZES_MM: dict[str, tuple[float, float]] = {
    "A3": (297, 420),
    "A4": (210, 297),
    "A5": (148, 210),
    "B5": (176, 250),
    "Letter": (215.9, 279.4),
    "Legal": (215.9, 355.6),
    "自定义": (210.0, 297.0),
}

CUSTOM_PAPER = "自定义"


@dataclass
class PageSettings:
    """一次排版的全部设置。"""

    paper_name: str = "A4"
    custom_width_mm: float = 210.0
    custom_height_mm: float = 297.0
    landscape: bool = False

    margin_top_mm: float = 10.0
    margin_bottom_mm: float = 10.0
    margin_left_mm: float = 10.0
    margin_right_mm: float = 10.0

    gap_mm: float = 5.0      # 行内图片间距
    gap_v_mm: float = 5.0    # 行间间距

    border_enabled: bool = False
    border_width_pt: float = 1.5
    border_color_hex: str = "#333333"

    def paper_size_mm(self) -> tuple[float, float]:
        """返回 (宽, 高)，单位 mm，已按方向调整。"""
        w, h = PAPER_SIZES_MM[self.paper_name]
        if self.landscape:
            w, h = h, w
        return w, h

    def page_size_pt(self) -> tuple[float, float]:
        """返回页面尺寸，单位 pt。"""
        w, h = self.paper_size_mm()
        return w * MM_TO_PT, h * MM_TO_PT

    def available_pt(self) -> tuple[float, float]:
        """返回扣掉边距后的可用区域尺寸，单位 pt。"""
        pw, ph = self.page_size_pt()
        aw = pw - (self.margin_left_mm + self.margin_right_mm) * MM_TO_PT
        ah = ph - (self.margin_top_mm + self.margin_bottom_mm) * MM_TO_PT
        return max(aw, 1.0), max(ah, 1.0)

    def margins_pt(self) -> tuple[float, float, float, float]:
        """返回 (上, 下, 左, 右) 边距，单位 pt。"""
        return (
            self.margin_top_mm * MM_TO_PT,
            self.margin_bottom_mm * MM_TO_PT,
            self.margin_left_mm * MM_TO_PT,
            self.margin_right_mm * MM_TO_PT,
        )
