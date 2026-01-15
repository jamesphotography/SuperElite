"""
SuperElite - One-Align 评分器
基于 q-future/one-align 的双维度图像评分 (质量 + 美学)
"""

import os
import torch
from PIL import Image
from typing import Dict, List, Tuple, Optional
from pathlib import Path


class OneAlignScorer:
    """One-Align 评分器 - 双维度评估 (质量 + 美学)"""

    def __init__(
        self,
        model_path: Optional[str] = None,
        quality_weight: float = 0.4,
        aesthetic_weight: float = 0.6,
    ):
        """
        初始化评分器

        Args:
            model_path: 模型路径 (默认使用 HuggingFace 缓存)
            quality_weight: 质量权重 (默认 0.4)
            aesthetic_weight: 美学权重 (默认 0.6)
        """
        self.model_path = model_path or "q-future/one-align"
        self.quality_weight = quality_weight
        self.aesthetic_weight = aesthetic_weight

        self.model = None
        self.device = None

        print(f"[OneAlign] 模型: {self.model_path}")
        print(f"[OneAlign] 权重: Quality={quality_weight}, Aesthetic={aesthetic_weight}")

    def _select_device(self) -> str:
        """选择最优设备 (MPS 优先)"""
        if torch.backends.mps.is_available():
            return "mps"
        elif torch.cuda.is_available():
            return "cuda"
        else:
            return "cpu"

    @staticmethod
    def _patch_llama_rotary_embedding():
        """
        修复 LlamaRotaryEmbedding 与 transformers 4.40+ 的兼容性问题

        transformers 4.40+ 可能有不同的 API：
        - 旧版: forward(self, x, seq_len=None)
        - 某些版本: forward(self, x, position_ids=None)
        
        One-Align 模型内部可能使用不同的调用方式，需要适配
        """
        try:
            from transformers.models.llama.modeling_llama import LlamaRotaryEmbedding
            import inspect

            # 检查原始 forward 的签名
            sig = inspect.signature(LlamaRotaryEmbedding.forward)
            params = list(sig.parameters.keys())

            # 保存原始的 forward 方法
            original_forward = LlamaRotaryEmbedding.forward

            if 'position_ids' in params:
                # 新版 API：接受 position_ids
                def patched_forward(self, x, position_ids=None, seq_len=None):
                    """兼容：如果传入 seq_len，转换为 position_ids"""
                    if seq_len is not None and position_ids is None:
                        batch_size = x.shape[0]
                        device = x.device
                        position_ids = torch.arange(seq_len, dtype=torch.long, device=device)
                        position_ids = position_ids.unsqueeze(0).expand(batch_size, -1)
                    return original_forward(self, x, position_ids=position_ids)
            else:
                # 当前版本 API：只接受 seq_len
                def patched_forward(self, x, position_ids=None, seq_len=None):
                    """兼容：如果传入 position_ids，转换为 seq_len"""
                    if seq_len is None and position_ids is not None:
                        seq_len = position_ids.shape[-1]
                    return original_forward(self, x, seq_len=seq_len)

            # 应用补丁
            LlamaRotaryEmbedding.forward = patched_forward
            print("[OneAlign] 已修复 LlamaRotaryEmbedding 兼容性")

        except ImportError:
            # 如果没有 LlamaRotaryEmbedding，跳过补丁
            pass
        except Exception as e:
            print(f"[OneAlign] 警告: 补丁失败 ({e})，可能导致兼容性问题")

    def load_model(self):
        """加载 One-Align 模型"""
        if self.model is not None:
            return

        from transformers import AutoModel

        # 修复 LlamaRotaryEmbedding 与 transformers 4.40 的兼容性问题
        self._patch_llama_rotary_embedding()

        self.device = self._select_device()
        print(f"[OneAlign] 使用设备: {self.device}")
        print("[OneAlign] 正在加载模型 (首次约需 1-2 分钟)...")

        # 根据设备选择dtype和加载方式
        if self.device == "mps":
            # MPS 需要使用 device_map="mps" 和 float16
            self.model = AutoModel.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16,
                device_map="mps",
                trust_remote_code=True,
            )
        elif self.device == "cuda":
            self.model = AutoModel.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16,
                device_map="auto",
                trust_remote_code=True,
            )
        else:
            self.model = AutoModel.from_pretrained(
                self.model_path,
                torch_dtype=torch.float32,
                device_map="cpu",
                trust_remote_code=True,
            )

        # 修复 One-Align 模型与 transformers 4.40 的兼容性问题
        # 模型内部代码引用了这些属性，但新版 transformers 没有自动设置
        if hasattr(self.model, 'model'):
            if not hasattr(self.model.model, '_use_flash_attention_2'):
                self.model.model._use_flash_attention_2 = False
            if not hasattr(self.model.model, '_use_sdpa'):
                self.model.model._use_sdpa = False
            print("[OneAlign] 已修复 attention 兼容性")

        # 设置为评估模式
        self.model.eval()

        print("[OneAlign] 模型加载成功")

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
                "pick_flag": str,      # "picked" / "rejected" / ""
                "color_label": str,    # "Green" / "Yellow" / "Red" / "Purple" / ""
            }
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片不存在: {image_path}")

        if self.model is None:
            self.load_model()

        # 加载图片
        image = Image.open(image_path).convert("RGB")

        with torch.inference_mode():
            # 质量评分 (One-Align 返回 0-5 分制)
            quality_score = self.model.score(
                [image],
                task_="quality",
                input_="image",
            )
            quality_raw = float(quality_score[0]) if isinstance(quality_score, list) else float(quality_score)
            quality = quality_raw * 20  # 转换为 0-100 分制

            # 美学评分 (One-Align 返回 0-5 分制)
            aesthetic_score = self.model.score(
                [image],
                task_="aesthetics",
                input_="image",
            )
            aesthetic_raw = float(aesthetic_score[0]) if isinstance(aesthetic_score, list) else float(aesthetic_score)
            aesthetic = aesthetic_raw * 20  # 转换为 0-100 分制

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

    def score_batch(self, image_paths: List[str]) -> List[Dict]:
        """
        批量评分 (TODO: 真正的批量推理优化)

        Args:
            image_paths: 图片路径列表

        Returns:
            评分结果列表
        """
        results = []
        for path in image_paths:
            try:
                result = self.score_image(path)
                result["file"] = path
                results.append(result)
            except Exception as e:
                results.append({"file": path, "error": str(e)})
        return results

    @staticmethod
    def _map_to_rating(total_score: float) -> Tuple[int, str, str]:
        """
        映射综合分到星级、旗标、色标

        Args:
            total_score: 综合分 (0-100)

        Returns:
            (rating, pick_flag, color_label)

        新阈值设计（0-4星，5星留给用户手动评级）：
        - 4星 (≥78): AI最高评价，顶级照片，约包10-15%
        - 3星 (≥72): 优秀照片，约包20-25%
        - 2星 (≥66): 中等照片，约包30-40% (大部分照片)
        - 1星 (≥58): 较低质量，约包15-20%
        - 0星 (<58): 质量最低，但保留，约包10-15%

        标签策略：
        - 不使用 rejected 标记（所有照片都保留）
        - 不使用 picked 标签和颜色标签
        - 5星保留给用户手动评级
        """
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
            return 0, "", ""  # 0星：质量最低，但不删除

    def warmup(self):
        """预热模型"""
        if self.model is None:
            self.load_model()


