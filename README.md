# WINTools

一款基于 **PySide6 + qfluentwidgets** 开发的 Windows 桌面工具集，采用 Fluent Design 风格界面。

## 技术栈

- **Python 3.x**
- **PySide6** — Qt6 的 Python 绑定
- **qfluentwidgets** — Fluent Design 风格 UI 组件库
- **QSS** — Qt 样式表，支持深色/浅色主题切换
- **OpenCV + zxing-cpp** — 二维码图像解码
- **PyInstaller** — 打包为可分发应用

## 项目结构

```
WINTool/
├── config/
│   ├── config.json              # qfluentwidgets 全局配置（字体、主题色、主题模式）
│   └── user_settings.json       # 用户设置（主题、默认页面等，JSON 格式持久化）
├── resources/
│   └── icon/
│       ├── app_icon_D.svg       # 应用图标
│       ├── app_icon_E.svg
│       ├── app_icon.ico         # 打包用多尺寸图标
│       └── sidebar_button/      # 侧边栏自定义图标（黑白双色，自动随主题切换）
│           ├── file_hash_black.svg
│           ├── file_hash_white.svg
│           ├── json_black.svg
│           ├── json_white.svg
│           ├── qrcode_black.svg
│           └── qrcode_white.svg
├── src/
│   ├── main.py                  # 应用入口
│   ├── models/                  # 数据模型（预留）
│   ├── services/
│   │   ├── hash_service.py      # 哈希计算服务（多算法并发、进度回调、CPU 检测）
│   │   └── settings_service.py  # 用户配置管理服务（JSON 持久化）
│   ├── ui/
│   │   ├── dialogs/             # 弹窗组件（预留）
│   │   ├── pages/
│   │   │   ├── home_page.py     # 主窗口（FluentWindow + 侧边栏导航）
│   │   │   ├── fhash_page.py    # 文件哈希值页面
│   │   │   ├── json_page.py     # JSON 格式化页面
│   │   │   ├── qrcode_page.py   # 二维码解码页面
│   │   │   └── settings_page.py # 应用设置页面
│   │   ├── qss/
│   │   │   ├── dark/
│   │   │   │   └── default_dark.qss
│   │   │   └── light/
│   │   │       └── default_light.qss
│   │   └── widgets/
│   │       └── custom_widget.py # 基础组件 + 自定义图标枚举
│   └── utils/
│       └── resource_path.py     # 资源路径工具（兼容开发与 PyInstaller 打包环境）
├── tests/                       # 测试目录
└── WINTools.spec                # PyInstaller 打包配置（onedir 模式）
```

## 核心模块说明

### `src/main.py`
应用入口，包含两项系统级优化：
- **Windows 多媒体定时器精度锁定**：将定时器精度设为 1ms，使 `QTimer` 能以更高粒度触发，提升高刷屏动画流畅度。
- **平滑滚动 FPS 动态 Patch**：在实例化任何滚动区域前，自动将 `qfluentwidgets` 的平滑滚动引擎 FPS 从硬编码 60 提升到当前屏幕实际刷新率，消除高刷屏滚动掉帧感。

### `src/ui/pages/home_page.py`
主窗口继承自 `FluentWindow`，负责：
- 侧边栏导航栏配置
- 子界面注册（文件哈希值、JSON 格式化、二维码解码、应用设置）
- 启动时根据 `user_settings.json` 中的 `default_page` 自动切换到用户指定的默认页面

### `src/services/settings_service.py`
**用户配置管理服务**，单例模式，JSON 持久化：
- 统一存储所有用户设置项到 `config/user_settings.json`
- 支持 `default_page`（默认打开页面）、`theme_mode`（主题模式）、`theme_color`（主题色）
- 启动时自动加载，变更时即时写入磁盘

### `src/services/hash_service.py`
**哈希计算服务层**，核心能力：
- 支持 **MD5 / SHA1 / SHA256** 三种算法
- **`calculate_file_hashes`**：单次文件读取，同时计算多个算法哈希，避免重复 I/O
- **`calculate_hashes_concurrent`**：基于 `ThreadPoolExecutor` 的并发批量计算，自动根据 CPU 核心数控制并发度
- **进度回调**：每个文件独立进度报告，驱动 UI 进度条
- **CPU 检测**：根据逻辑核心数推荐最佳并发文件数

