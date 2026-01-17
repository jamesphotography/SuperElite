# -*- coding: utf-8 -*-
"""
SuperElite - PyIQA 评分器 (基础模型)
使用 NIMA (美学) + TOPIQ (质量) 双模型评分

作为 One-Align (高级模型) 的轻量级替代方案
"""

import os
import sys
import torch
from PIL import Image
from typing import Dict, Optional, Tuple
from pathlib import Path

# 平台检测
IS_MACOS = sys.platform == 'darwin'
IS_WINDOWS = sys.platform.startswith('win')


class PyIQAScorer:
    """PyIQA 评分器 - 双维度评估 (质量 + 美学)"""

    def __init__(
        self,
        models_dir: Optional[str] = None,
        quality_weight: float = 0.4,
        aesthetic_weight: float = 0.6,
    ):
        """
        初始化评分器

        Args:
            models_dir: 模型目录 (默认使用项目 models 目录)
            quality_weight: 质量权重 (默认 0.4)
            aesthetic_weight: 美学权重 (默认 0.6)
        """
        self.quality_weight = quality_weight
        self.aesthetic_weight = aesthetic_weight

        # 确定模型目录
        if models_dir:
            self.models_dir = Path(models_dir)
        elif hasattr(sys, '_MEIPASS'):
            # PyInstaller 打包环境
            self.models_dir = Path(sys._MEIPASS) / 'models'
        else:
            # 开发环境
            self.models_dir = Path(__file__).parent.parent / 'models'

        self.nima_model = None
        self.topiq_model = None
        self.device = None

        print(f"[PyIQA] 模型目录: {self.models_dir}")
        print(f"[PyIQA] 权重: Quality={quality_weight}, Aesthetic={aesthetic_weight}")

    def _select_device(self) -> str:
        """选择最优设备 (MPS/CUDA/CPU)"""
        if IS_MACOS and torch.backends.mps.is_available():
            return "mps"
        elif torch.cuda.is_available():
            return "cuda"
        else:
            return "cpu"

    def load_model(self):
        """加载 NIMA 和 TOPIQ 模型"""
        if self.nima_model is not None and self.topiq_model is not None:
            return

        self.device = self._select_device()
        print(f"[PyIQA] 使用设备: {self.device}")

        # 加载 NIMA (美学评分)
        print("[PyIQA] 正在加载 NIMA 模型 (美学评分)...")
        self._load_nima()

        # 加载 TOPIQ (质量评分)
        print("[PyIQA] 正在加载 TOPIQ 模型 (质量评分)...")
        self._load_topiq()

        print("[PyIQA] 模型加载完成")

    def _load_nima(self):
        """加载 NIMA 模型"""
        from nima_model import NIMA, load_nima_weights

        nima_weights_path = self.models_dir / "nima_ava.pth"
        if not nima_weights_path.exists():
            raise FileNotFoundError(f"NIMA 权重文件不存在: {nima_weights_path}")

        self.nima_model = NIMA()
        load_nima_weights(self.nima_model, str(nima_weights_path), torch.device(self.device))
        self.nima_model.to(self.device)
        self.nima_model.eval()

    def _load_topiq(self):
        """加载 TOPIQ 模型"""
        from topiq_model import CFANet

        topiq_weights_path = self.models_dir / "cfanet_iaa_ava_res50-3cd62bb3.pth"
        if not topiq_weights_path.exists():
            raise FileNotFoundError(f"TOPIQ 权重文件不存在: {topiq_weights_path}")

        # 初始化 CFANet
        self.topiq_model = CFANet(
            semantic_model_name='resnet50',
            backbone_pretrain=False,
            use_ref=False,
            num_class=10,
        )

        # 加载权重
        state_dict = torch.load(str(topiq_weights_path), map_location=self.device, weights_only=True)
        if 'params' in state_dict:
            state_dict = state_dict['params']
        self.topiq_model.load_state_dict(state_dict, strict=False)
        self.topiq_model.to(self.device)
        self.topiq_model.eval()
        print(f"✅ TOPIQ 权重加载完成")

    def score_image(self, image_path: str) -> Dict:
        """
        评分单张图片

        Args:
            image_path: 图片路径

        Returns:
            {
                "quality": float,      # 质量分 (0-100)
                "aesthetic": float,    # 美学分 (0-100)
                "total": float,        # 综合分 (0-100)
                "rating": int,         # 星级 (0-4)
                "pick_flag": str,      # "" (不使用)
                "color_label": str,    # "" (不使用)
            }
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片不存在: {image_path}")

        if self.nima_model is None or self.topiq_model is None:
            self.load_model()

        # 加载图片
        image = Image.open(image_path).convert("RGB")
        
        # 转换为张量
        # 使用固定正方形尺寸 384x384，避免 MPS 上的 adaptive pooling 错误
        import torchvision.transforms as T
        transform = T.Compose([
            T.Resize((384, 384)),  # 固定正方形尺寸
            T.ToTensor(),
        ])
        img_tensor = transform(image).unsqueeze(0).to(self.device)

        # 尝试在主设备上评分，如果 MPS 遇到 adaptive pool 错误则回退到 CPU
        try:
            aesthetic, quality = self._run_inference(img_tensor)
        except RuntimeError as e:
            if "Adaptive pool MPS" in str(e) or "adaptive" in str(e).lower():
                # MPS adaptive pooling 不支持此尺寸，回退到 CPU
                img_tensor_cpu = img_tensor.cpu()
                self.nima_model.cpu()
                self.topiq_model.cpu()
                aesthetic, quality = self._run_inference(img_tensor_cpu)
                # 恢复到原设备
                self.nima_model.to(self.device)
                self.topiq_model.to(self.device)
            else:
                raise

        # 综合评分 (已经是 0-100 分制)
        total = quality * self.quality_weight + aesthetic * self.aesthetic_weight

        # 映射到星级和标签
        rating, pick_flag, color_label = self._map_to_rating(total)

        return {
            "quality": quality,
            "aesthetic": aesthetic,
            "total": total,
            "rating": rating,
            "pick_flag": pick_flag,
            "color_label": color_label,
        }
    
    def _run_inference(self, img_tensor: torch.Tensor) -> tuple:
        """在指定设备上运行推理"""
        with torch.inference_mode():
            # NIMA 美学评分 (1-10 → 0-100)
            aesthetic_raw = self.nima_model.predict_score(img_tensor).item()
            aesthetic = aesthetic_raw * 10  # 转换为 0-100

            # TOPIQ 质量评分 (1-10 → 0-100)
            quality_raw = self.topiq_model(img_tensor, return_mos=True, return_dist=False).item()
            quality = quality_raw * 10  # 转换为 0-100
        
        # 归一化分数，使其与 One-Align 的分数范围一致
        # NIMA+TOPIQ 原始范围约 40-70，One-Align 范围约 65-99
        # 使用线性映射: new = (old - old_min) / (old_max - old_min) * (new_max - new_min) + new_min
        aesthetic = self._normalize_score(aesthetic)
        quality = self._normalize_score(quality)
        
        return aesthetic, quality
    
    @staticmethod
    def _normalize_score(score: float) -> float:
        """
        归一化分数，使 PyIQA 的分数范围与 One-Align 一致
        
        原始范围: 约 40-70 (NIMA+TOPIQ 典型输出)
        目标范围: 约 55-99 (与 One-Align 对齐，扩大差距)
        """
        old_min, old_max = 40.0, 70.0  # PyIQA 典型输出范围
        new_min, new_max = 55.0, 99.0  # 目标范围 (扩大)
        
        # 先裁剪到预期范围
        score = max(old_min, min(old_max, score))
        
        # 线性映射
        normalized = (score - old_min) / (old_max - old_min) * (new_max - new_min) + new_min
        
        return normalized


    @staticmethod
    def _map_to_rating(total_score: float) -> Tuple[int, str, str]:
        """
        映射综合分到星级
        使用与 OneAlignScorer 相同的阈值
        """
        global _thresholds
        t4, t3, t2, t1 = _thresholds

        if total_score >= t4:
            return 4, "", ""
        elif total_score >= t3:
            return 3, "", ""
        elif total_score >= t2:
            return 2, "", ""
        elif total_score >= t1:
            return 1, "", ""
        else:
            return 0, "", ""

    def warmup(self):
        """预热模型"""
        if self.nima_model is None or self.topiq_model is None:
            self.load_model()


# 全局阈值配置 (与 OneAlignScorer 保持一致)
_thresholds = (78.0, 72.0, 66.0, 58.0)  # (4星, 3星, 2星, 1星)


def set_thresholds(t4: float, t3: float, t2: float, t1: float):
    """设置自定义星级阈值"""
    global _thresholds
    _thresholds = (t4, t3, t2, t1)


# 全局单例
_pyiqa_scorer_instance = None


def get_pyiqa_scorer(
    models_dir: Optional[str] = None,
    quality_weight: float = 0.4,
    aesthetic_weight: float = 0.6,
) -> PyIQAScorer:
    """获取评分器单例"""
    global _pyiqa_scorer_instance

    if _pyiqa_scorer_instance is None:
        _pyiqa_scorer_instance = PyIQAScorer(
            models_dir=models_dir,
            quality_weight=quality_weight,
            aesthetic_weight=aesthetic_weight,
        )

    return _pyiqa_scorer_instance


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python pyiqa_scorer.py <图片路径>")
        sys.exit(1)

    scorer = get_pyiqa_scorer()
    result = scorer.score_image(sys.argv[1])

    print(f"\n{'=' * 50}")
    print("PyIQA 评分结果 (NIMA + TOPIQ)")
    print(f"{'=' * 50}")
    print(f"质量分 (TOPIQ): {result['quality']:.2f}")
    print(f"美学分 (NIMA):  {result['aesthetic']:.2f}")
    print(f"综合分: {result['total']:.2f}")
    print(f"星级: {'⭐' * result['rating']} ({result['rating']}星)")
