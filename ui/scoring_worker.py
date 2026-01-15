# -*- coding: utf-8 -*-
"""
SuperElite - 后台评分工作线程
使用 QThread 在后台执行评分任务，不阻塞 UI
"""

import sys
import os
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from PySide6.QtCore import QThread, Signal, QObject

# 添加 backend 到路径
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

from one_align_scorer import get_one_align_scorer, set_thresholds
from exif_writer import get_exif_writer
from raw_converter import is_raw_file, raw_to_jpeg
from preset_manager import get_preset_manager


class ScoringWorker(QThread):
    """
    后台评分工作线程
    
    Signals:
        started_loading: 开始加载模型
        model_loaded: 模型加载完成
        progress: 进度更新 (current, total, filename, score, rating)
        log_message: 日志消息 (level, message)
        finished_scoring: 评分完成 (results, summary)
        error: 发生错误 (error_message)
    """
    
    # 信号定义
    started_loading = Signal()
    model_loaded = Signal()
    progress = Signal(int, int, str, float, int)  # current, total, filename, score, rating
    log_message = Signal(str, str)  # level, message
    finished_scoring = Signal(list, dict)  # results, summary
    request_threshold_confirmation = Signal(tuple, dict, dict)  # suggested_thresholds, counts, stats
    error = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 配置参数
        self.input_dir: Optional[str] = None
        self.thresholds: Tuple[float, float, float, float] = (78.0, 72.0, 66.0, 58.0)
        self.quality_weight: float = 0.4
        self.aesthetic_weight: float = 0.6
        self.write_xmp: bool = True
        self.organize: bool = False
        self.output_dir: Optional[str] = None
        self.csv_path: Optional[str] = None
        
        # 状态
        self._should_stop = False
        self._scorer = None
        self._exif_writer = None
        self.auto_calibrate = False
        self.confirmed_thresholds = None
    
    def set_confirmed_thresholds(self, thresholds):
        """设置用户确认的阈值"""
        self.confirmed_thresholds = thresholds
    
    def configure(
        self,
        input_dir: str,
        thresholds: Tuple[float, float, float, float] = (78.0, 72.0, 66.0, 58.0),
        quality_weight: float = 0.4,
        aesthetic_weight: float = 0.6,
        write_xmp: bool = True,
        organize: bool = False,
        output_dir: Optional[str] = None,
        csv_path: Optional[str] = None,
        auto_calibrate: bool = False,
    ):
        """配置评分参数"""
        self.input_dir = input_dir
        self.thresholds = thresholds
        self.quality_weight = quality_weight
        self.aesthetic_weight = aesthetic_weight
        self.write_xmp = write_xmp
        self.organize = organize
        self.output_dir = output_dir
        self.csv_path = csv_path
        self.auto_calibrate = auto_calibrate
        self.confirmed_thresholds = None  # 用户确认的阈值
    
    def stop(self):
        """请求停止处理"""
        self._should_stop = True
    
    def run(self):
        """线程主函数"""
        try:
            self._should_stop = False
            
            # 1. 扫描目录
            self.log_message.emit("info", f"📁 扫描目录: {self.input_dir}")
            image_paths = self._scan_directory(self.input_dir)
            
            if not image_paths:
                self.error.emit("未找到图片文件")
                return
            
            self.log_message.emit("info", f"   找到 {len(image_paths)} 张图片")
            
            # 2. 获取模型 (已在启动时预加载)
            self.started_loading.emit()
            
            set_thresholds(*self.thresholds)
            self._scorer = get_one_align_scorer(
                quality_weight=self.quality_weight,
                aesthetic_weight=self.aesthetic_weight,
            )
            # 单例模式，模型在启动时已预加载和预热，这里直接使用
            self._exif_writer = get_exif_writer()
            
            self.model_loaded.emit()
            self.log_message.emit("info", "✅ AI 模型就绪")
            
            # 3. 处理图片
            results = []
            start_time = time.time()
            
            for i, image_path in enumerate(image_paths):
                if self._should_stop:
                    self.log_message.emit("warning", "⚠️ 用户取消处理")
                    break
                
                filename = os.path.basename(image_path)
                
                try:
                    result = self._process_single_image(image_path)
                    results.append(result)
                    
                    # 发送进度
                    self.progress.emit(
                        i + 1,
                        len(image_paths),
                        filename,
                        result.get("total", 0),
                        result.get("rating", 0)
                    )
                    
                except Exception as e:
                    self.log_message.emit("error", f"❌ {filename}: {str(e)}")
                    results.append({
                        "path": image_path,
                        "filename": filename,
                        "error": str(e)
                    })
            
            # 4. 自动校准阈值 (如果启用)
            if self.auto_calibrate and not self._should_stop:
                self.log_message.emit("info", "🤖 正在计算自适应阈值...")
                calibrated_thresholds = self._calculate_percentile_thresholds(results)
                
                if calibrated_thresholds:
                    # 更新阈值
                    self.thresholds = calibrated_thresholds
                    set_thresholds(*calibrated_thresholds)
                    
                    # 重新映射星级 - 直接使用本地逻辑避免模块导入问题
                    self.log_message.emit("info", "🔄 重新映射星级...")
                    t4, t3, t2, t1 = calibrated_thresholds
                    for result in results:
                        if "error" not in result:
                            score = result["total"]
                            if score >= t4:
                                rating = 4
                            elif score >= t3:
                                rating = 3
                            elif score >= t2:
                                rating = 2
                            elif score >= t1:
                                rating = 1
                            else:
                                rating = 0
                            result["rating"] = rating
                    
                    self.log_message.emit("success", f"✅ 自适应阈值: {t4:.1f} / {t3:.1f} / {t2:.1f} / {t1:.1f}")
            
            # 5. 写入 XMP (如果启用)
            if self.write_xmp and not self._should_stop:
                self.log_message.emit("info", "📝 写入 XMP 元数据...")
                self._write_xmp_metadata(results)
            
            # 6. 整理目录 (如果启用)
            if self.organize and self.output_dir and not self._should_stop:
                self.log_message.emit("info", f"📂 整理文件到 {self.output_dir}")
                self._organize_by_rating(results)
            
            # 7. 导出 CSV (如果指定)
            if self.csv_path and not self._should_stop:
                self.log_message.emit("info", f"📊 导出 CSV: {self.csv_path}")
                self._export_csv(results)
            
            # 8. 保存 manifest 文件
            if not self._should_stop:
                self._save_manifest(results)
            
            # 9. 计算统计
            elapsed_time = time.time() - start_time
            summary = self._calculate_summary(results, elapsed_time)
            
            self.log_message.emit("success", f"✅ 完成! 耗时 {elapsed_time:.1f}s")
            self.finished_scoring.emit(results, summary)
            
        except Exception as e:
            self.error.emit(str(e))
    
    def _scan_directory(self, directory: str) -> List[str]:
        """扫描目录下的图片文件"""
        supported_extensions = {
            ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp",
            ".arw", ".cr2", ".cr3", ".nef", ".dng", ".orf", ".rw2", ".raf"
        }
        
        image_paths = []
        dir_path = Path(directory)
        
        for f in dir_path.iterdir():
            if f.is_file() and f.suffix.lower() in supported_extensions:
                image_paths.append(str(f))
        
        return sorted(image_paths)
    
    def _process_single_image(self, image_path: str) -> Dict:
        """处理单张图片"""
        filename = os.path.basename(image_path)
        temp_file = None
        
        try:
            # 处理 RAW 文件 - 需要先提取预览
            if is_raw_file(image_path):
                temp_file = raw_to_jpeg(image_path)
                if temp_file:
                    score_path = temp_file
                else:
                    raise Exception("无法提取 RAW 预览")
            else:
                score_path = image_path
            
            # 评分 - 使用正确的方法 score_image(path)
            score_result = self._scorer.score_image(score_path)
            
            return {
                "path": image_path,
                "filename": filename,
                "quality": score_result.get("quality", 0),
                "aesthetic": score_result.get("aesthetic", 0),
                "total": score_result.get("total", 0),
                "rating": score_result.get("rating", 0),
            }
            
        finally:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
    
    def _write_xmp_metadata(self, results: List[Dict]):
        """写入 XMP 元数据（包含质量分/美学分/总分）"""
        for result in results:
            if "error" in result:
                continue
            
            try:
                # 使用新方法写入完整评分
                # 质量分→城市, 美学分→省份, 总分→国家, 星级→Rating
                self._exif_writer.write_full_scoring_metadata(
                    result["path"],
                    quality_score=result.get("quality", 0),
                    aesthetic_score=result.get("aesthetic", 0),
                    total_score=result.get("total", 0),
                    rating=result.get("rating", 0)
                )
            except Exception as e:
                self.log_message.emit("warning", f"XMP 写入失败: {result['filename']}")
    
    def _organize_by_rating(self, results: List[Dict]):
        """按星级整理文件到原目录内的子目录"""
        import shutil
        
        output_path = Path(self.output_dir)
        moved_count = 0
        
        for result in results:
            if "error" in result:
                continue
            
            rating = result.get("rating", 0)
            star_dir = output_path / f"{rating}星"
            star_dir.mkdir(parents=True, exist_ok=True)
            
            src = Path(result["path"])
            dst = star_dir / src.name
            
            # 移动文件（不是复制）
            if src.exists() and src != dst:
                shutil.move(str(src), str(dst))
                result["organized_path"] = str(dst)
                moved_count += 1
        
        self.log_message.emit("info", f"   移动了 {moved_count} 个文件到星级子目录")
    
    def _export_csv(self, results: List[Dict]):
        """导出 CSV 报告"""
        import csv
        
        with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["文件名", "路径", "质量分", "美学分", "综合分", "星级"])
            
            for r in results:
                if "error" not in r:
                    writer.writerow([
                        r["filename"],
                        r["path"],
                        f"{r['quality']:.1f}",
                        f"{r['aesthetic']:.1f}",
                        f"{r['total']:.1f}",
                        r["rating"]
                    ])
    
    def _save_manifest(self, results: List[Dict]):
        """保存 manifest 文件到源目录"""
        import json
        from datetime import datetime
        
        manifest_path = Path(self.input_dir) / ".superelite_manifest.json"
        
        # 构建 manifest 数据
        manifest = {
            "version": "1.0",
            "app": "SuperElite",
            "created": datetime.now().isoformat(),
            "source_dir": self.input_dir,
            "settings": {
                "preset": "auto" if self.auto_calibrate else "custom",
                "thresholds": list(self.thresholds),
                "quality_weight": self.quality_weight,
                "aesthetic_weight": self.aesthetic_weight,
            },
            "statistics": {
                "total": len(results),
                "success": sum(1 for r in results if "error" not in r),
                "by_rating": {}
            },
            "files": []
        }
        
        # 统计星级分布
        for r in results:
            if "error" not in r:
                rating = r.get("rating", 0)
                manifest["statistics"]["by_rating"][str(rating)] = \
                    manifest["statistics"]["by_rating"].get(str(rating), 0) + 1
        
        # 记录每个文件
        for r in results:
            if "error" not in r:
                file_info = {
                    "filename": r["filename"],
                    "original_path": r["path"],
                    "organized_path": r.get("organized_path"),
                    "scores": {
                        "quality": round(r.get("quality", 0), 1),
                        "aesthetic": round(r.get("aesthetic", 0), 1),
                        "total": round(r.get("total", 0), 1),
                    },
                    "rating": r.get("rating", 0)
                }
                manifest["files"].append(file_info)
        
        # 写入文件
        try:
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            self.log_message.emit("info", f"📋 已保存 manifest: {manifest_path.name}")
        except Exception as e:
            self.log_message.emit("warning", f"Manifest 保存失败: {e}")
    
    
    def _calculate_percentile_thresholds(self, results: List[Dict]) -> Optional[Tuple[float, float, float, float]]:
        """计算百分位阈值 (20% 均分)
        
        Args:
            results: 评分结果列表
        
        Returns:
            (t4, t3, t2, t1) 阈值元组
        """
        import numpy as np
        
        # 提取有效分数
        scores = [r["total"] for r in results if "error" not in r and "total" in r]
        
        if not scores or len(scores) < 5:
            self.log_message.emit("warning", "⚠️ 图片数量太少，使用默认阈值")
            return None
        
        sorted_scores = np.array(sorted(scores))
        
        # 计算百分位点
        t4 = float(np.percentile(sorted_scores, 80))  # P80: 前 20% 为 4星
        t3 = float(np.percentile(sorted_scores, 60))  # P60: 20-40% 为 3星
        t2 = float(np.percentile(sorted_scores, 40))  # P40: 40-60% 为 2星
        t1 = float(np.percentile(sorted_scores, 20))  # P20: 60-80% 为 1星, <P20 为 0星
        
        return (round(t4, 1), round(t3, 1), round(t2, 1), round(t1, 1))
    
    def _calculate_summary(self, results: List[Dict], elapsed_time: float) -> Dict:
        """计算统计摘要"""
        success_results = [r for r in results if "error" not in r]
        
        # 按星级统计
        by_rating = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
        scores = []
        
        for r in success_results:
            rating = r.get("rating", 1)
            by_rating[rating] = by_rating.get(rating, 0) + 1
            scores.append(r.get("total", 0))
        
        return {
            "total": len(results),
            "success": len(success_results),
            "failed": len(results) - len(success_results),
            "by_rating": by_rating,
            "avg_score": sum(scores) / len(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "elapsed_time": elapsed_time,
            "speed": elapsed_time / len(results) if results else 0,
        }
