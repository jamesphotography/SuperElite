#!/usr/bin/env python3
"""
对比 Q-SiT-mini 和 One-Align 的评分排序
"""

import csv
import os
from scipy.stats import spearmanr, pearsonr, kendalltau
import numpy as np

def load_csv(path):
    """加载 CSV 结果"""
    results = {}
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            filepath = row.get('file', '')
            if filepath and row.get('error', '') == '':
                # 统一使用文件名作为 key
                filename = os.path.basename(filepath)
                results[filename] = {
                    'quality': float(row.get('quality', 0)),
                    'aesthetic': float(row.get('aesthetic', 0)),
                    'total': float(row.get('total', 0)),
                }
    return results


def main():
    data_dir = "/Users/jameszhenyu/Desktop/NEWTEST_preprocessed_1024"
    
    # 加载两个模型的结果
    qsit_path = os.path.join(data_dir, "qsit_mini_results.csv")
    onealign_path = os.path.join(data_dir, "results.csv")  # 之前的 One-Align 结果
    
    print(f"\n📁 加载结果文件...")
    print(f"   Q-SiT-mini: {qsit_path}")
    print(f"   One-Align:  {onealign_path}")
    
    if not os.path.exists(qsit_path):
        print(f"❌ 未找到 Q-SiT-mini 结果文件")
        return
    
    if not os.path.exists(onealign_path):
        print(f"❌ 未找到 One-Align 结果文件")
        return
    
    qsit_results = load_csv(qsit_path)
    onealign_results = load_csv(onealign_path)
    
    print(f"   Q-SiT-mini: {len(qsit_results)} 张")
    print(f"   One-Align:  {len(onealign_results)} 张")
    
    # 找到共同的文件
    common_files = set(qsit_results.keys()) & set(onealign_results.keys())
    print(f"   共同文件: {len(common_files)} 张")
    
    if len(common_files) < 10:
        print("❌ 共同文件太少，无法比较")
        return
    
    # 收集配对数据
    qsit_scores = []
    onealign_scores = []
    file_list = sorted(common_files)
    
    for f in file_list:
        qsit_scores.append(qsit_results[f]['total'])
        onealign_scores.append(onealign_results[f]['total'])
    
    qsit_scores = np.array(qsit_scores)
    onealign_scores = np.array(onealign_scores)
    
    # 计算排序
    qsit_ranks = np.argsort(np.argsort(-qsit_scores)) + 1  # 降序排名
    onealign_ranks = np.argsort(np.argsort(-onealign_scores)) + 1
    
    # 计算相关性
    print("\n" + "=" * 70)
    print("📊 分数相关性分析")
    print("=" * 70)
    
    spearman_corr, spearman_p = spearmanr(qsit_scores, onealign_scores)
    pearson_corr, pearson_p = pearsonr(qsit_scores, onealign_scores)
    kendall_corr, kendall_p = kendalltau(qsit_scores, onealign_scores)
    
    print(f"\n  Spearman 相关系数 (排序): {spearman_corr:.4f} (p={spearman_p:.2e})")
    print(f"  Pearson 相关系数 (分数):  {pearson_corr:.4f} (p={pearson_p:.2e})")
    print(f"  Kendall Tau (排序):      {kendall_corr:.4f} (p={kendall_p:.2e})")
    
    # 分数差异统计
    score_diff = qsit_scores - onealign_scores
    rank_diff = np.abs(qsit_ranks - onealign_ranks)
    
    print(f"\n📈 分数差异统计:")
    print(f"  平均差异: {np.mean(score_diff):.2f}")
    print(f"  差异标准差: {np.std(score_diff):.2f}")
    print(f"  最大正差: {np.max(score_diff):.2f}")
    print(f"  最大负差: {np.min(score_diff):.2f}")
    
    print(f"\n📈 排名差异统计:")
    print(f"  平均排名差异: {np.mean(rank_diff):.1f} 位")
    print(f"  排名差异 ≤5: {np.sum(rank_diff <= 5)}/{len(rank_diff)}")
    print(f"  排名差异 ≤10: {np.sum(rank_diff <= 10)}/{len(rank_diff)}")
    print(f"  排名差异 >20: {np.sum(rank_diff > 20)}/{len(rank_diff)}")
    
    # Top-10 对比
    print("\n" + "=" * 70)
    print("🏆 Top-10 对比")
    print("=" * 70)
    
    qsit_top10_idx = np.argsort(-qsit_scores)[:10]
    onealign_top10_idx = np.argsort(-onealign_scores)[:10]
    
    qsit_top10_files = set(file_list[i] for i in qsit_top10_idx)
    onealign_top10_files = set(file_list[i] for i in onealign_top10_idx)
    
    common_top10 = qsit_top10_files & onealign_top10_files
    
    print(f"\n  Q-SiT-mini Top-10 与 One-Align Top-10 重叠: {len(common_top10)}/10")
    
    print(f"\n  Q-SiT-mini Top-10:")
    for i, idx in enumerate(qsit_top10_idx):
        f = file_list[idx]
        oa_rank = int(onealign_ranks[idx])
        print(f"    {i+1:2d}. {f[:40]:<40} | Q-SiT: {qsit_scores[idx]:.1f} | OA排名: {oa_rank}")
    
    print(f"\n  One-Align Top-10:")
    for i, idx in enumerate(onealign_top10_idx):
        f = file_list[idx]
        qs_rank = int(qsit_ranks[idx])
        print(f"    {i+1:2d}. {f[:40]:<40} | OA: {onealign_scores[idx]:.1f} | Q-SiT排名: {qs_rank}")
    
    # Bottom-10 对比
    print("\n" + "=" * 70)
    print("📉 Bottom-10 对比")
    print("=" * 70)
    
    qsit_bottom10_idx = np.argsort(qsit_scores)[:10]
    onealign_bottom10_idx = np.argsort(onealign_scores)[:10]
    
    qsit_bottom10_files = set(file_list[i] for i in qsit_bottom10_idx)
    onealign_bottom10_files = set(file_list[i] for i in onealign_bottom10_idx)
    
    common_bottom10 = qsit_bottom10_files & onealign_bottom10_files
    
    print(f"\n  Q-SiT-mini Bottom-10 与 One-Align Bottom-10 重叠: {len(common_bottom10)}/10")
    
    # 最大差异案例
    print("\n" + "=" * 70)
    print("⚠️  最大差异案例 (排名差 > 30)")
    print("=" * 70)
    
    large_diff_idx = np.where(rank_diff > 30)[0]
    if len(large_diff_idx) > 0:
        for idx in large_diff_idx[:10]:  # 最多显示 10 个
            f = file_list[idx]
            print(f"\n  {f}")
            print(f"    Q-SiT:    分数={qsit_scores[idx]:.1f}, 排名={int(qsit_ranks[idx])}")
            print(f"    One-Align: 分数={onealign_scores[idx]:.1f}, 排名={int(onealign_ranks[idx])}")
            print(f"    排名差异: {int(rank_diff[idx])} 位")
    else:
        print("\n  没有排名差异超过 30 的案例 ✅")
    
    # 总结
    print("\n" + "=" * 70)
    print("📋 总结")
    print("=" * 70)
    
    if spearman_corr > 0.9:
        verdict = "✅ 高度一致 - 可以作为替代"
    elif spearman_corr > 0.7:
        verdict = "⚠️  中等一致 - 需要进一步评估"
    else:
        verdict = "❌ 一致性较低 - 不建议替代"
    
    print(f"\n  Spearman 相关系数: {spearman_corr:.4f}")
    print(f"  结论: {verdict}")


if __name__ == "__main__":
    main()
