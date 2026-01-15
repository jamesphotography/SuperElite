# -*- coding: utf-8 -*-
"""
SuperElite / 摄影评片 - 主窗口
PySide6 版本 - 极简艺术风格
"""

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QSlider, QProgressBar,
    QTextEdit, QGroupBox, QCheckBox, QMenuBar, QMenu,
    QFileDialog, QFrame, QSpacerItem, QSizePolicy, QComboBox
)
from PySide6.QtCore import Qt, Signal, QMimeData, QThread
from PySide6.QtGui import QFont, QDragEnterEvent, QDropEvent, QAction, QIcon

from ui.styles import (
    GLOBAL_STYLE, TITLE_STYLE, SUBTITLE_STYLE, VERSION_STYLE, VALUE_STYLE,
    COLORS, FONTS, LOG_COLORS, PROGRESS_INFO_STYLE, PROGRESS_PERCENT_STYLE
)
from ui.custom_dialogs import StyledMessageBox
from ui.scoring_worker import ScoringWorker


# ==================== 模型预加载线程 ====================
class ModelPreloadWorker(QThread):
    """后台预加载AI模型，程序启动时自动执行"""
    preload_started = Signal()  # 避免与 QThread.started 冲突
    finished = Signal(bool)  # success
    
    def run(self):
        """预加载模型"""
        try:
            self.preload_started.emit()
            
            # 添加 backend 到路径
            backend_path = Path(__file__).parent.parent / "backend"
            sys.path.insert(0, str(backend_path))
            
            from one_align_scorer import get_one_align_scorer
            
            # 获取评分器（会触发模型加载）
            scorer = get_one_align_scorer()
            scorer.warmup()  # 预热
            
            self.finished.emit(True)
        except Exception as e:
            print(f"模型预加载失败: {e}")
            self.finished.emit(False)


# ==================== 拖放输入框 ====================
class DropLineEdit(QLineEdit):
    """支持拖放目录的 QLineEdit"""
    pathDropped = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """验证拖入的内容"""
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].isLocalFile():
                path = urls[0].toLocalFile()
                if os.path.isdir(path):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        """处理拖放"""
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isdir(path):
                self.setText(path)
                self.pathDropped.emit(path)
                event.acceptProposedAction()
                return
        event.ignore()


