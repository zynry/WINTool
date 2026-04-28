# -*- mode: python ; coding: utf-8 -*-
"""
WINTools PyInstaller 打包配置
生成：单目录分发包（onedir），含所有资源文件。

用法：
    在项目根目录执行：
    pyinstaller WINTools.spec
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)          # 项目根目录（WINTools.spec 所在位置）
SRC  = ROOT / "src"

# ── 要打包进去的数据文件 ──────────────────────────────
# 格式：(源路径,  目标目录相对于 _MEIPASS)
added_files = [
    # 所有图标资源
    (str(ROOT / "resources"), "resources"),
    # qfluentwidgets 字体/资源（部分版本需要显式包含）
    # 如果打包后出现字体异常可取消注释：
    # (str(ROOT / ".venv/Lib/site-packages/qfluentwidgets/resource"), "qfluentwidgets/resource"),
]

a = Analysis(
    [str(SRC / "main.py")],
    pathex=[str(SRC)],              # 让 PyInstaller 能找到 ui/services/utils 等包
    binaries=[],
    datas=added_files,
    hiddenimports=[
        # PySide6 插件
        "PySide6.QtSvg",
        "PySide6.QtSvgWidgets",
        "PySide6.QtXml",
        "PySide6.QtNetwork",
        # qfluentwidgets 动态导入的模块
        "qfluentwidgets",
        "qfluentwidgets.common",
        "qfluentwidgets.components",
        "qfluentwidgets.window",
        # 项目自身包
        "ui",
        "ui.pages",
        "ui.pages.home_page",
        "ui.pages.fhash_page",
        "ui.pages.json_page",
        "ui.pages.settings_page",
        "ui.widgets",
        "ui.widgets.custom_widget",
        "services",
        "utils",
        "utils.resource_path",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "notebook",
        "pytest",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # onedir 模式：二进制单独放
    name="WINTools",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                       # 使用 UPX 压缩（无 UPX 时自动跳过）
    console=False,                  # 不弹出控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "resources" / "icon" / "app_icon.ico"),  # 应用图标
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="WINTools",                # 输出目录名：dist/WINTools/
)
