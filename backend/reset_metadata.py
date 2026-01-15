"""
SuperElite - Reset 工具
清除目录中所有图片的 AI 评分元数据
"""

import os
import subprocess
from pathlib import Path
from typing import List
from tqdm import tqdm


class MetadataReset:
    """元数据重置工具"""

    # 支持的文件扩展名
    SUPPORTED_EXTENSIONS = {
        # RAW 格式
        ".arw", ".cr2", ".cr3", ".nef", ".dng", ".raf",
        ".orf", ".rw2", ".pef", ".srw",
        # 常规格式
        ".jpg", ".jpeg", ".png",
    }

    def __init__(self, exiftool_path: str = "exiftool"):
        """
        初始化 Reset 工具

        Args:
            exiftool_path: exiftool 可执行文件路径
        """
        self.exiftool_path = exiftool_path
        self._verify_exiftool()

    def _verify_exiftool(self):
        """验证 exiftool 是否可用"""
        try:
            result = subprocess.run(
                [self.exiftool_path, "-ver"],
                capture_output=True,
                text=True,
                check=True,
            )
            print(f"[Reset] 使用 exiftool: {self.exiftool_path} (版本 {result.stdout.strip()})")
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                f"exiftool 未找到或无法执行: {self.exiftool_path}\n"
                "请安装 exiftool: brew install exiftool"
            )

    def scan_directory(self, directory: str) -> List[str]:
        """
        扫描目录中的所有支持图片

        Args:
            directory: 目录路径

        Returns:
            图片文件路径列表
        """
        directory = Path(directory)
        if not directory.exists():
            raise FileNotFoundError(f"目录不存在: {directory}")

        files = []
        for file_path in directory.rglob("*"):
            if file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                if not file_path.name.startswith("._"):  # 跳过 macOS 隐藏文件
                    files.append(str(file_path))

        return sorted(files)

    def reset_file(self, file_path: str) -> bool:
        """
        清除单个文件的 AI 评分元数据

        Args:
            file_path: 文件路径

        Returns:
            是否成功
        """
        try:
            # 要清除的字段
            clear_fields = [
                "-Rating=",              # 星级
                "-Subject=",             # 关键词
                "-Title=",               # 标题
                "-Caption-Abstract=",    # 摘要
                "-marked=",              # Pick 旗标
                "-Label=",               # 颜色标签
                "-overwrite_original",   # 覆盖原文件，不创建备份
            ]

            # 删除 XMP sidecar 文件（如果存在）
            xmp_path = Path(file_path).with_suffix(Path(file_path).suffix + ".xmp")
            if xmp_path.exists():
                xmp_path.unlink()
                print(f"[Reset] 已删除 XMP: {xmp_path.name}")

            # 清除嵌入的元数据
            result = subprocess.run(
                [self.exiftool_path] + clear_fields + [file_path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode != 0:
                print(f"[Reset] 警告: {Path(file_path).name} - {result.stderr.strip()}")
                return False

            return True

        except Exception as e:
            print(f"[Reset] 错误: {Path(file_path).name} - {str(e)}")
            return False

    def reset_directory(self, directory: str, confirm: bool = True) -> dict:
        """
        清除整个目录的 AI 评分元数据

        Args:
            directory: 目录路径
            confirm: 是否需要用户确认

        Returns:
            统计信息字典
        """
        # 扫描文件
        print(f"\n📁 扫描目录: {directory}")
        files = self.scan_directory(directory)
        print(f"   找到 {len(files)} 张图片")

        if len(files) == 0:
            print("\n❌ 没有找到支持的图片文件")
            return {"total": 0, "success": 0, "failed": 0}

        # 确认操作
        if confirm:
            print("\n⚠️  警告: 此操作将清除所有 AI 评分元数据（星级、标签、XMP文件）")
            print("   这个操作不可逆！")
            response = input("\n是否继续？(yes/no): ").strip().lower()
            if response not in ["yes", "y"]:
                print("\n❌ 操作已取消")
                return {"total": 0, "success": 0, "failed": 0}

        # 重置所有文件
        print(f"\n🔄 开始重置 {len(files)} 张图片的元数据...\n")
        success_count = 0
        failed_count = 0

        for file_path in tqdm(files, desc="重置进度", unit="张"):
            if self.reset_file(file_path):
                success_count += 1
            else:
                failed_count += 1

        # 统计结果
        print(f"\n✅ 完成! 成功: {success_count}/{len(files)}")
        if failed_count > 0:
            print(f"⚠️  失败: {failed_count} 张")

        return {
            "total": len(files),
            "success": success_count,
            "failed": failed_count,
        }


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="SuperElite Reset - 清除 AI 评分元数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 清除目录中的所有元数据（需要确认）
  python reset_metadata.py --dir /path/to/photos

  # 跳过确认直接清除
  python reset_metadata.py --dir /path/to/photos --yes

  # 使用自定义 exiftool 路径
  python reset_metadata.py --dir /path/to/photos --exiftool /custom/path/exiftool
        """,
    )

    parser.add_argument(
        "--dir",
        type=str,
        required=True,
        help="要清除元数据的图片目录",
    )

    parser.add_argument(
        "--yes",
        action="store_true",
        help="跳过确认提示，直接执行",
    )

    parser.add_argument(
        "--exiftool",
        type=str,
        default="exiftool",
        help="exiftool 可执行文件路径（默认: exiftool）",
    )

    args = parser.parse_args()

    # 创建 Reset 工具
    try:
        resetter = MetadataReset(exiftool_path=args.exiftool)
    except RuntimeError as e:
        print(f"\n❌ {e}")
        return 1

    # 执行重置
    stats = resetter.reset_directory(
        directory=args.dir,
        confirm=not args.yes,
    )

    # 显示统计
    print(f"\n📊 统计摘要:")
    print(f"   总数: {stats['total']}")
    print(f"   成功: {stats['success']}")
    print(f"   失败: {stats['failed']}")

    return 0 if stats['failed'] == 0 else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
