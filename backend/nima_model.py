"""
独立 NIMA (Neural Image Assessment) 模型实现
替代 pyiqa 库，用于美学评分

基于：
- pyiqa 的 NIMA 架构 (chaofengc/IQA-PyTorch)
- 原论文: Talebi, H., & Milanfar, P. (2018). NIMA: Neural image assessment.

依赖项：torch, torchvision, timm, PIL
"""

import os
import torch
import torch.nn as nn
import timm
import torchvision.transforms as T
from PIL import Image


class NIMA(nn.Module):
    """
    NIMA 美学评分模型
    
    使用 InceptionResNetV2 作为骨干网络，输出 1-10 分的概率分布
    
    输入: (N, 3, 299, 299) RGB 图像，值范围 [0, 1]
    输出: 美学评分 (1-10 范围的加权平均分)
    """
    
    def __init__(
        self,
        base_model_name: str = 'inception_resnet_v2',
        num_classes: int = 10,
        dropout_rate: float = 0.0,
    ):
        super(NIMA, self).__init__()
        
        # 使用 timm 创建骨干网络（仅提取特征）
        self.base_model = timm.create_model(
            base_model_name, 
            pretrained=False,  # 不加载 ImageNet 权重，我们会加载 NIMA 权重
            features_only=True
        )
        
        # 全局平均池化
        self.global_pool = nn.AdaptiveAvgPool2d(1)
        
        # 获取最后一层特征通道数
        in_ch = self.base_model.feature_info.channels()[-1]
        self.num_classes = num_classes
        
        # 分类头
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(p=dropout_rate),
            nn.Linear(in_features=in_ch, out_features=num_classes),
            nn.Softmax(dim=-1)
        )
        
        # 归一化参数（ImageNet 标准）
        self.register_buffer('default_mean', torch.tensor([0.5, 0.5, 0.5]).view(1, 3, 1, 1))
        self.register_buffer('default_std', torch.tensor([0.5, 0.5, 0.5]).view(1, 3, 1, 1))
        
        # 输入尺寸
        self.input_size = 299
    
    def preprocess(self, x: torch.Tensor) -> torch.Tensor:
        """预处理输入图像"""
        # Resize 和 Center Crop 到 299x299
        x = T.functional.resize(x, self.input_size)
        x = T.functional.center_crop(x, self.input_size)
        # ImageNet 归一化
        x = (x - self.default_mean.to(x.device)) / self.default_std.to(x.device)
        return x
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        前向传播
        
        Args:
            x: 输入图像张量 (N, 3, H, W)，值范围 [0, 1]
            
        Returns:
            概率分布 (N, 10)
        """
        x = self.preprocess(x)
        x = self.base_model(x)[-1]  # 取最后一层特征
        x = self.global_pool(x)
        dist = self.classifier(x)
        return dist
    
    def predict_score(self, x: torch.Tensor) -> torch.Tensor:
        """
        计算美学评分 (MOS - Mean Opinion Score)
        
        Args:
            x: 输入图像张量 (N, 3, H, W)
            
        Returns:
            评分张量 (N,)，范围 1-10
        """
        dist = self.forward(x)
        # 计算加权平均: sum(prob_i * score_i)，score_i = 1, 2, ..., 10
        scores = torch.arange(1, 11, dtype=torch.float32, device=x.device)
        mos = (dist * scores).sum(dim=1)
        return mos


def load_nima_weights(model: NIMA, weight_path: str, device: torch.device) -> None:
    """
    加载 NIMA 预训练权重
    
    Args:
        model: NIMA 模型实例
        weight_path: 权重文件路径
        device: 目标设备
    """
    if not os.path.exists(weight_path):
        raise FileNotFoundError(f"权重文件不存在: {weight_path}")
    
    state_dict = torch.load(weight_path, map_location=device, weights_only=True)
    
    # pyiqa 权重格式：{'params': {...}}
    if 'params' in state_dict:
        state_dict = state_dict['params']
    
    # 加载权重（strict=False 因为 buffer 不在权重文件中）
    missing, unexpected = model.load_state_dict(state_dict, strict=False)
    
    # 检查是否有关键权重缺失（排除 buffer）
    critical_missing = [k for k in missing if 'default_' not in k]
    if critical_missing:
        raise RuntimeError(f"关键权重缺失: {critical_missing}")
    
    print(f"✅ NIMA 权重加载完成: {os.path.basename(weight_path)}")


# 注意：NIMAScorer 封装类已移至 iqa_scorer.py
# 本模块仅提供 NIMA 模型定义和权重加载函数

