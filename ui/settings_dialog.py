# -*- coding: utf-8 -*-
"""
SuperElite - 设置对话框
极简艺术风格设置页面
"""

import sys
from pathlib import Path
from typing import Optional, Tuple

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QSlider, QPushButton, QCheckBox, QGroupBox,
    QRadioButton, QButtonGroup, QFrame, QSpacerItem, QSizePolicy
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

# 添加 backend 到路径
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from preset_manager import get_preset_manager, Preset
from ui.styles import COLORS, FONTS, GLOBAL_STYLE
from ui.custom_dialogs import StyledMessageBox


class SettingsDialog(QDialog):
    """设置对话框 - 极简艺术风格"""
    
    # 信号：配置已更改 (quality_weight, aesthetic_weight, thresholds, auto_calibrate, write_xmp, organize)
    config_changed = Signal(float, float, tuple, bool, bool, bool)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 预设管理器
        self.preset_manager = get_preset_manager()
        
        # 当前配置
        self.quality_weight = 0.4
        self.aesthetic_weight = 0.6
        self.thresholds = (78.0, 72.0, 66.0, 58.0)
        self.auto_calibrate = False
        self.write_xmp = True
        self.organize = False
        
        self._setup_window()
        self._setup_ui()
        self._load_user_config()
    
    def _setup_window(self):
        """设置窗口属性"""
        self.setWindowTitle("设置 / Settings")
        self.setMinimumWidth(500)
        self.setMinimumHeight(600)
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
        layout.setSpacing(16)
        
        #  只保留阈值设置
        self._create_threshold_section(layout)
        
        layout.addStretch()
        
        # 底部按钮
        self._create_button_section(layout)
    
    # ==================== 阈值设置区域 ====================
    def _create_threshold_section(self, parent_layout):
        """创建阈值设置区域"""
        group = QGroupBox("阈值设置 (用户设置基础)")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)
        
        # 自动校准复选框
        self.auto_calibrate_checkbox = QCheckBox("自动校准阈值")
        self.auto_calibrate_checkbox.setToolTip(
            "启用后，程序会先评分所有图片，根据分数分布（P80/P60/P40/P20）\n"
            "自动计算最佳阈值，并在弹窗中让您确认或调整。"
        )
        self.auto_calibrate_checkbox.toggled.connect(self._on_auto_calibrate_toggled)
        layout.addWidget(self.auto_calibrate_checkbox)
        
        # 提示文字
        self.threshold_hint = QLabel("启用后根据数据分布自动计算")
        self.threshold_hint.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        self.threshold_hint.setVisible(False)
        layout.addWidget(self.threshold_hint)
        
        # 阈值滑块
        threshold_layout = QGridLayout()
        threshold_layout.setSpacing(12)
        threshold_layout.setColumnStretch(1, 1)
        
        threshold_configs = [
            ("4★阈值", 78, "threshold_4star"),
            ("3★阈值", 72, "threshold_3star"),
            ("2★阈值", 66, "threshold_2star"),
            ("1★阈值", 58, "threshold_1star"),
        ]
        
        self.threshold_sliders = {}
        self.threshold_labels = {}
        
        for row, (label_text, default_val, key) in enumerate(threshold_configs):
            # 标签
            label = QLabel(label_text)
            label.setStyleSheet(f"color: {COLORS['text_secondary']};")
            threshold_layout.addWidget(label, row, 0)
            
            # 滑块
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(default_val)
            slider.valueChanged.connect(lambda v, k=key: self._on_threshold_changed(k, v))
            self.threshold_sliders[key] = slider
            threshold_layout.addWidget(slider, row, 1)
            
            # 数值标签
            value_label = QLabel(str(default_val))
            value_label.setStyleSheet(f"""
                color: {COLORS['text_primary']};
                font-size: 14px;
                font-weight: 500;
                font-family: {FONTS['mono']};
            """)
            value_label.setFixedWidth(50)
            value_label.setAlignment(Qt.AlignCenter)
            self.threshold_labels[key] = value_label
            threshold_layout.addWidget(value_label, row, 2)
        
        layout.addLayout(threshold_layout)
        
        # 恢复默认按钮
        reset_btn = QPushButton("恢复默认")
        reset_btn.setObjectName("secondary")
        reset_btn.setMaximumWidth(120)
        reset_btn.clicked.connect(self._reset_thresholds)
        layout.addWidget(reset_btn)
        
        parent_layout.addWidget(group)
    
    # ==================== 底部按钮区域 ====================
    def _create_button_section(self, parent_layout):
        """创建底部按钮"""
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        btn_layout.addStretch()
        
        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("secondary")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        # 保存按钮
        save_btn = QPushButton("保存并应用")
        save_btn.setMinimumWidth(120)
        save_btn.clicked.connect(self._save_and_apply)
        btn_layout.addWidget(save_btn)
        
        parent_layout.addLayout(btn_layout)
    
    # ==================== 事件处理 ====================
    def _on_threshold_changed(self, key, value):
        """阈值滑块变化"""
        self.threshold_labels[key].setText(str(value))
    
    def _on_auto_calibrate_toggled(self, checked):
        """自动校准开关切换"""
        # 启用时禁用滑块
        enabled = not checked
        for slider in self.threshold_sliders.values():
            slider.setEnabled(enabled)
        
        # 显示提示
        self.threshold_hint.setVisible(checked)
        
        self.auto_calibrate = checked
    
    def _reset_thresholds(self):
        """恢复默认阈值"""
        defaults = [78, 72, 66, 58]
        keys = ["threshold_4star", "threshold_3star", "threshold_2star", "threshold_1star"]
        
        for key, val in zip(keys, defaults):
            self.threshold_sliders[key].setValue(val)
    
    def _save_and_apply(self):
        """保存并应用设置"""
        # 获取当前阈值
        current_thresholds = (
            float(self.threshold_sliders["threshold_4star"].value()),
            float(self.threshold_sliders["threshold_3star"].value()),
            float(self.threshold_sliders["threshold_2star"].value()),
            float(self.threshold_sliders["threshold_1star"].value()),
        )
        
        # 验证阈值递减
        if not all(current_thresholds[i] > current_thresholds[i+1] for i in range(3)):
            StyledMessageBox.warning(
                self, "阈值错误",
                "阈值必须递减：5★ > 4★ > 3★ > 2★"
            )
            return
        
        self.thresholds = current_thresholds
        
        # 保存到 user 预设
        self.preset_manager.save_user_preset(
            thresholds=self.thresholds,
            quality_weight=self.quality_weight,
            aesthetic_weight=self.aesthetic_weight,
            write_xmp=self._write_xmp,
            organize=self._organize,
        )
        
        # 发送配置更改信号
        self.config_changed.emit(
            self.quality_weight,
            self.aesthetic_weight,
            self.thresholds,
            self.auto_calibrate,
            self._write_xmp,
            self._organize
        )
        
        self.accept()
    
    def _load_user_config(self):
        """加载用户配置"""
        user_preset = self.preset_manager.get_user_preset()
        if user_preset:
            # 加载阈值
            self.threshold_sliders["threshold_4star"].setValue(int(user_preset.thresholds[0]))
            self.threshold_sliders["threshold_3star"].setValue(int(user_preset.thresholds[1]))
            self.threshold_sliders["threshold_2star"].setValue(int(user_preset.thresholds[2]))
            self.threshold_sliders["threshold_1star"].setValue(int(user_preset.thresholds[3]))
            
            # 加载选项
            self._write_xmp = user_preset.write_xmp
            self._organize = user_preset.organize
    
    def get_current_config(self) -> dict:
        """获取当前配置"""
        return {
            "quality_weight": self.quality_weight,
            "aesthetic_weight": self.aesthetic_weight,
            "thresholds": self.thresholds,
            "auto_calibrate": self.auto_calibrate,
            "write_xmp": self._write_xmp,
            "organize": self._organize,
        }
