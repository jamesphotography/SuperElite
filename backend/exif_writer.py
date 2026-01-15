"""
EXIF 元数据写入模块
从 SuperPicky 的 exiftool_manager.py 简化而来
"""

import os
import subprocess
import shutil


class ExifWriter:
    """EXIF 元数据写入器"""

    def __init__(self, exiftool_path: str = None):
        """
        初始化 EXIF 写入器

        Args:
            exiftool_path: exiftool 可执行文件路径（可选，默认从 PATH 查找）
        """
        self.exiftool_path = exiftool_path or self._find_exiftool()

        if not self.exiftool_path:
            raise RuntimeError(
                "未找到 exiftool，请先安装:\n"
                "  macOS: brew install exiftool\n"
                "  Windows: 从 https://exiftool.org/ 下载"
            )

        print(f"[EXIF] 使用 exiftool: {self.exiftool_path}")

    def _find_exiftool(self) -> str:
        """在系统 PATH 中查找 exiftool"""
        return shutil.which('exiftool')

    def write_align_score(self, raw_file_path: str, align_score: float) -> bool:
        """
        将 Align 评分写入 RAW 文件 EXIF 元数据

        评分写入到 IPTC:Country-PrimaryLocationName 字段（国家/地区）
        格式：05.2f（如 "07.85"）

        Args:
            raw_file_path: RAW 文件路径
            align_score: Align 评分（0-10）

        Returns:
            True 如果写入成功，否则 False

        Raises:
            FileNotFoundError: RAW 文件不存在
        """
        if not os.path.exists(raw_file_path):
            raise FileNotFoundError(f"RAW 文件不存在: {raw_file_path}")

        # 格式化评分为固定宽度字符串（5位，2位小数）
        # 例如: 7.85 → "07.85", 10.00 → "10.00"
        align_str = f'{align_score:05.2f}'

        # 构建 exiftool 命令
        cmd = [
            self.exiftool_path,
            f'-IPTC:Country-PrimaryLocationName={align_str}',
            '-overwrite_original',  # 不保留备份文件（.original）
            '-m',  # 忽略 minor 错误和警告
            '-ignoreMinorErrors',  # 忽略 minor 错误
            raw_file_path
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            # 对于 DJI DNG 文件，忽略 minor 错误（returncode 仍然可能是 0）
            # 检查是否成功写入（即使有警告）
            if result.returncode != 0:
                # 检查是否只是警告性质的错误
                stderr_lower = result.stderr.lower()
                if 'warning' in stderr_lower or 'minor' in stderr_lower:
                    # 是警告，可以接受
                    return True
                else:
                    # 真正的错误
                    print(f"[EXIF] 写入失败: {result.stderr}")
                    return False

            return True

        except subprocess.TimeoutExpired:
            print(f"[EXIF] 写入超时: {raw_file_path}")
            return False

        except Exception as e:
            print(f"[EXIF] 写入异常: {e}")
            return False

    def write_rating(self, raw_file_path: str, rating: int) -> bool:
        """
        将星级评分写入 RAW 文件 XMP 元数据

        写入到 XMP:Rating 字段（Lightroom 星级）

        Args:
            raw_file_path: RAW 文件路径
            rating: 星级评分（0-5）

        Returns:
            True 如果写入成功，否则 False
        """
        if not os.path.exists(raw_file_path):
            raise FileNotFoundError(f"RAW 文件不存在: {raw_file_path}")

        # 确保评分在有效范围内
        rating = max(0, min(5, int(rating)))

        cmd = [
            self.exiftool_path,
            f'-XMP:Rating={rating}',
            '-overwrite_original',
            '-m',
            '-ignoreMinorErrors',
            raw_file_path
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                stderr_lower = result.stderr.lower()
                if 'warning' in stderr_lower or 'minor' in stderr_lower:
                    return True
                else:
                    return False

            return True

        except (subprocess.TimeoutExpired, Exception):
            return False

    def write_full_scoring_metadata(
        self,
        file_path: str,
        quality_score: float,
        aesthetic_score: float,
        total_score: float,
        rating: int
    ) -> bool:
        """
        写入完整评分元数据到图片文件

        字段映射:
        - 质量分 → IPTC:City (城市)
        - 美学分 → IPTC:Province-State (省/州)
        - 总分 → IPTC:Country-PrimaryLocationName (国家)
        - 星级 → XMP:Rating

        Args:
            file_path: 图片文件路径
            quality_score: 质量分 (0-100)
            aesthetic_score: 美学分 (0-100)
            total_score: 综合分 (0-100)
            rating: 星级评分 (0-5)

        Returns:
            True 如果写入成功，否则 False
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 格式化评分为固定宽度字符串
        quality_str = f'{quality_score:05.1f}'
        aesthetic_str = f'{aesthetic_score:05.1f}'
        total_str = f'{total_score:05.1f}'
        rating = max(0, min(5, int(rating)))

        cmd = [
            self.exiftool_path,
            f'-IPTC:City={quality_str}',                    # 质量分 → 城市
            f'-IPTC:Province-State={aesthetic_str}',        # 美学分 → 省份
            f'-IPTC:Country-PrimaryLocationName={total_str}',  # 总分 → 国家
            f'-XMP:Rating={rating}',                        # 星级
            '-overwrite_original',
            '-m',
            '-ignoreMinorErrors',
            file_path
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                stderr_lower = result.stderr.lower()
                if 'warning' in stderr_lower or 'minor' in stderr_lower:
                    return True
                return False

            return True

        except (subprocess.TimeoutExpired, Exception):
            return False

    def reset_metadata(self, file_path: str) -> bool:
        """
        重置/清除 SuperElite 写入的所有元数据

        清除:
        - XMP:Rating (星级)
        - XMP:Label (色标)
        - XMP:PickLabel (旗标)
        - IPTC:Country-PrimaryLocationName (国家/AI评分)
        - IPTC:Province-State (省份)
        - IPTC:City (城市)

        Args:
            file_path: 图片文件路径

        Returns:
            True 如果重置成功，否则 False
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        cmd = [
            self.exiftool_path,
            '-XMP:Rating=',                         # 清空星级
            '-XMP:Label=',                          # 清空色标
            '-XMP:PickLabel=',                      # 清空旗标
            '-IPTC:Country-PrimaryLocationName=',   # 清空国家
            '-IPTC:Province-State=',                # 清空省份
            '-IPTC:City=',                          # 清空城市
            '-overwrite_original',
            '-m',
            '-ignoreMinorErrors',
            file_path
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                stderr_lower = result.stderr.lower()
                if 'warning' in stderr_lower or 'minor' in stderr_lower:
                    return True
                return False

            return True

        except (subprocess.TimeoutExpired, Exception):
            return False

    def write_score_and_rating(
        self,
        raw_file_path: str,
        nima_score: float,
        rating: int
    ) -> bool:
        """
        同时写入 NIMA 评分和星级到 RAW 文件

        Args:
            raw_file_path: RAW 文件路径
            nima_score: NIMA 评分（0-10）
            rating: 星级评分（0-5）

        Returns:
            True 如果写入成功，否则 False
        """
        if not os.path.exists(raw_file_path):
            raise FileNotFoundError(f"RAW 文件不存在: {raw_file_path}")

        nima_str = f'{nima_score:05.2f}'
        rating = max(0, min(5, int(rating)))

        # 一次性写入两个字段
        cmd = [
            self.exiftool_path,
            f'-IPTC:Country-PrimaryLocationName={nima_str}',
            f'-XMP:Rating={rating}',
            '-overwrite_original',
            '-m',
            '-ignoreMinorErrors',
            raw_file_path
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                stderr_lower = result.stderr.lower()
                if 'warning' in stderr_lower or 'minor' in stderr_lower:
                    return True
                return False

            return True

        except (subprocess.TimeoutExpired, Exception):
            return False

    def write_caption(self, raw_file_path: str, caption: str) -> bool:
        """
        将评语写入 Caption (题注) 字段

        写入到 IPTC:Caption-Abstract 和 XMP:Description 字段

        Args:
            raw_file_path: RAW/图片文件路径
            caption: 评语文本

        Returns:
            True 如果写入成功，否则 False
        """
        if not os.path.exists(raw_file_path):
            raise FileNotFoundError(f"文件不存在: {raw_file_path}")

        cmd = [
            self.exiftool_path,
            f'-IPTC:Caption-Abstract={caption}',
            f'-XMP:Description={caption}',
            '-overwrite_original',
            '-m',
            '-ignoreMinorErrors',
            raw_file_path
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                stderr_lower = result.stderr.lower()
                if 'warning' in stderr_lower or 'minor' in stderr_lower:
                    return True
                return False

            return True

        except (subprocess.TimeoutExpired, Exception):
            return False

    def write_keywords(self, raw_file_path: str, keywords: list) -> bool:
        """
        将关键字写入 Keywords 字段

        写入到 IPTC:Keywords 和 XMP:Subject 字段

        Args:
            raw_file_path: RAW/图片文件路径
            keywords: 关键字列表

        Returns:
            True 如果写入成功，否则 False
        """
        if not os.path.exists(raw_file_path):
            raise FileNotFoundError(f"文件不存在: {raw_file_path}")

        if not keywords:
            return True  # 空列表视为成功

        # 构建命令：每个关键字作为单独的参数
        cmd = [
            self.exiftool_path,
        ]

        # 添加每个关键字
        for kw in keywords:
            cmd.append(f'-IPTC:Keywords={kw}')
            cmd.append(f'-XMP:Subject={kw}')

        cmd.extend([
            '-overwrite_original',
            '-m',
            '-ignoreMinorErrors',
            raw_file_path
        ])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                stderr_lower = result.stderr.lower()
                if 'warning' in stderr_lower or 'minor' in stderr_lower:
                    return True
                return False

            return True

        except (subprocess.TimeoutExpired, Exception):
            return False

    def write_all_metadata(
        self,
        raw_file_path: str,
        score: float,
        rating: int,
        title: str = None,
        caption: str = None,
        keywords: list = None,
        pick_flag: str = None,
        color_label: str = None,
    ) -> bool:
        """
        一次性写入所有元数据到图片文件

        Args:
            raw_file_path: RAW/图片文件路径
            score: AI 评分，写入城市字段
            rating: 星级评分 (0-5)
            title: 作品名称 (可选)，写入标题字段
            caption: 后期建议/题注 (可选)
            keywords: 关键字列表 (可选)
            pick_flag: Lightroom 旗标: "picked" / "rejected" / ""
            color_label: Lightroom 色标: "Red" / "Yellow" / "Green" / "Blue" / "Purple"

        Returns:
            True 如果写入成功，否则 False
        """
        if not os.path.exists(raw_file_path):
            raise FileNotFoundError(f"文件不存在: {raw_file_path}")

        # 格式化评分
        score_str = f'{score:05.2f}'
        rating = max(0, min(5, int(rating)))

        # 构建命令
        cmd = [
            self.exiftool_path,
            f'-IPTC:Country-PrimaryLocationName={score_str}',  # 分数 → 城市
            f'-XMP:Rating={rating}',  # 星级
        ]

        # 添加标题 (作品名)
        if title:
            cmd.append(f'-IPTC:ObjectName={title}')      # IPTC 标题
            cmd.append(f'-XMP:Title={title}')            # XMP 标题
            cmd.append(f'-IPTC:Headline={title}')        # 副标题也写入

        # 添加后期建议
        if caption:
            cmd.append(f'-IPTC:Caption-Abstract={caption}')
            cmd.append(f'-XMP:Description={caption}')

        # 添加关键字
        if keywords:
            for kw in keywords:
                cmd.append(f'-IPTC:Keywords={kw}')
                cmd.append(f'-XMP:Subject={kw}')

        # Lightroom 旗标 (Pick Label): picked=1, rejected=-1
        if pick_flag:
            if pick_flag.lower() == "picked":
                cmd.append('-XMP:PickLabel=1')
            elif pick_flag.lower() == "rejected":
                cmd.append('-XMP:PickLabel=-1')

        # Lightroom 色标 (Color Label)
        if color_label:
            cmd.append(f'-XMP:Label={color_label}')

        cmd.extend([
            '-overwrite_original',
            '-m',
            '-ignoreMinorErrors',
            raw_file_path
        ])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                stderr_lower = result.stderr.lower()
                if 'warning' in stderr_lower or 'minor' in stderr_lower:
                    return True
                print(f"[EXIF] 写入失败: {result.stderr}")
                return False

            return True

        except subprocess.TimeoutExpired:
            print(f"[EXIF] 写入超时: {raw_file_path}")
            return False
        except Exception as e:
            print(f"[EXIF] 写入异常: {e}")
            return False

    def read_align_score(self, raw_file_path: str) -> float:
        """
        从 RAW 文件 EXIF 读取 Align 评分

        Args:
            raw_file_path: RAW 文件路径

        Returns:
            Align 评分（0-10），如果未找到则返回 None

        Raises:
            FileNotFoundError: RAW 文件不存在
        """
        if not os.path.exists(raw_file_path):
            raise FileNotFoundError(f"RAW 文件不存在: {raw_file_path}")

        # 构建 exiftool 命令
        cmd = [
            self.exiftool_path,
            '-IPTC:Country-PrimaryLocationName',
            '-s3',  # 仅输出值，不包含标签名
            raw_file_path
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                return None

            # 解析评分
            value = result.stdout.strip()
            if not value:
                return None

            return float(value)

        except (ValueError, subprocess.TimeoutExpired, Exception):
            return None

    def check_exiftool_version(self) -> str:
        """
        检查 exiftool 版本

        Returns:
            exiftool 版本号字符串
        """
        try:
            result = subprocess.run(
                [self.exiftool_path, '-ver'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                return result.stdout.strip()

        except Exception:
            pass

        return "未知"


# 全局单例
_writer_instance = None


def get_exif_writer() -> ExifWriter:
    """
    获取 EXIF 写入器单例

    Returns:
        ExifWriter 实例
    """
    global _writer_instance

    if _writer_instance is None:
        _writer_instance = ExifWriter()

    return _writer_instance


if __name__ == '__main__':
    # 测试代码
    import sys

    writer = get_exif_writer()
    print(f"exiftool 版本: {writer.check_exiftool_version()}")

    if len(sys.argv) >= 2:
        raw_file = sys.argv[1]

        # 完整测试：写入所有元数据
        if len(sys.argv) >= 3 and sys.argv[2] == '--full-test':
            print("\n=== 完整元数据写入测试 ===")
            
            test_score = 8.75
            test_rating = 4
            test_title = "晨曦中的冰岛瀑布"
            test_caption = "后期建议：可适当增强天空色彩饱和度，压暗前景提升层次感，建议裁切右侧干扰元素。"
            test_keywords = ["瀑布", "冰岛", "岩石", "苔藓", "溪流", "晨雾", "绿色", "长曝光"]
            
            print(f"文件: {raw_file}")
            print(f"评分: {test_score}")
            print(f"星级: {test_rating}")
            print(f"标题: {test_title}")
            print(f"后期建议: {test_caption}")
            print(f"关键字: {test_keywords}")
            print()
            
            success = writer.write_all_metadata(
                raw_file,
                score=test_score,
                rating=test_rating,
                title=test_title,
                caption=test_caption,
                keywords=test_keywords
            )
            
            print(f"写入结果: {'✅ 成功' if success else '❌ 失败'}")
            
            # 验证写入
            print("\n=== 验证写入结果 ===")
            import subprocess
            result = subprocess.run(
                ['exiftool', '-Rating', '-Country-PrimaryLocationName', 
                 '-ObjectName', '-Headline', '-Title',
                 '-Caption-Abstract', '-Keywords', '-Subject', raw_file],
                capture_output=True, text=True
            )
            print(result.stdout)
            
        # 旧测试：仅写入 NIMA 评分
        elif len(sys.argv) >= 3:
            score = float(sys.argv[2])
            print(f"写入 NIMA 评分: {score:.2f}")
            success = writer.write_nima_score(raw_file, score)
            print(f"结果: {'成功' if success else '失败'}")

        # 读取测试
        print(f"\n读取 Align 评分...")
        score = writer.read_align_score(raw_file)
        if score is not None:
            print(f"当前 Align 评分: {score:.2f}")
        else:
            print("未找到评分")
    else:
        print("用法:")
        print("  python exif_writer.py <图片路径> --full-test    # 完整测试")
        print("  python exif_writer.py <图片路径> <评分>          # 仅写入评分")
        print("  python exif_writer.py <图片路径>                 # 仅读取")
