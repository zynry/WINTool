# coding: utf-8
import json
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
)

from qfluentwidgets import (
    CaptionLabel,
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


# ── JSON 语法高亮配色（VS Code 风格）──────────────────
_COLORS = {
    True: {  # dark
        "key": "#9cdcfe",
        "string": "#ce9178",
        "number": "#b5cea8",
        "bool": "#569cd6",
        "null": "#569cd6",
        "punctuation": "#d4d4d4",
    },
    False: {  # light
        "key": "#0451a5",
        "string": "#a31515",
        "number": "#098658",
        "bool": "#0000ff",
        "null": "#0000ff",
        "punctuation": "#333333",
    },
}


class JsonHighlighter:
    """轻量 JSON 高亮器：将 JSON 字符串转为带颜色 span 的 HTML。"""

    def __init__(self, is_dark: bool = True):
        self.is_dark = is_dark
        self.colors = _COLORS[is_dark]

    def highlight(self, text: str) -> str:
        """对格式化后的 JSON 文本进行高亮，返回 HTML 字符串。"""
        lines = text.split("\n")
        highlighted_lines = []

        for line in lines:
            highlighted_lines.append(self._highlight_line(line))

        bg = "#1e1e1e" if self.is_dark else "#ffffff"
        fg = "#d4d4d4" if self.is_dark else "#333333"
        return (
            f'<pre style="background:{bg};color:{fg};'
            f'margin:0;padding:8px 12px;font-family:Consolas,monospace;font-size:10pt;">'
            + "\n".join(highlighted_lines)
            + "</pre>"
        )

    def _highlight_line(self, line: str) -> str:
        """对单行进行高亮。"""
        result = []
        i = 0
        n = len(line)

        while i < n:
            ch = line[i]

            # 字符串（key 或 value）
            if ch == '"':
                j = i + 1
                while j < n and line[j] != '"':
                    if line[j] == "\\" and j + 1 < n:
                        j += 2
                    else:
                        j += 1
                j = min(j + 1, n)
                raw = line[i:j]
                html_raw = self._escape_html(raw)

                rest = line[j:].lstrip()
                if rest.startswith(":"):
                    color = self.colors["key"]
                else:
                    color = self.colors["string"]
                result.append(f'<span style="color:{color};">{html_raw}</span>')
                i = j
                continue

            # 数字
            if ch.isdigit() or (ch == "-" and i + 1 < n and line[i + 1].isdigit()):
                j = i + 1
                while j < n and (line[j].isdigit() or line[j] in ".eE+-"):
                    j += 1
                raw = line[i:j]
                result.append(
                    f'<span style="color:{self.colors["number"]};">'
                    f'{self._escape_html(raw)}</span>'
                )
                i = j
                continue

            # true / false / null
            word_match = re.match(r"\b(true|false|null)\b", line[i:])
            if word_match:
                word = word_match.group(1)
                color = self.colors["bool"] if word in ("true", "false") else self.colors["null"]
                result.append(f'<span style="color:{color};">{word}</span>')
                i += len(word)
                continue

            # 普通字符（标点、空白等）
            result.append(self._escape_html(ch))
            i += 1

        return "".join(result)

    @staticmethod
    def _escape_html(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class JsonOutputEdit(QTextEdit):
    """支持缩进指南线绘制的 JSON 输出编辑器。"""

    INDENT_PX = 16       # 每个缩进层级的像素宽度（需与字体宽度匹配）
    INDENT_CHARS = 4     # 每个缩进层级的空格数

    def __init__(self, parent=None):
        super().__init__(parent)
        self._guide_color = QColor("#333333")
        self.setReadOnly(True)

    def setGuideColor(self, color: QColor):
        self._guide_color = color
        self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        self._draw_indent_guides()

    def _draw_indent_guides(self):
        doc = self.document()
        viewport = self.viewport()
        viewport_rect = viewport.rect()

        # 计算滚动偏移量
        scroll_x = self.horizontalScrollBar().value()
        scroll_y = self.verticalScrollBar().value()

        painter = QPainter(viewport)
        painter.setPen(QPen(self._guide_color, 1))

        block = doc.firstBlock()
        while block.isValid():
            rect = doc.documentLayout().blockBoundingRect(block)
            # 转为视口坐标
            top = int(rect.top()) - scroll_y + doc.documentMargin()
            bottom = int(rect.bottom()) - scroll_y + doc.documentMargin()

            if bottom < viewport_rect.top():
                block = block.next()
                continue
            if top > viewport_rect.bottom():
                break

            text = block.text()
            spaces = len(text) - len(text.lstrip(" "))
            levels = spaces // self.INDENT_CHARS

            # 第一个层级偏移为 padding_left + 0，从 level=1 开始不画 level=0
            margin_left = int(doc.documentMargin()) - scroll_x
            for level in range(1, levels + 1):
                x = margin_left + level * self.INDENT_PX
                painter.drawLine(x, int(top), x, int(bottom))

            block = block.next()


class JsonPage(_Widget):
    """JSON 格式化页面。"""

    def __init__(self, parent=None):
        super().__init__("JsonPage", parent=parent)
        self._setup_ui()
        self._connect_signals()
        # 监听主题变化，延迟一帧应用样式，确保在 qfluentwidgets 全局样式表之后生效
        qconfig.themeChanged.connect(self._on_theme_changed)
        QTimer.singleShot(0, self._apply_all_styles)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 24, 16)
        main_layout.setSpacing(12)

        # ── 顶部控制栏 ────────────────────────────────
        control_layout = QHBoxLayout()
        control_layout.setSpacing(8)

        self.format_btn = PrimaryPushButton("格式化", self)
        self.format_btn.setIcon(FluentIcon.ALIGNMENT)
        control_layout.addWidget(self.format_btn)

        self.minify_btn = PushButton("压缩", self)
        self.minify_btn.setIcon(FluentIcon.ZOOM_IN)
        control_layout.addWidget(self.minify_btn)

        control_layout.addSpacing(12)

        self.copy_btn = ToolButton(FluentIcon.COPY)
        self.copy_btn.setToolTip("复制结果")
        control_layout.addWidget(self.copy_btn)

        self.clear_btn = ToolButton(FluentIcon.DELETE)
        self.clear_btn.setToolTip("清空")
        control_layout.addWidget(self.clear_btn)

        control_layout.addStretch()
        main_layout.addLayout(control_layout)

        # ── 左右分割器：输入 / 输出 ───────────────────
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # 左侧输入卡片
        self.input_frame, self.input_edit = self._create_editor_card(
            "JSON 输入", "在此粘贴或输入 JSON 内容..."
        )
        self.splitter.addWidget(self.input_frame)

        # 右侧输出卡片（使用自定义 JsonOutputEdit 绘制缩进指南线）
        self.output_frame, self.output_edit = self._create_editor_card(
            "格式化结果", "", output=True
        )
        self.splitter.addWidget(self.output_frame)

        self.splitter.setSizes([400, 400])
        self.splitter.setHandleWidth(6)

        main_layout.addWidget(self.splitter, stretch=1)

        # ── 底部状态栏 ────────────────────────────────
        status_layout = QHBoxLayout()
        status_layout.setSpacing(12)

        self.status_dot = QFrame(self)
        self.status_dot.setFixedSize(8, 8)
        self.status_dot.setStyleSheet(
            "background: #6c757d; border-radius: 4px;"
        )
        status_layout.addWidget(self.status_dot)

        self.status_label = CaptionLabel("等待输入", self)
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        self.chars_label = CaptionLabel("0 字符", self)
        status_layout.addWidget(self.chars_label)

        main_layout.addLayout(status_layout)

    def _create_editor_card(self, title: str, placeholder: str, output: bool = False) -> tuple[QFrame, QTextEdit]:
        frame = QFrame()
        frame.setObjectName("jsonEditorCard")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)

        # 标题栏
        header = QFrame()
        header.setObjectName("jsonEditorHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 6)
        header_layout.setSpacing(0)

        title_lbl = CaptionLabel(title)
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        layout.addWidget(header)

        # 文本编辑区
        if output:
            edit: QTextEdit = JsonOutputEdit()
        else:
            edit = QTextEdit()
            edit.setPlaceholderText(placeholder)
            edit.setAcceptRichText(False)
            edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        edit.setFrameShape(QFrame.Shape.NoFrame)
        font = edit.font()
        font.setFamily("Consolas, Segoe UI, monospace")
        font.setPointSize(10)
        edit.setFont(font)
        layout.addWidget(edit, stretch=1)

        return frame, edit

    def _apply_all_styles(self):
        """根据当前主题统一应用所有样式（延迟调用，确保覆盖全局样式表）。"""
        dark = isDarkTheme()

        card_bg = "#252525" if dark else "#f5f5f5"
        card_border = "#333333" if dark else "#e0e0e0"
        edit_bg = "#1e1e1e" if dark else "#ffffff"
        edit_fg = "#e0e0e0" if dark else "#333333"
        placeholder = "#777777" if dark else "#999999"
        handle_bg = "#444444" if dark else "#d0d0d0"

        # 卡片样式（使用 !important 防止被全局样式表覆盖）
        card_css = f"""
            QFrame#jsonEditorCard {{
                background-color: {card_bg} !important;
                border: 1px solid {card_border};
                border-radius: 10px;
            }}
        """
        self.input_frame.setStyleSheet(card_css)
        self.output_frame.setStyleSheet(card_css)

        # 输入框样式
        input_css = f"""
            QTextEdit {{
                color: {edit_fg} !important;
                background-color: {edit_bg} !important;
                padding: 8px 12px;
                border: none;
            }}
            QTextEdit::placeholder {{
                color: {placeholder};
            }}
        """
        self.input_edit.setStyleSheet(input_css)

        # 输出框样式（背景与输入框一致，内容由 HTML 控制颜色）
        self.output_edit.setStyleSheet(input_css)
        # 设置缩进指南线颜色
        if isinstance(self.output_edit, JsonOutputEdit):
            guide = QColor("#444444") if dark else QColor("#d0d0d0")
            self.output_edit.setGuideColor(guide)

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
        """主题切换时延迟一帧重刷样式和高亮。"""
        QTimer.singleShot(0, self._apply_all_styles)
        # 如果已有结果，重新高亮以刷新颜色
        QTimer.singleShot(0, self._refresh_highlight)

    def _refresh_highlight(self):
        raw = self.output_edit.property("_raw_json")
        if raw:
            self._render_highlighted(raw)

    def _connect_signals(self):
        self.format_btn.clicked.connect(self._on_format)
        self.minify_btn.clicked.connect(self._on_minify)
        self.copy_btn.clicked.connect(self._on_copy)
        self.clear_btn.clicked.connect(self._on_clear)
        self.input_edit.textChanged.connect(self._on_input_changed)

    # ── 核心逻辑 ────────────────────────────────────

    def _parse_input(self) -> tuple[bool, str]:
        text = self.input_edit.toPlainText().strip()
        if not text:
            return False, "输入为空"
        try:
            json.loads(text)
            return True, ""
        except json.JSONDecodeError as e:
            return False, str(e)

    def _do_format(self, indent: int | None = 4, separators: tuple | None = None) -> str:
        text = self.input_edit.toPlainText().strip()
        if not text:
            return ""
        data = json.loads(text)
        kwargs: dict = {"ensure_ascii": False, "indent": indent}
        if separators:
            kwargs["separators"] = separators
        return json.dumps(data, **kwargs)

    def _render_highlighted(self, raw_json: str):
        """将格式化后的 JSON 渲染为带颜色高亮的 HTML。"""
        highlighter = JsonHighlighter(isDarkTheme())
        html = highlighter.highlight(raw_json)
        self.output_edit.setHtml(html)
        self.output_edit.setProperty("_raw_json", raw_json)

    def _on_format(self):
        ok, err = self._parse_input()
        if not ok:
            self._show_error(err)
            return
        try:
            result = self._do_format(indent=4)
            self._render_highlighted(result)
            self._update_status(True, len(result))
        except Exception as e:
            self._show_error(str(e))

    def _on_minify(self):
        ok, err = self._parse_input()
        if not ok:
            self._show_error(err)
            return
        try:
            result = self._do_format(indent=None, separators=(",", ":"))
            # 压缩后不进行高亮，直接显示纯文本
            self.output_edit.setPlainText(result)
            self.output_edit.setProperty("_raw_json", "")
            self._update_status(True, len(result))
        except Exception as e:
            self._show_error(str(e))

    def _on_copy(self):
        text = self.output_edit.toPlainText()
        if text:
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(text)
                InfoBar.success(
                    title="已复制",
                    content="结果已复制到剪贴板",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=2000,
                    parent=self,
                )
        else:
            InfoBar.warning(
                title="无内容",
                content="结果区域为空",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self,
            )

    def _on_clear(self):
        self.input_edit.clear()
        self.output_edit.clear()
        self.output_edit.setProperty("_raw_json", "")
        self._update_status(None, 0)

    def _on_input_changed(self):
        text = self.input_edit.toPlainText()
        self.chars_label.setText(f"{len(text)} 字符")

    def _update_status(self, ok: bool | None, result_len: int):
        if ok is True:
            self.status_label.setText("合法 JSON")
            self.status_dot.setStyleSheet("background: #28a745; border-radius: 4px;")
            self.chars_label.setText(f"结果 {result_len} 字符")
        elif ok is False:
            self.status_label.setText("格式错误")
            self.status_dot.setStyleSheet("background: #dc3545; border-radius: 4px;")
        else:
            self.status_label.setText("等待输入")
            self.status_dot.setStyleSheet("background: #6c757d; border-radius: 4px;")
            self.chars_label.setText("0 字符")

    def _show_error(self, message: str):
        self.output_edit.setPlainText(f"错误：{message}")
        self.output_edit.setProperty("_raw_json", "")
        self._update_status(False, 0)
        InfoBar.error(
            title="解析失败",
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self,
        )
