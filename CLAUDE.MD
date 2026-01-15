# SuperElite - AI 风光摄影智能选片工具

> 基于 One-Align 的双维度评分 (质量 + 美学)

## 项目状态

**最后更新**: 2026-01-15  
**模型选型**: One-Align (确认通过 100 张图片对比测试)  
**开发阶段**: CLI 功能完善

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 评分模型 | One-Align (`q-future/one-align`) ~15GB |
| 运行环境 | Python 3.10+ / PyTorch / MPS |
| 硬件要求 | Apple Silicon Mac Only |
| 元数据工具 | ExifTool |

---

## 目录结构

```
SuperElite/
├── backend/
│   ├── main.py              # CLI 主程序
│   ├── one_align_scorer.py  # One-Align 评分器
│   ├── exif_writer.py       # EXIF/XMP 写入
│   ├── raw_converter.py     # RAW 预览提取
│   ├── reset_metadata.py    # 重置元数据
│   └── requirements.txt
├── .venv/                   # Python 虚拟环境
├── models/                  # 模型目录 (暂未使用)
└── CLAUDE.MD               # 本文档
```

---

## 已实现功能

| 功能 | 参数 | 状态 |
|------|------|:----:|
| 目录扫描 | `--dir <路径>` | ✅ |
| 交互模式 | (无参数) | ✅ |
| 双维度评分 | Quality + Aesthetic | ✅ |
| 权重配置 | `--quality-weight / --aesthetic-weight` | ✅ |
| XMP 写入 | `--write-xmp` | ✅ |
| 星级分类 | `--organize --output <目录>` | ✅ |
| CSV 导出 | `--csv <文件>` | ✅ |
| 硬件检测 | `--check-hardware` | ✅ |
| RAW 支持 | ARW/CR2/CR3/NEF/DNG 等 | ✅ |

---

## 待开发功能

### 必须实现
- [ ] `--version` - 显示版本号
- [ ] `--thresholds "78,72,66,58"` - 自定义星级阈值

### 待评估
- [ ] `--workers N` - 多线程并行 (需测试效果)

### 后续
- [ ] 进度保存/中断恢复
- [ ] GUI 启动器

---

## 星级阈值 (当前默认)

| 星级 | 阈值 | 说明 |
|:----:|:----:|------|
| 4★ | ≥78 | 顶级照片 (~10-15%) |
| 3★ | ≥72 | 优秀照片 (~20-25%) |
| 2★ | ≥66 | 中等照片 (~30-40%) |
| 1★ | ≥58 | 较差照片 (~15-20%) |
| 0★ | <58 | 质量不佳，标记 rejected |

---

## 使用方法

```bash
cd /Users/jameszhenyu/Documents/JamesAPPS/SuperNima/SuperElite/backend
source ../.venv/bin/activate

# 交互模式
python main.py

# 完整参数
python main.py --dir /path/to/photos \
               --write-xmp \
               --organize --output /path/to/output \
               --csv results.csv

# 硬件检测
python main.py --check-hardware
```

---

## 测试记录

### 2026-01-15 模型对比测试
- 对比 One-Align vs NIMA+TOPIQ
- 测试集: 100 张风光摄影
- 结论: One-Align 更符合人工评价，确认选型
- 结果文件: `~/Desktop/comparison_merged.csv`

---

## 归档说明

`/SuperNima/_archived/` 包含旧代码:
- JamesAlign (旧 Lightroom 插件方案)
- NIMA.mlpackage (旧模型)
- JamesElite-App (旧 Swift 应用)

这些已不再使用，可安全删除。
