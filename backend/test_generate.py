#!/usr/bin/env python3
"""
测试 One-Align 的文本生成能力
尝试绕过 score() 方法，直接用模型做分类/描述
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


def expand2square(pil_img, background_color):
    """将图片填充为正方形"""
    width, height = pil_img.size
    if width == height:
        return pil_img
    elif width > height:
        result = Image.new(pil_img.mode, (width, width), background_color)
        result.paste(pil_img, (0, (width - height) // 2))
        return result
    else:
        result = Image.new(pil_img.mode, (height, height), background_color)
        result.paste(pil_img, ((height - width) // 2, 0))
        return result


def main():
    test_dir = "/Users/jameszhenyu/Desktop/NEWTEST/4"
    
    # 找 JPG 文件测试
    jpg_file = None
    for f in os.listdir(test_dir):
        if f.lower().endswith('.jpg'):
            jpg_file = os.path.join(test_dir, f)
            break
    
    if not jpg_file:
        print("❌ 未找到 JPG 测试图片")
        return
    
    print(f"\n📷 测试图片: {os.path.basename(jpg_file)}\n")
    
    # 加载模型
    scorer = OneAlignScorer()
    scorer.load_model()
    model = scorer.model
    
    print(f"\n{'='*70}")
    print("🔍 检查模型方法")
    print(f"{'='*70}")
    
    methods_to_check = ['generate', 'forward', 'chat', 'tokenizer', 'image_processor']
    for method in methods_to_check:
        has_method = hasattr(model, method)
        print(f"  {method}: {'✅' if has_method else '❌'}")
    
    # 加载图片
    image = Image.open(jpg_file).convert("RGB")
    
    print(f"\n{'='*70}")
    print("🧪 测试文本生成")
    print(f"{'='*70}")
    
    # 准备图像张量
    image_squared = expand2square(image, tuple(int(x*255) for x in model.image_processor.image_mean))
    image_tensor = model.image_processor.preprocess([image_squared], return_tensors="pt")["pixel_values"].half().to(model.device)
    
    # IMAGE_TOKEN_INDEX 通常是 -200
    IMAGE_TOKEN_INDEX = -200
    
    def tokenizer_image_token(prompt, tokenizer, image_token_index=IMAGE_TOKEN_INDEX, return_tensors=None):
        """简化版的 tokenizer_image_token"""
        prompt_chunks = prompt.split('<|image|>')
        input_ids = []
        
        for i, chunk in enumerate(prompt_chunks):
            chunk_ids = tokenizer.encode(chunk, add_special_tokens=(i == 0))
            input_ids.extend(chunk_ids)
            if i < len(prompt_chunks) - 1:
                input_ids.append(image_token_index)
        
        if return_tensors == 'pt':
            return torch.tensor(input_ids, dtype=torch.long)
        return input_ids
    
    # 准备测试提示
    test_prompts = [
        # 分类任务
        ("场景分类 (EN)", 
         "USER: Classify this landscape photo into one category: sunset, sunrise, aurora, night, waterfall, mountain, seascape, cityscape, forest, desert. Answer with one word only.\n<|image|>\nASSISTANT:"),
        
        ("场景分类 (中文)", 
         "USER: 这是什么类型的风光照片？请从以下选项中选择一个：日落、日出、极光、夜景、瀑布、山景、海景、城市、森林、沙漠。只回答一个词。\n<|image|>\nASSISTANT:"),
        
        ("时间判断", 
         "USER: What time of day was this photo taken? Answer: golden hour, blue hour, midday, night, or overcast.\n<|image|>\nASSISTANT:"),
        
        ("情绪判断", 
         "USER: What is the mood of this photograph? Answer with one or two words.\n<|image|>\nASSISTANT:"),
        
        # 描述任务
        ("简短描述 (EN)", 
         "USER: Describe this photograph in one sentence.\n<|image|>\nASSISTANT:"),
        
        ("简短描述 (中文)", 
         "USER: 用一句话描述这张照片。\n<|image|>\nASSISTANT:"),
        
        # 更详细的分析
        ("优点分析", 
         "USER: What are the main strengths of this photograph?\n<|image|>\nASSISTANT:"),
        
        ("改进建议", 
         "USER: What could be improved in this photograph?\n<|image|>\nASSISTANT:"),
    ]
    
    for name, prompt in test_prompts:
        print(f"\n--- {name} ---")
        
        start = time.time()
        
        try:
            # Tokenize prompt
            input_ids = tokenizer_image_token(prompt, model.tokenizer, IMAGE_TOKEN_INDEX, return_tensors='pt').unsqueeze(0).to(model.device)
            
            # 尝试 generate
            with torch.inference_mode():
                output_ids = model.generate(
                    input_ids,
                    images=image_tensor,
                    max_new_tokens=100,
                    do_sample=False,
                    num_beams=1,
                    use_cache=True,
                )
            
            # 解码输出
            output_text = model.tokenizer.decode(output_ids[0], skip_special_tokens=True)
            
            # 提取 ASSISTANT 之后的部分
            if "ASSISTANT:" in output_text:
                response = output_text.split("ASSISTANT:")[-1].strip()
            else:
                response = output_text
            
            elapsed = time.time() - start
            print(f"  📝 Response: {response}")
            print(f"  ⏱️  Time: {elapsed:.2f}s")
            
        except Exception as e:
            elapsed = time.time() - start
            print(f"  ❌ Error: {e}")
            print(f"  ⏱️  Time: {elapsed:.2f}s")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
