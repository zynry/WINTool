# coding: utf-8
"""用户配置管理服务。

以 JSON 格式持久化存储用户在设置页中的选项。
"""

from __future__ import annotations

import json
from pathlib import Path


# 可选的默认启动页面
PAGE_OPTIONS: list[tuple[str, str]] = [
    ("file_hash", "文件哈希值"),
    ("json", "JSON 格式化"),
    ("qrcode", "二维码解码"),
]

_DEFAULT_CONFIG = {
    "default_page": "file_hash",
    "theme_mode": "Dark",
    "theme_color": "#ff009faa",
}


class SettingsService:
    """管理用户配置的读写。"""

    _instance: SettingsService | None = None

    def __new__(cls) -> SettingsService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._config = {}
            cls._instance._path = Path(__file__).resolve().parent.parent.parent / "config" / "user_settings.json"
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        """从磁盘加载配置，文件不存在时使用默认值。"""
        if self._path.exists():
            try:
                with self._path.open("r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self._config = {**_DEFAULT_CONFIG, **loaded}
                return
            except Exception:
                pass
        self._config = dict(_DEFAULT_CONFIG)
        self._save()

    def _save(self) -> None:
        """将当前配置写入磁盘。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(self._config, f, ensure_ascii=False, indent=4)

    def get(self, key: str, default=None):
        return self._config.get(key, default)

    def set(self, key: str, value) -> None:
        self._config[key] = value
        self._save()

    @property
    def default_page(self) -> str:
        return self._config.get("default_page", "file_hash")

    @default_page.setter
    def default_page(self, value: str) -> None:
        self._config["default_page"] = value
        self._save()

    @property
    def theme_mode(self) -> str:
        return self._config.get("theme_mode", "Dark")

    @theme_mode.setter
    def theme_mode(self, value: str) -> None:
        self._config["theme_mode"] = value
        self._save()

    @property
    def theme_color(self) -> str:
        return self._config.get("theme_color", "#ff009faa")

    @theme_color.setter
    def theme_color(self, value: str) -> None:
        self._config["theme_color"] = value
        self._save()
