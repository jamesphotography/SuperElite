# -*- coding: utf-8 -*-
"""
SuperElite - 自动校准确认对话框
显示建议阈值和分数分布，让用户确认
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ui.styles import COLORS, FONTS, GLOBAL_STYLE


class CalibrateConfirmDialog(QDialog):
    """自动校准确认对话框"""
    
    def __init__(self, suggested_thresholds, counts, stats, parent=None):
        """
        Args:
            suggested_thresholds: (t4, t3, t2, t1) 建议阈值
            counts: {rating: count} 各星级数量
            stats: {max, min, avg} 分数统计
        """
        super().__init__(parent)
        
        self.suggested_thresholds = suggested_thresholds
        self.counts = counts
        self.stats = stats
        self.accepted = False
        
        self._setup_window()
        self._setup_ui()
    
    def _setup_window(self):
        """设置窗口属性"""
        self.setWindowTitle("自动校准 - 确认阈值")
        self.setMinimumWidth(550)
        self.setModal(True)
        
        # 应用全局样式
        self.setStyleSheet(GLOBAL_STYLE + f"""
            QDialog {{
                background-color: {COLORS['bg_primary']};
            }}
        """)
    
    def _setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(20)
        
        # 标题
        title = QLabel("📊 分数分布分析")
        title.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 18px;
            font-weight: 600;
        """)
        layout.addWidget(title)
        
        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setStyleSheet(f"background-color: {COLORS['border']};")
        layout.addWidget(line1)
        
        # 统计信息
        self._create_stats_section(layout)
        
        # 建议阈值
        self._create_thresholds_section(layout)
        
        # 星级分布
        self._create_distribution_section(layout)
        
        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setStyleSheet(f"background-color: {COLORS['border']};")
        layout.addWidget(line2)
        
        # 说明
        hint = QLabel("💡 提示：建议阈值基于照片分数分布自动计算，保证星级均匀分布")
        hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        
        layout.addStretch()
        
        # 按钮
        self._create_button_section(layout)
    
    def _create_stats_section(self, parent_layout):
        """创建统计信息区域"""
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(20)
        
        # 最高分
        max_label = QLabel(f"最高分: {self.stats['max']:.1f}")
        max_label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 14px;
            font-family: {FONTS['mono']};
        """)
        stats_layout.addWidget(max_label)
        
        # 最低分
        min_label = QLabel(f"最低分: {self.stats['min']:.1f}")
        min_label.setStyleSheet(f"""
            color: {COLORS['text_secondary']};
            font-size: 14px;
            font-family: {FONTS['mono']};
        """)
        stats_layout.addWidget(min_label)
        
        # 平均分
        avg_label = QLabel(f"平均: {self.stats['avg']:.1f}")
        avg_label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 14px;
            font-weight: 500;
            font-family: {FONTS['mono']};
        """)
        stats_layout.addWidget(avg_label)
        
        stats_layout.addStretch()
        parent_layout.addLayout(stats_layout)
    
    def _create_thresholds_section(self, parent_layout):
        """创建建议阈值区域"""
        group_label = QLabel("📐 建议阈值 (基于20%均分):")
        group_label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 15px;
            font-weight: 500;
        """)
        parent_layout.addWidget(group_label)
        
        # 阈值网格
        grid = QGridLayout()
        grid.setSpacing(12)
        grid.setColumnStretch(1, 1)
        
        t4, t3, t2, t1 = self.suggested_thresholds
        
        thresholds_data = [
            ("4★ 阈值:", t4, f"≥ {t4:.1f}"),
            ("3★ 阈值:", t3, f"≥ {t3:.1f}"),
            ("2★ 阈值:", t2, f"≥ {t2:.1f}"),
            ("1★ 阈值:", t1, f"≥ {t1:.1f}"),
        ]
        
        for row, (label_text, value, display) in enumerate(thresholds_data):
            # 标签
            label = QLabel(label_text)
            label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
            grid.addWidget(label, row, 0)
            
            # 数值
            value_label = QLabel(display)
            value_label.setStyleSheet(f"""
                color: {COLORS['text_primary']};
                font-size: 15px;
                font-weight: 600;
                font-family: {FONTS['mono']};
            """)
            grid.addWidget(value_label, row, 1)
        
        parent_layout.addLayout(grid)
    
    def _create_distribution_section(self, parent_layout):
        """创建星级分布区域"""
        group_label = QLabel("⭐ 预计星级分布:")
        group_label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 15px;
            font-weight: 500;
        """)
        parent_layout.addWidget(group_label)
        
        # 分布信息
        dist_layout = QVBoxLayout()
        dist_layout.setSpacing(8)
        
        total = sum(self.counts.values())
        
        for rating in [4, 3, 2, 1, 0]:
            count = self.counts.get(rating, 0)
            percent = (count / total * 100) if total > 0 else 0
            
            star_text = "★" * rating + "☆" * (4 - rating)
            dist_text = f"{star_text}  {count}张 ({percent:.0f}%)"
            
            dist_label = QLabel(dist_text)
            dist_label.setStyleSheet(f"""
                color: {COLORS['text_secondary']};
                font-size: 13px;
                font-family: {FONTS['mono']};
            """)
            dist_layout.addWidget(dist_label)
        
        parent_layout.addLayout(dist_layout)
    
    def _create_button_section(self, parent_layout):
        """创建按钮区域"""
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        btn_layout.addStretch()
        
        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondary")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        # 确认按钮
        confirm_btn = QPushButton("使用建议阈值")
        confirm_btn.setMinimumWidth(140)
        confirm_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(confirm_btn)
        
        parent_layout.addLayout(btn_layout)
    
    def _on_confirm(self):
        """确认使用建议阈值"""
        self.accepted = True
        self.accept()
    
    def get_thresholds(self):
        """获取确认的阈值"""
        if self.accepted:
            return self.suggested_thresholds
        return None