### `src/ui/pages/fhash_page.py`
**文件哈希值**功能页面，已完整实现：
- 支持**文件拖拽**和**多文件选择**添加到列表
- **卡片式布局**：每个文件独立成卡，含圆角、主题自适应背景、Fluent 风格分隔线
- **同时计算三算法**：一次读取自动得出 MD5、SHA1、SHA256，无需手动切换
- 顶部显示根据 CPU 核心数推荐的**并行计算数量**提示
- 每个文件独立**进度条**实时展示计算进度
- 每种算法的哈希值独立显示，均可一键**复制**到剪贴板
- 支持从列表中移除单个文件或一键清空
- 使用 `QScrollArea` + `qfluentwidgets.ScrollBar` 组合，既解决滚动回弹问题又保持 Fluent 风格滚动条

### `src/ui/pages/json_page.py`
**JSON 格式化**功能页面，已完整实现：
- **输入 / 输出分栏**：使用 `QSplitter` 水平分割，可拖动调整输入区与结果区比例
- **卡片式布局**：输入区和输出区均采用圆角卡片包裹，主题自适应背景
- **格式化**：将压缩或凌乱的 JSON 一键排版为带缩进的可读格式
- **压缩**：将 JSON 去除所有空白，压缩为最小体积
- **复制结果**：一键将格式化后的内容复制到剪贴板
- **实时字符统计**：底部状态栏实时显示输入字符数
- **错误提示**：输入非法 JSON 时，底部状态栏变红并弹出 `InfoBar` 错误提示
- **JSON 语法高亮**：VS Code 风格配色，Key/Value/字符串/数字/布尔值均有独立颜色
- **缩进指南线**：自定义 `paintEvent` 绘制层级连线，便于阅读嵌套结构
- 等宽字体显示，便于开发者阅读和比对

### `src/ui/pages/qrcode_page.py`
**二维码解码**功能页面，已完整实现：
- **图片导入**：支持文件选择、全局拖拽、`Ctrl+V` 粘贴三种方式导入二维码图片
- **解码引擎**：优先使用 **zxing-cpp**（高识别率），回退 OpenCV `QRCodeDetector` + 7 种图像预处理变体
- **结果展示**：左侧缩略图预览 + 右侧大号文本框完整展示解码内容，不再截断
- **快捷操作**：
  - **复制内容**：一键将解码结果复制到剪贴板
  - **打开链接**：若解码结果为 URL（`http://` / `https://`），自动显示按钮，点击用系统浏览器打开
- **状态提示**：醒目显示 `✅ 解码成功` 或 `❌ 未检测到`
- 每次导入新图片自动清空上次结果
- 支持批量导入，底部简表展示多图解码概览（可选隐藏）

### `src/utils/resource_path.py`
资源路径工具，兼容开发与 PyInstaller 打包环境：
- 开发时：使用源码目录中的 `resources/` 文件夹
- 打包后：使用 PyInstaller 解压目录 `sys._MEIPASS/resources`

### `src/ui/widgets/custom_widget.py`
- **`_Widget`**：所有子界面的基类，去除 `QFrame` 默认边框与背景，使 `FluentWindow` 背景能正确透传。
- **`SidebarIcon`**：自定义侧边栏图标枚举。遵循约定：将 `<name>_black.svg` 和 `<name>_white.svg` 放入 `resources/icon/sidebar_button/`，再在枚举中添加成员即可自动支持主题切换。

### `config/user_settings.json`
用户配置文件，JSON 格式，定义：
- `default_page`：默认打开页面（`file_hash` / `json` / `qrcode`）
- `theme_mode`：主题模式（`Light` / `Dark` / `Auto`）
- `theme_color`：主题色（如 `#ff009faa`）

### `config/config.json`
qfluentwidgets 的配置文件，定义：
- 字体回退栈：`Segoe UI`、`Microsoft YaHei`、`PingFang SC`

### `WINTools.spec`
PyInstaller 打包配置（onedir 模式）：
- 包含 `resources/` 目录作为数据文件
- 隐藏导入 PySide6 插件及项目内部模块
- 使用 `app_icon.ico` 作为可执行文件图标
- 输出目录：`dist/WINTools/`

## 打包说明

```bash
# 安装 PyInstaller
python -m pip install pyinstaller

# 执行打包
pyinstaller WINTools.spec

# 输出目录
dist/WINTools/
```

打包后应用已包含所有资源文件和依赖，可直接复制 `dist/WINTools/` 文件夹分发。

## 当前状态

| 模块 | 状态 |
|------|------|
| 应用框架 & 导航 | 已完成 |
| 主题 & 个性化设置 | 已完成（统一 JSON 持久化） |
| 文件哈希值功能 | 已完成 |
| JSON 格式化 | 已完成 |
| 二维码解码 | 已完成 |
| PyInstaller 打包 | 已完成 |
| 其他工具模块 | 预留扩展 |
