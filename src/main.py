import ctypes
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


def _lock_win_timer(period_ms: int = 1) -> int | None:
    """
    将 Windows 多媒体定时器精度锁定到 period_ms 毫秒。

    Windows 默认精度约 15.62 ms（约 64 fps 上限），设为 1 ms 后
    QTimer 可以按需以 ≤1 ms 的粒度触发，使高刷屏上的动画帧率
    能够真正跟上屏幕刷新率。

    返回实际设置的周期（供退出时 timeEndPeriod 使用），非 Windows
    平台返回 None。
    """
    if sys.platform != "win32":
        return None
    ret = ctypes.windll.winmm.timeBeginPeriod(period_ms)
    # timeBeginPeriod 返回 0 (TIMERR_NOERROR)"""  """ 表示成功
    return period_ms if ret == 0 else None


def _unlock_win_timer(period_ms: int | None) -> None:
    """释放之前申请的定时器精度，还原系统全局状态。"""
    if sys.platform == "win32" and period_ms is not None:
        ctypes.windll.winmm.timeEndPeriod(period_ms)


def _patch_smooth_scroll_fps(app: QApplication) -> None:
    """
    将 qfluentwidgets 滚动引擎的 fps 从硬编码的 60 修改为当前
    主屏幕的实际刷新率（最低保留 60）。

    qfluentwidgets 的 SmoothScrollEngineBase 使用
        self.smoothMoveTimer.start(int(1000 / self.fps))
    以及
        self.stepsTotal = self.fps * self.duration / 1000
    两处均依赖 self.fps。将其提升到屏幕刷新率后，定时器触发间隔
    和插值步数都会同步缩短/增多，动画更新次数与屏幕刷新率匹配，
    从而消除高刷屏上滚动"掉帧"的视觉感。

    实现方式：包装 __init__，在原始初始化完成后覆写 fps，不修改
    任何库源码，也不影响已实例化的对象。
    """
    screen = app.primaryScreen()
    target_fps = max(60, int(screen.refreshRate())) if screen else 60

    try:
        from qfluentwidgets.common.smooth_scroll import SmoothScrollEngineBase

        _original_init = SmoothScrollEngineBase.__init__

        def _patched_init(self, widget, orient=Qt.Orientation.Vertical):
            _original_init(self, widget, orient)
            self.fps = target_fps

        SmoothScrollEngineBase.__init__ = _patched_init
    except Exception:
        # 如果 qfluentwidgets 内部结构变化导致导入失败，静默跳过，
        # 不影响应用正常启动。
        pass


if __name__ == "__main__":
    timer_period = _lock_win_timer(1)

    app = QApplication(sys.argv)

    # 必须在任何 ScrollArea / SmoothScrollArea 实例化之前完成 patch
    _patch_smooth_scroll_fps(app)

    # 延迟导入：确保 patch 在 UI 树构建前生效
    from ui.pages.home_page import HomePage

    home = HomePage()
    home.show()

    exit_code = app.exec()

    _unlock_win_timer(timer_period)
    sys.exit(exit_code)
