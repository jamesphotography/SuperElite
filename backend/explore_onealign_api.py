#!/usr/bin/env python3
"""
深入探索 One-Align 模型的所有可用接口和方法
"""

import sys
from pathlib import Path
import torch

sys.path.insert(0, str(Path(__file__).parent))

# 使用已有的 scorer 来加载模型
from one_align_scorer import OneAlignScorer

def main():
    print("=" * 70)
    print("🔍 探索 One-Align 模型的所有接口")
    print("=" * 70)
    
    # 加载模型
    scorer = OneAlignScorer()
    scorer.load_model()
    model = scorer.model
    
    print("\n" + "=" * 70)
    print("📋 模型类信息")
    print("=" * 70)
    print(f"模型类型: {type(model)}")
    print(f"模型类名: {model.__class__.__name__}")
    if hasattr(model, '__module__'):
        print(f"模型模块: {model.__module__}")
    
    print("\n" + "=" * 70)
    print("📋 所有公开方法 (不以 _ 开头)")
    print("=" * 70)
    
    public_methods = []
    for attr_name in dir(model):
        if not attr_name.startswith('_'):
            attr = getattr(model, attr_name, None)
            if callable(attr):
                public_methods.append(attr_name)
    
    for method in sorted(public_methods):
        print(f"  • {method}")
    
    print(f"\n  共 {len(public_methods)} 个公开方法")
    
    # 重点方法的详细信息
    important_methods = ['score', 'forward', 'generate', 'chat', 
                         'encode_image', 'encode_images', 'get_model',
                         'prepare_inputs_labels_for_multimodal',
                         'preprocess', 'embed_tokens']
    
    print("\n" + "=" * 70)
    print("🔍 重点方法详细信息")
    print("=" * 70)
    
    for method_name in important_methods:
        if hasattr(model, method_name):
            method = getattr(model, method_name)
            print(f"\n✅ {method_name}:")
            if hasattr(method, '__doc__') and method.__doc__:
                doc = method.__doc__.strip()[:300]
                print(f"   文档: {doc}...")
            
            # 尝试获取方法签名
            import inspect
            try:
                sig = inspect.signature(method)
                print(f"   签名: {method_name}{sig}")
            except (ValueError, TypeError):
                print(f"   签名: 无法获取")
        else:
            print(f"\n❌ {method_name}: 不存在")
    
    # 检查模型配置
    print("\n" + "=" * 70)
    print("⚙️ 模型配置")
    print("=" * 70)
    
    if hasattr(model, 'config'):
        config = model.config
        print(f"  配置类型: {type(config)}")
        
        # 列出配置的主要属性
        config_attrs = ['model_type', 'hidden_size', 'num_hidden_layers', 
                        'vocab_size', 'max_position_embeddings']
        for attr in config_attrs:
            if hasattr(config, attr):
                print(f"  {attr}: {getattr(config, attr)}")
    
    # 检查是否有 tokenizer
    print("\n" + "=" * 70)
    print("📝 Tokenizer 信息")
    print("=" * 70)
    
    if hasattr(model, 'tokenizer'):
        print(f"  ✅ model.tokenizer 存在")
        print(f"  类型: {type(model.tokenizer)}")
    else:
        print(f"  ❌ model.tokenizer 不存在")
    
    # 检查 image processor
    print("\n" + "=" * 70)
    print("🖼️ Image Processor 信息")
    print("=" * 70)
    
    if hasattr(model, 'image_processor'):
        print(f"  ✅ model.image_processor 存在")
    elif hasattr(model, 'image_tower'):
        print(f"  ✅ model.image_tower 存在")
    else:
        print(f"  ❌ 没有明确的 image processor")
    
    # 尝试查看 score 方法的源代码
    print("\n" + "=" * 70)
    print("📖 score 方法源代码位置")
    print("=" * 70)
    
    import inspect
    if hasattr(model, 'score'):
        try:
            source_file = inspect.getfile(model.score)
            print(f"  文件: {source_file}")
        except:
            print("  无法获取源文件")


if __name__ == "__main__":
    main()
