# -*- mode: python ; coding: utf-8 -*-
"""
SuperElite - PyInstaller 打包配置
不包含模型，模型在运行时按需下载
支持 macOS 和 Windows 双平台
"""

import os
import sys
import site
from PyInstaller.utils.hooks import collect_data_files, copy_metadata

# 获取当前工作目录
base_path = os.path.abspath('.')

# 平台检测
IS_WINDOWS = sys.platform.startswith('win')
IS_MACOS = sys.platform == 'darwin'

# 动态获取 site-packages 路径
sp = site.getsitepackages()
site_packages = sp[1] if len(sp) > 1 else sp[0]

# =====================================================
# 数据文件配置 (包含基础模型 NIMA + TOPIQ)
# =====================================================
all_datas = [
    # 图片资源
    (os.path.join(base_path, 'img'), 'img'),
]

# 基础模型 (NIMA + TOPIQ) - 约 500MB
models_path = os.path.join(base_path, 'models')
if os.path.exists(models_path):
    all_datas.append((models_path, 'models'))

# ExifTool bundle (如果存在)
exiftool_bundle_path = os.path.join(base_path, 'exiftool_bundle')
if os.path.exists(exiftool_bundle_path):
    all_datas.append((exiftool_bundle_path, 'exiftool_bundle'))


# 收集依赖包的数据文件
try:
    rawpy_datas = collect_data_files('rawpy')
    all_datas.extend(rawpy_datas)
    all_datas.extend(copy_metadata('rawpy'))
except Exception:
    pass

try:
    transformers_datas = collect_data_files('transformers')
    all_datas.extend(transformers_datas)
    all_datas.extend(copy_metadata('transformers'))
except Exception:
    pass

try:
    imageio_datas = collect_data_files('imageio')
    all_datas.extend(imageio_datas)
    all_datas.extend(copy_metadata('imageio'))
except Exception:
    pass

# 图标路径 (跨平台)
if IS_WINDOWS:
    icon_path = os.path.join(base_path, 'img', 'SuperElite.ico')
else:
    icon_path = os.path.join(base_path, 'img', 'SuperElite.icns')
if not os.path.exists(icon_path):
    icon_path = None


# =====================================================
# 分析配置
# =====================================================
a = Analysis(
    ['main.py'],
    pathex=[base_path],
    binaries=[],
    datas=all_datas,
    hiddenimports=[
        # PyTorch 和 AI
        'torch',
        'torch.nn',
        'torch.utils',
        'torchvision',
        'torchvision.transforms',
        'transformers',
        'transformers.models',
        'transformers.models.auto',
        'accelerate',
        'sentencepiece',
        'protobuf',
        'huggingface_hub',
        
        # PySide6 GUI
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        
        # 图像处理
        'PIL',
        'PIL.Image',
        'Pillow',
        'rawpy',
        'imageio',
        
        # 工具库
        'tqdm',
        'icecream',
        'flask',
        
        # 后端模块
        'backend',
        'backend.one_align_scorer',
        'backend.pyiqa_scorer',
        'backend.nima_model',
        'backend.topiq_model',
        'backend.exif_writer',
        'backend.model_downloader',
        'backend.region_detector',
        'backend.raw_converter',
        'backend.reset_metadata',
        'backend.manifest_manager',
        'backend.preset_manager',
        'backend.photo_critic',
        
        # timm (骨干网络)
        'timm',
        'timm.models',
        'timm.models.resnet',
        'timm.models.inception_resnet_v2',

        
        # UI 模块
        'ui',
        'ui.main_window',
        'ui.scoring_worker',
        'ui.styles',
        'ui.settings_dialog',
        'ui.download_source_dialog',
        'ui.calibrate_confirm_dialog',
        'ui.custom_dialogs',
        'ui.manifest_action_dialog',
        
        # 多进程支持
        'multiprocessing',
        'multiprocessing.spawn',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt5', 
        'PyQt6', 
        'tkinter',
        # 不需要的大型包
        'matplotlib',
        'scipy',
        # 间接依赖，代码中未使用 (节省 ~300MB)
        'numba',
        'llvmlite',
        'pyarrow',
        'cv2',
        'opencv',
        'opencv-python',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# =====================================================
# 可执行文件配置
# =====================================================
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SuperElite',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI 应用，不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,  # 让 PyInstaller 自动检测架构
    codesign_identity=None,  # 在 build_release.sh 中手动签名
    entitlements_file=None,
    icon=icon_path,
)

# =====================================================
# 应用程序包配置
# =====================================================
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SuperElite',
)

# =====================================================
# macOS .app 包配置 (仅 macOS)
# =====================================================
if IS_MACOS:
    app = BUNDLE(
        coll,
        name='SuperElite.app',
        icon=icon_path,
        bundle_identifier='com.jamesphotography.superelite',
        info_plist={
            'CFBundleName': 'SuperElite',
            'CFBundleDisplayName': '摄影评片',
            'CFBundleVersion': '1.0.0',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,  # 支持深色模式
            'LSMinimumSystemVersion': '12.0',  # macOS Monterey+
            'NSHumanReadableCopyright': '© 2026 James Photography',
        },
    )

