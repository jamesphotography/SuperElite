#!/usr/bin/env python3
"""
One-Align 多维度评分测试
使用已有的 OneAlignScorer 中的正确模型加载方式
"""

import os
import sys
import time
from pathlib import Path
from PIL import Image
import torch

sys.path.insert(0, str(Path(__file__).parent))
from raw_converter import is_raw_file, raw_to_jpeg
from one_align_scorer import OneAlignScorer

def prepare_image(image_path: str) -> tuple[str, bool]:
    """准备图片"""
    if not is_raw_file(image_path):
        return image_path, False

    import tempfile
    temp_path = os.path.join(
        tempfile.gettempdir(),
        f"test_multi_{os.path.basename(image_path)}.jpg"
    )
    extracted = raw_to_jpeg(image_path, temp_path)

    img = Image.open(extracted)
    max_size = 1920
    w, h = img.size
    if w > max_size or h > max_size:
        ratio = min(max_size / w, max_size / h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)
        img.save(extracted, "JPEG", quality=95)

    return extracted, True


def main():
    test_dir = "/Users/jameszhenyu/Desktop/NEWTEST/4"
    
    # 收集图片
    extensions = {".jpg", ".jpeg", ".png", ".arw", ".cr2", ".cr3", ".nef", ".dng", ".raf"}
    image_files = []
    for f in os.listdir(test_dir):
        if os.path.splitext(f)[1].lower() in extensions:
            image_files.append(os.path.join(test_dir, f))
    
    print(f"\n📁 测试目录: {test_dir}")
    print(f"   找到 {len(image_files)} 张图片\n")
    
    # 使用已有的 scorer 加载模型（正确处理了兼容性问题）
    scorer = OneAlignScorer()
    scorer.load_model()
    
    model = scorer.model  # 获取加载好的模型
    
    # 测试所有可能的 task_ 参数
    tasks = [
        # 核心指标
        "quality",           # 质量
        "aesthetics",        # 美学
        
        # 技术指标
        "sharpness",         # 锐度
        "noise level",       # 噪点
        "exposure",          # 曝光
        "dynamic range",     # 动态范围
        "focus",             # 对焦
        "clarity",           # 清晰度
        
        # 构图指标
        "composition",       # 构图
        "balance",           # 平衡
        "framing",           # 取景
        "visual flow",       # 视觉流动
        
        # 光线指标
        "lighting",          # 光线
        "contrast",          # 对比度
        "color",             # 色彩
        "color harmony",     # 色彩和谐
        "saturation",        # 饱和度
        "white balance",     # 白平衡
        
        # 情感指标
        "mood",              # 情绪
        "atmosphere",        # 氛围
        "emotional impact",  # 情感冲击
        
        # 综合指标
        "overall appeal",    # 整体吸引力
        "storytelling",      # 叙事性
        "originality",       # 原创性
        "professionalism",   # 专业度
    ]
    
    # 只处理第一张图来测试（用 JPG，避免 RAW 处理时间干扰）
    # 找 JPG 文件
    jpg_files = [f for f in image_files if f.lower().endswith('.jpg')]
    if jpg_files:
        test_image = jpg_files[0]
    else:
        test_image = image_files[0]
    
    print(f"\n📷 测试图片: {os.path.basename(test_image)}")
    
    processed_path, is_temp = prepare_image(test_image)
    print(f"   {'[RAW→JPEG 提取]' if is_temp else '[直接读取]'}")
    
    image = Image.open(processed_path).convert("RGB")
    
    print(f"\n{'='*70}")
    print("🔬 测试所有 task_ 参数")
    print(f"{'='*70}")
    
    results = {}
    with torch.inference_mode():
        for task in tasks:
            start = time.time()
            try:
                score = model.score([image], task_=task, input_="image")
                score_value = float(score[0]) if isinstance(score, (list, torch.Tensor)) else float(score)
                elapsed = time.time() - start
                results[task] = (score_value, elapsed)
                print(f"  {task:25s}: {score_value:.2f}/5.0  ({score_value*20:.0f}/100)  [{elapsed:.2f}s]")
            except Exception as e:
                elapsed = time.time() - start
                results[task] = (None, elapsed)
                print(f"  {task:25s}: ❌ 错误 - {e}  [{elapsed:.2f}s]")
    
    # 清理
    if is_temp and os.path.exists(processed_path):
        os.remove(processed_path)
    
    # 统计
    print(f"\n{'='*70}")
    print("📊 统计")
    print(f"{'='*70}")
    
    valid_results = [(t, s, e) for t, (s, e) in results.items() if s is not None]
    if valid_results:
        avg_time = sum(e for _, _, e in valid_results) / len(valid_results)
        print(f"  成功率: {len(valid_results)}/{len(tasks)}")
        print(f"  平均耗时: {avg_time:.2f}s / 项")
        print(f"  总耗时: {sum(e for _, _, e in valid_results):.1f}s")
        
        # 分数分布
        scores = sorted([(t, s) for t, s, _ in valid_results], key=lambda x: -x[1])
        print(f"\n  📈 分数排序 (高→低):")
        for t, s in scores:
            bar = "█" * int(s * 4)
            print(f"    {t:25s}: {s:.2f}  {bar}")


if __name__ == "__main__":
    main()
