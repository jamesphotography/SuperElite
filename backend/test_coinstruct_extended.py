#!/usr/bin/env python3
"""
测试 co-instruct 的扩展能力
- 场景描述
- 关键字生成
- 场景分类
- 拍摄时间/地点推断
- 情绪/氛围描述
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
        f"test_ext_{os.path.basename(image_path)}.jpg"
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
    
    # 只用 JPG 测试
    jpg_file = None
    for f in os.listdir(test_dir):
        if f.lower().endswith('.jpg'):
            jpg_file = os.path.join(test_dir, f)
            break
    
    if not jpg_file:
        # 用第一张图
        for f in os.listdir(test_dir):
            ext = os.path.splitext(f)[1].lower()
            if ext in {".jpg", ".jpeg", ".png", ".arw", ".cr2", ".cr3", ".nef", ".dng", ".raf"}:
                jpg_file = os.path.join(test_dir, f)
                break
    
    print(f"\n📷 测试图片: {os.path.basename(jpg_file)}\n")
    
    # 加载模型
    print("=" * 70)
    print("🚀 加载 co-instruct 模型...")
    print("=" * 70)
    
    from transformers import AutoModelForCausalLM
    
    model = AutoModelForCausalLM.from_pretrained(
        "q-future/co-instruct",
        trust_remote_code=True,
        torch_dtype=torch.float16,
        attn_implementation="eager",
        device_map={"": "mps"}
    )
    
    print("✅ 模型加载完成\n")
    
    # 准备图片
    processed_path, is_temp = prepare_image(jpg_file)
    image = Image.open(processed_path).convert("RGB")
    print(f"   {'[RAW→JPEG]' if is_temp else '[直接读取]'}")
    
    # 扩展能力测试
    extended_prompts = [
        # === 场景描述 ===
        ("场景描述 (EN)", 
         "USER: The image: <|image|> Describe what you see in this photograph in detail. Include the subject, setting, and any notable elements. ASSISTANT:"),
        
        ("场景描述 (中文)", 
         "USER: The image: <|image|> 请详细描述这张照片中的场景。 ASSISTANT:"),
        
        # === 关键字生成 ===
        ("关键字 (EN)", 
         "USER: The image: <|image|> Generate 10 keywords that describe this photograph. List them separated by commas. ASSISTANT:"),
        
        ("关键字 (中文)", 
         "USER: The image: <|image|> 为这张照片生成10个描述性关键词，用逗号分隔。 ASSISTANT:"),
        
        # === 场景分类 ===
        ("场景分类", 
         "USER: The image: <|image|> Classify this photograph into one category: sunset, sunrise, aurora, night/starry, waterfall, mountain, ocean/seascape, cityscape, forest, desert, wildlife, portrait, street. Answer with one word. ASSISTANT:"),
        
        ("拍摄类型", 
         "USER: The image: <|image|> What type of photography is this: landscape, portrait, wildlife, architecture, street, macro, aerial, underwater? Answer with one word. ASSISTANT:"),
        
        # === 时间/地点推断 ===
        ("拍摄时间", 
         "USER: The image: <|image|> What time of day was this photo taken: sunrise/golden hour, morning, midday, afternoon, sunset/golden hour, blue hour, night? ASSISTANT:"),
        
        ("可能地点", 
         "USER: The image: <|image|> Where do you think this photograph was taken? Describe the likely location or region. ASSISTANT:"),
        
        # === 情绪/氛围 ===
        ("情绪氛围", 
         "USER: The image: <|image|> Describe the mood and atmosphere of this photograph in 2-3 words. ASSISTANT:"),
        
        ("情感标签", 
         "USER: The image: <|image|> What emotion does this photograph evoke? Choose from: peaceful, dramatic, mysterious, joyful, melancholic, awe-inspiring, romantic, energetic. ASSISTANT:"),
        
        # === 技术信息推断 ===
        ("拍摄设备推测", 
         "USER: The image: <|image|> Based on the image quality and characteristics, guess what camera type was used: smartphone, mirrorless, DSLR, drone, action camera? ASSISTANT:"),
        
        ("焦段推测", 
         "USER: The image: <|image|> Estimate the focal length used: ultra-wide (14-24mm), wide (24-35mm), standard (35-50mm), short telephoto (70-135mm), telephoto (200mm+)? ASSISTANT:"),
        
        # === 标题生成 ===
        ("英文标题", 
         "USER: The image: <|image|> Create a poetic title for this photograph in 3-5 words. ASSISTANT:"),
        
        ("中文标题", 
         "USER: The image: <|image|> 为这张照片创作一个富有诗意的中文标题，3-5个字。 ASSISTANT:"),
        
        # === 社交媒体 ===
        ("Instagram 文案", 
         "USER: The image: <|image|> Write a short Instagram caption for this photograph with relevant hashtags. ASSISTANT:"),
    ]
    
    print("\n" + "=" * 70)
    print("🧪 扩展能力测试")
    print("=" * 70)
    
    results = {}
    
    for prompt_name, prompt in extended_prompts:
        print(f"\n{'─' * 60}")
        print(f"🔸 {prompt_name}")
        
        start = time.time()
        try:
            response = model.chat(prompt, [image], max_new_tokens=150)
            elapsed = time.time() - start
            
            # 只提取文本部分
            if hasattr(response, 'cpu'):
                response_text = str(response)
            else:
                response_text = response
            
            print(f"   ⏱️ {elapsed:.1f}s")
            print(f"   📝 {response_text}")
            
            results[prompt_name] = {
                "response": response_text,
                "time": elapsed,
            }
            
        except Exception as e:
            elapsed = time.time() - start
            print(f"   ❌ Error ({elapsed:.1f}s): {e}")
            results[prompt_name] = {"error": str(e), "time": elapsed}
    
    # 清理
    if is_temp and os.path.exists(processed_path):
        os.remove(processed_path)
    
    # 统计
    print("\n\n" + "=" * 70)
    print("📊 测试统计")
    print("=" * 70)
    
    success = sum(1 for r in results.values() if "error" not in r)
    total_time = sum(r["time"] for r in results.values())
    
    print(f"   成功: {success}/{len(results)}")
    print(f"   总耗时: {total_time:.1f}s")
    print(f"   平均: {total_time/len(results):.1f}s/问题")


if __name__ == "__main__":
    main()
