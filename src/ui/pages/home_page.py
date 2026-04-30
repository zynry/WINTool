from pathlib import Path

from PySide6.QtGui import QIcon
from qfluentwidgets import FluentIcon as FIF
from qfluentwidgets import FluentWindow, NavigationItemPosition

from services.settings_service import SettingsService
from ui.pages.fhash_page import FileHashPage
from ui.pages.json_page import JsonPage
from ui.pages.qrcode_page import QRCodePage
from ui.pages.settings_page import SettingsPage
from ui.widgets.custom_widget import SidebarIcon
from utils.resource_path import res


class HomePage(FluentWindow):
    """主界面"""

    def __init__(self):
        super().__init__()

        self.CFHash = FileHashPage(self)
        self.jsonInterface = JsonPage(self)
        self.qrInterface = QRCodePage(self)
        self.settingInterface = SettingsPage(self)

        self.setui()
        self.initWindow()
        self._switch_to_default_page()

    def setui(self):

        self.addSubInterface(self.CFHash, SidebarIcon.FILE_HASH, "文件哈希值")
        self.addSubInterface(self.jsonInterface, SidebarIcon.JSON, "JSON 格式化")
        self.addSubInterface(self.qrInterface, SidebarIcon.QRCODE, "二维码解码")

        self.addSubInterface(
            self.settingInterface,
            FIF.SETTING,
            "应用设置",
            NavigationItemPosition.BOTTOM,
        )

    def _switch_to_default_page(self):
        """根据用户配置切换到默认页面。"""
        svc = SettingsService()
        mapping = {
            "file_hash": self.CFHash,
            "json": self.jsonInterface,
            "qrcode": self.qrInterface,
        }
        target = mapping.get(svc.default_page)
        if target:
            self.switchTo(target)

    def initWindow(self):
        self.resize(800, 700)
        self.setWindowIcon(QIcon(res("icon/app_icon_D.svg")))
        self.setWindowTitle("WINTools")
