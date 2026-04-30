from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    ColorSettingCard,
    ComboBox,
    ExpandLayout,
    FluentIcon,
    OptionsSettingCard,
    ScrollArea,
    SettingCard,
    SettingCardGroup,
    qconfig,
    setTheme,
    setThemeColor,
)

from services.settings_service import PAGE_OPTIONS, SettingsService
from ui.widgets.custom_widget import _Widget


class DefaultPageSettingCard(SettingCard):
    """默认启动页面设置卡片。"""

    def __init__(self, parent=None):
        self._svc = SettingsService()
        super().__init__(
            FluentIcon.HOME,
            "默认打开页面",
            "设置启动应用时默认显示的页面",
            parent=parent,
        )

        self.combo = ComboBox(self)
        self._key_to_text = dict(PAGE_OPTIONS)
        self._text_to_key = {v: k for k, v in PAGE_OPTIONS}
        self.combo.addItems([t for _, t in PAGE_OPTIONS])

        # 加载当前值
        current_key = self._svc.default_page
        if current_key in self._key_to_text:
            self.combo.setCurrentText(self._key_to_text[current_key])

        self.combo.currentTextChanged.connect(self._on_changed)

        self.hBoxLayout.addStretch(1)
        self.hBoxLayout.addWidget(self.combo, 0, Qt.AlignmentFlag.AlignRight)
        self.hBoxLayout.addSpacing(16)

    def _on_changed(self, text: str):
        key = self._text_to_key.get(text)
        if key:
            self._svc.default_page = key


class SettingsPage(_Widget):
    """应用设置页面"""

    def __init__(self, parent=None):
        super().__init__("SettingsPage", parent=parent)

        # ── 滚动容器 ────────────────────────────────────────────
        self.scrollArea = ScrollArea(self)
        self.scrollWidget = QWidget(self.scrollArea)
        self.expandLayout = ExpandLayout(self.scrollWidget)

        # ── 外观分组 ────────────────────────────────────────────
        self.appearanceGroup = SettingCardGroup("个性化", self.scrollWidget)

        # 主题模式（浅色 / 深色 / 跟随系统）
        self.themeCard = OptionsSettingCard(
            qconfig.themeMode,
            FluentIcon.BRUSH,
            "应用主题",
            "调整应用的明暗外观",
            texts=["浅色", "深色", "跟随系统设置"],
            parent=self.appearanceGroup,
        )

        # 主题色
        self.colorCard = ColorSettingCard(
            qconfig.themeColor,
            FluentIcon.PALETTE,
            "主题色",
            "调整应用的强调色",
            parent=self.appearanceGroup,
        )

        # ── 通用分组 ────────────────────────────────────────────
        self.generalGroup = SettingCardGroup("通用", self.scrollWidget)

        # 默认打开页面
        self.defaultPageCard = DefaultPageSettingCard(parent=self.generalGroup)

        self._initLayout()
        self._connectSignals()

    # ── 布局 ────────────────────────────────────────────────────

    def _initLayout(self):
        # ScrollArea
        self.scrollArea.setObjectName("settingsScrollArea")
        self.scrollWidget.setObjectName("settingsScrollWidget")
        self.scrollArea.setWidget(self.scrollWidget)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scrollArea.setViewportMargins(0, 0, 0, 20)
        # 用 #objectName 选择器精确命中本控件，不向子组件级联
        self.scrollArea.setStyleSheet(
            "QScrollArea#settingsScrollArea { background: transparent; border: none; }"
        )
        self.scrollWidget.setStyleSheet(
            "QWidget#settingsScrollWidget { background: transparent; }"
        )
        # viewport 是 QScrollArea 内部独立子控件，需单独处理
        self.scrollArea.viewport().setObjectName("settingsScrollAreaViewport")
        self.scrollArea.viewport().setStyleSheet(
            "QWidget#settingsScrollAreaViewport { background: transparent; }"
        )

        # 卡片加入分组
        self.appearanceGroup.addSettingCard(self.themeCard)
        self.appearanceGroup.addSettingCard(self.colorCard)
        self.generalGroup.addSettingCard(self.defaultPageCard)

        # 分组加入滚动区域的 ExpandLayout
        self.expandLayout.setSpacing(28)
        self.expandLayout.setContentsMargins(36, 20, 36, 0)
        self.expandLayout.addWidget(self.appearanceGroup)
        self.expandLayout.addWidget(self.generalGroup)

        # 页面主布局
        mainLayout = QVBoxLayout(self)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        mainLayout.addWidget(self.scrollArea)

    # ── 信号 ────────────────────────────────────────────────────

    def _connectSignals(self):
        svc = SettingsService()

        # 主题模式改变 → setTheme（save=False，由 SettingsService 统一持久化）
        self.themeCard.optionChanged.connect(
            lambda ci: (
                setTheme(qconfig.get(ci), save=False),
                svc.set("theme_mode", qconfig.get(ci).value),
            )
        )
        # 主题色改变 → setThemeColor
        self.colorCard.colorChanged.connect(
            lambda color: (
                setThemeColor(color, save=False),
                svc.set("theme_color", color.name()),
            )
        )
