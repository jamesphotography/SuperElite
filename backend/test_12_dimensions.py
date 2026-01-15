#!/usr/bin/env python3
"""
风光摄影 12 维度评分测试
2 核心 + 10 风光专属维度
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
        f"test_12d_{os.path.basename(image_path)}.jpg"
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


# 风光摄影 12 维度
LANDSCAPE_DIMENSIONS = [
    # 核心 (2)
    ("quality", "质量"),
    ("aesthetics", "美学"),
    # 技术关键 (4)
    ("sharpness", "锐度"),
    ("exposure", "曝光"),
    ("dynamic range", "动态范围"),
    ("clarity", "清晰度"),
    # 构图关键 (2)
    ("composition", "构图"),
    ("visual flow", "视觉流动"),
    # 光线色彩 (3)
    ("lighting", "光线"),
    ("color harmony", "色彩和谐"),
    ("contrast", "对比度"),
    # 情感 (1)
    ("atmosphere", "氛围"),
]


def main():
    test_dir = "/Users/jameszhenyu/Desktop/NEWTEST/4"
    
    # 收集图片
    extensions = {".jpg", ".jpeg", ".png", ".arw", ".cr2", ".cr3", ".nef", ".dng", ".raf"}
    image_files = []
    for f in os.listdir(test_dir):
        if os.path.splitext(f)[1].lower() in extensions:
            image_files.append(os.path.join(test_dir, f))
    
    print(f"\n📁 测试目录: {test_dir}")
    print(f"   找到 {len(image_files)} 张图片")
    print(f"   测试维度: {len(LANDSCAPE_DIMENSIONS)} 个\n")
    
    # 加载模型
    scorer = OneAlignScorer()
    scorer.load_model()
    model = scorer.model
    
    print(f"\n{'='*80}")
    print("🏔️  风光摄影 12 维度评分测试")
    print(f"{'='*80}\n")
    
    all_results = {}
    
    for img_path in image_files:
        filename = os.path.basename(img_path)
        print(f"\n{'─'*80}")
        print(f"📷 {filename}")
        print(f"{'─'*80}")
        
        processed_path, is_temp = prepare_image(img_path)
        if is_temp:
            print("   [RAW→JPEG 提取]")
        
        image = Image.open(processed_path).convert("RGB")
        
        scores = {}
        start_total = time.time()
        
        with torch.inference_mode():
            for task_en, task_cn in LANDSCAPE_DIMENSIONS:
                start = time.time()
                score = model.score([image], task_=task_en, input_="image")
                score_value = float(score[0]) if isinstance(score, (list, torch.Tensor)) else float(score)
                elapsed = time.time() - start
                scores[task_en] = (score_value, task_cn, elapsed)
        
        total_time = time.time() - start_total
        
        # 清理
        if is_temp and os.path.exists(processed_path):
            os.remove(processed_path)
        
        # 输出结果
        print(f"\n   {'维度':<15} {'中文':<10} {'分数':>8} {'百分制':>8}")
        print(f"   {'─'*50}")
        
        for task_en, (score, task_cn, _) in scores.items():
            bar = "█" * int(score * 4)
            print(f"   {task_en:<15} {task_cn:<10} {score:>6.2f}/5  {score*20:>5.0f}/100  {bar}")
        
        # 计算综合分
        core_score = (scores["quality"][0] * 0.4 + scores["aesthetics"][0] * 0.6) * 20
        avg_all = sum(s[0] for s in scores.values()) / len(scores) * 20
        
        print(f"\n   ⏱️  总耗时: {total_time:.1f}s ({total_time/len(LANDSCAPE_DIMENSIONS):.2f}s/维度)")
        print(f"   📊 核心加权分 (Q40%+A60%): {core_score:.1f}/100")
        print(f"   📊 12维度平均分: {avg_all:.1f}/100")
        
        all_results[filename] = {
            "scores": scores,
            "total_time": total_time,
            "core_score": core_score,
            "avg_all": avg_all,
        }
    
    # 汇总
    print(f"\n\n{'='*80}")
    print("📊 汇总")
    print(f"{'='*80}\n")
    
    print(f"{'文件名':<45} {'核心分':>8} {'12维均分':>8} {'耗时':>8}")
    print(f"{'─'*75}")
    
    for filename, data in all_results.items():
        print(f"{filename:<45} {data['core_score']:>6.1f}  {data['avg_all']:>8.1f}  {data['total_time']:>6.1f}s")
    
    # 总时间
    total_all = sum(d["total_time"] for d in all_results.values())
    avg_per_image = total_all / len(all_results)
    print(f"\n总耗时: {total_all:.1f}s | 平均: {avg_per_image:.1f}s/张 | {avg_per_image/len(LANDSCAPE_DIMENSIONS):.2f}s/维度")


if __name__ == "__main__":
    main()
