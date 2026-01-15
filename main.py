#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SuperElite / 摄影评片 - GUI 入口点
PySide6 版本
"""

import sys
import os

# 修复 macOS PyInstaller 打包后的多进程问题
import multiprocessing
if sys.platform == 'darwin':
    multiprocessing.set_start_method('spawn', force=True)
multiprocessing.freeze_support()

# 确保模块路径正确
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from ui.main_window import SuperEliteMainWindow

# 全局窗口引用，防止重复创建
_main_window = None


def main():
    """主函数"""
    global _main_window
    
    # 检查是否已有 QApplication 实例
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # 设置应用属性
    app.setApplicationName("SuperElite")
    app.setApplicationDisplayName("摄影评片")
    app.setOrganizationName("JamesPhotography")
    app.setOrganizationDomain("jamesphotography.com.au")
    
    # 设置应用图标
    icon_path = os.path.join(os.path.dirname(__file__), "img", "icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # 创建并显示窗口
    if _main_window is None:
        _main_window = SuperEliteMainWindow()
        _main_window.show()
    else:
        _main_window.raise_()
        _main_window.activateWindow()
    
    # 运行事件循环
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
