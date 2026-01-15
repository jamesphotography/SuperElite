#!/usr/bin/env python3
"""
SuperElite - AI 风光摄影智能选片工具
基于 One-Align 的双维度评分 (质量 + 美学)
"""

import sys
import os
import platform
import argparse
import json
import shutil
from pathlib import Path
from typing import List, Dict
from tqdm import tqdm

from one_align_scorer import get_one_align_scorer
from exif_writer import get_exif_writer
from raw_converter import is_raw_file, raw_to_jpeg


def check_apple_silicon() -> bool:
    """检测是否为 Apple Silicon Mac"""
    if platform.system() != "Darwin":
        return False
    return platform.machine() == "arm64"


def validate_hardware():
    """验证硬件兼容性"""
    if not check_apple_silicon():
        print("=" * 60)
        print("❌ SuperElite 仅支持 Apple Silicon Mac")
        print("=" * 60)
        print(f"\n当前: {platform.system()} / {platform.machine()}")
        sys.exit(1)
    print(f"✅ 硬件检测通过: Apple Silicon ({platform.machine()})")


def scan_directory(directory: str) -> List[str]:
    """扫描目录下的所有图片文件"""
    if not os.path.exists(directory):
        raise FileNotFoundError(f"目录不存在: {directory}")

    extensions = {
        ".jpg", ".jpeg", ".png",
        ".arw", ".cr2", ".cr3", ".nef", ".dng",
        ".raf", ".orf", ".rw2", ".pef", ".srw",
    }

    image_paths = []
    for root, _, files in os.walk(directory):
        for file in files:
            if os.path.splitext(file)[1].lower() in extensions:
                image_paths.append(os.path.join(root, file))

    image_paths.sort()
    return image_paths


def prepare_image(image_path: str) -> tuple[str, bool]:
    """准备图片用于评分 (RAW 提取预览)"""
    if not is_raw_file(image_path):
        return image_path, False

    import tempfile
    temp_path = os.path.join(
        tempfile.gettempdir(),
        f"superelite_{os.path.basename(image_path)}.jpg"
    )
    extracted = raw_to_jpeg(image_path, temp_path)

    # 调整到 1920px
    from PIL import Image
    img = Image.open(extracted)
    max_size = 1920
    w, h = img.size
    if w > max_size or h > max_size:
        ratio = min(max_size / w, max_size / h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)
        img.save(extracted, "JPEG", quality=95)

    return extracted, True


def organize_by_rating(results: List[Dict], output_dir: str, copy_files: bool = True):
    """按星级分目录组织文件"""
    rating_dirs = {
        4: "4-star",
        3: "3-star",
        2: "2-star",
        1: "1-star",
        0: "0-star",
    }

    # 创建目录
    for dir_name in rating_dirs.values():
        os.makedirs(os.path.join(output_dir, dir_name), exist_ok=True)

    # 复制/移动文件
    for result in results:
        if "error" in result:
            continue

        rating = result["rating"]
        src = result["file"]
        dst_dir = os.path.join(output_dir, rating_dirs[rating])
        dst = os.path.join(dst_dir, os.path.basename(src))

        if copy_files:
            shutil.copy2(src, dst)
        else:
            shutil.move(src, dst)

    print(f"✅ 文件已按星级分类到: {output_dir}")


def write_xmp_metadata(exif_writer, results: List[Dict]):
    """写入 XMP 元数据"""
    for result in results:
        if "error" in result:
            continue

        try:
            exif_writer.write_all_metadata(
                result["file"],
                score=result["total"],
                rating=result["rating"],
                title=f"Quality: {result['quality']:.0f} | Aesthetic: {result['aesthetic']:.0f}",
                caption=f"SuperElite AI 评分: {result['total']:.1f}/100",
                keywords=["SuperElite", f"{result['rating']}-star"],
                # Lightroom 特有字段
                pick_flag=result.get("pick_flag", ""),
                color_label=result.get("color_label", ""),
            )
        except Exception as e:
            print(f"⚠️  XMP 写入失败 {result['file']}: {e}")


def export_csv(results: List[Dict], output_path: str):
    """导出 CSV 报告"""
    import csv

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "file", "quality", "aesthetic", "total", "rating", "pick_flag", "color_label"
        ])
        writer.writeheader()
        for result in results:
            if "error" not in result:
                writer.writerow({
                    "file": result["file"],
                    "quality": f"{result['quality']:.2f}",
                    "aesthetic": f"{result['aesthetic']:.2f}",
                    "total": f"{result['total']:.2f}",
                    "rating": result["rating"],
                    "pick_flag": result.get("pick_flag", ""),
                    "color_label": result.get("color_label", ""),
                })

    print(f"✅ CSV 报告已导出: {output_path}")


