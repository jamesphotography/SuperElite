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
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple
from tqdm import tqdm

from one_align_scorer import get_one_align_scorer, set_thresholds
from exif_writer import get_exif_writer
from raw_converter import is_raw_file, raw_to_jpeg
from logger import get_logger, setup_logging
from preset_manager import get_preset_manager, Preset

# 版本信息
VERSION = "1.0"


def get_git_hash() -> str:
    """获取最后一次 git commit 的短 hash"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def print_version():
    """打印版本信息"""
    git_hash = get_git_hash()
    print(f"SuperElite v{VERSION} (commit: {git_hash})")


def parse_thresholds(thresholds_str: str) -> Tuple[float, float, float, float]:
    """
    解析阈值字符串
    
    Args:
        thresholds_str: 格式 "78,72,66,58" (4星,3星,2星,1星)
    
    Returns:
        (t4, t3, t2, t1) 阈值元组
    """
    try:
        parts = [float(x.strip()) for x in thresholds_str.split(",")]
        if len(parts) != 4:
            raise ValueError("需要 4 个阈值")
        if not all(parts[i] > parts[i+1] for i in range(3)):
            raise ValueError("阈值必须递减 (4星 > 3星 > 2星 > 1星)")
        return tuple(parts)
    except Exception as e:
        print(f"❌ 阈值格式错误: {e}")
        print("   正确格式: --thresholds \"78,72,66,58\"")
        sys.exit(1)


# 默认阈值
DEFAULT_THRESHOLDS = (78.0, 72.0, 66.0, 58.0)


def calculate_percentile_thresholds(scores: List[float]) -> Tuple[float, float, float, float]:
    """
    根据 20% 均分计算百分位阈值
    
    Args:
        scores: 所有图片的综合分列表
    
    Returns:
        (t4, t3, t2, t1) 阈值元组
        - P80 -> 4星阈值
        - P60 -> 3星阈值  
        - P40 -> 2星阈值
        - P20 -> 1星阈值
    """
    import numpy as np
    
    sorted_scores = np.array(sorted(scores))
    
    # 计算百分位点
    t4 = float(np.percentile(sorted_scores, 80))  # P80: 前 20% 为 4星
    t3 = float(np.percentile(sorted_scores, 60))  # P60: 20-40% 为 3星
    t2 = float(np.percentile(sorted_scores, 40))  # P40: 40-60% 为 2星
    t1 = float(np.percentile(sorted_scores, 20))  # P20: 60-80% 为 1星, <P20 为 0星
    
    return (round(t4, 1), round(t3, 1), round(t2, 1), round(t1, 1))


def prompt_threshold_confirmation(
    suggested: Tuple[float, float, float, float],
    counts: Dict[int, int],
    stats: Dict[str, float],
) -> Tuple[float, float, float, float]:
    """
    提示用户确认阈值
    
    Args:
        suggested: 建议阈值 (t4, t3, t2, t1)
        counts: 各星级数量
        stats: 分数统计 {max, min, avg}
    
    Returns:
        最终确认的阈值
    """
    t4, t3, t2, t1 = suggested
    
    print("\n" + "=" * 60)
    print("📊 分数分布分析:")
    print(f"   最高分: {stats['max']:.1f}  |  最低分: {stats['min']:.1f}  |  平均: {stats['avg']:.1f}")
    print()
    print("📐 根据 20% 均分，建议阈值:")
    print(f"   4★ ≥ {t4} ({counts[4]}张)  |  3★ ≥ {t3} ({counts[3]}张)")
    print(f"   2★ ≥ {t2} ({counts[2]}张)  |  1★ ≥ {t1} ({counts[1]}张)")
    print(f"   0★  < {t1} ({counts[0]}张)")
    print("=" * 60)
    
    while True:
        choice = input("\n是否使用此阈值？ [Y]使用建议 / [N]使用默认 / [C]自定义: ").strip().upper()
        
        if choice == "Y" or choice == "":
            print(f"✅ 使用建议阈值: {t4}, {t3}, {t2}, {t1}")
            return suggested
        
        elif choice == "N":
            print(f"✅ 使用默认阈值: {DEFAULT_THRESHOLDS[0]}, {DEFAULT_THRESHOLDS[1]}, {DEFAULT_THRESHOLDS[2]}, {DEFAULT_THRESHOLDS[3]}")
            return DEFAULT_THRESHOLDS
        
        elif choice == "C":
            return prompt_custom_thresholds(suggested)
        
        else:
            print("❌ 无效输入，请输入 Y/N/C")


def prompt_custom_thresholds(
    suggested: Tuple[float, float, float, float]
) -> Tuple[float, float, float, float]:
    """
    让用户逐个调整阈值
    
    Args:
        suggested: 建议阈值
    
    Returns:
        用户调整后的阈值
    """
    t4, t3, t2, t1 = suggested
    result = []
    
    labels = [("4★", t4), ("3★", t3), ("2★", t2), ("1★", t1)]
    
    print("\n🛠️  自定义阈值 (直接回车保持建议值):")
    
    for label, default in labels:
        while True:
            user_input = input(f"   {label} 阈值 [默认 {default}]: ").strip()
            
            if user_input == "":
                result.append(default)
                break
            
            try:
                value = float(user_input)
                # 检查递减顺序
                if result and value >= result[-1]:
                    print(f"   ❌ 阈值必须递减 (当前值必须小于 {result[-1]})")
                    continue
                result.append(value)
                break
            except ValueError:
                print("   ❌ 请输入有效数字")
    
    final = tuple(result)
    print(f"\n✅ 使用自定义阈值: {final[0]}, {final[1]}, {final[2]}, {final[3]}")
    return final


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


def remap_ratings(
    results: List[Dict],
    thresholds: Tuple[float, float, float, float],
) -> List[Dict]:
    """
    根据新阈值重新映射星级
    
    Args:
        results: 评分结果列表
        thresholds: (t4, t3, t2, t1) 阈值
    
    Returns:
        更新后的结果列表
    """
    t4, t3, t2, t1 = thresholds
    
    for result in results:
        if "error" in result:
            continue
        
        total = result["total"]
        
        if total >= t4:
            result["rating"] = 4
            result["pick_flag"] = ""
            result["color_label"] = ""
        elif total >= t3:
            result["rating"] = 3
            result["pick_flag"] = ""
            result["color_label"] = ""
        elif total >= t2:
            result["rating"] = 2
            result["pick_flag"] = ""
            result["color_label"] = ""
        elif total >= t1:
            result["rating"] = 1
            result["pick_flag"] = ""
            result["color_label"] = ""
        else:
            result["rating"] = 0
            result["pick_flag"] = "rejected"
            result["color_label"] = ""
    
    return results


def count_by_rating(results: List[Dict]) -> Dict[int, int]:
    """统计各星级数量"""
    counts = {4: 0, 3: 0, 2: 0, 1: 0, 0: 0}
    for r in results:
        if "error" not in r:
            rating = r.get("rating", 0)
            counts[rating] = counts.get(rating, 0) + 1
    return counts


def main():
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        description="SuperElite - AI 风光摄影智能选片工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--version", "-v", action="store_true", help="显示版本号")
    parser.add_argument("--dir", type=str, help="输入目录 (RAW/JPEG)")
    parser.add_argument("--output", type=str, help="输出目录 (分星级)")
    parser.add_argument("--quality-weight", type=float, default=None, help="质量权重 (默认 0.4)")
    parser.add_argument("--aesthetic-weight", type=float, default=None, help="美学权重 (默认 0.6)")
    parser.add_argument(
        "--thresholds", type=str, 
        help='自定义星级阈值，格式: "78,72,66,58" (4星,3星,2星,1星)'
    )
    parser.add_argument(
        "--auto-calibrate", action="store_true",
        help="自动校准模式: 根据照片分布计算最佳阈值 (五等分)"
    )
    parser.add_argument("--organize", action="store_true", help="按星级分目录")
    parser.add_argument("--write-xmp", action="store_true", help="写入 XMP 元数据")
    parser.add_argument("--csv", type=str, help="导出 CSV 报告路径")
    parser.add_argument("--check-hardware", action="store_true", help="仅检测硬件")
    
    # 日志功能
    parser.add_argument(
        "--log", nargs="?", const="", default=None,
        help="保存日志到文件 (不指定路径则自动生成)"
    )
    parser.add_argument("--verbose", action="store_true", help="详细输出模式")
    parser.add_argument("--quiet", "-q", action="store_true", help="安静模式 (只输出错误和最终结果)")
    
    # 预设功能
    parser.add_argument("--preset", type=str, help="使用预设 (default/strict/relaxed/user)")
    parser.add_argument("--save-preset", type=str, metavar="NAME", help="保存当前配置为预设")
    parser.add_argument("--list-presets", action="store_true", help="列出所有可用预设")

    args = parser.parse_args()

    # 版本检测
    if args.version:
        print_version()
        sys.exit(0)

    # 列出预设
    if args.list_presets:
        preset_manager = get_preset_manager()
        preset_manager.print_presets()
        sys.exit(0)

    # 硬件检测
    if args.check_hardware:
        validate_hardware()
        sys.exit(0)

    # 设置日志
    log_path = None
    if args.log is not None:
        log_path = setup_logging(args.log, args.verbose, args.quiet)
        logger = get_logger()
        logger.info(f"SuperElite v{VERSION} ({get_git_hash()}) 启动")
        if log_path and not args.quiet:
            print(f"📝 日志文件: {log_path}")
    elif args.quiet:
        setup_logging(quiet=True)
    elif args.verbose:
        setup_logging(verbose=True)

    validate_hardware()

    # 预设管理器
    preset_manager = get_preset_manager()

    # 加载预设配置
    quality_weight = 0.4
    aesthetic_weight = 0.6
    thresholds = None
    write_xmp = args.write_xmp
    organize = args.organize

    if args.preset:
        preset = preset_manager.get_preset(args.preset)
        if preset is None:
            print(f"❌ 预设不存在: {args.preset}")
            print("   使用 --list-presets 查看可用预设")
            sys.exit(1)
        
        print(f"✅ 使用预设: {preset.name} ({preset.description})")
        quality_weight = preset.quality_weight
        aesthetic_weight = preset.aesthetic_weight
        thresholds = preset.thresholds
        write_xmp = write_xmp or preset.write_xmp
        organize = organize or preset.organize

    # 命令行参数覆盖预设
    if args.quality_weight is not None:
        quality_weight = args.quality_weight
    if args.aesthetic_weight is not None:
        aesthetic_weight = args.aesthetic_weight

    # 检查参数冲突
    if args.thresholds and args.auto_calibrate:
        print("❌ --thresholds 和 --auto-calibrate 不能同时使用")
        sys.exit(1)

    # 设置自定义阈值 (仅当不使用 auto-calibrate 时)
    if args.thresholds:
        thresholds = parse_thresholds(args.thresholds)
    
    if thresholds and not args.auto_calibrate:
        set_thresholds(*thresholds)
        print(f"✅ 使用阈值: 4星≥{thresholds[0]}, 3星≥{thresholds[1]}, 2星≥{thresholds[2]}, 1星≥{thresholds[3]}")

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
        quality_weight=quality_weight,
        aesthetic_weight=aesthetic_weight,
    )
    scorer.warmup()

    exif_writer = get_exif_writer()

    # Auto-calibrate 模式: 先评分，不写入，等用户确认阈值后再写入
    if args.auto_calibrate:
        # 第一步: 评分所有图片 (不写入 XMP)
        results = process_batch(image_paths, scorer, exif_writer, write_xmp=False)
        
        # 提取所有分数
        scores = [r["total"] for r in results if "error" not in r]
        
        if not scores:
            print("❌ 没有有效的评分结果")
            sys.exit(1)
        
        # 第二步: 计算建议阈值
        suggested_thresholds = calculate_percentile_thresholds(scores)
        
        # 用建议阈值计算各星级数量 (用于显示)
        temp_results = remap_ratings(results.copy(), suggested_thresholds)
        counts = count_by_rating(temp_results)
        
        # 统计信息
        stats = {
            "max": max(scores),
            "min": min(scores),
            "avg": sum(scores) / len(scores),
        }
        
        # 第三步: 用户确认
        final_thresholds = prompt_threshold_confirmation(suggested_thresholds, counts, stats)
        
        # 第四步: 应用最终阈值，重新映射星级
        results = remap_ratings(results, final_thresholds)
        
        # 第五步: 写入 XMP (如果指定了 --write-xmp)
        if write_xmp:
            print("\n📝 写入 XMP 元数据...")
            write_xmp_metadata(exif_writer, results)
        
        # 统计
        success = len([r for r in results if "error" not in r])
        print(f"\n✅ 完成! 成功: {success}/{len(results)}")
    
    else:
        # 标准模式: 使用默认/自定义阈值，直接处理
        results = process_batch(image_paths, scorer, exif_writer, write_xmp=write_xmp)

    # 按星级分目录
    if organize and args.output:
        organize_by_rating(results, args.output)

    # 导出 CSV
    if args.csv:
        export_csv(results, args.csv)

    # 输出 JSON 摘要
    summary = {
        "total": len(results),
        "success": len([r for r in results if "error" not in r]),
        "by_rating": count_by_rating(results),
    }

    print(f"\n📊 统计摘要:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # 保存预设
    if args.save_preset:
        final_thresholds = thresholds or DEFAULT_THRESHOLDS
        preset = Preset(
            name=args.save_preset,
            description=f"用户自定义预设 ({args.save_preset})",
            thresholds=final_thresholds,
            quality_weight=quality_weight,
            aesthetic_weight=aesthetic_weight,
            write_xmp=write_xmp,
            organize=organize,
        )
        if preset_manager.save_preset(preset):
            print(f"\n✅ 预设已保存: {args.save_preset}")
            print(f"   使用: --preset {args.save_preset}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 错误: {e}", file=sys.stderr)
        sys.exit(1)
