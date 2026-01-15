#!/usr/bin/env python3
"""
One-Align 完整分析能力测试
测试模型除了打分之外还能提供什么信息
"""

import os
import sys
import time
from pathlib import Path
from PIL import Image
import torch

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from raw_converter import is_raw_file, raw_to_jpeg

def prepare_image(image_path: str) -> tuple[str, bool]:
    """准备图片 (RAW 提取预览)"""
    if not is_raw_file(image_path):
        return image_path, False

    import tempfile
    temp_path = os.path.join(
        tempfile.gettempdir(),
        f"test_analysis_{os.path.basename(image_path)}.jpg"
    )
    extracted = raw_to_jpeg(image_path, temp_path)

    # 调整到 1920px
    img = Image.open(extracted)
    max_size = 1920
    w, h = img.size
    if w > max_size or h > max_size:
        ratio = min(max_size / w, max_size / h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)
        img.save(extracted, "JPEG", quality=95)

    return extracted, True


def load_one_align_model():
    """加载 One-Align 模型"""
    print("=" * 70)
    print("🚀 加载 One-Align 模型...")
    print("=" * 70)
    
    from transformers import AutoModelForCausalLM
    
    # 加载模型
    model = AutoModelForCausalLM.from_pretrained(
        "q-future/one-align",
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map="mps"
    )
    
    print("✅ 模型加载完成\n")
    return model


def run_analysis(model, image_path: str, prompts: list[tuple[str, str]]) -> dict:
    """
    运行多个分析提示
    
    Args:
        model: One-Align 模型
        image_path: 图片路径
        prompts: [(name, prompt), ...] 提示列表
    
    Returns:
        {name: (result, time), ...}
    """
    results = {}
    
    for name, prompt in prompts:
        print(f"  📝 {name}...", end=" ", flush=True)
        start = time.time()
        
        try:
            result = model.chat(
                image=image_path,
                msg=prompt,
                input_ids=None,
                max_new_tokens=512,
                do_sample=False,
            )
            elapsed = time.time() - start
            results[name] = (result, elapsed)
            print(f"({elapsed:.1f}s)")
        except Exception as e:
            elapsed = time.time() - start
            results[name] = (f"ERROR: {e}", elapsed)
            print(f"❌ ({elapsed:.1f}s)")
    
    return results