def process_batch(
    image_paths: List[str],
    scorer,
    exif_writer,
    write_xmp: bool = True,
) -> List[Dict]:
    """批量处理图片"""
    results = []
    total = len(image_paths)

    print(f"\n🚀 开始处理 {total} 张图片...\n")

    for idx, original_path in enumerate(tqdm(image_paths, desc="评分进度")):
        processed_path = None
        is_temp = False

        try:
            # 准备图片
            processed_path, is_temp = prepare_image(original_path)

            # 评分
            result = scorer.score_image(processed_path)
            result["file"] = original_path

            results.append(result)

        except Exception as e:
            results.append({"file": original_path, "error": str(e)})
            tqdm.write(f"❌ {os.path.basename(original_path)}: {e}")

        finally:
            # 清理临时文件
            if is_temp and processed_path and os.path.exists(processed_path):
                os.remove(processed_path)

    # 写入 XMP
    if write_xmp:
        print("\n📝 写入 XMP 元数据...")
        write_xmp_metadata(exif_writer, results)

    # 统计
    success = len([r for r in results if "error" not in r])
    print(f"\n✅ 完成! 成功: {success}/{total}")

    return results


def main():
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        description="SuperElite - AI 风光摄影智能选片工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--dir", type=str, help="输入目录 (RAW/JPEG)")
    parser.add_argument("--output", type=str, help="输出目录 (分星级)")
    parser.add_argument("--quality-weight", type=float, default=0.4, help="质量权重 (默认 0.4)")
    parser.add_argument("--aesthetic-weight", type=float, default=0.6, help="美学权重 (默认 0.6)")
    parser.add_argument("--organize", action="store_true", help="按星级分目录")
    parser.add_argument("--write-xmp", action="store_true", help="写入 XMP 元数据")
    parser.add_argument("--csv", type=str, help="导出 CSV 报告路径")
    parser.add_argument("--check-hardware", action="store_true", help="仅检测硬件")

    args = parser.parse_args()

    # 硬件检测
    if args.check_hardware:
        validate_hardware()
        sys.exit(0)

    validate_hardware()

    # 交互式输入目录 (如果未提供 --dir)
    input_dir = args.dir
    if not input_dir:
        print("\n" + "=" * 60)
        print("🎯 SuperElite - AI 风光摄影智能选片工具")
        print("   基于 One-Align 双维度评分 (质量 + 美学)")
        print("=" * 60)
        print("\n请输入图片目录路径 (支持 RAW + JPEG):")
        print("(提示: 可拖拽文件夹到终端自动填充)\n")

        input_dir = input("📁 目录路径: ").strip()

        if not input_dir:
            print("\n❌ 未提供目录路径")
            sys.exit(1)

        # 展开 ~ 符号
        input_dir = os.path.expanduser(input_dir)

    # 扫描文件
    print("\n📁 扫描目录...")
    image_paths = scan_directory(input_dir)
    print(f"   找到 {len(image_paths)} 张图片")

    if not image_paths:
        print("❌ 未找到图片")
        sys.exit(1)

    # 初始化评分器
    scorer = get_one_align_scorer(
        quality_weight=args.quality_weight,
        aesthetic_weight=args.aesthetic_weight,
    )
    scorer.warmup()

    exif_writer = get_exif_writer()

    # 批量处理
    results = process_batch(image_paths, scorer, exif_writer, write_xmp=args.write_xmp)

    # 按星级分目录
    if args.organize and args.output:
        organize_by_rating(results, args.output)

    # 导出 CSV
    if args.csv:
        export_csv(results, args.csv)

    # 输出 JSON 摘要
    summary = {
        "total": len(results),
        "success": len([r for r in results if "error" not in r]),
        "by_rating": {
            "4-star": len([r for r in results if r.get("rating") == 4]),
            "3-star": len([r for r in results if r.get("rating") == 3]),
            "2-star": len([r for r in results if r.get("rating") == 2]),
            "1-star": len([r for r in results if r.get("rating") == 1]),
            "0-star": len([r for r in results if r.get("rating") == 0]),
        },
    }

    print(f"\n📊 统计摘要:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)
