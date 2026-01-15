#!/usr/bin/env python3
"""
测试 q-future/co-instruct 的对话能力
可以：1) 分析单张图片 2) 对比两张图片
"""

import os
import sys
import time
from pathlib import Path
from PIL import Image
import torch

sys.path.insert(0, str(Path(__file__).parent))
from raw_converter import is_raw_file, raw_to_jpeg


def prepare_image(image_path: str) -> tuple[str, bool]:
    """准备图片"""
    if not is_raw_file(image_path):
        return image_path, False

    import tempfile
    temp_path = os.path.join(
        tempfile.gettempdir(),
        f"test_coinstruct_{os.path.basename(image_path)}.jpg"
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
    
    # 加载 co-instruct 模型
    print("=" * 70)
    print("🚀 加载 co-instruct 模型...")
    print("=" * 70)
    
    from transformers import AutoModelForCausalLM
    
    model = AutoModelForCausalLM.from_pretrained(
        "q-future/co-instruct",
        trust_remote_code=True,
        torch_dtype=torch.float16,
        attn_implementation="eager",
        device_map={"": "mps"}  # Apple Silicon
    )
    
    print("✅ co-instruct 加载完成\n")
    
    # 准备所有图片
    images = []
    filenames = []
    temp_files = []
    
    for img_path in image_files:
        processed_path, is_temp = prepare_image(img_path)
        img = Image.open(processed_path).convert("RGB")
        images.append(img)
        filenames.append(os.path.basename(img_path))
        if is_temp:
            temp_files.append(processed_path)
        print(f"   加载: {filenames[-1]} {'[RAW→JPEG]' if is_temp else ''}")
    
    # 测试提示列表
    single_image_prompts = [
        ("质量问题检测", "USER: The image: <|image|> Which quality issues exist in this image? List all problems like blur, noise, exposure issues, etc. ASSISTANT:"),
        ("整体质量评价", "USER: The image: <|image|> Describe the overall quality of this landscape photograph. Is it professional quality? ASSISTANT:"),
        ("技术分析", "USER: The image: <|image|> Analyze the technical aspects: sharpness, exposure, dynamic range, color accuracy. ASSISTANT:"),
        ("构图分析", "USER: The image: <|image|> How is the composition of this photograph? Describe the use of foreground, leading lines, and balance. ASSISTANT:"),
        ("优缺点总结", "USER: The image: <|image|> What are the strengths and weaknesses of this photograph? Be specific. ASSISTANT:"),
        ("中文分析", "USER: The image: <|image|> 请用中文分析这张风光照片的优缺点。 ASSISTANT:"),
    ]
    
    # 对每张图片进行单图分析
    print("\n" + "=" * 70)
    print("📷 单图分析测试")
    print("=" * 70)
    
    for i, (img, filename) in enumerate(zip(images, filenames)):
        print(f"\n{'─' * 70}")
        print(f"📷 {filename}")
        print(f"{'─' * 70}")
        
        for prompt_name, prompt in single_image_prompts:
            print(f"\n  🔸 {prompt_name}")
            
            start = time.time()
            try:
                response = model.chat(prompt, [img], max_new_tokens=200)
                elapsed = time.time() - start
                print(f"     ⏱️ {elapsed:.1f}s")
                print(f"     📝 {response}")
            except Exception as e:
                elapsed = time.time() - start
                print(f"     ❌ Error ({elapsed:.1f}s): {e}")
    
    # 图片对比测试（如果有多张图）
    if len(images) >= 2:
        print("\n\n" + "=" * 70)
        print("🔄 双图对比测试")
        print("=" * 70)
        
        compare_prompt = "USER: The first image: <|image|>\nThe second image: <|image|>\nWhich image has better quality? Compare their technical quality, composition, and aesthetic appeal. ASSISTANT:"
        
        # 只对比几组
        comparisons = [
            (0, 1),
            (0, 2) if len(images) > 2 else None,
            (2, 3) if len(images) > 3 else None,
        ]
        
        for pair in comparisons:
            if pair is None:
                continue
            i, j = pair
            print(f"\n{'─' * 70}")
            print(f"🔄 对比: {filenames[i]} vs {filenames[j]}")
            print(f"{'─' * 70}")
            
            start = time.time()
            try:
                response = model.chat(compare_prompt, [images[i], images[j]], max_new_tokens=300)
                elapsed = time.time() - start
                print(f"  ⏱️ {elapsed:.1f}s")
                print(f"  📝 {response}")
            except Exception as e:
                elapsed = time.time() - start
                print(f"  ❌ Error ({elapsed:.1f}s): {e}")
    
    # 清理临时文件
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    print("\n\n✅ 测试完成")


if __name__ == "__main__":
    main()
