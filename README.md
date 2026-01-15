# SuperElite

> 🎯 AI 风光摄影智能选片工具 - 基于 One-Align 双维度评分

## 功能特点

- **双维度评分**: 质量 (40%) + 美学 (60%)
- **智能分级**: 0-4 星 + Pick Flag + Color Label
- **Lightroom 集成**: XMP Sidecar + 分目录输出
- **批量处理**: 支持 RAW + JPEG，实时进度显示

## 安装

```bash
cd SuperElite/backend
pip install -r requirements.txt
brew install exiftool  # macOS
```

## 使用

```bash
# 基础用法
python main.py --dir ~/Photos/RAW --write-xmp

# 高级用法
python main.py \
    --dir ~/Photos/RAW \
    --output ~/Photos/Scored \
    --organize \
    --write-xmp \
    --csv results.csv
```

## 评分规则

| 总分 | 星级 | 旗标 | 色标 |
|------|------|------|------|
| ≥70 | 4星 | Picked ✓ | Green |
| 60-69 | 3星 | Picked ✓ | Yellow |
| 50-59 | 2星 | - | - |
| 40-49 | 1星 | - | Red |
| <40 | 0星 | Rejected ✗ | Purple |

## 系统要求

- macOS (Apple Silicon M1/M2/M3/M4)
- Python 3.10+
- 16GB+ 内存 (推荐 32GB+)

## 许可

MIT License
