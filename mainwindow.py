"""主窗口：拖放图片、页面设置、实时预览与打印。"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QMarginsF, QSizeF, Qt
from PySide6.QtGui import (
    QColor,
    QIcon,
    QImage,
    QPainter,
    QPageLayout,
    QPageSize,
    QPixmap,
)
from PySide6.QtPrintSupport import QPrintDialog, QPrintPreviewDialog, QPrinter
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from image_store import ImageItem, ImageStore, read_image_info, supported_image_extensions
from layout_engine import PageLayout, compute_layout
from page_settings import CUSTOM_PAPER, MM_TO_PT, PAPER_SIZES_MM, PageSettings
from preview_widget import PreviewView, update_preview
from renderer import draw_page

ORDER_ORIGINAL = "拖入顺序"
ORDER_RATIO_ASC = "宽高比（从小到大）"
ORDER_RATIO_DESC = "宽高比（从大到小）"

_EXTENSIONS = supported_image_extensions()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("图片排版打印工具")
        self.resize(1200, 780)

        self.settings = PageSettings()
        self.images: List[ImageItem] = []
        self.store = ImageStore(max_images=64)
        self.pages: List[PageLayout] = []

        self.setAcceptDrops(True)
        self._build_ui()
        self._wire_signals()
        self._rebuild()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        # 预览视图最先创建，供工具栏动作连接信号
        self._view = PreviewView()

        toolbar = QToolBar("主工具栏", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        act_add = toolbar.addAction("添加图片")
        act_add.triggered.connect(self._choose_files)
        act_remove = toolbar.addAction("移除选中")
        act_remove.triggered.connect(self._remove_selected)
        act_clear = toolbar.addAction("清空")
        act_clear.triggered.connect(self._clear_images)
        toolbar.addSeparator()
        act_fit = toolbar.addAction("适应窗口")
        act_fit.triggered.connect(self._view.fit_all)
        act_100 = toolbar.addAction("100%")
        act_100.triggered.connect(self._view.reset_zoom)
        toolbar.addSeparator()
        act_preview = toolbar.addAction("打印预览")
        act_preview.triggered.connect(self._print_preview)
        act_print = toolbar.addAction("打印…")
        act_print.triggered.connect(self._print)

        # ---- 左侧：图片列表 + 设置面板 ----
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.setSpacing(6)
        left.setFixedWidth(360)

        list_group = QGroupBox("图片（拖拽图片到此窗口，可在列表中拖动排序）")
        list_layout = QVBoxLayout(list_group)
        self._image_list = QListWidget()
        self._image_list.setSelectionMode(QListWidget.ExtendedSelection)
        self._image_list.setDragDropMode(QListWidget.InternalMove)
        self._image_list.setIconSize(self._image_list.iconSize())
        self._image_list.setToolTip("支持拖动调整顺序；Delete 键删除选中项")
        self._image_list.setMinimumHeight(160)
        list_layout.addWidget(self._image_list)
        left_layout.addWidget(list_group, stretch=3)

        # 页面设置
        page_group = QGroupBox("页面设置")
        page_form = QFormLayout(page_group)
        self._paper_combo = QComboBox()
        self._paper_combo.addItems(list(PAPER_SIZES_MM.keys()))
        self._paper_combo.setCurrentText(self.settings.paper_name)
        self._orientation_combo = QComboBox()
        self._orientation_combo.addItems(["纵向", "横向"])
        self._custom_w = self._make_spin(10, 1000, self.settings.custom_width_mm, " mm")
        self._custom_h = self._make_spin(10, 1000, self.settings.custom_height_mm, " mm")
        self._margin_t = self._make_spin(0, 100, self.settings.margin_top_mm, " mm")
        self._margin_b = self._make_spin(0, 100, self.settings.margin_bottom_mm, " mm")
        self._margin_l = self._make_spin(0, 100, self.settings.margin_left_mm, " mm")
        self._margin_r = self._make_spin(0, 100, self.settings.margin_right_mm, " mm")
        page_form.addRow("纸张：", self._paper_combo)
        page_form.addRow("方向：", self._orientation_combo)
        page_form.addRow("自定义宽：", self._custom_w)
        page_form.addRow("自定义高：", self._custom_h)
        page_form.addRow("上边距：", self._margin_t)
        page_form.addRow("下边距：", self._margin_b)
        page_form.addRow("左边距：", self._margin_l)
        page_form.addRow("右边距：", self._margin_r)
        left_layout.addWidget(page_group)

        # 间距
        gap_group = QGroupBox("间距")
        gap_form = QFormLayout(gap_group)
        self._gap_h = self._make_spin(0, 100, self.settings.gap_mm, " mm")
        self._gap_v = self._make_spin(0, 100, self.settings.gap_v_mm, " mm")
        gap_form.addRow("图片间距：", self._gap_h)
        gap_form.addRow("行间距：", self._gap_v)
        left_layout.addWidget(gap_group)

        # 边框
        border_group = QGroupBox("边框")
        border_form = QFormLayout(border_group)
        self._border_check = QCheckBox("启用边框")
        self._border_width = self._make_spin(0.5, 20, self.settings.border_width_pt, " pt")
        self._border_color_btn = QPushButton()
        border_form.addRow("", self._border_check)
        border_form.addRow("宽度：", self._border_width)
        border_form.addRow("颜色：", self._border_color_btn)
        left_layout.addWidget(border_group)

        # 排序
        order_group = QGroupBox("排列")
        order_form = QFormLayout(order_group)
        self._order_combo = QComboBox()
        self._order_combo.addItems([ORDER_ORIGINAL, ORDER_RATIO_ASC, ORDER_RATIO_DESC])
        order_form.addRow("顺序：", self._order_combo)
        left_layout.addWidget(order_group)
        left_layout.addStretch(1)

        # 右侧：预览
        preview_group = QGroupBox("实时预览")
        preview_layout = QVBoxLayout(preview_group)
        self._status_label = QLabel()
        preview_layout.addWidget(self._view)
        preview_layout.addWidget(self._status_label)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(preview_group)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([360, 840])
        self.setCentralWidget(splitter)

    @staticmethod
    def _make_spin(min_v: float, max_v: float, value: float, suffix: str) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(min_v, max_v)
        sp.setValue(value)
        sp.setSingleStep(1.0 if min_v >= 1 else 0.1)
        sp.setDecimals(1)
        sp.setSuffix(suffix)
        return sp

    # ------------------------------------------------------------------
    # 信号连接
    # ------------------------------------------------------------------
    def _wire_signals(self) -> None:
        for w in (
            self._paper_combo, self._orientation_combo, self._custom_w,
            self._custom_h, self._margin_t, self._margin_b, self._margin_l,
            self._margin_r, self._gap_h, self._gap_v, self._border_width,
            self._border_check, self._order_combo,
        ):
            if isinstance(w, QComboBox):
                w.currentTextChanged.connect(lambda *_: self._rebuild())
            elif isinstance(w, (QDoubleSpinBox,)):
                w.valueChanged.connect(lambda *_: self._rebuild())
            else:
                w.toggled.connect(lambda *_: self._rebuild())

        self._paper_combo.currentTextChanged.connect(self._on_paper_changed)
        self._border_color_btn.clicked.connect(self._pick_border_color)
        self._image_list.model().rowsMoved.connect(self._on_list_reordered)
        self._image_list.itemSelectionChanged.connect(self._update_status)

    # ------------------------------------------------------------------
    # 图片管理
    # ------------------------------------------------------------------
    def _on_paper_changed(self, name: str) -> None:
        is_custom = name == CUSTOM_PAPER
        self._custom_w.setEnabled(is_custom)
        self._custom_h.setEnabled(is_custom)

    def _choose_files(self) -> None:
        exts = " ".join(f"*.{e}" for e in sorted(_EXTENSIONS))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", "", f"图片文件 ({exts});;所有文件 (*)",
        )
        self._add_paths(paths)

    def _add_paths(self, paths: List[str]) -> None:
        added = 0
        for p in paths:
            if not p:
                continue
            info = read_image_info(p)
            if info is None:
                QMessageBox.warning(self, "无法读取", f"无法读取图片：{p}")
                continue
            self.images.append(info)
            added += 1
        if added:
            self._refresh_list()
            self._rebuild()

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self._image_list.selectedItems()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.images):
                del self.images[r]
        self._refresh_list()
        self._rebuild()

    def _clear_images(self) -> None:
        self.images.clear()
        self.store.clear()
        self._refresh_list()
        self._rebuild()

    def _refresh_list(self) -> None:
        self._image_list.blockSignals(True)
        self._image_list.clear()
        for i, item in enumerate(self.images):
            li = QListWidgetItem()
            li.setText(f"{i + 1}. {item.name}  ({item.width}×{item.height})")
            li.setData(Qt.UserRole, i)
            img = self.store.load(item.path)
            if img and not img.isNull():
                pm = QPixmap.fromImage(img).scaledToHeight(36, Qt.SmoothTransformation)
                li.setIcon(QIcon(pm))
            li.setToolTip(item.path)
            self._image_list.addItem(li)
        self._image_list.blockSignals(False)
        self._update_status()

    def _on_list_reordered(self, *_args) -> None:
        new_order: List[ImageItem] = []
        for row in range(self._image_list.count()):
            idx = self._image_list.item(row).data(Qt.UserRole)
            if isinstance(idx, int) and 0 <= idx < len(self.images):
                new_order.append(self.images[idx])
        if len(new_order) == len(self.images):
            self.images = new_order
        self._refresh_list()
        self._rebuild()

    # ------------------------------------------------------------------
    # 拖放
    # ------------------------------------------------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths: List[str] = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if not local:
                continue
            suffix = Path(local).suffix.lower().lstrip(".")
            if suffix in _EXTENSIONS:
                paths.append(local)
            elif Path(local).is_dir():
                for f in sorted(Path(local).iterdir()):
                    if f.is_file() and f.suffix.lower().lstrip(".") in _EXTENSIONS:
                        paths.append(str(f))
        if paths:
            self._add_paths(paths)
        event.acceptProposedAction()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self._remove_selected()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # 排版与预览
    # ------------------------------------------------------------------
    def _provider(self, index: int) -> Optional[QImage]:
        if 0 <= index < len(self.images):
            return self.store.load(self.images[index].path)
        return None

    def _rebuild(self) -> None:
        self._sync_settings_from_ui()

        if not self.images:
            self.pages = []
            update_preview(self._view, [], self.settings, self._provider)
            self._update_status()
            return

        aspects = [(i, item.ratio) for i, item in enumerate(self.images)]
        order = self._order_combo.currentText()
        if order == ORDER_RATIO_ASC:
            aspects.sort(key=lambda t: t[1])
        elif order == ORDER_RATIO_DESC:
            aspects.sort(key=lambda t: t[1], reverse=True)

        aw, ah = self.settings.available_pt()
        gap_x = self.settings.gap_mm * MM_TO_PT
        gap_y = self.settings.gap_v_mm * MM_TO_PT

        self.pages = compute_layout(aspects, aw, ah, gap_x, gap_y)
        update_preview(self._view, self.pages, self.settings, self._provider)
        self._update_status()

    def _sync_settings_from_ui(self) -> None:
        s = self.settings
        s.paper_name = self._paper_combo.currentText()
        s.custom_width_mm = self._custom_w.value()
        s.custom_height_mm = self._custom_h.value()
        s.landscape = self._orientation_combo.currentText() == "横向"
        s.margin_top_mm = self._margin_t.value()
        s.margin_bottom_mm = self._margin_b.value()
        s.margin_left_mm = self._margin_l.value()
        s.margin_right_mm = self._margin_r.value()
        s.gap_mm = self._gap_h.value()
        s.gap_v_mm = self._gap_v.value()
        s.border_enabled = self._border_check.isChecked()
        s.border_width_pt = self._border_width.value()

    def _update_status(self) -> None:
        total_px = len(self.images)
        if total_px == 0:
            self._status_label.setText("未载入图片")
            return
        selected = len(self._image_list.selectedItems())
        page_word = f"{len(self.pages)} 页" if self.pages else "排版中…"
        self._status_label.setText(
            f"共 {total_px} 张图片（选中 {selected}） · {page_word} · "
            f"页面 {self.settings.paper_name} · "
            f"间距 {self.settings.gap_mm:.1f} mm"
        )

    # ------------------------------------------------------------------
    # 打印
    # ------------------------------------------------------------------
    def _configure_printer(self, printer: QPrinter) -> None:
        printer.setResolution(300)
        printer.setFullPage(True)
        w_mm, h_mm = self.settings.paper_size_mm()
        printer.setPageSize(QPageSize(QSizeF(w_mm, h_mm), QPageSize.Millimeter))
        layout = QPageLayout(printer.pageLayout())
        # PySide6 6.11：边距单位通过 setUnits 指定，setMargins 不再接收单位参数
        layout.setUnits(QPageLayout.Millimeter)
        layout.setMargins(
            QMarginsF(
                self.settings.margin_left_mm,
                self.settings.margin_top_mm,
                self.settings.margin_right_mm,
                self.settings.margin_bottom_mm,
            )
        )
        printer.setPageLayout(layout)

    def _paint_pages(self, printer: QPrinter) -> None:
        """把全部页面画到打印机上（打印预览回调与直接打印共用）。"""
        if not self.pages:
            return
        painter = QPainter(printer)
        scale = printer.resolution() / 72.0
        for i, page in enumerate(self.pages):
            if i > 0:
                printer.newPage()
            draw_page(painter, page, self.settings, self._provider, scale)
        painter.end()

    def _print_preview(self) -> None:
        if not self.pages:
            QMessageBox.information(self, "提示", "当前没有可排版的内容。")
            return
        printer = QPrinter(QPrinter.HighResolution)
        self._configure_printer(printer)
        dialog = QPrintPreviewDialog(printer, self)
        dialog.setWindowTitle("打印预览")
        dialog.paintRequested.connect(self._paint_pages)
        dialog.exec()

    def _print(self) -> None:
        if not self.pages:
            QMessageBox.information(self, "提示", "当前没有可排版的内容。")
            return
        printer = QPrinter(QPrinter.HighResolution)
        self._configure_printer(printer)
        dialog = QPrintDialog(printer, self)
        if dialog.exec() == QDialog.Accepted:
            self._paint_pages(printer)

    # ------------------------------------------------------------------
    # 边框颜色
    # ------------------------------------------------------------------
    def _pick_border_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.settings.border_color_hex), self, "选择边框颜色")
        if color.isValid():
            self.settings.border_color_hex = color.name()
            self._update_border_button()
            self._rebuild()

    def _update_border_button(self) -> None:
        color = QColor(self.settings.border_color_hex)
        self._border_color_btn.setText(color.name())
        self._border_color_btn.setStyleSheet(
            f"background-color:{color.name()}; color: {'#ffffff' if color.lightness() < 128 else '#000000'};"
        )
