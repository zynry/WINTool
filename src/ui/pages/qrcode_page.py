# coding: utf-8
"""二维码解码页面。

支持拖拽上传、Ctrl+V 粘贴、文件选择批量导入，
使用 OpenCV QRCodeDetector 解码，结果可导出 Excel / CSV / TXT。
"""

from __future__ import annotations

import csv
import io
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import (
    QClipboard,
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QKeyEvent,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
)

from qfluentwidgets import (
    CaptionLabel,
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
    ToolButton,
    isDarkTheme,
    qconfig,
)

from ui.widgets.custom_widget import _Widget
from utils.resource_path import res

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget


# ── 数据模型 ──────────────────────────────────────────
@dataclass
class DecodeResult:
    uid: str         # 唯一标识（与 img_list item 对应）
    filename: str
    filepath: str
    content: str
    status: str  # "成功" / "未检测到" / "失败"


# ── 后台解码线程 ──────────────────────────────────────
class DecodeWorker(QThread):
    finished = Signal(list)  # list[tuple[str, DecodeResult]]  (uid, result)
    progress = Signal(int, int)  # current, total

    def __init__(self, tasks: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.tasks = tasks  # [(uid, filepath), ...]

    def run(self):
        results: list[tuple[str, DecodeResult]] = []
        detector = cv2.QRCodeDetector()

        def decode_one(task: tuple[str, str]) -> tuple[str, DecodeResult]:
            uid, fp = task
            fname = os.path.basename(fp)
            try:
                img = cv2.imread(fp, cv2.IMREAD_COLOR)
                if img is None:
                    return uid, DecodeResult(uid, fname, fp, "", "读取失败")

                # 尝试多码检测
                ok, decoded, _, _ = detector.detectAndDecodeMulti(img)
                if ok and decoded:
                    texts = [d for d in decoded if d]
                    if texts:
                        return uid, DecodeResult(uid, fname, fp, "\n".join(texts), "成功")

                # 回退单码检测
                data, _, _ = detector.detectAndDecode(img)
                if data:
                    return uid, DecodeResult(uid, fname, fp, data, "成功")

                return uid, DecodeResult(uid, fname, fp, "", "未检测到")
            except Exception as e:
                return uid, DecodeResult(uid, fname, fp, "", f"失败: {e}")

        total = len(self.tasks)
        with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as pool:
            for i, result in enumerate(pool.map(decode_one, self.tasks)):
                results.append(result)
                self.progress.emit(i + 1, total)

        self.finished.emit(results)


# ── 图片列表控件（支持拖拽+粘贴）───────────────────────
class ImageDropList(QListWidget):
    """支持文件拖拽和 Ctrl+V 粘贴的图片列表。"""

    filesDropped = Signal(list)  # list[tuple[str, str]]  (uid, filepath)
    itemsDeleted = Signal(list)  # list[str] 被删除的 uid 列表

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QPixmap(80, 80).size())
        self.setSpacing(8)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setDragEnabled(False)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
        if paths:
            self.filesDropped.emit(paths)
        event.acceptProposedAction()

    def keyPressEvent(self, event: QKeyEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_V:
            self._paste_from_clipboard()
        elif event.key() == Qt.Key.Key_Delete:
            self._delete_selected()
        else:
            super().keyPressEvent(event)

    def _paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        mime = clipboard.mimeData()
        if mime and mime.hasImage():
            img = clipboard.image()
            if not img.isNull():
                self._save_clipboard_image(img)
        elif mime and mime.hasUrls():
            paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
            if paths:
                tasks = [(str(uuid.uuid4()), p) for p in paths]
                self.filesDropped.emit(tasks)

    def _save_clipboard_image(self, img: QImage):
        """将剪贴板图片保存到临时文件并触发解码。"""
        from tempfile import gettempdir
        uid = str(uuid.uuid4())
        tmp_path = os.path.join(gettempdir(), f"qrcode_paste_{uid}.png")
        img.save(tmp_path)
        self.filesDropped.emit([(uid, tmp_path)])

    def _delete_selected(self):
        deleted_uids: list[str] = []
        for item in self.selectedItems():
            uid = item.data(Qt.ItemDataRole.UserRole)
            if uid:
                deleted_uids.append(uid)
            row = self.row(item)
            self.takeItem(row)
        if deleted_uids:
            self.itemsDeleted.emit(deleted_uids)


# ── 主页面 ────────────────────────────────────────────
class QRCodePage(_Widget):
    """二维码解码页面。"""

    def __init__(self, parent=None):
        super().__init__("QRCodePage", parent=parent)
        self._results: dict[str, DecodeResult] = {}
        self._worker: DecodeWorker | None = None
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 24, 16)
        main_layout.setSpacing(12)

        # ── 顶部控制栏 ────────────────────────────────
        control_layout = QHBoxLayout()
        control_layout.setSpacing(8)

        self.select_btn = PrimaryPushButton("选择图片", self)
        self.select_btn.setIcon(FluentIcon.FOLDER)
        control_layout.addWidget(self.select_btn)

        control_layout.addSpacing(12)

        self.export_combo = ComboBox(self)
        self.export_combo.addItems(["导出为...", "Excel (.xlsx)", "CSV (.csv)", "TXT (.txt)"])
        self.export_combo.setCurrentIndex(0)
        self.export_combo.setMinimumWidth(140)
        control_layout.addWidget(self.export_combo)

        self.clear_btn = ToolButton(FluentIcon.DELETE)
        self.clear_btn.setToolTip("清空列表")
        control_layout.addWidget(self.clear_btn)

        control_layout.addStretch()

        self.status_label = CaptionLabel("等待导入...", self)
        control_layout.addWidget(self.status_label)

        main_layout.addLayout(control_layout)

        # ── 左右分割器：图片列表 / 结果表格 ───────────
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # 左侧图片列表卡片
        self.img_frame = QFrame()
        self.img_frame.setObjectName("qrImgFrame")
        img_layout = QVBoxLayout(self.img_frame)
        img_layout.setContentsMargins(2, 2, 2, 2)
        img_layout.setSpacing(0)

        img_header = QFrame()
        img_header_layout = QHBoxLayout(img_header)
        img_header_layout.setContentsMargins(12, 8, 12, 6)
        img_header_layout.addWidget(CaptionLabel("图片列表 (支持拖拽 / Ctrl+V 粘贴)"))
        img_header_layout.addStretch()
        img_layout.addWidget(img_header)

        self.img_list = ImageDropList()
        img_layout.addWidget(self.img_list, stretch=1)

        self.splitter.addWidget(self.img_frame)

        # 右侧结果表格卡片
        self.result_frame = QFrame()
        self.result_frame.setObjectName("qrResultFrame")
        result_layout = QVBoxLayout(self.result_frame)
        result_layout.setContentsMargins(2, 2, 2, 2)
        result_layout.setSpacing(0)

        result_header = QFrame()
        result_header_layout = QHBoxLayout(result_header)
        result_header_layout.setContentsMargins(12, 8, 12, 6)
        result_header_layout.addWidget(CaptionLabel("解码结果"))
        result_header_layout.addStretch()
        result_layout.addWidget(result_header)

        self.result_table = QTableWidget(self)
        self.result_table.setColumnCount(3)
        self.result_table.setHorizontalHeaderLabels(["文件名", "解码内容", "状态"])
        self.result_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.result_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.result_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.result_table.setWordWrap(True)
        result_layout.addWidget(self.result_table, stretch=1)

        self.splitter.addWidget(self.result_frame)
        self.splitter.setSizes([350, 450])
        self.splitter.setHandleWidth(6)

        # 延迟应用样式，确保在 qfluentwidgets 全局样式表之后生效
        QTimer.singleShot(0, self._apply_all_styles)

        main_layout.addWidget(self.splitter, stretch=1)

    def _apply_all_styles(self):
        """根据当前主题统一应用所有样式。"""
        dark = isDarkTheme()

        # 卡片背景
        card_bg = "#252525" if dark else "#e8f4fc"
        card_border = "#333333" if dark else "#d0e6f0"
        # 列表/表格背景
        inner_bg = "#1e1e1e" if dark else "#ffffff"
        inner_fg = "#e0e0e0" if dark else "#333333"
        # 表头
        header_bg = "#2a2a2a" if dark else "#d6eaf8"
        header_fg = "#e0e0e0" if dark else "#333333"
        # Splitter handle
        handle_bg = "#444444" if dark else "#d0d0d0"

        # 卡片样式
        card_css = f"""
            QFrame#qrImgFrame, QFrame#qrResultFrame {{
                background-color: {card_bg} !important;
                border: 1px solid {card_border};
                border-radius: 10px;
            }}
        """
        self.img_frame.setStyleSheet(card_css)
        self.result_frame.setStyleSheet(card_css)

        # 图片列表样式
        list_css = f"""
            QListWidget {{
                color: {inner_fg} !important;
                background-color: {inner_bg} !important;
                border: none;
                padding: 8px;
            }}
            QListWidget::item {{
                color: {inner_fg} !important;
                background-color: transparent;
                border-radius: 6px;
                padding: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {'#3a3a3a' if dark else '#cce5ff'};
                border-radius: 6px;
            }}
        """
        self.img_list.setStyleSheet(list_css)

        # 表格样式
        table_css = f"""
            QTableWidget {{
                color: {inner_fg} !important;
                background-color: {inner_bg} !important;
                border: none;
                gridline-color: {'#333333' if dark else '#e0e0e0'};
            }}
            QHeaderView::section {{
                color: {header_fg} !important;
                background-color: {header_bg} !important;
                padding: 6px 10px;
                border: none;
                border-bottom: 1px solid {'#444444' if dark else '#d0d0d0'};
            }}
            QTableView QTableCornerButton::section {{
                background-color: {header_bg} !important;
                border: none;
            }}
            QTableWidget::item {{
                color: {inner_fg} !important;
                background-color: {inner_bg} !important;
                padding: 4px 8px;
            }}
            QTableWidget::item:selected {{
                background-color: {'#3a3a3a' if dark else '#cce5ff'};
            }}
        """
        self.result_table.setStyleSheet(table_css)

        # Splitter handle
        self.splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {handle_bg};
                width: 2px;
                margin: 40px 0px;
                border-radius: 1px;
            }}
        """)

    def _on_theme_changed(self, theme):
        QTimer.singleShot(0, self._apply_all_styles)

    def _connect_signals(self):
        self.select_btn.clicked.connect(self._on_select_files)
        self.img_list.filesDropped.connect(self._on_files_dropped)
        self.img_list.itemsDeleted.connect(self._on_items_deleted)
        self.export_combo.currentIndexChanged.connect(self._on_export)
        self.clear_btn.clicked.connect(self._on_clear)
        qconfig.themeChanged.connect(self._on_theme_changed)

    def _on_items_deleted(self, uids: list[str]):
        """图片列表删除后同步移除对应解码结果。"""
        removed = 0
        for uid in uids:
            if self._results.pop(uid, None):
                removed += 1
        self._refresh_table()
        self.status_label.setText(f"共 {self.img_list.count()} 张 | 已移除 {removed} 项")

    # ── 文件处理 ────────────────────────────────────

    def _on_select_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择二维码图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tiff);;所有文件 (*.*)",
        )
        if paths:
            tasks = [(str(uuid.uuid4()), p) for p in paths]
            self._add_images(tasks)

    def _on_files_dropped(self, tasks: list[tuple[str, str]]):
        self._add_images(tasks)

    def _add_images(self, tasks: list[tuple[str, str]]):
        """添加图片到列表并启动解码。"""
        valid_tasks: list[tuple[str, str]] = []
        for uid, p in tasks:
            ext = Path(p).suffix.lower()
            if ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff", ".tif"}:
                valid_tasks.append((uid, p))

        if not valid_tasks:
            InfoBar.warning(
                title="无有效图片",
                content="未找到支持的图片格式",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )
            return

        # 添加到列表并显示缩略图
        for uid, fp in valid_tasks:
            pixmap = QPixmap(fp)
            if pixmap.isNull():
                continue
            thumb = pixmap.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            item = QListWidgetItem(thumb, os.path.basename(fp))
            item.setData(Qt.ItemDataRole.UserRole, uid)
            item.setToolTip(fp)
            self.img_list.addItem(item)

        self.status_label.setText(f"已导入 {self.img_list.count()} 张图片，正在解码...")
        self._start_decode(valid_tasks)

    def _start_decode(self, tasks: list[tuple[str, str]]):
        if self._worker and self._worker.isRunning():
            return
        # 断开旧 worker 信号，避免重复连接
        if self._worker is not None:
            try:
                self._worker.finished.disconnect(self._on_decode_finished)
            except RuntimeError:
                pass
        self._worker = DecodeWorker(tasks, self)
        self._worker.finished.connect(self._on_decode_finished)
        self._worker.start()

    def _on_decode_finished(self, uid_results: list[tuple[str, DecodeResult]]):
        for uid, r in uid_results:
            self._results[uid] = r
        self._refresh_table()

        success = sum(1 for r in self._results.values() if r.status == "成功")
        fail = sum(1 for r in self._results.values() if r.status != "成功")
        self.status_label.setText(
            f"共 {self.img_list.count()} 张 | 成功 {success} / 失败 {fail}"
        )

        if any(r.status == "成功" for _, r in uid_results):
            InfoBar.success(
                title="解码完成",
                content=f"本批成功解码 {sum(1 for _, r in uid_results if r.status == '成功')} 个二维码",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )

    def _refresh_table(self):
        # 保存当前滚动位置，避免刷新后自动跳回顶部
        vbar = self.result_table.verticalScrollBar()
        scroll_value = vbar.value() if vbar else 0

        self.result_table.setRowCount(len(self._results))
        for i, r in enumerate(self._results.values()):
            self.result_table.setItem(i, 0, QTableWidgetItem(self._ellipsize(r.filename)))
            self.result_table.setItem(i, 1, QTableWidgetItem(r.content))
            self.result_table.setItem(i, 2, QTableWidgetItem(r.status))

        # 恢复滚动位置
        if vbar:
            vbar.setValue(scroll_value)

    @staticmethod
    def _ellipsize(text: str, max_len: int = 20) -> str:
        """超出 max_len 时折叠为 前10 + ... + 后7。"""
        if len(text) <= max_len:
            return text
        return text[:10] + "..." + text[-7:]

    # ── 导出 ────────────────────────────────────────

    def _on_export(self, index: int):
        if index == 0 or not self._results:
            return

        # 断开信号避免 setCurrentIndex 触发递归/崩溃
        self.export_combo.currentIndexChanged.disconnect(self._on_export)
        self.export_combo.setCurrentIndex(0)
        self.export_combo.currentIndexChanged.connect(self._on_export)

        formats = ["", "xlsx", "csv", "txt"]
        fmt = formats[index]

        # 只导出成功的结果
        success_results = [r for r in self._results.values() if r.status == "成功"]
        if not success_results:
            InfoBar.warning(
                title="无数据",
                content="没有可导出的成功解码结果",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )
            return

        # 延迟导出到下一帧事件循环，避免在信号处理函数内弹模态对话框导致崩溃
        if fmt == "xlsx":
            QTimer.singleShot(0, lambda: self._export_excel(success_results))
        elif fmt == "csv":
            QTimer.singleShot(0, lambda: self._export_csv(success_results))
        elif fmt == "txt":
            QTimer.singleShot(0, lambda: self._export_txt(success_results))

    def _export_excel(self, results: list[DecodeResult]):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 Excel", "qrcode_results.xlsx", "Excel 文件 (*.xlsx)"
        )
        if not path:
            return
        try:
            from openpyxl import Workbook
            wb = Workbook()
            ws = wb.active
            if ws is None:
                ws = wb.create_sheet("二维码解码结果")
            else:
                ws.title = "二维码解码结果"
            ws.append(["文件名", "解码内容"])
            for r in results:
                ws.append([r.filename, r.content])
            wb.save(path)
            self._notify_exported(path)
        except Exception as e:
            InfoBar.error(title="导出失败", content=str(e), parent=self)

    def _export_csv(self, results: list[DecodeResult]):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", "qrcode_results.csv", "CSV 文件 (*.csv)"
        )
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["文件名", "解码内容"])
                for r in results:
                    writer.writerow([r.filename, r.content])
            self._notify_exported(path)
        except Exception as e:
            InfoBar.error(title="导出失败", content=str(e), parent=self)

    def _export_txt(self, results: list[DecodeResult]):
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 TXT", "qrcode_results.txt", "文本文件 (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                for r in results:
                    f.write(f"{r.filename}: {r.content}\n")
            self._notify_exported(path)
        except Exception as e:
            InfoBar.error(title="导出失败", content=str(e), parent=self)

    def _notify_exported(self, path: str):
        InfoBar.success(
            title="导出成功",
            content=f"已保存到 {os.path.basename(path)}",
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )

    # ── 清空 ────────────────────────────────────────

    def _on_clear(self):
        self.img_list.clear()
        self.result_table.setRowCount(0)
        self._results.clear()
        self.status_label.setText("等待导入...")


# 补全导入
from PySide6.QtWidgets import QApplication, QTableWidgetItem
