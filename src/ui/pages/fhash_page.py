# coding: utf-8
import os
import threading
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    ScrollBar,
    StrongBodyLabel,
    ToolButton,
    isDarkTheme,
)

from services.hash_service import (
    calculate_hashes_concurrent,
    get_cpu_info_text,
    get_recommended_workers,
)
from ui.widgets.custom_widget import _Widget


def _format_size(size_bytes: int) -> str:
    """将字节数格式化为人类可读的字符串。"""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024:
            return f"{size:.1f} {unit}".replace(".0 ", " ")
        size /= 1024
    return f"{size:.1f} PB"


class FileHashCard(QFrame):
    """单个文件的哈希结果卡片。"""

    removed = Signal(str)              # file_path
    copy_requested = Signal(str, str)  # label, value

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent=parent)
        self.file_path = file_path
        self.hashes: dict[str, str] = {}

        self.setObjectName("fileHashCard")
        self._apply_card_style()

        self._setup_ui()
        self._connect_signals()

    def _apply_card_style(self):
        """根据当前主题应用卡片样式。"""
        if isDarkTheme():
            self.setStyleSheet("""
                QFrame#fileHashCard {
                    background-color: #2c2c2c;
                    border: 1px solid #3a3a3a;
                    border-radius: 10px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame#fileHashCard {
                    background-color: #ffffff;
                    border: 1px solid #e0e0e0;
                    border-radius: 10px;
                }
            """)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 14, 18, 14)
        main_layout.setSpacing(10)

        # ── 顶部行：文件名 + 大小 + 删除 ──────────
        top_layout = QHBoxLayout()
        top_layout.setSpacing(8)

        self.name_label = StrongBodyLabel(Path(self.file_path).name)
        self.name_label.setToolTip(self.file_path)
        top_layout.addWidget(self.name_label, stretch=1)

        try:
            size_text = _format_size(Path(self.file_path).stat().st_size)
        except OSError:
            size_text = "无法读取"
        self.size_label = CaptionLabel(size_text)
        top_layout.addWidget(self.size_label)

        self.remove_btn = ToolButton(FluentIcon.CLOSE)
        self.remove_btn.setToolTip("移除该文件")
        top_layout.addWidget(self.remove_btn)

        main_layout.addLayout(top_layout)

        # ── 进度条 ───────────────────────────────
        self.progress_bar = ProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(18)
        main_layout.addWidget(self.progress_bar)

        # ── 分隔线 ───────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setStyleSheet("color: palette(mid);")
        sep.setFixedHeight(1)
        main_layout.addWidget(sep)

        # ── 哈希值区域 ───────────────────────────
        hash_layout = QVBoxLayout()
        hash_layout.setSpacing(6)

        self.md5_row, self.md5_value, self.md5_btn = self._create_hash_row("MD5")
        self.sha1_row, self.sha1_value, self.sha1_btn = self._create_hash_row("SHA1")
        self.sha256_row, self.sha256_value, self.sha256_btn = self._create_hash_row("SHA256")

        hash_layout.addLayout(self.md5_row)
        hash_layout.addLayout(self.sha1_row)
        hash_layout.addLayout(self.sha256_row)

        main_layout.addLayout(hash_layout)

    def _create_hash_row(self, algo: str):
        layout = QHBoxLayout()
        layout.setSpacing(10)

        label = CaptionLabel(f"{algo}:")
        label.setFixedWidth(52)
        layout.addWidget(label)

        value_label = BodyLabel("等待计算...")
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value_label.setWordWrap(False)
        font = value_label.font()
        font.setFamily("Consolas, monospace")
        value_label.setFont(font)
        layout.addWidget(value_label, stretch=1)

        btn = ToolButton(FluentIcon.COPY)
        btn.setToolTip(f"复制 {algo}")
        btn.setEnabled(False)
        layout.addWidget(btn)

        btn.clicked.connect(
            lambda _=False, a=algo, lbl=value_label: self._on_copy(a, lbl)
        )

        return layout, value_label, btn

    def _connect_signals(self):
        self.remove_btn.clicked.connect(
            lambda: self.removed.emit(self.file_path)
        )

    def _on_copy(self, algo: str, lbl: BodyLabel):
        text = lbl.text()
        if text and text != "等待计算..." and not text.startswith("错误"):
            self.copy_requested.emit(algo, text)

    def set_progress(self, percent: int):
        self.progress_bar.setValue(max(0, min(100, percent)))

    def set_hashes(self, hashes: dict[str, str]):
        self.hashes = hashes
        mapping = {
            "md5": (self.md5_value, self.md5_btn),
            "sha1": (self.sha1_value, self.sha1_btn),
            "sha256": (self.sha256_value, self.sha256_btn),
        }
        for algo, (lbl, btn) in mapping.items():
            val = hashes.get(algo, "")
            lbl.setText(val)
            btn.setEnabled(bool(val))
        self.progress_bar.setValue(100)

    def set_error(self, message: str):
        for lbl, btn in [
            (self.md5_value, self.md5_btn),
            (self.sha1_value, self.sha1_btn),
            (self.sha256_value, self.sha256_btn),
        ]:
            lbl.setText(f"错误: {message}")
            btn.setEnabled(False)
        self.progress_bar.setValue(0)

    def refresh_theme(self):
        """主题切换时刷新卡片样式。"""
        self._apply_card_style()