# 全局阈值配置
_thresholds = (78.0, 72.0, 66.0, 58.0)  # (4星, 3星, 2星, 1星)

# 全局单例
_scorer_instance = None


def set_thresholds(t4: float, t3: float, t2: float, t1: float):
    """
    设置自定义星级阈值
    
    Args:
        t4: 4星阈值 (≥t4 为4星)
        t3: 3星阈值 (≥t3 为3星)
        t2: 2星阈值 (≥t2 为2星)
        t1: 1星阈值 (≥t1 为1星，<t1 为0星)
    """
    global _thresholds
    _thresholds = (t4, t3, t2, t1)


def get_one_align_scorer(
    model_path: Optional[str] = None,
    quality_weight: float = 0.4,
    aesthetic_weight: float = 0.6,
) -> OneAlignScorer:
    """获取评分器单例"""
    global _scorer_instance

    if _scorer_instance is None:
        _scorer_instance = OneAlignScorer(
            model_path=model_path,
            quality_weight=quality_weight,
            aesthetic_weight=aesthetic_weight,
        )

    return _scorer_instance


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python one_align_scorer.py <图片路径>")
        sys.exit(1)

    scorer = get_one_align_scorer()
    result = scorer.score_image(sys.argv[1])

    print(f"\n{'=' * 50}")
    print("评分结果")
    print(f"{'=' * 50}")
    print(f"质量分: {result['quality']:.2f}")
    print(f"美学分: {result['aesthetic']:.2f}")
    print(f"综合分: {result['total']:.2f}")
    print(f"星级: {'⭐' * result['rating']} ({result['rating']}星)")
    print(f"旗标: {result['pick_flag'] or '-'}")
    print(f"色标: {result['color_label'] or '-'}")
