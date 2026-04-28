# WINTools

一款基于 **PySide6 + qfluentwidgets** 开发的 Windows 桌面工具集，采用 Fluent Design 风格界面。

## 技术栈

- **Python 3.x**
- **PySide6** — Qt6 的 Python 绑定
- **qfluentwidgets** — Fluent Design 风格 UI 组件库
- **QSS** — Qt 样式表，支持深色/浅色主题切换

## 项目结构

```
WINTool/
├── config/
│   └── config.json              # qfluentwidgets 全局配置（字体、主题色、主题模式）
├── resources/
│   └── icon/
│       ├── app_icon_D.svg       # 应用图标
│       ├── app_icon_E.svg
│       └── sidebar_button/      # 侧边栏自定义图标（黑白双色，自动随主题切换）
│           ├── file_hash_black.svg
│           └── file_hash_white.svg
├── src/
│   ├── main.py                  # 应用入口
│   ├── models/                  # 数据模型（预留）
│   ├── services/
│   │   └── hash_service.py      # 哈希计算服务（多算法并发、进度回调、CPU 检测）
│   ├── ui/
│   │   ├── dialogs/             # 弹窗组件（预留）
│   │   ├── pages/
│   │   │   ├── home_page.py     # 主窗口（FluentWindow + 侧边栏导航）
│   │   │   ├── fhash_page.py    # 文件哈希值页面
│   │   │   └── settings_page.py # 应用设置页面
│   │   ├── qss/
│   │   │   ├── dark/
│   │   │   │   └── default_dark.qss
│   │   │   └── light/
│   │   │       └── default_light.qss
│   │   └── widgets/
│   │       └── custom_widget.py # 基础组件 + 自定义图标枚举
│   └── utils/                   # 工具函数（预留）
└── tests/                       # 测试目录
```

## 核心模块说明

### `src/main.py`
应用入口，包含两项系统级优化：
- **Windows 多媒体定时器精度锁定**：将定时器精度设为 1ms，使 `QTimer` 能以更高粒度触发，提升高刷屏动画流畅度。
- **平滑滚动 FPS 动态 Patch**：在实例化任何滚动区域前，自动将 `qfluentwidgets` 的平滑滚动引擎 FPS 从硬编码 60 提升到当前屏幕实际刷新率，消除高刷屏滚动掉帧感。

### `src/ui/pages/home_page.py`
主窗口继承自 `FluentWindow`，负责：
- 侧边栏导航栏配置
- 子界面注册（文件哈希值、应用设置）

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
- **卡片式布局**：每个文件独立成卡，含圆角、主题自适应背景、 Fluent 风格分隔线
- **同时计算三算法**：一次读取自动得出 MD5、SHA1、SHA256，无需手动切换
- 顶部显示根据 CPU 核心数推荐的**并行计算数量**提示
- 每个文件独立**进度条**实时展示计算进度
- 每种算法的哈希值独立显示，均可一键**复制**到剪贴板
- 支持从列表中移除单个文件或一键清空
- 使用 `QScrollArea` + `qfluentwidgets.ScrollBar` 组合，既解决滚动回弹问题又保持 Fluent 风格滚动条

### `src/ui/pages/settings_page.py`
**应用设置**页面，已支持：
- **主题模式**：浅色 / 深色 / 跟随系统设置
- **主题色**：实时调整应用强调色（默认 `#ff931daa`）

### `src/ui/widgets/custom_widget.py`
- **`_Widget`**：所有子界面的基类，去除 `QFrame` 默认边框与背景，使 `FluentWindow` 背景能正确透传。
- **`SidebarIcon`**：自定义侧边栏图标枚举。遵循约定：将 `<name>_black.svg` 和 `<name>_white.svg` 放入 `resources/icon/sidebar_button/`，再在枚举中添加成员即可自动支持主题切换。

### `config/config.json`
qfluentwidgets 的配置文件，定义：
- 字体回退栈：`Segoe UI`、`Microsoft YaHei`、`PingFang SC`
- 默认主题色：`#ff931daa`
- 默认主题模式：`Light`

## 当前状态

| 模块 | 状态 |
|------|------|
| 应用框架 & 导航 | 已完成 |
| 主题 & 个性化设置 | 已完成 |
| 文件哈希值功能 | 已完成 |
| 其他工具模块 | 预留扩展 |
