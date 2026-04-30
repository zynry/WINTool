# coding: utf-8
"""二维码解码页面。

支持拖拽上传、Ctrl+V 粘贴、文件选择批量导入，
使用 OpenCV QRCodeDetector 解码，结果可导出 Excel / CSV / TXT。
"""

from __future__ import annotations

import csv
import io
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import cv2
import numpy as np
import zxingcpp
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QUrl
from PySide6.QtGui import (
    QClipboard,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QImage,
    QKeyEvent,
    QKeySequence,
    QPixmap,
    QShortcut,
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
    QTextEdit,
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
    idx: int         # 批次内索引
    filename: str
    filepath: str
    content: str
    status: str  # "成功" / "未检测到" / "失败"


# ── 后台解码线程 ──────────────────────────────────────
class DecodeWorker(QThread):
    finished = Signal(list)  # list[DecodeResult]
    progress = Signal(int, int)  # current, total

    def __init__(self, paths: list[str], parent=None):
        super().__init__(parent)
        self.paths = paths

    def run(self):
        results: list[DecodeResult] = []
        cv_detector = cv2.QRCodeDetector()

        def _opencv_try_decode(img) -> str | None:
            """OpenCV 回退解码（含预处理）。"""
            data, _, _ = cv_detector.detectAndDecode(img)
            if data:
                return data
            ok, decoded, _, _ = cv_detector.detectAndDecodeMulti(img)
            if ok and decoded:
                texts = [d for d in decoded if d]
                if texts:
                    return "\n".join(texts)

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            variants = [
                gray,
                cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2),
                cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1],
                cv2.GaussianBlur(gray, (5, 5), 0),
                cv2.dilate(cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1], np.ones((2, 2), np.uint8), iterations=1),
                cv2.erode(cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1], np.ones((2, 2), np.uint8), iterations=1),
                cv2.bitwise_not(gray),
            ]
            for variant in variants:
                data, _, _ = cv_detector.detectAndDecode(variant)
                if data:
                    return data
                ok, decoded, _, _ = cv_detector.detectAndDecodeMulti(variant)
                if ok and decoded:
                    texts = [d for d in decoded if d]
                    if texts:
                        return "\n".join(texts)
            return None

        def decode_one(idx: int, fp: str) -> DecodeResult:
            fname = os.path.basename(fp)
            try:
                img = cv2.imread(fp, cv2.IMREAD_COLOR)
                if img is None:
                    return DecodeResult(idx, fname, fp, "", "读取失败")

                # 优先使用 zxing-cpp（识别率更高）
                zx_results = zxingcpp.read_barcodes(img)
                if zx_results:
                    texts = [r.text for r in zx_results if r.text]
                    if texts:
                        return DecodeResult(idx, fname, fp, "\n".join(texts), "成功")

                # 回退 OpenCV
                data = _opencv_try_decode(img)
                if data:
                    return DecodeResult(idx, fname, fp, data, "成功")

                return DecodeResult(idx, fname, fp, "", "未检测到")
            except Exception as e:
                return DecodeResult(idx, fname, fp, "", f"失败: {e}")

        total = len(self.paths)
        with ThreadPoolExecutor(max_workers=min(8, os.cpu_count() or 4)) as pool:
            for i, result in enumerate(pool.map(lambda args: decode_one(*args), enumerate(self.paths))):
                results.append(result)
                self.progress.emit(i + 1, total)

        self.finished.emit(results)


# ── 图片列表控件（支持拖拽+粘贴）───────────────────────
class ImageDropList(QListWidget):
    """支持文件拖拽和 Ctrl+V 粘贴的图片列表。"""

    filesDropped = Signal(list)  # list[tuple[str, str]]  (uid, filepath)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QPixmap(80, 80).size())
        self.setSpacing(8)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setDragEnabled(False)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

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
                self.filesDropped.emit(paths)

    def _save_clipboard_image(self, img: QImage):
        """将剪贴板图片保存到临时文件并触发解码。"""
        from tempfile import gettempdir
        tmp_path = os.path.join(gettempdir(), "qrcode_paste.png")
        img.save(tmp_path)
        self.filesDropped.emit([tmp_path])


