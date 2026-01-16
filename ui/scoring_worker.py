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

from exif_writer import get_exif_writer
from raw_converter import is_raw_file, raw_to_jpeg, find_paired_jpg
from preset_manager import get_preset_manager
from manifest_manager import ManifestManager, MANIFEST_FILENAME


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
    calibration_completed = Signal(tuple)  # calibrated_thresholds - 自动校准完成后发送
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
        self._manifest = None  # ManifestManager 实例
        self.auto_calibrate = False
        self.confirmed_thresholds = None
        self.model_mode = "basic"  # 新增：模型模式 "basic" 或 "advanced"
    
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
        model_mode: str = "basic",  # 新增："basic" 或 "advanced"
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
        self.model_mode = model_mode  # 新增：模型模式
    
    def stop(self):
        """请求停止处理"""
        self._should_stop = True
    
    def run(self):
        """线程主函数"""
        try:
            self._should_stop = False
            
            # 显示任务开始
            self.log_message.emit("info", "━" * 45)
            self.log_message.emit("info", "🎯 开始 AI 评分任务")
            self.log_message.emit("info", "━" * 45)
            
            # 步骤 1: 扫描目录
            self.log_message.emit("info", "")
            self.log_message.emit("info", "📁 [步骤 1/4] 扫描目录...")
            self.log_message.emit("info", f"   目录: {self.input_dir}")
            all_image_paths = self._scan_directory(self.input_dir)
            
            if not all_image_paths:
                self.error.emit("未找到图片文件")
                return
            
            self.log_message.emit("success", f"   ✓ 找到 {len(all_image_paths)} 张图片")
            
            # 步骤 2: 检查处理状态
            self.log_message.emit("info", "")
            self.log_message.emit("info", "📋 [步骤 2/4] 检查处理状态...")
            
            self._manifest = ManifestManager(self.input_dir)
            self._manifest.set_config(
                self.thresholds,
                self.quality_weight,
                self.aesthetic_weight,
            )
            self._manifest.set_total_files(len(all_image_paths))
            
            # 过滤出待处理文件（跳过已处理且未修改的）
            image_paths = self._manifest.get_pending_files(all_image_paths)
            skipped_count = len(all_image_paths) - len(image_paths)
            
            if skipped_count > 0:
                self.log_message.emit("info", f"   ○ 跳过已处理: {skipped_count} 张")
            
            if not image_paths:
                self.log_message.emit("success", "")
                self.log_message.emit("success", "✅ 所有文件已处理完成，无需重新评分")
                # 返回已有结果
                summary = self._manifest.get_summary()
                self.finished_scoring.emit([], summary)
                return
            
            self.log_message.emit("success", f"   ✓ 待处理: {len(image_paths)} 张")
            
            # 标记开始处理
            self._manifest.start_processing()
            
            # 步骤 3: 加载 AI 模型
            self.log_message.emit("info", "")
            if self.model_mode == "advanced":
                self.log_message.emit("info", "[步骤 3/4] 加载 詹姆斯水平 评分模型...")
            else:
                self.log_message.emit("info", "[步骤 3/4] 加载 爱好者水平 评分模型...")
            self.started_loading.emit()

            
            # 根据模式选择评分器
            if self.model_mode == "advanced":
                # 高级模式：使用 One-Align
                from one_align_scorer import get_one_align_scorer, set_thresholds
                set_thresholds(*self.thresholds)
                self._scorer = get_one_align_scorer(
                    quality_weight=self.quality_weight,
                    aesthetic_weight=self.aesthetic_weight,
                )
            else:
                # 基础模式：使用 NIMA + TOPIQ
                from pyiqa_scorer import get_pyiqa_scorer, set_thresholds
                set_thresholds(*self.thresholds)
                self._scorer = get_pyiqa_scorer(
                    quality_weight=self.quality_weight,
                    aesthetic_weight=self.aesthetic_weight,
                )
            
            self._exif_writer = get_exif_writer()
            
            self.model_loaded.emit()
            self.log_message.emit("success", "   ✓ AI 模型就绪")

            
            # 步骤 4: 开始评分
            self.log_message.emit("info", "")
            self.log_message.emit("info", "⭐ [步骤 4/4] AI 评分中...")
            self.log_message.emit("info", f"   阈值: {self.thresholds[0]:.0f} / {self.thresholds[1]:.0f} / {self.thresholds[2]:.0f} / {self.thresholds[3]:.0f}")
            self.log_message.emit("info", "")
            
            # 4. 处理图片
            results = []
            start_time = time.time()
            total_to_process = len(image_paths)
            
            for i, image_path in enumerate(image_paths):
                if self._should_stop:
                    self.log_message.emit("warning", "⚠️ 用户取消处理")
                    # 中断时保存当前进度
                    self._manifest.save()
                    break
                
                filename = os.path.basename(image_path)
                
                try:
                    result = self._process_single_image(image_path)
                    results.append(result)
                    
                    # 更新 manifest
                    self._manifest.add_file_result(
                        filename=filename,
                        file_path=image_path,
                        quality=result.get("quality", 0),
                        aesthetic=result.get("aesthetic", 0),
                        total=result.get("total", 0),
                        rating=result.get("rating", 0),
                    )
                    
                    # 每处理 10 个文件保存一次 manifest（防止中断丢失）
                    if (i + 1) % 10 == 0:
                        self._manifest.save()
                    
                    # 计算时间估算
                    elapsed = time.time() - start_time
                    avg_time = elapsed / (i + 1)
                    remaining = avg_time * (total_to_process - i - 1)
                    
                    # 格式化剩余时间
                    if remaining >= 60:
                        remaining_str = f"{int(remaining // 60)}分{int(remaining % 60)}秒"
                    else:
                        remaining_str = f"{int(remaining)}秒"
                    
                    # 显示分数和星级
                    quality = result.get("quality", 0)
                    aesthetic = result.get("aesthetic", 0)
                    total = result.get("total", 0)
                    rating = result.get("rating", 0)
                    stars = "★" * rating + "☆" * (4 - rating)
                    
                    # 截短文件名
                    short_name = filename[:28] + "..." if len(filename) > 31 else filename
                    
                    self.log_message.emit(
                        "default",
                        f"   [{i+1:3d}/{total_to_process}] {short_name:<31} "
                        f"Q:{quality:.0f} A:{aesthetic:.0f} → {stars}  剩余: {remaining_str}"
                    )
                    
                    # 发送进度
                    self.progress.emit(
                        i + 1,
                        total_to_process,
                        filename,
                        total,
                        rating
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
                    # 发送信号保存到用户自定义
                    self.calibration_completed.emit(calibrated_thresholds)
            
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
            
            # 显示完成摘要
            self.log_message.emit("info", "")
            self.log_message.emit("info", "━" * 45)
            self.log_message.emit("success", "✅ AI 评分完成!")
            self.log_message.emit("info", "━" * 45)
            
            # 统计成功和失败
            success_count = sum(1 for r in results if "error" not in r)
            error_count = sum(1 for r in results if "error" in r)
            
            self.log_message.emit("info", f"   成功: {success_count} 张")
            if error_count > 0:
                self.log_message.emit("warning", f"   失败: {error_count} 张")
            
            if elapsed_time >= 60:
                time_str = f"{int(elapsed_time // 60)}分{int(elapsed_time % 60)}秒"
            else:
                time_str = f"{elapsed_time:.1f}秒"
            
            if success_count > 0:
                self.log_message.emit("info", f"   总耗时: {time_str} ({elapsed_time/success_count:.2f}秒/张)")
            else:
                self.log_message.emit("info", f"   总耗时: {time_str}")
            
            self.log_message.emit("info", f"   已保存 manifest: .superelite_manifest.json")
            
            # 如果有错误，显示错误汇总
            if error_count > 0:
                self.log_message.emit("info", "")
                self.log_message.emit("warning", f"⚠️ 失败文件汇总 ({error_count} 个):")
                # 只显示前 10 个
                error_files = [r for r in results if "error" in r][:10]
                for r in error_files:
                    short_err = r["error"][:50] + "..." if len(r["error"]) > 50 else r["error"]
                    self.log_message.emit("error", f"   • {r['filename']}: {short_err}")
                if error_count > 10:
                    self.log_message.emit("warning", f"   ... 还有 {error_count - 10} 个文件失败")
            
            self.finished_scoring.emit(results, summary)
            
        except Exception as e:
            self.error.emit(str(e))
    
    def _scan_directory(self, directory: str) -> List[str]:
        """
        扫描目录下的图片文件（只扫描顶层目录，不进入子目录）
        
        注意：
        1. 只扫描用户选择目录的顶层文件
        2. 不进入用户原有的子目录（保护用户文件结构）
        3. 如果 RAW 和 JPG 同名存在，只返回 RAW（处理时会自动使用 JPG 评分）
        """
        supported_extensions = {
            # 常见图片格式
            ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp",
            # 主流相机 RAW 格式
            ".arw", ".cr2", ".cr3", ".nef", ".dng", ".orf", ".rw2", ".raf",
            # 小众相机 RAW 格式
            ".3fr", ".iiq", ".rwl", ".srw", ".x3f", ".pef", ".erf", ".kdc", ".dcr", ".mrw", ".fff",
        }
        
        raw_extensions = {
            ".arw", ".cr2", ".cr3", ".nef", ".dng", ".orf", ".rw2", ".raf",
            ".3fr", ".iiq", ".rwl", ".srw", ".x3f", ".pef", ".erf", ".kdc", ".dcr", ".mrw", ".fff",
        }
        
        jpg_extensions = {".jpg", ".jpeg"}
        
        # 只扫描顶层目录（不递归）
        all_files = []
        dir_path = Path(directory)
        
        for f in dir_path.iterdir():  # 改为 iterdir，不递归
            # 跳过隐藏文件和目录
            if f.name.startswith("."):
                continue
            # 跳过子目录（不进入）
            if f.is_dir():
                continue
            if f.is_file() and f.suffix.lower() in supported_extensions:
                all_files.append(f)
        
        # 收集所有 RAW 文件的基名（不区分大小写）
        raw_basenames = set()
        for f in all_files:
            if f.suffix.lower() in raw_extensions:
                raw_basenames.add(f.stem.lower())
        
        # 过滤掉有配对 RAW 的 JPG
        image_paths = []
        for f in all_files:
            if f.suffix.lower() in jpg_extensions:
                if f.stem.lower() in raw_basenames:
                    # 跳过有配对 RAW 的 JPG
                    continue
            image_paths.append(str(f))
        
        return sorted(image_paths)
    
    def _process_single_image(self, image_path: str) -> Dict:
        """
        处理单张图片
        
        处理逻辑:
        1. RAW + 同名 JPG → 用 JPG 评分，EXIF 写入两者
        2. RAW 无同名 JPG → 提取内嵌预览评分
        3. 纯 JPG → 直接评分
        4. 所有图片统一缩放到长边 672px 后评分
        """
        filename = os.path.basename(image_path)
        temp_files = []  # 需要清理的临时文件
        related_files = [image_path]  # 需要写入 EXIF 的文件列表
        
        try:
            from PIL import Image
            import tempfile
            
            # 确定用于评分的源图片
            if is_raw_file(image_path):
                # 检查是否有同名 JPG
                paired_jpg = find_paired_jpg(image_path)
                if paired_jpg:
                    # 有同名 JPG：用 JPG 评分，写入两者
                    source_path = paired_jpg
                    related_files.append(paired_jpg)
                else:
                    # 无同名 JPG：提取 RAW 内嵌预览
                    extracted = raw_to_jpeg(image_path)
                    if extracted:
                        source_path = extracted
                        temp_files.append(extracted)
                    else:
                        raise Exception("无法提取 RAW 预览")
            else:
                # 非 RAW 文件（JPG/TIFF 等）
                source_path = image_path
            
            # 打开并缩放图片到长边 672px
            img = Image.open(source_path)
            img = img.convert('RGB')  # 确保 RGB 模式
            
            max_edge = 672
            width, height = img.size
            
            if width > max_edge or height > max_edge:
                # 需要缩小
                if width > height:
                    new_width = max_edge
                    new_height = int(height * max_edge / width)
                else:
                    new_height = max_edge
                    new_width = int(width * max_edge / height)
                
                img = img.resize((new_width, new_height), Image.LANCZOS)
            
            # 保存缩放后的临时文件
            base_name = os.path.splitext(os.path.basename(image_path))[0]
            temp_jpg = os.path.join(
                tempfile.gettempdir(),
                f'_superelite_resized_{base_name}.jpg'
            )
            img.save(temp_jpg, 'JPEG', quality=90)
            temp_files.append(temp_jpg)
            
            # 关闭图片释放内存
            img.close()
            
            # 用缩放后的图片评分
            score_path = temp_jpg
            score_result = self._scorer.score_image(score_path)
            
            return {
                "path": image_path,
                "filename": filename,
                "quality": score_result.get("quality", 0),
                "aesthetic": score_result.get("aesthetic", 0),
                "total": score_result.get("total", 0),
                "rating": score_result.get("rating", 0),
                "related_files": related_files,  # 用于写入 EXIF
            }
            
        finally:
            # 清理所有临时文件
            for temp_file in temp_files:
                if temp_file and os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
    
    def _write_xmp_metadata(self, results: List[Dict]):
        """写入 XMP 元数据（包含质量分/美学分/总分）到所有关联文件"""
        for result in results:
            if "error" in result:
                continue
            
            # 获取需要写入的所有文件（包括 RAW+JPG 配对）
            related_files = result.get("related_files", [result["path"]])
            
            for file_path in related_files:
                try:
                    # 使用新方法写入完整评分
                    # 质量分→城市, 美学分→省份, 总分→国家, 星级→Rating
                    self._exif_writer.write_full_scoring_metadata(
                        file_path,
                        quality_score=result.get("quality", 0),
                        aesthetic_score=result.get("aesthetic", 0),
                        total_score=result.get("total", 0),
                        rating=result.get("rating", 0)
                    )
                except Exception as e:
                    self.log_message.emit("warning", f"XMP 写入失败: {os.path.basename(file_path)}")
    
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
        """完成并保存 manifest 文件"""
        if self._manifest is None:
            return
        
        # 标记处理完成
        self._manifest.complete_processing()
        self.log_message.emit("info", f"📋 已保存 manifest: {MANIFEST_FILENAME}")
    
    
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
            "scores": scores,  # 所有成功文件的分数列表
            "avg_score": sum(scores) / len(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "elapsed_time": elapsed_time,
            "speed": elapsed_time / len(results) if results else 0,
        }
