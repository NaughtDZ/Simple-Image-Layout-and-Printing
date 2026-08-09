"""图片排版引擎。

算法（v2：目标行数 + 均匀切段，稳定且能铺满页面）
------------------------------------------------
1. 选定一个"目标行数 r"：行数越多，每行分配的图片越少、行越高，图片越大。
2. 把图片按宽高比"均匀切成 r 段"，每段作为一行；行与行之间保留顺序。
3. 每一行的行高 h_i = (可用宽度 - 行内间距) / 该行宽高比总和，
   因此**每一行都恰好满宽**，行内图片等比缩放、无裁切。
4. 总占用高度 T(r) 随 r 单调递增；用二分找**使整组图片放得下页面的最大 r**，
   也就是让图片尽量大、页面尽量铺满。
5. 按序把各行填入页面，超过页面高度则自动分页（每一页也尽量满）。

坐标系：所有尺寸单位为磅（pt，1/72 英寸）。坐标原点为页面“可用区域”
（即扣掉四周边距之后）的左上角。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Tuple

AspectItem = Tuple[int, float]  # (原始下标, 宽高比 w/h)


@dataclass
class PlacedImage:
    """排版结果中的一张图片。"""

    index: int   # 图片在原始列表中的下标
    x: float     # 可用区域内的左上角 X（pt）
    y: float     # 可用区域内的左上角 Y（pt）
    w: float     # 宽度（pt）
    h: float     # 高度（pt）
    ratio: float # 宽高比 w / h


@dataclass
class PageLayout:
    """一页的排版结果。"""

    images: List[PlacedImage]
    content_h: float  # 本页内容实际占用高度（pt）


def _row_height(row: Sequence[AspectItem], available_w: float, gap_x: float) -> float:
    """使该行恰好满宽所需的行高（pt）。"""
    total_aspect = sum(r for _, r in row)
    if total_aspect <= 0:
        return available_w
    return (available_w - (len(row) - 1) * gap_x) / total_aspect


def _split_rows(aspects: Sequence[AspectItem], rows_target: int) -> List[List[AspectItem]]:
    """把图片按宽高比均匀切成 rows_target 段，保持原始顺序。

    每段的宽高比总和尽量接近 total / rows_target，从而让各行高度接近，
    视觉上更整齐。切分仅在极端情况下才会触发行数修正。
    """
    n = len(aspects)
    if rows_target >= n:
        return [[a] for a in aspects]
    if rows_target <= 1:
        return [list(aspects)]

    total = sum(r for _, r in aspects)
    per = total / rows_target
    cuts = [k * per for k in range(1, rows_target)]

    rows: List[List[AspectItem]] = []
    cur: List[AspectItem] = []
    cur_sum = 0.0
    ci = 0
    for item in aspects:
        cur.append(item)
        cur_sum += item[1]
        while ci < len(cuts) and cur_sum >= cuts[ci]:
            # 避免切出空段或剩余不足
            if len(cur) >= 1 and n - sum(len(x) for x in rows) - len(cur) >= len(cuts) - ci:
                rows.append(cur)
                cur = []
                cur_sum = 0.0
                ci += 1
            else:
                break
    if cur:
        rows.append(cur)

    # 行数修正（正常情况下不会走到这里）
    while len(rows) > rows_target:
        merged = rows.pop()
        rows[-1] = rows[-1] + merged
    while len(rows) < rows_target:
        mx = max(range(len(rows)), key=lambda i: sum(r for _, r in rows[i]))
        seg = rows[mx]
        if len(seg) < 2:
            break
        half = len(seg) // 2
        rows = rows[:mx] + [seg[:half], seg[half:]] + rows[mx + 1:]
    return rows


def _total_height(
    aspects: Sequence[AspectItem],
    rows_target: int,
    available_w: float,
    gap_x: float,
    gap_y: float,
) -> float:
    """估算把整组图片排成 rows_target 行时的总占用高度（pt）。"""
    rows = _split_rows(aspects, rows_target)
    h_sum = sum(_row_height(row, available_w, gap_x) for row in rows)
    return h_sum + (len(rows) - 1) * gap_y


def _best_row_count(
    aspects: Sequence[AspectItem],
    available_w: float,
    available_h: float,
    gap_x: float,
    gap_y: float,
) -> int:
    """二分求"整组图片能放下一页"的最大行数（图片最大、页面最满）。"""
    lo, hi = 1, len(aspects)
    best = 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if _total_height(aspects, mid, available_w, gap_x, gap_y) <= available_h + 0.5:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def compute_layout(
    aspects: Sequence[AspectItem],
    available_w: float,
    available_h: float,
    gap_x: float,
    gap_y: float,
) -> List[PageLayout]:
    """计算完整排版。

    :param aspects: 图片列表，元素为 (index, 宽高比 w/h)
    :param available_w: 可用宽度（pt）
    :param available_h: 可用高度（pt）
    :param gap_x: 行内图片间距（pt）
    :param gap_y: 行间间距（pt）
    :return: 若干页的排版结果，页内坐标基于可用区域左上角
    """
    if not aspects or available_w <= 1.0 or available_h <= 1.0:
        return []

    r = _best_row_count(aspects, available_w, available_h, gap_x, gap_y)
    rows = _split_rows(aspects, r)

    # 按序装页
    page_groups: List[List[Tuple[List[AspectItem], float]]] = []
    page_rows: List[Tuple[List[AspectItem], float]] = []
    used = 0.0
    for row in rows:
        h = _row_height(row, available_w, gap_x)
        if h > available_h:
            # 极端超宽图导致单行超高：单独一页并缩放到页面高度
            h = available_h
            if page_rows:
                page_groups.append(page_rows)
                page_rows, used = [], 0.0
        elif page_rows and used + h > available_h:
            page_groups.append(page_rows)
            page_rows, used = [], 0.0
        page_rows.append((row, h))
        used += h + gap_y
    if page_rows:
        page_groups.append(page_rows)

    # 生成每张图片的精确目标矩形
    result: List[PageLayout] = []
    for group in page_groups:
        placed: List[PlacedImage] = []
        y = 0.0
        for row, row_h in group:
            row_aspect = sum(r for _, r in row)
            if row_h >= available_h and row_aspect * row_h > available_w:
                # 单行超高且超宽：水平居中摆放
                x = (available_w - row_aspect * row_h) / 2.0
            else:
                x = 0.0
            for idx, r in row:
                placed.append(PlacedImage(index=idx, x=x, y=y,
                                          w=r * row_h, h=row_h, ratio=r))
                x += r * row_h + gap_x
            y += row_h + gap_y
        content_h = (y - gap_y) if placed else 0.0
        result.append(PageLayout(images=placed, content_h=content_h))
    return result
