from enum import Enum
from pathlib import Path

from PySide6.QtWidgets import QFrame
from qfluentwidgets import FluentIconBase, Theme, qconfig

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class _Widget(QFrame):
    def __init__(self, objName: str, parent=None):
        super().__init__(parent=parent)
        # 必须给子界面设置全局唯一的对象名
        self.setObjectName(objName)
        # 去掉 QFrame 默认的 StyledPanel 边框和自带背景，
        # 让 FluentWindow 的背景透过来
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFrameShadow(QFrame.Shadow.Plain)


class SidebarIcon(FluentIconBase, Enum):
    """
    项目自定义图标枚举。

    命名规则
    --------
    每个成员的值对应 resources/icon/sidebar_button/ 目录下
    的文件名前缀（不含颜色后缀和扩展名）。

    例如：FILE_HASH  →  file_hash_black.svg / file_hash_white.svg

    新增图标只需：
      1. 将 <name>_black.svg 和 <name>_white.svg 放入上述目录
      2. 在此枚举中添加一行  NAME = "<name>"
    """

    FILE_HASH = "file_hash"

    def path(self, theme: Theme = Theme.AUTO) -> str:
        """
        根据当前主题返回对应颜色版本的 SVG 路径。

        qfluentwidgets 内部通过 render() → path(Theme.AUTO) 调用此方法，
        因此必须在此处把 AUTO 解析为实际主题，否则永远返回黑色图标。
        """
        if theme == Theme.AUTO:
            theme = qconfig.theme  # 解析为 Theme.LIGHT 或 Theme.DARK

        base = _PROJECT_ROOT / "resources" / "icon" / "sidebar_button" / self.value
        if theme == Theme.DARK:
            return str(base) + "_white.svg"
        return str(base) + "_black.svg"