class FileHashPage(_Widget):
    """文件哈希值计算页面。"""

    _progress_signal = Signal(str, int, int)  # path, read, total
    _complete_signal = Signal(str, dict)      # path, {algo: hash}
    _error_signal = Signal(str, str)          # path, error_msg
    _finished_signal = Signal()               # 全部完成

    def __init__(self, parent=None):
        super().__init__("FileHashPage", parent=parent)
        self.setAcceptDrops(True)

        self._file_paths: list[str | Path] = []
        self._file_cards: dict[str, FileHashCard] = {}
        self._is_calculating = False

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # ── 顶部控制栏 ────────────────────────────────
        control_layout = QHBoxLayout()
        control_layout.setSpacing(12)

        self.add_btn = PrimaryPushButton("添加文件", self)
        self.add_btn.setIcon(FluentIcon.FOLDER_ADD)
        control_layout.addWidget(self.add_btn)

        self.clear_btn = PushButton("清空列表", self)
        self.clear_btn.setIcon(FluentIcon.DELETE)
        control_layout.addWidget(self.clear_btn)

        control_layout.addStretch()

        self.cpu_label = CaptionLabel(get_cpu_info_text(), self)
        control_layout.addWidget(self.cpu_label)

        main_layout.addLayout(control_layout)

        # ── 文件列表区域 ──────────────────────────────
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        # 隐藏原生垂直滚动条，使用自定义 ScrollBar
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                width: 0px;
            }
        """)

        self.scroll_widget = QWidget(self.scroll_area)
        self.scroll_widget.setStyleSheet("QWidget { background: transparent; }")
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_layout.setSpacing(12)
        self.scroll_layout.setSizeConstraint(
            QVBoxLayout.SizeConstraint.SetMinAndMaxSize
        )

        self.scroll_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

        self.scroll_area.setWidget(self.scroll_widget)

        # qfluentwidgets 自定义滚动条
        self.v_scroll_bar = ScrollBar(Qt.Vertical, self.scroll_area)

        self.empty_label = BodyLabel(
            "拖拽文件到此处，或点击「添加文件」按钮",
            self.scroll_widget,
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_layout.addWidget(self.empty_label)
        self.scroll_layout.addStretch(1)

        main_layout.addWidget(self.scroll_area, stretch=1)

        # ── 底部操作栏 ────────────────────────────────
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        self.start_btn = PrimaryPushButton("开始计算", self)
        self.start_btn.setIcon(FluentIcon.PLAY)
        self.start_btn.setEnabled(False)
        bottom_layout.addWidget(self.start_btn)
        main_layout.addLayout(bottom_layout)

    def _connect_signals(self):
        self.add_btn.clicked.connect(self._on_add_files)
        self.clear_btn.clicked.connect(self._on_clear)
        self.start_btn.clicked.connect(self._on_start)

        self._progress_signal.connect(self._on_progress)
        self._complete_signal.connect(self._on_complete)
        self._error_signal.connect(self._on_error)
        self._finished_signal.connect(self._on_all_finished)

    # ── 文件管理 ────────────────────────────────────

    def _on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "", "所有文件 (*)"
        )
        if files:
            self._add_files(files)

    def _add_files(self, paths: list[str]):
        for path in paths:
            path = os.path.normpath(path)
            if path in self._file_cards:
                continue
            self._file_paths.append(path)
            card = FileHashCard(path, self.scroll_widget)
            card.removed.connect(self._on_remove_card)
            card.copy_requested.connect(self._on_copy_hash)
            self._file_cards[path] = card
            self.scroll_layout.insertWidget(
                self.scroll_layout.count() - 2, card
            )

        self._update_empty_state()
        self._update_start_btn()

    def _on_remove_card(self, file_path: str):
        card = self._file_cards.pop(file_path, None)
        if card:
            self._file_paths.remove(file_path)
            card.deleteLater()
            self._update_empty_state()
            self._update_start_btn()

    def _on_clear(self):
        for card in self._file_cards.values():
            card.deleteLater()
        self._file_cards.clear()
        self._file_paths.clear()
        self._update_empty_state()
        self._update_start_btn()

    def _update_empty_state(self):
        has_files = len(self._file_cards) > 0
        self.empty_label.setVisible(not has_files)

    def _update_start_btn(self):
        enabled = len(self._file_paths) > 0 and not self._is_calculating
        self.start_btn.setEnabled(enabled)

    # ── 拖拽支持 ────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if os.path.isfile(path):
                paths.append(path)
        if paths:
            self._add_files(paths)

    # ── 计算逻辑 ────────────────────────────────────

    def _on_start(self):
        if not self._file_paths or self._is_calculating:
            return

        self._is_calculating = True
        self._update_start_btn()
        self.start_btn.setText("计算中...")
        self.add_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)

        for card in self._file_cards.values():
            card.set_progress(0)
            for lbl, btn in [
                (card.md5_value, card.md5_btn),
                (card.sha1_value, card.sha1_btn),
                (card.sha256_value, card.sha256_btn),
            ]:
                lbl.setText("计算中...")
                btn.setEnabled(False)

        def on_progress(path: str, read: int, total: int):
            self._progress_signal.emit(path, read, total)

        def on_complete(path: str, hashes: dict[str, str]):
            self._complete_signal.emit(path, hashes)

        def on_error(path: str, exc: Exception):
            self._error_signal.emit(path, str(exc))

        def task():
            calculate_hashes_concurrent(
                self._file_paths,
                max_workers=get_recommended_workers(),
                on_progress=on_progress,
                on_complete=on_complete,
                on_error=on_error,
            )
            self._finished_signal.emit()

        threading.Thread(target=task, daemon=True).start()

    def _on_progress(self, path: str, read: int, total: int):
        card = self._file_cards.get(path)
        if card and total > 0:
            percent = int(read * 100 / total)
            card.set_progress(percent)

    def _on_complete(self, path: str, hashes: dict[str, str]):
        card = self._file_cards.get(path)
        if card:
            card.set_hashes(hashes)

    def _on_error(self, path: str, message: str):
        card = self._file_cards.get(path)
        if card:
            card.set_error(message)

    def _on_all_finished(self):
        self._is_calculating = False
        self._update_start_btn()
        self.start_btn.setText("开始计算")
        self.add_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)

    def _on_copy_hash(self, algo: str, hash_value: str):
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(hash_value)
            InfoBar.success(
                title="已复制",
                content=f"{algo} 哈希值已复制到剪贴板",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )
