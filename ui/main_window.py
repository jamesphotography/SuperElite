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
        self._is_downloading = False  # 是否正在下载模型
        
        # 配置（从设置对话框传入）
        self._quality_weight = 0.4
        self._aesthetic_weight = 0.6
        self._thresholds = (78.0, 72.0, 66.0, 58.0)
        self._auto_calibrate = True  # 默认启用全自动模式
        self._write_xmp = True
        self._organize = True  # 默认启用分目录
        self._last_preset_index = 0  # 预设下拉菜单选中索引 (0=auto)
        self._model_mode = "basic"  # 模型模式: "basic" 或 "advanced"

        
        # 系统检查
        if not self._check_system_requirements():
            return  # 会在 show 时显示错误
        
        # 不再强制下载大模型，用户可直接使用爱好者水平
        # 模型预加载将在首次评分时按需进行
    
    def _check_system_requirements(self) -> bool:
        """检查系统要求"""
        try:
            from pathlib import Path
            import sys
            backend_path = Path(__file__).parent.parent / "backend"
            sys.path.insert(0, str(backend_path))
            
            from region_detector import check_system_requirements, get_system_memory_gb
            
            passed, error_msg = check_system_requirements()
            
            if not passed:
                memory = get_system_memory_gb()
                StyledMessageBox.critical(
                    self,
                    "系统要求不满足",
                    f"您的系统内存为 {memory:.1f}GB\n\n"
                    f"SuperElite 需要至少 16GB 内存才能运行 AI 模型。\n\n"
                    f"请关闭其他应用程序或升级硬件后重试。"
                )
                return False
            
            return True
        except Exception as e:
            self._log("warning", f"⚠️ 系统检查失败: {e}")
            return True  # 检查失败时继续
    
    def _check_and_download_model(self) -> bool:
        """检查模型是否已下载，如未下载则引导用户下载"""
        try:
            from pathlib import Path
            import sys
            backend_path = Path(__file__).parent.parent / "backend"
            sys.path.insert(0, str(backend_path))
            
            from region_detector import is_model_cached, get_recommended_endpoint
            
            if is_model_cached():
                self._log("info", "✅ AI 模型已就绪")
                return True
            
            # 模型未下载，显示下载对话框
            from ui.download_source_dialog import DownloadSourceDialog
            
            _, _, is_china = get_recommended_endpoint()
            
            dialog = DownloadSourceDialog(
                recommended_is_china=is_china,
                parent=self
            )
            
            if not dialog.exec():
                # 用户取消
                StyledMessageBox.information(
                    self,
                    "需要下载模型",
                    "SuperElite 需要 AI 模型才能运行。\n\n"
                    "您可以稍后重新启动程序进行下载。"
                )
                return False
            
            # 开始下载
            endpoint = dialog.get_selected_endpoint()
            self._start_model_download(endpoint)
            return True
            
        except Exception as e:
            self._log("warning", f"⚠️ 模型检查失败: {e}")
            return True  # 检查失败时继续
    
    def _start_model_download(self, endpoint: str):
        """启动模型下载"""
        from backend.model_downloader import ModelDownloader
        
        self._is_downloading = True
        self._set_status("模型下载中", "warning")
        self._log("info", "")
        self._log("info", "📥 开始下载 AI 模型...")
        self._log("info", f"   下载源: {endpoint}")
        self._log("info", "   支持断点续传，可随时关闭程序")
        self._log("info", "")
        
        self._downloader = ModelDownloader(endpoint, self)
        self._downloader.progress.connect(self._on_download_progress)
        self._downloader.log_message.connect(self._on_download_log)
        self._downloader.finished.connect(self._on_download_finished)
        self._downloader.start()
    
    def _on_download_log(self, log_type: str, message: str):
        """下载日志"""
        self._log(log_type, message)
    
    def _on_download_progress(self, percent: int, desc: str):
        """下载进度更新"""
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(percent)
        self.progress_percent.setText(f"{percent}%")
        if desc:
            self._set_status(f"下载: {desc}", "warning")
    
    def _on_download_finished(self, success: bool, message: str):
        """下载完成"""
        self._is_downloading = False
        
        if success:
            self._log("success", "✅ 模型下载完成")
            self.progress_bar.setValue(100)
            self.progress_percent.setText("100%")
            # 继续加载模型
            self._start_model_preload()
        else:
            self._log("error", f"❌ 模型下载失败: {message}")
            self._set_status("下载失败", "error")
            StyledMessageBox.warning(
                self,
                "下载失败",
                f"模型下载失败:\n{message}\n\n"
                f"请检查网络连接或更换下载源后重试。"
            )

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
        self._create_model_section(main_layout)  # 新：模型选择（爱好者/大师）
        self._create_preset_section(main_layout)  # 预设下拉菜单
        self._create_weight_section(main_layout)  # 权重滑块
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
        brand_layout.setSpacing(0)
        brand_layout.setContentsMargins(0, 0, 0, 0)
        
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

    # ==================== 模型选择区域 ====================
    def _create_model_section(self, parent_layout):
        """创建模型选择区域 - 爱好者/大师"""
        layout = QHBoxLayout()
        layout.setSpacing(12)
        
        # 标签
        label = QLabel("评分模型:")
        label.setStyleSheet(f"color: {COLORS['text_secondary']}; font-size: 14px;")
        label.setFixedWidth(90)
        layout.addWidget(label)
        
        # 模型下拉菜单
        self.model_combo = QComboBox()
        self._update_model_combo()  # 初始化模型选项
        self.model_combo.currentIndexChanged.connect(self._on_model_changed)
        layout.addWidget(self.model_combo, 1)
        
        # 模型下载按钮（仅当高级模型未下载时显示）
        self.download_model_btn = QPushButton("下载高级模型")
        self.download_model_btn.setObjectName("secondary")
        self.download_model_btn.setFixedWidth(120)
        self.download_model_btn.clicked.connect(self._on_download_advanced_model)
        self.download_model_btn.setVisible(not self._is_advanced_model_available())
        layout.addWidget(self.download_model_btn)
        
        parent_layout.addLayout(layout)
    
    def _is_advanced_model_available(self) -> bool:
        """检查高级模型 (One-Align) 是否已下载"""
        try:
            from pathlib import Path
            import sys
            backend_path = Path(__file__).parent.parent / "backend"
            sys.path.insert(0, str(backend_path))
            from region_detector import is_model_cached
            return is_model_cached()
        except:
            return False
    
    def _update_model_combo(self):
        """更新模型下拉菜单选项"""
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        
        has_advanced = self._is_advanced_model_available()
        
        # 添加选项
        self.model_combo.addItem("爱好者水平 (500MB, 内置)")
        self.model_combo.addItem("詹姆斯水平 (15GB)" + ("" if has_advanced else " [未下载]"))
        
        # 默认选择：如果高级模型可用，默认使用大师模式
        if has_advanced:
            self.model_combo.setCurrentIndex(1)  # 大师
            self._model_mode = "advanced"
        else:
            self.model_combo.setCurrentIndex(0)  # 爱好者
            self._model_mode = "basic"
        
        self.model_combo.blockSignals(False)
    
    def _on_model_changed(self, index):
        """模型选择变化"""
        if index == 0:  # 爱好者水平
            self._model_mode = "basic"
            self._log("info", "已切换到 爱好者水平")
            self._log("default", "   使用内置评分模型，速度快")
        else:  # 詹姆斯水平
            if not self._is_advanced_model_available():
                # 高级模型未下载，提示下载
                StyledMessageBox.information(
                    self,
                    "需要下载模型",
                    "詹姆斯水平需要下载 15GB 模型。\n\n"
                    "点击「下载高级模型」按钮开始下载。"
                )
                # 切回爱好者水平
                self.model_combo.blockSignals(True)
                self.model_combo.setCurrentIndex(0)
                self.model_combo.blockSignals(False)
                self._model_mode = "basic"
                return
            
            self._model_mode = "advanced"
            self._log("info", "已切换到 詹姆斯水平")
            self._log("default", "   使用高级评分模型，质量+美学双维度评估")
    
    def _on_download_advanced_model(self):
        """下载高级模型"""
        from ui.download_source_dialog import DownloadSourceDialog
        from region_detector import get_recommended_endpoint
        
        _, _, is_china = get_recommended_endpoint()
        
        dialog = DownloadSourceDialog(
            recommended_is_china=is_china,
            parent=self
        )
        
        if dialog.exec():
            endpoint = dialog.get_selected_endpoint()
            self._start_model_download(endpoint)

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
        self._update_preset_combo()  # 初始化预设选项
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
    
    def _update_preset_combo(self):
        """更新预设下拉菜单选项"""
        current_index = self.preset_combo.currentIndex() if hasattr(self, 'preset_combo') and self.preset_combo.count() > 0 else 0
        
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        
        # 获取用户自定义阈值
        custom_thresholds = self._get_saved_custom_thresholds()
        if custom_thresholds:
            custom_text = f"自定义 ({custom_thresholds[0]:.0f}/{custom_thresholds[1]:.0f}/{custom_thresholds[2]:.0f}/{custom_thresholds[3]:.0f})"
        else:
            custom_text = "自定义..."
        
        self.preset_combo.addItems([
            "全自动 (20% 均分)",
            "固定阈值 (78/72/66/58)",
            custom_text
        ])
        
        self.preset_combo.setCurrentIndex(min(current_index, 2))
        self.preset_combo.blockSignals(False)
    
    def _get_saved_custom_thresholds(self):
        """获取保存的自定义阈值"""
        try:
            from pathlib import Path
            import sys
            backend_path = Path(__file__).parent.parent / "backend"
            sys.path.insert(0, str(backend_path))
            from preset_manager import get_preset_manager
            
            preset_manager = get_preset_manager()
            user_preset = preset_manager.get_user_preset()
            if user_preset:
                return user_preset.thresholds
        except:
            pass
        return None
    
    def _save_custom_thresholds(self, thresholds: tuple):
        """保存自定义阈值"""
        try:
            from pathlib import Path
            import sys
            backend_path = Path(__file__).parent.parent / "backend"
            sys.path.insert(0, str(backend_path))
            from preset_manager import get_preset_manager
            
            preset_manager = get_preset_manager()
            preset_manager.save_user_preset(
                thresholds=thresholds,
                quality_weight=self._quality_weight,
                aesthetic_weight=self._aesthetic_weight,
            )
            # 更新下拉菜单显示
            self._update_preset_combo()
            return True
        except Exception as e:
            self._log("warning", f"⚠️ 保存自定义阈值失败: {e}")
            return False
    
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
        """创建按钮区域"""
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
            
            # 检测是否有 manifest 文件，自动弹出操作对话框
            from manifest_manager import has_manifest, ManifestManager
            if has_manifest(path):
                self._show_manifest_dialog(path)
    
    def _on_preset_changed(self, index):
        """预设选择变化"""
        if index == 0:  # 全自动
            self._last_preset_index = index
            self._auto_calibrate = True
            self._log("info", "🤖 已启用全自动模式")
            self._log("default", "   将按 20% 均分自动分配星级，完成后保存到自定义")
        
        elif index == 1:  # 固定阈值
            self._last_preset_index = index
            self._auto_calibrate = False
            self._thresholds = (78.0, 72.0, 66.0, 58.0)
            self._log("info", "🛠️  已切换到固定阈值")
            self._log("default", f"   阈值: 78/72/66/58")
        
        elif index == 2:  # 自定义
            custom_thresholds = self._get_saved_custom_thresholds()
            if custom_thresholds:
                self._last_preset_index = index
                self._auto_calibrate = False
                self._thresholds = custom_thresholds
                self._log("info", "🛠️  已切换到自定义阈值")
                self._log("default", f"   阈值: {custom_thresholds[0]:.0f}/{custom_thresholds[1]:.0f}/{custom_thresholds[2]:.0f}/{custom_thresholds[3]:.0f}")
            else:
                # 没有保存的自定义阈值，打开设置对话框
                self._show_settings()
                # 恢复到上一次的选择
                self.preset_combo.blockSignals(True)
                self.preset_combo.setCurrentIndex(self._last_preset_index)
                self.preset_combo.blockSignals(False)
    
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
    
    def _show_manifest_dialog(self, dir_path: str) -> bool:
        """
        显示 manifest 操作对话框
        
        Returns:
            True 如果用户选择了操作（非取消）
        """
        from manifest_manager import ManifestManager
        from ui.manifest_action_dialog import ManifestActionDialog
        
        manifest = ManifestManager(dir_path)
        summary = manifest.get_summary()
        
        dialog = ManifestActionDialog(
            parent=self,
            summary=summary,
            is_in_progress=manifest.is_in_progress,
            current_thresholds=self._thresholds,
        )
        
        if dialog.exec():
            action = dialog.get_action()
            
            if action == ManifestActionDialog.ACTION_CANCEL:
                return False
            
            elif action == ManifestActionDialog.ACTION_RESET:
                # 重置数据 - 直接执行完整重置流程（不再弹确认框）
                self._execute_reset(dir_path)
                return True
            
            elif action == ManifestActionDialog.ACTION_RERATE:
                # 快速重评星（使用用户选择的阈值）
                selected_thresholds = dialog.get_selected_thresholds()
                self._perform_quick_rerate(dir_path, manifest, selected_thresholds)
                return True
            
            elif action == ManifestActionDialog.ACTION_CONTINUE:
                # 继续处理
                self._configure_and_start_worker(dir_path)
                return True
        
        return False

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
        
        # 检测是否有 manifest（已处理过的目录）
        from manifest_manager import has_manifest
        
        if has_manifest(dir_path):
            # 使用共享的对话框处理逻辑
            if self._show_manifest_dialog(dir_path):
                return  # 已经处理了（重评星/重置/继续）
            else:
                return  # 用户取消
        
        # 正常处理流程（新目录）
        self._configure_and_start_worker(dir_path)
    
    def _configure_and_start_worker(self, dir_path: str):
        """配置 worker 并开始处理"""
        thresholds = self._thresholds
        
        # 配置 worker
        self._worker.configure(
            input_dir=dir_path,
            thresholds=thresholds,
            quality_weight=self._quality_weight,
            aesthetic_weight=self._aesthetic_weight,
            write_xmp=self._write_xmp,
            organize=self._organize,
            output_dir=dir_path,
            csv_path=None,
            auto_calibrate=self._auto_calibrate,
            model_mode=self._model_mode,  # 新增：模型模式
        )
        
        # 开始处理
        self._start_processing()

    
    def _perform_reset_and_process(self, dir_path: str):
        """重置数据后重新处理"""
        from exif_writer import get_exif_writer
        from pathlib import Path
        
        exif_writer = get_exif_writer()
        
        # 扫描顶层文件
        supported_extensions = {
            ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp",
            ".arw", ".cr2", ".cr3", ".nef", ".dng", ".orf", ".rw2", ".raf",
            ".3fr", ".iiq", ".rwl", ".srw", ".x3f", ".pef", ".erf", ".kdc", ".dcr", ".mrw", ".fff"
        }
        
        files = []
        for f in Path(dir_path).iterdir():  # 只扫描顶层
            # 跳过隐藏文件和子目录
            if f.name.startswith(".") or f.is_dir():
                continue
            if f.is_file() and f.suffix.lower() in supported_extensions:
                files.append(str(f))
        
        # 清除元数据
        for file_path in files:
            try:
                exif_writer.reset_metadata(file_path)
            except:
                pass
        
        self._log("success", f"✅ 已重置 {len(files)} 个文件的元数据")
        
        # 继续处理
        self._configure_and_start_worker(dir_path)
    
    def _perform_quick_rerate(self, dir_path: str, manifest, thresholds: tuple = None):
        """使用缓存分数快速重评星"""
        from exif_writer import get_exif_writer
        from manifest_manager import quick_rerate
        from PySide6.QtWidgets import QApplication
        from pathlib import Path
        
        # 使用传入的阈值或默认阈值
        if thresholds is None:
            thresholds = self._thresholds
        
        # 清空日志
        self.log_text.clear()
        
        # 显示任务信息
        self._log("info", "━" * 45)
        self._log("info", "⚡ 快速重评星")
        self._log("info", "━" * 45)
        self._log("info", f"📁 目录: {dir_path}")
        self._log("info", "")
        
        # 步骤 1: 显示配置
        self._log("info", "⚙️ [步骤 1/3] 加载配置...")
        self._log("info", f"   新阈值: {thresholds[0]:.1f} / {thresholds[1]:.1f} / {thresholds[2]:.1f} / {thresholds[3]:.1f}")
        self._log("info", f"   权重: 质量 {self._quality_weight:.0%} + 美学 {self._aesthetic_weight:.0%}")
        self._log("info", "")
        
        # 初始化进度条
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self._set_status("重评星中", "accent")
        
        try:
            # 步骤 2: 计算新星级
            self._log("info", "🔄 [步骤 2/3] 读取缓存分数并计算新星级...")
            self._log("info", "   请稍候...")
            
            # 强制更新 UI，让用户看到进度
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            
            results = quick_rerate(
                directory=dir_path,
                new_thresholds=thresholds,
                quality_weight=self._quality_weight,
                aesthetic_weight=self._aesthetic_weight,
            )
            
            total = len(results)
            self._log("success", f"   ✓ 读取了 {total} 个文件的缓存分数")
            self._log("info", "")
            
            # 步骤 3: 写入 EXIF
            self._log("info", "📝 [步骤 3/3] 写入新星级到 EXIF...")
            exif_writer = get_exif_writer()
            changed_count = 0
            
            for i, r in enumerate(results):
                filename = r["filename"]
                
                # 查找文件（可能在子目录）
                file_path = None
                for f in Path(dir_path).rglob(filename):
                    file_path = f
                    break
                
                if file_path and file_path.exists():
                    try:
                        exif_writer.write_rating(str(file_path), r["new_rating"])
                        
                        # 只显示有变化的文件
                        if r["changed"]:
                            changed_count += 1
                            stars_old = "★" * r["old_rating"] + "☆" * (4 - r["old_rating"])
                            stars_new = "★" * r["new_rating"] + "☆" * (4 - r["new_rating"])
                            self._log("default", f"   [{i+1:3d}/{total}] {filename[:35]:<35} {stars_old} → {stars_new}")
                    except Exception as e:
                        self._log("warning", f"   ⚠️ {filename}: {e}")
                
                # 更新进度
                progress = int((i + 1) / total * 100)
                self.progress_bar.setValue(progress)
                self.progress_percent.setText(f"{progress}%")
                
                # 每 10 个文件刷新 UI
                if (i + 1) % 10 == 0:
                    QApplication.processEvents()
            
            # 完成
            self.progress_bar.setValue(100)
            self.progress_percent.setText("100%")
            self._set_status("就绪", "success")
            
            self._log("info", "")
            self._log("info", "━" * 45)
            self._log("success", "✅ 快速重评星完成!")
            self._log("info", "━" * 45)
            self._log("info", f"   处理文件: {total} 个")
            self._log("info", f"   星级变化: {changed_count} 个")
            
            # 显示新的分布
            by_rating = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
            for r in results:
                by_rating[r["new_rating"]] = by_rating.get(r["new_rating"], 0) + 1
            
            self._log("info", "")
            self._log("info", "📊 新的星级分布:")
            for star in range(4, -1, -1):
                count = by_rating.get(star, 0)
                bar = "█" * min(count, 30)
                self._log("default", f"   {'★' * star}{'☆' * (4-star)}: {count:3d} {bar}")
            
        except Exception as e:
            self._set_status("错误", "error")
            self._log("error", f"❌ 重评星失败: {e}")
    
    def _setup_worker(self):
        """设置后台工作线程"""
        self._worker = ScoringWorker(self)
        
        # 连接信号
        self._worker.started_loading.connect(self._on_model_loading)
        self._worker.model_loaded.connect(self._on_model_loaded)
        self._worker.progress.connect(self._on_progress)
        self._worker.log_message.connect(self._on_log_message)
        self._worker.finished_scoring.connect(self._on_scoring_finished)
        self._worker.calibration_completed.connect(self._on_calibration_completed)
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
        self._log("info", "🔄 正在加载 选片模型...")
    
    def _on_preload_finished(self, success: bool):
        """预加载完成"""
        self._model_loaded = success
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_percent.setText("0%")
        
        if success:
            self._set_status("就绪", "success")
            self._log("success", "✅ 选片模型 加载完成")
            # 启用按钮
            self.start_btn.setEnabled(True)
            self.reset_btn.setEnabled(True)
        else:
            self._set_status("模型加载失败", "error")
            self._log("error", "❌ 选片模型 加载失败")
    
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
    
    def _on_calibration_completed(self, thresholds: tuple):
        """自动校准完成，保存阈值到用户自定义"""
        self._save_custom_thresholds(thresholds)
        self._thresholds = thresholds
        self._log("info", "💾 已保存校准阈值到「自定义」预设")
    
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
        
        # 分数统计
        if 'scores' in summary and summary['scores']:
            scores = summary['scores']
            max_score = max(scores)
            min_score = min(scores)
            avg_score = sum(scores) / len(scores)
            self._log("info", "📊 分数统计:")
            self._log("info", f"   最高分: {max_score:.1f}")
            self._log("info", f"   最低分: {min_score:.1f}")
            self._log("info", f"   平均分: {avg_score:.1f}")
            self._log("info", "")
            
            # 10分区间分布
            self._log("info", "📈 分数区间分布:")
            intervals = {
                "90-100": 0,
                "80-89": 0,
                "70-79": 0,
                "60-69": 0,
                "50-59": 0,
                "40-49": 0,
                "0-39": 0,
            }
            for s in scores:
                if s >= 90:
                    intervals["90-100"] += 1
                elif s >= 80:
                    intervals["80-89"] += 1
                elif s >= 70:
                    intervals["70-79"] += 1
                elif s >= 60:
                    intervals["60-69"] += 1
                elif s >= 50:
                    intervals["50-59"] += 1
                elif s >= 40:
                    intervals["40-49"] += 1
                else:
                    intervals["0-39"] += 1
            
            for interval, count in intervals.items():
                bar = "█" * min(count, 30)
                self._log("default", f"   {interval}: {count:3d} {bar}")
            self._log("info", "")
        
        # 星级分布
        self._log("info", "⭐ 星级分布:")
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
        
        # 执行重置
        self._execute_reset(dir_path)
    
    def _execute_reset(self, dir_path: str):
        """执行完整重置（核心逻辑）"""
        # 禁用按钮
        self.start_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        self._set_status("重置中", "warning")
        
        # 清空日志
        self.log_text.clear()
        
        # 执行清除
        self._log("info", "━" * 45)
        self._log("info", "🧹 开始完整重置")
        self._log("info", "━" * 45)
        self._log("info", f"📁 目标目录: {dir_path}")
        self._log("info", "")
        
        import sys
        from pathlib import Path
        backend_path = Path(__file__).parent.parent / "backend"
        sys.path.insert(0, str(backend_path))
        from exif_writer import get_exif_writer
        from manifest_manager import ManifestManager, has_manifest
        
        # 步骤 1: 检测 manifest
        self._log("info", "📋 [步骤 1/4] 检测处理记录...")
        
        if has_manifest(dir_path):
            manifest = ManifestManager(dir_path)
            summary = manifest.get_summary()
            self._log("success", f"   ✓ 发现 manifest 文件")
            self._log("info", f"   已处理: {summary.get('processed_files', 0)} 个文件")
            self._log("info", "")
            
            # 步骤 2: 恢复文件位置
            self._log("info", "📂 [步骤 2/4] 恢复文件位置...")
            self._log("info", "   将文件从星级子目录移回顶层...")
            restore_result = manifest.restore_files()
            
            if restore_result["moved"] > 0:
                self._log("success", f"   ✓ 移动了 {restore_result['moved']} 个文件")
            if restore_result["already_in_place"] > 0:
                self._log("info", f"   ○ {restore_result['already_in_place']} 个文件已在原位")
            if restore_result["failed"] > 0:
                self._log("warning", f"   ✗ {restore_result['failed']} 个文件移动失败")
            self._log("info", "")
            
            # 步骤 3: 删除 manifest
            self._log("info", "🗑️ [步骤 3/4] 删除处理记录...")
            manifest.delete()
            self._log("success", "   ✓ 已删除 .superelite_manifest.json")
            self._log("info", "")
        else:
            self._log("info", "   ○ 未发现 manifest 文件，跳过恢复步骤")
            self._log("info", "")
        
        # 步骤 4: 清除 EXIF 元数据
        self._log("info", "🏷️ [步骤 4/4] 清除 EXIF 元数据...")
        exif_writer = get_exif_writer()
        
        # 扫描顶层目录的文件（不进入用户原有子目录）
        self._log("info", "   扫描顶层目录图片文件...")
        supported_extensions = {
            ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp",
            ".arw", ".cr2", ".cr3", ".nef", ".dng", ".orf", ".rw2", ".raf",
            ".3fr", ".iiq", ".rwl", ".srw", ".x3f", ".pef", ".erf", ".kdc", ".dcr", ".mrw", ".fff"
        }
        
        files = []
        for f in Path(dir_path).iterdir():  # 只扫描顶层
            # 跳过隐藏文件和子目录
            if f.name.startswith(".") or f.is_dir():
                continue
            if f.is_file() and f.suffix.lower() in supported_extensions:
                files.append(str(f))
        
        if not files:
            self._log("warning", "   未找到图片文件")
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
        
        self._log("info", "")
        self._log("info", "━" * 45)
        self._log("success", "✅ 重置完成!")
        self._log("info", "━" * 45)
        self._log("info", f"   清除元数据: {success_count} / {total} 成功")
        self._log("info", "   目录已恢复到初始状态")
        
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
