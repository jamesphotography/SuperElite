#!/usr/bin/env python3
"""
Q-SiT-mini vs One-Align 对比测试
对同样 100 张照片评分，比较排序一致性
"""

import os
import sys
import time
import csv
from pathlib import Path
from PIL import Image
import torch
import numpy as np
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))


def wa5(logits):
    """加权平均计算分数 (0-1)"""
    logprobs = np.array([logits["Excellent"], logits["Good"], logits["Fair"], logits["Poor"], logits["Bad"]])
    probs = np.exp(logprobs) / np.sum(np.exp(logprobs))
    return np.inner(probs, np.array([1, 0.75, 0.5, 0.25, 0]))


def load_qsit_mini():
    """加载 Q-SiT-mini 模型"""
    print("\n" + "=" * 60)
    print("🚀 加载 Q-SiT-mini 模型...")
    print("=" * 60)
    
    from transformers import AutoProcessor, LlavaOnevisionForConditionalGeneration, AutoTokenizer
    
    model_id = "zhangzicheng/q-sit-mini"
    
    model = LlavaOnevisionForConditionalGeneration.from_pretrained(
        model_id,
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True,
    ).to("mps")  # Apple Silicon
    
    processor = AutoProcessor.from_pretrained(model_id)
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    
    # 定义评分 token
    toks = ["Excellent", "Good", "Fair", "Poor", "Bad"]
    ids_ = [id_[0] for id_ in tokenizer(toks)["input_ids"]]
    
    print("✅ Q-SiT-mini 加载完成\n")
    
    return model, processor, tokenizer, toks, ids_


def score_with_qsit(model, processor, tokenizer, toks, ids_, image, task="quality"):
    """使用 Q-SiT-mini 评分"""
    
    if task == "quality":
        prompt_text = "Assume you are an image quality evaluator. \nYour rating should be chosen from the following five categories: Excellent, Good, Fair, Poor, and Bad (from high to low). \nHow would you rate the quality of this image?"
        prefix_text = "The quality of this image is "
    else:
        prompt_text = "Assume you are an image aesthetic evaluator. \nYour rating should be chosen from the following five categories: Excellent, Good, Fair, Poor, and Bad (from high to low). \nHow would you rate the aesthetic of this image?"
        prefix_text = "The aesthetic of this image is "
    
    conversation = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt_text},
                {"type": "image"},
            ],
        },
    ]
    
    prompt = processor.apply_chat_template(conversation, add_generation_prompt=True)
    inputs = processor(images=image, text=prompt, return_tensors='pt').to("mps", torch.float16)
    
    # 添加助手前缀
    prefix_ids = tokenizer(prefix_text, return_tensors="pt")["input_ids"].to("mps")
    inputs["input_ids"] = torch.cat([inputs["input_ids"], prefix_ids], dim=-1)
    inputs["attention_mask"] = torch.ones_like(inputs["input_ids"])
    
    # 生成评分 token
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=1,
            output_logits=True,
            return_dict_in_generate=True,
        )
    
    # 提取 logits 并计算分数
    last_logits = output.logits[-1][0]
    logits_dict = {tok: last_logits[id_].item() for tok, id_ in zip(toks, ids_)}
    score = wa5(logits_dict) * 100  # 转换为 0-100
    
    return score


def main():
    test_dir = "/Users/jameszhenyu/Desktop/NEWTEST_preprocessed_1024"
    
    # 收集图片
    extensions = {".jpg", ".jpeg", ".png"}
    image_files = []
    for f in os.listdir(test_dir):
        if os.path.splitext(f)[1].lower() in extensions:
            image_files.append(os.path.join(test_dir, f))
    
    image_files = sorted(image_files)[:100]  # 取前 100 张
    
    print(f"\n📁 测试目录: {test_dir}")
    print(f"   找到 {len(image_files)} 张图片\n")
    
    # 加载 Q-SiT-mini
    model, processor, tokenizer, toks, ids_ = load_qsit_mini()
    
    # 评分
    print("\n" + "=" * 60)
    print("🔬 Q-SiT-mini 评分中...")
    print("=" * 60 + "\n")
    
    results = []
    start_total = time.time()
    
    for img_path in tqdm(image_files, desc="评分进度"):
        filename = os.path.basename(img_path)
        
        try:
            image = Image.open(img_path).convert("RGB")
            
            start = time.time()
            quality_score = score_with_qsit(model, processor, tokenizer, toks, ids_, image, "quality")
            aesthetic_score = score_with_qsit(model, processor, tokenizer, toks, ids_, image, "aesthetic")
            elapsed = time.time() - start
            
            # 综合分 (和 One-Align 相同权重: Q40% + A60%)
            total_score = quality_score * 0.4 + aesthetic_score * 0.6
            
            results.append({
                "file": filename,
                "quality": quality_score,
                "aesthetic": aesthetic_score,
                "total": total_score,
                "time": elapsed,
            })
            
        except Exception as e:
            tqdm.write(f"❌ {filename}: {e}")
            results.append({
                "file": filename,
                "quality": 0,
                "aesthetic": 0,
                "total": 0,
                "time": 0,
                "error": str(e),
            })
    
    total_time = time.time() - start_total
    
    # 保存结果
    output_csv = os.path.join(test_dir, "qsit_mini_results.csv")
    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "quality", "aesthetic", "total", "time", "error"])
        writer.writeheader()
        for r in results:
            writer.writerow(r)
    
    print(f"\n✅ 结果已保存: {output_csv}")
    
    # 统计
    valid_results = [r for r in results if "error" not in r]
    avg_time = sum(r["time"] for r in valid_results) / len(valid_results) if valid_results else 0
    
    print(f"\n📊 统计:")
    print(f"   成功: {len(valid_results)}/{len(results)}")
    print(f"   总耗时: {total_time:.1f}s")
    print(f"   平均耗时: {avg_time:.2f}s/张")
    
    # 分数分布
    if valid_results:
        totals = [r["total"] for r in valid_results]
        print(f"\n   分数分布:")
        print(f"   最高: {max(totals):.1f}")
        print(f"   最低: {min(totals):.1f}")
        print(f"   平均: {sum(totals)/len(totals):.1f}")


if __name__ == "__main__":
    main()
