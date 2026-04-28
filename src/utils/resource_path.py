# coding: utf-8
"""
资源路径工具模块。

打包后 PyInstaller 将资源文件解压到 sys._MEIPASS，
开发时则使用源码目录中的 resources 文件夹。
"""

import sys
from pathlib import Path


def resource_root() -> Path:
    """返回资源根目录（resources/）的绝对路径。

    - 打包环境（PyInstaller）：sys._MEIPASS / resources
    - 开发环境：项目根目录 / resources
    """
    if getattr(sys, "frozen", False):
        # PyInstaller 解包目录
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        # 本文件位于 src/utils/，往上两层是项目根
        base = Path(__file__).resolve().parent.parent.parent
    return base / "resources"


def res(relative: str) -> str:
    """返回资源文件的字符串绝对路径。

    Parameters
    ----------
    relative:
        相对于 resources/ 目录的路径，例如 "icon/app_icon_D.svg"
    """
    return str(resource_root() / relative)