# ==================== 主窗口 ====================
class SuperEliteMainWindow(QMainWindow):
    """SuperElite 主窗口 - 极简艺术风格"""

    def __init__(self):
        super().__init__()
        self._setup_window()
        self._setup_menu()
        self._setup_ui()
        self._setup_worker()
        self._show_initial_help()
        
        # 状态
        self._is_processing = False
        self._model_loaded = False  # 模型是否已加载
        
        # 配置（从设置对话框传入）
        self._quality_weight = 0.4
        self._aesthetic_weight = 0.6
        self._thresholds = (78.0, 72.0, 66.0, 58.0)
        self._auto_calibrate = True  # 默认启用全自动模式
        self._write_xmp = True
        self._organize = True  # 默认启用分目录
        self._last_preset_index = 0  # 预设下拉菜单选中索引 (0=auto)
        
        # 启动时预加载模型
        self._start_model_preload()

    def _setup_window(self):
        """设置窗口属性"""
        self.setWindowTitle("SuperElite / 摄影评片")
        self.setMinimumSize(720, 680)  # 与 SuperPicky 保持一致
        self.resize(820, 760)
        
        # 应用全局样式
        self.setStyleSheet(GLOBAL_STYLE)
        
        # 设置应用图标
        icon_path = os.path.join(os.path.dirname(__file__), "..", "img", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

    def _setup_menu(self):
        """设置菜单栏"""
        menubar = self.menuBar()
        
        # 设置菜单
        settings_menu = menubar.addMenu("设置")
        
        preferences_action = QAction("偏好设置...", self)
        preferences_action.setShortcut("Cmd+,")  # macOS 标准快捷键
        preferences_action.triggered.connect(self._show_settings)
        settings_menu.addAction(preferences_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        about_action = QAction("关于 SuperElite", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_ui(self):
        """设置主 UI"""
        # 中央 widget
        central = QWidget()
        self.setCentralWidget(central)
        
        # 主布局
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(28, 20, 28, 20)
        main_layout.setSpacing(16)
        
        # 各区域
        self._create_header_section(main_layout)
        self._create_directory_section(main_layout)
        self._create_preset_section(main_layout)  # 新：预设下拉菜单
        self._create_weight_section(main_layout)  # 新：权重滑块
        self._create_log_section(main_layout)
        self._create_progress_section(main_layout)
        self._create_button_section(main_layout)

    # ==================== Header 区域 ====================
    def _create_header_section(self, parent_layout):
        """创建头部区域 - 品牌展示"""
        header = QFrame()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(16)
        
        # 应用图标
        icon_path = os.path.join(os.path.dirname(__file__), "..", "img", "icon.png")
        if os.path.exists(icon_path):
            from PySide6.QtGui import QPixmap
            icon_label = QLabel()
            pixmap = QPixmap(icon_path)
            # 缩放到 64x64
            scaled_pixmap = pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_label.setPixmap(scaled_pixmap)
            icon_label.setFixedSize(64, 64)
            header_layout.addWidget(icon_label)
        
        # 品牌名
        brand_layout = QVBoxLayout()
        brand_layout.setSpacing(4)
        
        # 主标题 - 中文
        title = QLabel("摄影评片")
        title.setStyleSheet(TITLE_STYLE)
        brand_layout.addWidget(title)
        
        # 副标题 - 英文
        subtitle = QLabel("SuperElite AI 选片工具")
        subtitle.setStyleSheet(SUBTITLE_STYLE)
        brand_layout.addWidget(subtitle)
        
        header_layout.addLayout(brand_layout)
        header_layout.addStretch()
        
        # 版本号 + commit hash - 放在同一个背景框内
        version_frame = QFrame()
        version_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLORS['bg_elevated']};
                border-radius: 12px;
                padding: 6px 12px;
            }}
        """)
        version_inner = QVBoxLayout(version_frame)
        version_inner.setContentsMargins(12, 6, 12, 6)
        version_inner.setSpacing(2)
        
        version_label = QLabel("V1.0")
        version_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 12px; font-family: {FONTS['mono']}; font-weight: 500;")
        version_label.setAlignment(Qt.AlignCenter)
        version_inner.addWidget(version_label)
        
        # commit hash
        hash_label = QLabel("050ae93")
        hash_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px; font-family: {FONTS['mono']};")
        hash_label.setAlignment(Qt.AlignCenter)
        version_inner.addWidget(hash_label)
        
        header_layout.addWidget(version_frame)
        
        parent_layout.addWidget(header)

    # ==================== 目录选择区域 ====================
    def _create_directory_section(self, parent_layout):
        """创建目录选择区域 - 紧凑布局"""
        layout = QHBoxLayout()
        layout.setSpacing(12)
        
        # 目录标签
        label = QLabel("目录:")
        label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
        label.setFixedWidth(90)
        layout.addWidget(label)
        
        # 拖放输入框
        self.dir_input = DropLineEdit()
        self.dir_input.setPlaceholderText("📁 拖放文件夹到此处，或点击浏览...")
        layout.addWidget(self.dir_input, 1)
        
        # 浏览按钮
        browse_btn = QPushButton("浏览")
        browse_btn.setObjectName("browse")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_directory)
        layout.addWidget(browse_btn)
        
        parent_layout.addLayout(layout)

    # ==================== 预设选择区域 ====================
    def _create_preset_section(self, parent_layout):
        """创建预设选择区域 - 无标题"""
        layout = QHBoxLayout()
        layout.setSpacing(12)
        
        # 标签
        label = QLabel("评分标准:")
        label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
        label.setFixedWidth(90)
        layout.addWidget(label)
        
        # 预设下拉菜单
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            "auto (全自动20%均分)",
            "default (默认: 78/72/66/58)",
            "strict (严格: 85/80/75/70)",
            "relaxed (宽松: 70/60/50/40)",
            "自定义..."
        ])
        self.preset_combo.setCurrentIndex(0)  # 默认选中全自动
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        layout.addWidget(self.preset_combo, 1)
        
        # 分目录开关
        self.organize_checkbox = QCheckBox("分目录")
        self.organize_checkbox.setChecked(True)  # 默认启用
        self.organize_checkbox.setToolTip("按星级复制文件到子目录 (1星、2星...)")
        self.organize_checkbox.stateChanged.connect(self._on_organize_changed)
        layout.addWidget(self.organize_checkbox)
        
        parent_layout.addLayout(layout)
    
    # ==================== 权重调整区域 ====================
    def _create_weight_section(self, parent_layout):
        """创建权重调整区域 - 单行布局"""
        layout = QHBoxLayout()
        layout.setSpacing(12)
        
        # 左侧标签
        label = QLabel("评分权重:")
        label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
        label.setFixedWidth(90)
        layout.addWidget(label)
        
        # 质量标签
        left_label = QLabel("质量")
        left_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px;")
        layout.addWidget(left_label)
        
        # 滑块 (0-100, 0=100%质量, 100=100%美学)
        self.weight_slider = QSlider(Qt.Horizontal)
        self.weight_slider.setRange(0, 100)
        self.weight_slider.setValue(40)  # 默认 0.4质量/0.6美学
        self.weight_slider.valueChanged.connect(self._on_weight_changed)
        layout.addWidget(self.weight_slider, 1)
        
        # 美学标签
        right_label = QLabel("美学")
        right_label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 13px;")
        right_label.setFixedWidth(30)  # 固定宽度避免被裁剪
        layout.addWidget(right_label)
        
        # 当前分配显示
        self.weight_label = QLabel("0.4 ← → 0.6")
        self.weight_label.setStyleSheet(f"""
            color: {COLORS['text_primary']};
            font-size: 13px;
            font-weight: 500;
            font-family: {FONTS['mono']};
        """)
        self.weight_label.setFixedWidth(100)
        layout.addWidget(self.weight_label)
        
        parent_layout.addLayout(layout)

    # ==================== 日志区域 ====================
    def _create_log_section(self, parent_layout):
        """创建日志区域"""
        # 日志标题行（包含状态指示器）
        log_header = QFrame()
        log_header_layout = QHBoxLayout(log_header)
        log_header_layout.setContentsMargins(0, 8, 0, 4)
        log_header_layout.setSpacing(8)
        
        log_title = QLabel("控制台")
        log_title.setStyleSheet(f"color: {COLORS['text_tertiary']}; font-size: 12px;")
        log_header_layout.addWidget(log_title)
        
        log_header_layout.addStretch()
        
        # 状态指示器
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 10px;")
        log_header_layout.addWidget(self.status_dot)
        
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
        log_header_layout.addWidget(self.status_label)
        
        parent_layout.addWidget(log_header)
        
        # 日志文本框
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(200)
        parent_layout.addWidget(self.log_text, 1)  # 弹性伸展

    # ==================== 进度区域 ====================
    def _create_progress_section(self, parent_layout):
        """创建进度区域"""
        progress_frame = QFrame()
        progress_layout = QHBoxLayout(progress_frame)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(12)
        
        progress_layout.addStretch()
        
        # 百分比
        self.progress_percent = QLabel("0%")
        self.progress_percent.setStyleSheet(PROGRESS_PERCENT_STYLE)
        progress_layout.addWidget(self.progress_percent)
        
        parent_layout.addWidget(progress_frame)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        parent_layout.addWidget(self.progress_bar)

    # ==================== 按钮区域 ====================
    def _create_button_section(self, parent_layout):
        """创建按钮区域 - 重置在开始旁边"""
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        btn_layout.addStretch()
        
        # 重置按钮 - 清除元数据
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setObjectName("secondary")
        self.reset_btn.setMinimumWidth(100)
        self.reset_btn.setToolTip("清除选定目录中所有图片的 XMP 评级数据")
        self.reset_btn.clicked.connect(self._on_reset_metadata)
        self.reset_btn.setEnabled(False)  # 初始禁用，等待模型加载完成
        btn_layout.addWidget(self.reset_btn)
        
        # 开始按钮
        self.start_btn = QPushButton("开始处理")
        self.start_btn.setMinimumWidth(140)
        self.start_btn.clicked.connect(self._on_start)
        self.start_btn.setEnabled(False)  # 初始禁用，等待模型加载完成
        btn_layout.addWidget(self.start_btn)
        
        parent_layout.addLayout(btn_layout)

    # ==================== 事件处理 ====================
    def _browse_directory(self):
        """浏览目录"""
        path = QFileDialog.getExistingDirectory(
            self, "选择照片目录", os.path.expanduser("~")
        )
        if path:
            self.dir_input.setText(path)
    
    def _on_preset_changed(self, index):
        """预设选择变化"""
        if index == 4:  # 自定义 (最后一个)
            # 打开设置对话框
            self._show_settings()
            # 恢复到上一次的选择
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentIndex(self._last_preset_index)
            self.preset_combo.blockSignals(False)
        elif index == 0:  # auto - 全自动
            self._last_preset_index = index
            # 启用自动校准
            self._auto_calibrate = True
            # 不需要加载预设，评分后自动计算阈值
            self._log("info", "🤖 已启用全自动模式")
            self._log("default", "   将按 20% 均分自动分配星级")
        else:
            self._last_preset_index = index
            self._auto_calibrate = False
            # 加载预设
            preset_names = ["default", "strict", "relaxed"]
            preset_name = preset_names[index - 1]  # 跳过auto
            
            from pathlib import Path
            import sys
            backend_path = Path(__file__).parent.parent / "backend"
            sys.path.insert(0, str(backend_path))
            from preset_manager import get_preset_manager
            
            preset_manager = get_preset_manager()
            preset = preset_manager.get_preset(preset_name)
            
            if preset:
                # 更新阈值
                self._thresholds = preset.thresholds
                # 更新权重
                self._quality_weight = preset.quality_weight
                self._aesthetic_weight = preset.aesthetic_weight
                # 更新权重滑块
                aesthetic_pct = int(preset.aesthetic_weight * 100)
                self.weight_slider.blockSignals(True)
                self.weight_slider.setValue(aesthetic_pct)
                self.weight_slider.blockSignals(False)
                self._on_weight_changed(aesthetic_pct)  # 更新显示
                
                self._log("info", f"🛠️  已切换到 {preset_name} 预设")
                self._log("default", f"   阈值: {preset.thresholds[0]}/{preset.thresholds[1]}/{preset.thresholds[2]}/{preset.thresholds[3]}")
    
    def _on_weight_changed(self, value):
        """权重滑块变化"""
        # value: 0-100, 0=100%质量, 100=100%美学
        self._aesthetic_weight = value / 100.0
        self._quality_weight = 1.0 - self._aesthetic_weight
        
        # 更新显示
        self.weight_label.setText(
            f"{self._quality_weight:.1f} ← → {self._aesthetic_weight:.1f}"
        )
    
    def _on_organize_changed(self, state):
        """分目录开关变化"""
        self._organize = (state == Qt.Checked)

    def _on_start(self):
        """开始处理"""
        if self._is_processing:
            # 已在处理中，变成停止按钮
            self._stop_processing()
            return
        
        dir_path = self.dir_input.text().strip()
        if not dir_path:
            StyledMessageBox.warning(self, "提示", "请先选择要处理的目录")
            return
        if not os.path.isdir(dir_path):
            StyledMessageBox.warning(self, "提示", "目录不存在，请重新选择")
            return
        
        # 使用配置中的阈值（从设置对话框）
        thresholds = self._thresholds
        
        # 配置 worker
        self._worker.configure(
            input_dir=dir_path,
            thresholds=thresholds,
            quality_weight=self._quality_weight,
            aesthetic_weight=self._aesthetic_weight,
            write_xmp=self._write_xmp,
            organize=self._organize,
            output_dir=dir_path,  # 直接在原目录内创建子目录
            csv_path=None,
            auto_calibrate=self._auto_calibrate,
        )
        
        # 开始处理
        self._start_processing()
    
    def _setup_worker(self):
        """设置后台工作线程"""
        self._worker = ScoringWorker(self)
        
        # 连接信号
        self._worker.started_loading.connect(self._on_model_loading)
        self._worker.model_loaded.connect(self._on_model_loaded)
        self._worker.progress.connect(self._on_progress)
        self._worker.log_message.connect(self._on_log_message)
        self._worker.finished_scoring.connect(self._on_scoring_finished)
        self._worker.error.connect(self._on_error)
    
    def _start_model_preload(self):
        """启动时预加载模型"""
        self._preload_worker = ModelPreloadWorker(self)
        self._preload_worker.preload_started.connect(self._on_preload_started)
        self._preload_worker.finished.connect(self._on_preload_finished)
        self._preload_worker.start()
    
    def _on_preload_started(self):
        """预加载开始"""
        self._set_status("模型加载中", "warning")
        self.progress_bar.setRange(0, 0)  # 不确定模式
        self.progress_percent.setText("⏳")
        self._log("info", "🔄 正在预加载 AI 模型...")
    
    def _on_preload_finished(self, success: bool):
        """预加载完成"""
        self._model_loaded = success
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_percent.setText("0%")
        
        if success:
            self._set_status("就绪", "success")
            self._log("success", "✅ AI 模型加载完成，可以开始处理")
            # 启用按钮
            self.start_btn.setEnabled(True)
            self.reset_btn.setEnabled(True)
        else:
            self._set_status("模型加载失败", "error")
            self._log("error", "❌ 模型加载失败")
    
    def _start_processing(self):
        """开始处理"""
        self._is_processing = True
        self.start_btn.setText("停止")
        self.start_btn.setObjectName("secondary")
        self.start_btn.setStyleSheet("")  # 刷新样式
        self.reset_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_text.clear()
        self._log("info", "🚀 开始处理...")
        self._worker.start()
    
    def _stop_processing(self):
        """停止处理"""
        self._worker.stop()
        self._log("warning", "ℹ️ 正在停止...")
    
    def _on_model_loading(self):
        """模型加载中"""
        self._set_status("模型加载中", "warning")
        # 使用进度条不确定模式显示加载中
        self.progress_bar.setRange(0, 0)  # 不确定模式 (无限循环动画)
        self.progress_percent.setText("⏳")
    
    def _on_model_loaded(self):
        """模型加载完成"""
        self._set_status("处理中", "accent")
        # 恢复进度条正常模式
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_percent.setText("0%")
    
    def _on_progress(self, current: int, total: int, filename: str, score: float, rating: int):
        """进度更新"""
        percent = int(current / total * 100) if total > 0 else 0
        self.progress_bar.setValue(percent)
        self.progress_percent.setText(f"{percent}%")
        
        # 记录日志
        stars = "★" * rating + "☆" * (5 - rating)
        self._log("default", f"[{current:3d}/{total}] {filename[:35]:<35} → {score:.1f} {stars}")
    
    def _on_log_message(self, level: str, message: str):
        """日志消息"""
        self._log(level, message)
    
    def _on_scoring_finished(self, results: list, summary: dict):
        """评分完成"""
        self._is_processing = False
        self.start_btn.setText("开始处理")
        self.start_btn.setObjectName("")
        self.start_btn.setStyleSheet("")  # 刷新样式
        self.reset_btn.setEnabled(True)
        self._set_status("就绪", "muted")
        self.progress_bar.setValue(100)
        
        # 显示统计
        self._log("success", "\n" + "━" * 40)
        self._log("success", "✅ 处理完成!")
        self._log("info", f"   总计: {summary['total']} 张")
        self._log("info", f"   成功: {summary['success']} 张")
        self._log("info", f"   耗时: {summary['elapsed_time']:.1f}s ({summary['speed']:.2f}s/张)")
        self._log("info", "")
        self._log("info", "各星级分布:")
        for star in range(5, 0, -1):
            count = summary['by_rating'].get(star, 0)
            bar = "█" * min(count, 30)
            self._log("default", f"   {"★" * star}{"☆" * (5-star)}: {count:3d} {bar}")
        
        # 播放系统提示音
        import subprocess
        subprocess.run(['afplay', '/System/Library/Sounds/Glass.aiff'], check=False)
        
        # 弹窗询问是否打开目录
        dir_path = self.dir_input.text().strip()
        result = StyledMessageBox.question(
            self,
            "处理完成",
            f"已完成 {summary['success']} 张图片的评分处理。\n\n"
            f"是否打开结果目录？"
        )
        
        if result == StyledMessageBox.Yes:
            # 用 Finder 打开目录
            subprocess.run(['open', dir_path], check=False)
    
    def _on_error(self, error_message: str):
        """错误处理"""
        self._is_processing = False
        self.start_btn.setText("开始处理")
        self.start_btn.setObjectName("")
        self.start_btn.setStyleSheet("")
        self.reset_btn.setEnabled(True)
        self._set_status("错误", "error")
        
        self._log("error", f"\n❌ 错误: {error_message}")
        StyledMessageBox.critical(self, "错误", error_message)

    def _on_reset_metadata(self):
        """重置/清除元数据"""
        dir_path = self.dir_input.text().strip()
        if not dir_path:
            StyledMessageBox.warning(self, "提示", "请先选择要清除的目录")
            return
        if not os.path.isdir(dir_path):
            StyledMessageBox.warning(self, "提示", "目录不存在，请重新选择")
            return
        
        # 确认对话框
        result = StyledMessageBox.question(
            self,
            "确认重置",
            f"即将清除目录中所有图片的评级数据:\n\n"
            f"{dir_path}\n\n"
            f"清除内容: 星级、色标、旗标、国家、省份、城市\n\n"
            f"此操作不可撤销，确定继续？"
        )
        
        if result != StyledMessageBox.Yes:
            return
        
        # 禁用按钮
        self.start_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        self._set_status("重置中", "warning")
        
        # 清空日志
        self.log_text.clear()
        
        # 执行清除
        self._log("info", f"🧹 开始重置元数据: {dir_path}")
        
        import sys
        from pathlib import Path
        backend_path = Path(__file__).parent.parent / "backend"
        sys.path.insert(0, str(backend_path))
        from exif_writer import get_exif_writer
        
        exif_writer = get_exif_writer()
        
        # 扫描文件
        supported_extensions = {
            ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp",
            ".arw", ".cr2", ".cr3", ".nef", ".dng", ".orf", ".rw2", ".raf"
        }
        
        files = []
        for f in Path(dir_path).iterdir():
            if f.is_file() and f.suffix.lower() in supported_extensions:
                files.append(str(f))
        
        if not files:
            self._log("warning", "未找到图片文件")
            self.start_btn.setEnabled(True)
            self.reset_btn.setEnabled(True)
            self._set_status("就绪", "success")
            return
        
        self._log("info", f"   找到 {len(files)} 张图片")
        
        # 初始化进度条
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        
        # 批量处理 (每10个一批)
        batch_size = 10
        success_count = 0
        total = len(files)
        
        from PySide6.QtWidgets import QApplication
        
        for i in range(0, total, batch_size):
            batch = files[i:i+batch_size]
            batch_success = 0
            batch_names = []
            
            for file_path in batch:
                try:
                    if exif_writer.reset_metadata(file_path):
                        batch_success += 1
                        batch_names.append(f"✓ {os.path.basename(file_path)}")
                    else:
                        batch_names.append(f"✗ {os.path.basename(file_path)}")
                except Exception as e:
                    batch_names.append(f"✗ {os.path.basename(file_path)}")
            
            success_count += batch_success
            
            # 更新进度
            progress = int((i + len(batch)) / total * 100)
            self.progress_bar.setValue(progress)
            self.progress_percent.setText(f"{progress}%")
            
            # 输出这一批的结果
            end_idx = min(i + batch_size, total)
            self._log("default", f"   [{i+1}-{end_idx}/{total}] {batch_success}/{len(batch)} 成功")
            
            # 让UI有机会更新
            QApplication.processEvents()
        
        # 完成
        self.progress_bar.setValue(100)
        self.progress_percent.setText("100%")
        self._log("success", f"\n✅ 重置完成! 成功: {success_count}/{total}")
        
        # 恢复按钮
        self.start_btn.setEnabled(True)
        self.reset_btn.setEnabled(True)
        self._set_status("就绪", "success")

    def _show_initial_help(self):
        """显示初始帮助信息"""
        self._log("muted", "欢迎使用 SuperElite / 摄影评片")
        self._log("muted", "━" * 40)
        self._log("muted", "1. 拖放或浏览选择照片目录")
        self._log("muted", "2. 调整评分阈值 (可选)")
        self._log("muted", "3. 点击「开始处理」")

    def _log(self, level: str, message: str):
        """添加日志（带时间戳）"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        color = LOG_COLORS.get(level, LOG_COLORS['default'])
        self.log_text.append(f'<span style="color:{COLORS["text_muted"]}">[{timestamp}]</span> <span style="color:{color}">{message}</span>')
    
    def _set_status(self, text: str, color_key: str = "muted"):
        """设置状态指示器"""
        color = COLORS.get(color_key, COLORS['text_muted'])
        self.status_label.setText(text)
        self.status_label.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 10px;")

    def _show_about(self):
        """显示关于对话框"""
        # TODO: 实现 AboutDialog
        StyledMessageBox.information(
            self, 
            "关于 SuperElite",
            "SuperElite / 摄影评片\n\n"
            "AI 照片美学评分工具\n"
            "基于 One-Align 模型\n\n"
            "© 2025 James Yu"
        )
    
    def _show_settings(self):
        """显示设置对话框"""
        from ui.settings_dialog import SettingsDialog
        
        dialog = SettingsDialog(self)
        dialog.config_changed.connect(self._on_config_changed)
        dialog.exec()
    
    def _on_config_changed(self, quality_weight, aesthetic_weight, thresholds, 
                          auto_calibrate, write_xmp, organize):
        """配置更改事件"""
        # 更新内部配置
        self._quality_weight = quality_weight
        self._aesthetic_weight = aesthetic_weight
        self._thresholds = thresholds
        self._auto_calibrate = auto_calibrate
        self._write_xmp = write_xmp
        self._organize = organize
        
        # 更新主窗口UI（但不显示滑块，保持简洁）
        # 阈值滑块已隐藏，不需要更新
        
        self._log("info", "⚙️  设置已更新")
        self._log("default", f"   权重: 质量 {quality_weight:.2f} / 美学 {aesthetic_weight:.2f}")
        self._log("default", f"   阈值: {thresholds[0]}/{thresholds[1]}/{thresholds[2]}/{thresholds[3]}")
        if auto_calibrate:
            self._log("default", "   自动校准: 已启用")

    def closeEvent(self, event):
        """窗口关闭事件"""
        if self._is_processing:
            result = StyledMessageBox.question(
                self, 
                "确认退出", 
                "正在处理中，确定要退出吗？"
            )
            if result == StyledMessageBox.No:
                event.ignore()
                return
            self._worker.stop()
            self._worker.wait(2000)  # 等待线程结束
        event.accept()