def main():
    # 测试目录
    test_dir = "/Users/jameszhenyu/Desktop/NEWTEST/4"
    
    # 收集图片
    extensions = {".jpg", ".jpeg", ".png", ".arw", ".cr2", ".cr3", ".nef", ".dng", ".raf"}
    image_files = []
    for f in os.listdir(test_dir):
        if os.path.splitext(f)[1].lower() in extensions:
            image_files.append(os.path.join(test_dir, f))
    
    print(f"\n📁 测试目录: {test_dir}")
    print(f"   找到 {len(image_files)} 张图片\n")
    
    # 加载模型
    model = load_one_align_model()
    
    # 定义所有测试提示 - 榨干模型能力！
    analysis_prompts = [
        # === 基础评分 ===
        ("Quality Score", "Rate the quality of this image. Output a score between 0-100."),
        ("Aesthetic Score", "Rate the aesthetic of this image. Output a score between 0-100."),
        
        # === 技术分析 ===
        ("Technical Analysis", 
         "Analyze the technical aspects of this photograph: sharpness, noise level, exposure, dynamic range, color accuracy, and any optical issues like distortion or chromatic aberration."),
        
        ("Focus Quality", 
         "Evaluate the focus quality of this image. Is the main subject sharp? Is there any motion blur or camera shake? Describe the depth of field."),
        
        ("Exposure Analysis", 
         "Analyze the exposure of this photograph. Are there blown highlights or crushed shadows? Is the histogram well balanced? Suggest any exposure corrections."),
        
        # === 构图分析 ===
        ("Composition Analysis", 
         "Analyze the composition of this photograph. Consider: rule of thirds, leading lines, symmetry, framing, visual balance, foreground/background relationship, and use of negative space."),
        
        ("Visual Flow", 
         "Describe how the eye moves through this image. What draws attention first? Is there a clear visual hierarchy? Are there any distracting elements?"),
        
        # === 光线分析 ===
        ("Lighting Analysis", 
         "Analyze the lighting in this photograph: type of light (natural/artificial), direction, quality (hard/soft), color temperature, and how it shapes the subject."),
        
        ("Golden Hour Assessment", 
         "Is this image shot during golden hour, blue hour, or other special lighting conditions? How does the light quality affect the mood?"),
        
        # === 色彩分析 ===
        ("Color Analysis", 
         "Analyze the color palette of this image: dominant colors, color harmony, saturation levels, and emotional impact of the colors."),
        
        ("Color Grading Suggestions", 
         "Suggest color grading improvements for this image. What adjustments to hue, saturation, or tone would enhance the visual impact?"),
        
        # === 情感与风格 ===
        ("Mood & Atmosphere", 
         "Describe the mood and atmosphere of this photograph. What emotions does it evoke? Is it peaceful, dramatic, melancholic, joyful?"),
        
        ("Photography Style", 
         "Identify the photography style and genre of this image. Is it landscape, portrait, street, documentary, fine art, commercial? What stylistic influences do you see?"),
        
        # === 主体与场景 ===
        ("Subject Description", 
         "Describe in detail what is depicted in this photograph. What is the main subject? What is in the foreground, midground, and background?"),
        
        ("Scene Classification", 
         "Classify this scene: sunset, sunrise, night, aurora, cityscape, seascape, mountain, forest, desert, architecture, wildlife, portrait, street, macro, abstract, etc."),
        
        # === 综合评价 ===
        ("Strengths", 
         "List the main strengths of this photograph. What makes it stand out? What has the photographer done well?"),
        
        ("Weaknesses", 
         "List any weaknesses or areas for improvement in this photograph. Be constructive and specific."),
        
        ("Improvement Suggestions", 
         "Provide specific suggestions to improve this photograph, both in-camera (composition, timing, settings) and in post-processing."),
        
        # === 用途建议 ===
        ("Usage Recommendations", 
         "What would this image be suitable for? Portfolio, stock photography, fine art print, social media, editorial, commercial use?"),
        
        # === 中文测试 ===
        ("中文综合评价", 
         "请用中文详细分析这张照片的优缺点，包括构图、光线、色彩、技术质量等方面，并给出具体的改进建议。"),
    ]
    
    # 处理每张图片
    all_results = {}
    
    for img_path in image_files:
        filename = os.path.basename(img_path)
        print("\n" + "=" * 70)
        print(f"📷 处理: {filename}")
        print("=" * 70)
        
        # 准备图片
        processed_path, is_temp = prepare_image(img_path)
        print(f"   {'[RAW→JPEG 提取]' if is_temp else '[直接读取]'}")
        
        # 运行所有分析
        start_total = time.time()
        results = run_analysis(model, processed_path, analysis_prompts)
        total_time = time.time() - start_total
        
        all_results[filename] = {
            "results": results,
            "total_time": total_time,
        }
        
        # 清理临时文件
        if is_temp and os.path.exists(processed_path):
            os.remove(processed_path)
        
        print(f"\n⏱️  总耗时: {total_time:.1f}s ({total_time/len(analysis_prompts):.1f}s/项)")
    
    # 输出详细报告
    print("\n\n")
    print("=" * 70)
    print("📊 完整分析报告")
    print("=" * 70)
    
    for filename, data in all_results.items():
        print(f"\n\n{'#' * 70}")
        print(f"# {filename}")
        print(f"# 总耗时: {data['total_time']:.1f}s")
        print(f"{'#' * 70}")
        
        for name, (result, elapsed) in data["results"].items():
            print(f"\n--- {name} ({elapsed:.1f}s) ---")
            print(result)
    
    # 时间统计
    print("\n\n")
    print("=" * 70)
    print("⏱️  时间统计汇总")
    print("=" * 70)
    
    for filename, data in all_results.items():
        print(f"\n{filename}:")
        for name, (_, elapsed) in data["results"].items():
            print(f"  {name}: {elapsed:.1f}s")
        print(f"  ---")
        print(f"  总计: {data['total_time']:.1f}s")


if __name__ == "__main__":
    main()
