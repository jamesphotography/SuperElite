#!/usr/bin/env python3
"""
SuperElite 日志模块
支持同时输出到控制台和文件
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


class SuperEliteLogger:
    """SuperElite 日志管理器"""
    
    def __init__(self, name: str = "SuperElite"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.file_handler = None
        self.console_handler = None
        self._setup_console_handler()
    
    def _setup_console_handler(self):
        """设置控制台输出"""
        if self.console_handler:
            return
        
        self.console_handler = logging.StreamHandler()
        self.console_handler.setLevel(logging.INFO)
        
        # 简洁的控制台格式
        console_format = logging.Formatter('%(message)s')
        self.console_handler.setFormatter(console_format)
        self.logger.addHandler(self.console_handler)
    
    def enable_file_logging(self, log_path: Optional[str] = None) -> str:
        """
        启用文件日志
        
        Args:
            log_path: 日志文件路径，None 则自动生成
            
        Returns:
            实际日志文件路径
        """
        if self.file_handler:
            self.logger.removeHandler(self.file_handler)
        
        # 自动生成日志文件名
        if log_path is None or log_path == "":
            log_dir = Path.home() / ".superelite" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_path = str(log_dir / f"superelite_{timestamp}.log")
        else:
            # 确保目录存在
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        
        self.file_handler = logging.FileHandler(log_path, encoding='utf-8')
        self.file_handler.setLevel(logging.DEBUG)
        
        # 详细的文件格式
        file_format = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.file_handler.setFormatter(file_format)
        self.logger.addHandler(self.file_handler)
        
        return log_path
    
    def set_verbose(self, verbose: bool = True):
        """设置详细模式"""
        if verbose:
            self.console_handler.setLevel(logging.DEBUG)
        else:
            self.console_handler.setLevel(logging.INFO)
    
    def set_quiet(self, quiet: bool = True):
        """设置安静模式 - 只输出错误和最终结果"""
        if quiet:
            self.console_handler.setLevel(logging.ERROR)
    
    def info(self, message: str):
        """INFO 级别日志"""
        self.logger.info(message)
    
    def debug(self, message: str):
        """DEBUG 级别日志"""
        self.logger.debug(message)
    
    def warning(self, message: str):
        """WARNING 级别日志"""
        self.logger.warning(message)
    
    def error(self, message: str):
        """ERROR 级别日志"""
        self.logger.error(message)
    
    def section(self, title: str):
        """打印分节标题"""
        line = "=" * 60
        self.info(f"\n{line}")
        self.info(f"  {title}")
        self.info(line)
    
    def subsection(self, title: str):
        """打印子节标题"""
        self.info(f"\n{'─' * 40}")
        self.info(f"  {title}")
        self.info('─' * 40)
    
    def score_result(self, index: int, total: int, filename: str, 
                     score: float, rating: int):
        """记录评分结果"""
        stars = "★" * rating + "☆" * (5 - rating)
        self.info(f"[{index:4d}/{total}] {filename[:40]:<40} → {score:5.1f} → {stars}")
    
    def summary(self, stats: dict):
        """打印统计摘要"""
        self.section("处理完成")
        
        if "counts" in stats:
            counts = stats["counts"]
            self.info("各星级分布:")
            for star in range(5, 0, -1):
                count = counts.get(star, 0)
                bar = "█" * min(count // 2, 30)
                self.info(f"  {'★' * star}{'☆' * (5-star)}: {count:4d} {bar}")
        
        if "total_time" in stats:
            total = stats.get("total_images", 1)
            time = stats["total_time"]
            self.info(f"\n总耗时: {time:.1f}s ({time/total:.2f}s/张)")
        
        if "thresholds" in stats:
            t = stats["thresholds"]
            self.info(f"使用阈值: {t[0]:.1f}/{t[1]:.1f}/{t[2]:.1f}/{t[3]:.1f}")


# 全局日志实例
_logger = None


def get_logger() -> SuperEliteLogger:
    """获取全局日志实例"""
    global _logger
    if _logger is None:
        _logger = SuperEliteLogger()
    return _logger


def setup_logging(log_path: Optional[str] = None, verbose: bool = False, quiet: bool = False) -> str:
    """
    设置日志
    
    Args:
        log_path: 日志文件路径，None 表示不输出到文件，"" 表示自动生成
        verbose: 是否启用详细模式
        quiet: 是否启用安静模式（只输出错误和最终结果）
        
    Returns:
        日志文件路径（如果启用了文件日志）
    """
    logger = get_logger()
    
    if quiet:
        logger.set_quiet(True)
    elif verbose:
        logger.set_verbose(True)
    
    if log_path is not None:
        return logger.enable_file_logging(log_path)
    
    return ""
