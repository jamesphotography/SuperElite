"""
RAW 文件转 JPG 模块
从 SuperPicky 项目提取并简化
"""

import os
import rawpy
import imageio


def raw_to_jpeg(raw_file_path: str, jpg_file_path: str = None) -> str:
    """
    将 RAW 文件转换为 JPEG（提取内嵌缩略图）

    Args:
        raw_file_path: RAW 文件路径
        jpg_file_path: 输出 JPG 文件路径（可选，默认使用临时目录）

    Returns:
        生成的 JPG 文件路径

    Raises:
        FileNotFoundError: RAW 文件不存在
        ValueError: RAW 文件无法读取或无内嵌缩略图
    """
    if not os.path.exists(raw_file_path):
        raise FileNotFoundError(f"RAW 文件不存在: {raw_file_path}")

    # 如果未指定输出路径，使用临时目录
    if jpg_file_path is None:
        import tempfile
        base_name = os.path.splitext(os.path.basename(raw_file_path))[0]
        jpg_file_path = os.path.join(
            tempfile.gettempdir(),
            f'_tmp_superelite_{base_name}.jpg'  # 明显的临时文件前缀
        )

    try:
        with rawpy.imread(raw_file_path) as raw:
            # 提取 RAW 文件内嵌的缩略图
            thumbnail = raw.extract_thumb()

            if thumbnail.format == rawpy.ThumbFormat.JPEG:
                # JPEG 格式：直接写入文件
                with open(jpg_file_path, 'wb') as f:
                    f.write(thumbnail.data)
            elif thumbnail.format == rawpy.ThumbFormat.BITMAP:
                # BITMAP 格式：使用 imageio 转换
                imageio.imsave(jpg_file_path, thumbnail.data)
            else:
                raise ValueError(f"不支持的缩略图格式: {thumbnail.format}")

    except Exception as e:
        raise ValueError(f"RAW 文件转换失败: {e}")

    return jpg_file_path


def is_raw_file(file_path: str) -> bool:
    """
    检查文件是否为 RAW 格式

    Args:
        file_path: 文件路径

    Returns:
        True 如果是 RAW 文件，否则 False
    """
    raw_extensions = {
        '.nef',   # Nikon
        '.cr2',   # Canon
        '.cr3',   # Canon (新格式)
        '.arw',   # Sony
        '.orf',   # Olympus
        '.rw2',   # Panasonic
        '.dng',   # Adobe/通用
        '.raf',   # Fujifilm
        '.raw',   # 通用
    }

    ext = os.path.splitext(file_path)[1].lower()
    return ext in raw_extensions


def scan_raw_files(directory: str, recursive: bool = False) -> list:
    """
    扫描目录下的所有 RAW 文件

    Args:
        directory: 目录路径
        recursive: 是否递归扫描子目录

    Returns:
        RAW 文件路径列表（绝对路径）
    """
    if not os.path.isdir(directory):
        raise NotADirectoryError(f"不是有效的目录: {directory}")

    raw_files = []

    if recursive:
        # 递归扫描
        for root, dirs, files in os.walk(directory):
            for file_name in files:
                # 跳过 macOS 临时文件
                if file_name.startswith('._'):
                    continue
                file_path = os.path.join(root, file_name)
                if is_raw_file(file_path):
                    raw_files.append(file_path)
    else:
        # 仅扫描当前目录
        for file_name in os.listdir(directory):
            # 跳过 macOS 临时文件
            if file_name.startswith('._'):
                continue
            file_path = os.path.join(directory, file_name)
            if os.path.isdir(file_path):
                continue
            if is_raw_file(file_path):
                raw_files.append(file_path)

    # 按文件名排序
    raw_files.sort()

    return raw_files


if __name__ == '__main__':
    # 测试代码
    import sys

    if len(sys.argv) < 2:
        print("用法: python raw_converter.py <RAW文件路径>")
        sys.exit(1)

    raw_file = sys.argv[1]

    print(f"正在转换: {raw_file}")
    jpg_file = raw_to_jpeg(raw_file)
    print(f"已生成: {jpg_file}")
