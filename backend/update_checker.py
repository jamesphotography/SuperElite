# -*- coding: utf-8 -*-
"""
SuperElite - 版本更新检测器
通过 GitHub Releases API 检测新版本
"""

import urllib.request
import json
import re
from typing import Optional, Tuple
from PySide6.QtCore import QThread, Signal


# GitHub 仓库信息
GITHUB_REPO = "jamesphotography/SuperElite"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"

# 当前版本 (与 main_window.py 保持一致)
CURRENT_VERSION = "1.0.0"


def parse_version(version_str: str) -> Tuple[int, ...]:
    """
    解析版本号字符串为可比较的元组
    
    Args:
        version_str: 版本字符串，如 "v1.0.0" 或 "1.2.3"
    
    Returns:
        版本号元组，如 (1, 0, 0)
    """
    # 移除 'v' 前缀
    clean = version_str.lstrip('vV')
    # 提取数字部分
    match = re.match(r'(\d+)\.(\d+)\.(\d+)', clean)
    if match:
        return tuple(int(x) for x in match.groups())
    return (0, 0, 0)


def compare_versions(v1: str, v2: str) -> int:
    """
    比较两个版本号
    
    Returns:
        1 if v1 > v2
        0 if v1 == v2
        -1 if v1 < v2
    """
    t1 = parse_version(v1)
    t2 = parse_version(v2)
    
    if t1 > t2:
        return 1
    elif t1 < t2:
        return -1
    return 0


class UpdateChecker(QThread):
    """
    后台检查更新的线程
    
    Signals:
        update_available: 发现新版本时发出，参数为 (latest_version, download_url, release_notes)
        no_update: 当前已是最新版本
        check_failed: 检查失败
    """
    update_available = Signal(str, str, str)  # (version, url, notes)
    no_update = Signal()
    check_failed = Signal(str)  # error message
    
    def __init__(self, current_version: str = CURRENT_VERSION, parent=None):
        super().__init__(parent)
        self.current_version = current_version
    
    def run(self):
        """执行版本检查"""
        try:
            # 请求 GitHub API
            request = urllib.request.Request(
                GITHUB_API_URL,
                headers={
                    'User-Agent': 'SuperElite-UpdateChecker',
                    'Accept': 'application/vnd.github.v3+json'
                }
            )
            
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            latest_version = data.get('tag_name', '')
            download_url = data.get('html_url', GITHUB_RELEASES_URL)
            release_notes = data.get('body', '')[:500]  # 限制长度
            
            if not latest_version:
                self.check_failed.emit("无法获取最新版本信息")
                return
            
            # 比较版本
            if compare_versions(latest_version, self.current_version) > 0:
                self.update_available.emit(latest_version, download_url, release_notes)
            else:
                self.no_update.emit()
                
        except urllib.error.URLError as e:
            self.check_failed.emit(f"网络错误: {e.reason}")
        except json.JSONDecodeError:
            self.check_failed.emit("解析版本信息失败")
        except Exception as e:
            self.check_failed.emit(f"检查更新失败: {str(e)}")


def check_for_updates_sync() -> Optional[dict]:
    """
    同步检查更新 (用于调试)
    
    Returns:
        dict with 'has_update', 'latest_version', 'download_url', 'notes'
        or None if check failed
    """
    try:
        request = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                'User-Agent': 'SuperElite-UpdateChecker',
                'Accept': 'application/vnd.github.v3+json'
            }
        )
        
        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        latest_version = data.get('tag_name', '')
        
        return {
            'has_update': compare_versions(latest_version, CURRENT_VERSION) > 0,
            'latest_version': latest_version,
            'current_version': CURRENT_VERSION,
            'download_url': data.get('html_url', GITHUB_RELEASES_URL),
            'notes': data.get('body', '')[:500]
        }
    except Exception as e:
        print(f"检查更新失败: {e}")
        return None


if __name__ == "__main__":
    # 测试
    result = check_for_updates_sync()
    if result:
        print(f"当前版本: {result['current_version']}")
        print(f"最新版本: {result['latest_version']}")
        print(f"有更新: {result['has_update']}")
        print(f"下载地址: {result['download_url']}")
    else:
        print("检查更新失败")