# ── 主页面 ────────────────────────────────────────────
class QRCodePage(_Widget):
    """二维码解码页面。"""

    def __init__(self, parent=None):
        super().__init__("QRCodePage", parent=parent)
        self._results: list[DecodeResult] = []
        self._worker: DecodeWorker | None = None
        self._setup_ui()
        self._connect_signals()
        self.setAcceptDrops(True)

        # 全局 Ctrl+V 快捷键（不受焦点影响）
        self._paste_shortcut = QShortcut(
            QKeySequence("Ctrl+V"), self, self._paste_from_clipboard
        )

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
            self._add_images(paths)
        event.acceptProposedAction()

    def _paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        mime = clipboard.mimeData()
        if mime and mime.hasImage():
            img = clipboard.image()
            if not img.isNull():
                from tempfile import gettempdir
                tmp_path = os.path.join(gettempdir(), "qrcode_paste.png")
                img.save(tmp_path)
                self._add_images([tmp_path])
        elif mime and mime.hasUrls():
            paths = [u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
            if paths:
                self._add_images(paths)

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
        self.clear_btn.setToolTip("清空")
        control_layout.addWidget(self.clear_btn)

        control_layout.addStretch()

        self.status_label = CaptionLabel("等待导入...", self)
        control_layout.addWidget(self.status_label)

        main_layout.addLayout(control_layout)

        # ── 主体：左侧缩略图 + 右侧解码内容 ───────────
        body_layout = QHBoxLayout()
        body_layout.setSpacing(12)

        # 左侧：缩略图预览
        self.img_frame = QFrame()
        self.img_frame.setObjectName("qrImgFrame")
        img_layout = QVBoxLayout(self.img_frame)
        img_layout.setContentsMargins(12, 12, 12, 12)
        img_layout.setSpacing(8)

        img_layout.addWidget(CaptionLabel("二维码预览", self), alignment=Qt.AlignmentFlag.AlignCenter)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(200, 200)
        self.preview_label.setMaximumSize(260, 260)
        self.preview_label.setText("拖拽或粘贴\n二维码图片")
        self.preview_label.setWordWrap(True)
        img_layout.addWidget(self.preview_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.preview_name = CaptionLabel("", self)
        self.preview_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_layout.addWidget(self.preview_name, alignment=Qt.AlignmentFlag.AlignCenter)

        body_layout.addWidget(self.img_frame)

        # 右侧：解码结果展示
        self.result_frame = QFrame()
        self.result_frame.setObjectName("qrResultFrame")
        result_layout = QVBoxLayout(self.result_frame)
        result_layout.setContentsMargins(16, 16, 16, 16)
        result_layout.setSpacing(12)

        # 状态
        self.result_status = CaptionLabel("等待导入...", self)
        self.result_status.setStyleSheet("font-size: 15px; font-weight: 600;")
        result_layout.addWidget(self.result_status)

        # 解码内容文本框
        self.result_content = QTextEdit(self)
        self.result_content.setPlaceholderText("解码内容将显示在这里...")
        self.result_content.setReadOnly(True)
        result_layout.addWidget(self.result_content, stretch=1)

        # 操作按钮
        btn_layout = QHBoxLayout()
        self.copy_btn = PushButton("复制内容", self)
        self.copy_btn.setIcon(FluentIcon.COPY)
        self.open_link_btn = PushButton("打开链接", self)
        self.open_link_btn.setIcon(FluentIcon.LINK)
        self.open_link_btn.setVisible(False)
        btn_layout.addWidget(self.copy_btn)
        btn_layout.addWidget(self.open_link_btn)
        btn_layout.addStretch()
        result_layout.addLayout(btn_layout)

        body_layout.addWidget(self.result_frame, stretch=1)
        main_layout.addLayout(body_layout, stretch=1)

        # 延迟应用样式，确保在 qfluentwidgets 全局样式表之后生效
        QTimer.singleShot(0, self._apply_all_styles)

    def _apply_all_styles(self):
        """根据当前主题统一应用所有样式。"""
        dark = isDarkTheme()

        # 卡片背景
        card_bg = "#252525" if dark else "#e8f4fc"
        card_border = "#333333" if dark else "#d0e6f0"
        # 内部背景
        inner_bg = "#1e1e1e" if dark else "#ffffff"
        inner_fg = "#e0e0e0" if dark else "#333333"
        # 表头
        header_bg = "#2a2a2a" if dark else "#d6eaf8"
        header_fg = "#e0e0e0" if dark else "#333333"

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

        # 预览区占位文字颜色
        self.preview_label.setStyleSheet(f"color: {'#888888' if dark else '#999999'}; font-size: 14px;")

        # 解码内容文本框样式
        content_css = f"""
            QTextEdit {{
                color: {inner_fg} !important;
                background-color: {inner_bg} !important;
                border: 1px solid {card_border};
                border-radius: 8px;
                padding: 12px;
                font-size: 14px;
                font-family: 'Consolas', 'Microsoft YaHei', monospace;
            }}
        """
        self.result_content.setStyleSheet(content_css)

    def _on_theme_changed(self, theme):
        QTimer.singleShot(0, self._apply_all_styles)

    def _connect_signals(self):
        self.select_btn.clicked.connect(self._on_select_files)
        self.copy_btn.clicked.connect(self._on_copy)
        self.open_link_btn.clicked.connect(self._on_open_link)
        self.export_combo.currentIndexChanged.connect(self._on_export)
        self.clear_btn.clicked.connect(self._on_clear)
        qconfig.themeChanged.connect(self._on_theme_changed)

    # ── 文件处理 ────────────────────────────────────

    def _on_select_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择二维码图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tiff);;所有文件 (*.*)",
        )
        if paths:
            self._add_images(paths)

    def _on_files_dropped(self, paths: list[str]):
        self._add_images(paths)

    def _add_images(self, paths: list[str]):
        """添加图片到列表并启动解码（每次新导入自动清空之前的结果）。"""
        # 清空之前的结果和UI
        self._results = []
        self.result_content.clear()
        self.result_content.setPlaceholderText("解码内容将显示在这里...")
        self.result_status.setText("正在解码...")
        self.open_link_btn.setVisible(False)

        valid_paths: list[str] = []
        for p in paths:
            ext = Path(p).suffix.lower()
            if ext in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff", ".tif"}:
                valid_paths.append(p)

        if not valid_paths:
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

        # 显示第一张图片的缩略图
        first_fp = valid_paths[0]
        pixmap = QPixmap(first_fp)
        if not pixmap.isNull():
            thumb = pixmap.scaled(220, 220, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.preview_label.setPixmap(thumb)
            self.preview_name.setText(os.path.basename(first_fp))

        self.status_label.setText(f"已导入 {len(valid_paths)} 张图片，正在解码...")
        self._start_decode(valid_paths)

    def _start_decode(self, paths: list[str]):
        if self._worker and self._worker.isRunning():
            return
        # 断开旧 worker 信号，避免重复连接
        if self._worker is not None:
            try:
                self._worker.finished.disconnect(self._on_decode_finished)
            except RuntimeError:
                pass
        self._worker = DecodeWorker(paths, self)
        self._worker.finished.connect(self._on_decode_finished)
        self._worker.start()

    def _on_decode_finished(self, results: list[DecodeResult]):
        self._results = results

        success = sum(1 for r in self._results if r.status == "成功")
        fail = sum(1 for r in self._results if r.status != "成功")
        self.status_label.setText(f"共 {len(results)} 张 | 成功 {success} / 失败 {fail}")

        # 更新主展示区域（取第一个成功的结果）
        success_results = [r for r in results if r.status == "成功"]
        if success_results:
            first = success_results[0]
            self.result_status.setText(f"✅ 解码成功")
            self.result_status.setStyleSheet("font-size: 15px; font-weight: 600; color: #28a745;")
            self.result_content.setPlainText(first.content)
            # 判断是否为链接
            is_url = first.content.startswith(("http://", "https://"))
            self.open_link_btn.setVisible(is_url)
            if is_url:
                self.open_link_btn.setProperty("url", first.content)
        else:
            # 取第一个结果展示失败原因
            first = results[0] if results else None
            if first:
                self.result_status.setText(f"❌ {first.status}")
                self.result_status.setStyleSheet("font-size: 15px; font-weight: 600; color: #dc3545;")
                self.result_content.setPlainText("")
            self.open_link_btn.setVisible(False)

        if success > 0:
            InfoBar.success(
                title="解码完成",
                content=f"成功解码 {success} 个二维码",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )

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
        success_results = [r for r in self._results if r.status == "成功"]
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
        self._results = []
        self.result_content.clear()
        self.result_content.setPlaceholderText("解码内容将显示在这里...")
        self.result_status.setText("等待导入...")
        self.result_status.setStyleSheet("font-size: 15px; font-weight: 600;")
        self.preview_label.clear()
        self.preview_label.setText("拖拽或粘贴\n二维码图片")
        self.preview_name.setText("")
        self.open_link_btn.setVisible(False)
        self.status_label.setText("等待导入...")

    def _on_copy(self):
        text = self.result_content.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
            InfoBar.success(
                title="已复制",
                content="解码内容已复制到剪贴板",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=1500,
                parent=self,
            )

    def _on_open_link(self):
        url = self.open_link_btn.property("url")
        if url:
            QDesktopServices.openUrl(QUrl(url))


# 补全导入
from PySide6.QtWidgets import QApplication, QTableWidgetItem
