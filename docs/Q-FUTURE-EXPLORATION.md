# Q-Future 模型探索报告

> 测试日期：2026-01-15
> 测试环境：Apple Silicon Mac (MPS)

## 📊 模型矩阵概览

| 模型 | 功能 | 大小 | 速度 | 适用场景 |
|------|------|------|------|----------|
| **one-align** | 多维度评分 | ~15GB | 1.15s/张 | 快速筛选、批量排序 |
| **co-instruct** | 对话分析 | ~13GB | 15-60s/问题 | 详细分析、对比选择 |
| **q-sit-mini** | 评分+解释 | 0.5GB | 4s/张 | ❌ 排序不一致 |
| **Compare2Score** | 对比评分 | 未测试 | - | 待探索 |

---

## ✅ One-Align 深度探索

### 核心发现

`score()` 方法的 `task_` 参数可以接受**任意字符串**，不仅限于 `quality` 和 `aesthetics`。

### 已验证可用的 25 个维度

#### 核心指标
- `quality` - 质量
- `aesthetics` - 美学

#### 技术指标
- `sharpness` - 锐度
- `noise level` - 噪点等级
- `exposure` - 曝光
- `dynamic range` - 动态范围
- `focus` - 对焦
- `clarity` - 清晰度

#### 构图指标
- `composition` - 构图
- `balance` - 平衡
- `framing` - 取景
- `visual flow` - 视觉流动

#### 光线与色彩
- `lighting` - 光线
- `contrast` - 对比度
- `color` - 色彩
- `color harmony` - 色彩和谐
- `saturation` - 饱和度
- `white balance` - 白平衡

#### 情感指标
- `mood` - 情绪
- `atmosphere` - 氛围
- `emotional impact` - 情感冲击

#### 综合指标
- `overall appeal` - 整体吸引力
- `storytelling` - 叙事性
- `originality` - 原创性
- `professionalism` - 专业度

### 风光摄影推荐 12 维度

经过分析，推荐以下 12 个维度用于风光摄影评估：

| 类别 | 维度 |
|------|------|
| 核心 | quality, aesthetics |
| 技术 | sharpness, exposure, dynamic range, clarity |
| 构图 | composition, visual flow |
| 光线 | lighting, color harmony, contrast |
| 情感 | atmosphere |

### 12 维度测试结果

测试图片：4 张风光照（1 DNG, 2 NEF, 1 JPG）

| 图片 | 核心分 | 12维均分 | 耗时 |
|------|--------|----------|------|
| DJI 无人机 | 86.6 | 87.0 | 8.6s |
| NEF #1 | 83.7 | 84.7 | 6.8s |
| NEF #2 | 81.1 | 81.8 | 6.8s |
| 赛丽亚兰瀑布 JPG | **95.4** | **95.4** | 6.9s |

**结论**：核心分与 12 维均分高度相关，说明 quality + aesthetics 已经能很好代表整体质量。

### One-Align 限制与技术分析

#### 关于 `generate()` 方法

**这不是 bug，而是设计如此。**

One-Align 模型的源代码分析表明：

1. **模型专为评分优化**：
   - 构造了固定的评分提示词模板：`"How would you rate the {task_} of this {input_}?"`
   - 只提取最后一个 token 的 logits（对应 `excellent/good/fair/poor/bad` 5 个等级）
   - 直接计算加权分数 `[5,4,3,2,1]` 返回

2. **`generate()` 理论上存在**：
   - 因为继承自 `LlamaForCausalLM`，所以有 `generate()` 方法
   - 但 `prepare_inputs_labels_for_multimodal` 内部处理专门为 `score()` 设计
   - 调用 `generate()` 时会出现内部状态问题（NoneType 错误）

3. **官方文档确认**：
   > "The model's architecture and purpose are focused on providing scores for visual inputs."

#### 限制总结

| 功能 | 状态 | 原因 |
|------|------|------|
| 评分 (任意 task_) | ✅ 可用 | 设计目的 |
| 文本生成 | ❌ 不可用 | 非设计目的 |
| 对话/问答 | ❌ 不可用 | 无 chat() 方法 |
| 图片分类 | ❌ 不可用 | 只输出 5 级评分 |

**结论**：One-Align = 纯评分模型，接口已被完全探索。如需对话能力，必须使用 Co-Instruct（独立模型）。


## ✅ Co-Instruct 探索

### 🎯 核心价值：通用视觉问答接口

**Co-instruct 的本质是一个可以与图片对话的 AI 模型**。

只要给出正确的提示词（Prompt），就能获得相应的回答。这意味着：
- 不需要多个专用模型（分类模型、描述模型、关键字模型）
- 一个模型解决所有视觉理解需求
- 完全可定制的输出格式
- 跨平台运行（Windows/Mac/Linux）

### 📌 提示词模板

```python
# 基础模板
prompt = "USER: The image: <|image|> {你的问题} ASSISTANT:"
response = model.chat(prompt, [image], max_new_tokens=100)
```

### ✅ 实际有用的能力

以下能力已验证可用，且**无法从 EXIF 元数据获取**：

#### 1. 场景描述 (Caption)

| 语言 | 提示词 |
|------|--------|
| EN | `Describe what you see in this photograph in detail.` |
| 中文 | `请详细描述这张照片中的场景。` |

**示例输出**：
```
The image depicts a waterfall flowing through a circular rock formation, 
with lush green vegetation surrounding the scene. The overall clarity is 
excellent, with ample lighting, vibrant colors, and very clear texture details.
```

#### 2. 关键字生成 (Keywords)

| 格式 | 提示词 |
|------|--------|
| 逗号分隔 | `Generate 10 keywords that describe this photograph. List them separated by commas.` |
| 中文 | `为这张照片生成10个描述性关键词，用逗号分隔。` |

**示例输出**：
```
Waterfall, cave, green, moss, cloudy, landscape, water, flow, natural, beauty
```

**用途**：写入 XMP `Keywords` / `Subject` 字段

#### 3. 场景分类 (Classification)

| 类型 | 提示词 |
|------|--------|
| 场景 | `Classify this photograph into one category: sunset, sunrise, aurora, night/starry, waterfall, mountain, ocean/seascape, cityscape, forest, desert. Answer with one word.` |
| 拍摄类型 | `What type of photography is this: landscape, portrait, wildlife, architecture, street, macro, aerial, underwater? Answer with one word.` |

**示例输出**：
```
waterfall
landscape
```

**用途**：写入 XMP `Category` / Lightroom `Label` 字段

#### 4. 情感/氛围标签 (Mood)

| 类型 | 提示词 |
|------|--------|
| 简短 | `Describe the mood and atmosphere of this photograph in 2-3 words.` |
| 选择式 | `What emotion does this photograph evoke? Choose from: peaceful, dramatic, mysterious, joyful, melancholic, awe-inspiring, romantic, energetic.` |

**示例输出**：
```
Mysterious and serene.
awe-inspiring
```

**用途**：写入 XMP `Rating Notes` 或自定义字段

#### 5. 标题生成 (Title)

| 语言 | 提示词 |
|------|--------|
| EN | `Create a poetic title for this photograph in 3-5 words.` |
| 中文 | `为这张照片创作一个富有诗意的中文标题，3-5个字。` |

**示例输出**：
```
"Nature's Artistry: A Waterfall's Wrath"
壮丽的水瀑峡谷
```

**用途**：写入 XMP `Title` / `Headline` 字段

### ⚠️ 不需要的能力（EXIF 已有）

以下信息可从 EXIF 直接获取，无需 AI 推断：

| 信息 | EXIF 字段 |
|------|-----------|
| 拍摄设备 | `Make`, `Model` |
| 焦距 | `FocalLength`, `FocalLengthIn35mmFormat` |
| 拍摄时间 | `DateTimeOriginal` |
| 拍摄地点 | `GPSLatitude`, `GPSLongitude` (如有) |
| 曝光参数 | `ExposureTime`, `FNumber`, `ISO` |

### 📊 质量分析能力

除了元数据相关能力，Co-instruct 还擅长质量分析：

#### 单图分析

```python
# 质量问题检测
"USER: The image: <|image|> Which quality issues exist in this image? ASSISTANT:"

# 整体质量评价
"USER: The image: <|image|> Describe the overall quality of this landscape photograph. ASSISTANT:"

# 技术分析
"USER: The image: <|image|> Analyze the technical aspects: sharpness, exposure, dynamic range, color accuracy. ASSISTANT:"

# 优缺点总结
"USER: The image: <|image|> What are the strengths and weaknesses of this photograph? ASSISTANT:"
```

#### 双图对比

```python
"USER: The first image: <|image|>\nThe second image: <|image|>\nWhich image has better quality? Compare their technical quality, composition, and aesthetic appeal. ASSISTANT:"
```

#### 示例输出

**单图分析**：
```
The image has accurate exposure with no obvious overexposed or underexposed areas. 
The focus is precise, resulting in a clear image with no noticeable noise. 
The colors are rich, and there is ample lighting. 
The texture details are clear, and the composition is centered. 
The main subject, a waterfall in the middle, is clearly defined. 
Therefore, the image quality is excellent.
```

**双图对比**：
```
The first image has better quality. While both images have good clarity 
and composition, the first image has richer texture details, more vibrant 
colors, and a more interesting subject. The second image has weaker 
lighting and less vibrant colors.
```

### ⏱️ 速度统计

| 任务 | 耗时 |
|------|------|
| 单个问题（简短回答） | 2-6s |
| 单个问题（详细回答） | 15-40s |
| 双图对比 | 60-70s |
| 完整分析 (6问题/张) | ~200s/张 |

### 🔧 自定义提示词指南

你可以根据需求自定义任何提示词：

```python
# 自定义分类列表
"Classify this photo: mountain, forest, ocean, river, lake, glacier. Answer with one word."

# 限定输出格式
"List 5 keywords, one per line, in lowercase."

# 组合多个任务
"Describe this photo in one sentence, then list 5 keywords separated by commas."

# 特定领域
"What bird species can you identify in this photograph?"
"What architectural style is shown in this building?"
```

---



## ❌ Q-SiT-mini 测试结论

### 100 张照片对比测试

| 指标 | 数值 |
|------|------|
| Spearman 相关系数 | **0.28** (很低) |
| 平均排名差异 | 28.7 位 |
| Top-10 重叠 | 3/10 |

### 结论

Q-SiT-mini **不适合作为 One-Align 替代品**：
- 分数集中在 98-99 分，区分度低
- 排序与 One-Align 差异巨大
- 可能适合一般照片，但对高质量风光照片区分度不足

---

## 💡 推荐工作流

### 方案一：快速筛选模式（仅评分）

```
One-Align (quality + aesthetics) → 排序 → 输出
速度：1.15s/张
输出：XMP Rating + 评分 CSV
```

### 方案二：详细分析模式（评分 + 分类 + 关键字）

```
1. One-Align (quality + aesthetics) → 评分
2. Co-Instruct → 场景分类 + 关键字 + 描述
3. ExifTool → 写入 XMP 元数据

速度：~10-15s/张
输出：XMP Rating + Keywords + Category + Caption
```

### 方案三：完整工作流（评分 + 分类 + 分析报告）

```
1. One-Align 快速筛选 → 排序
2. Top 30% → Co-Instruct 详细分析 → 优缺点报告
3. 精选 → Co-Instruct 双图对比 → 最终选择

速度：快速筛选 1.15s/张，详细分析按需
输出：完整 XMP + Markdown 分析报告
```

---

## 🔧 模型加载代码

### One-Align

```python
from transformers import AutoModel
import torch

model = AutoModel.from_pretrained(
    "q-future/one-align",
    torch_dtype=torch.float16,
    device_map="mps",  # 或 "cuda" / "cpu"
    trust_remote_code=True,
)

# 评分
score = model.score([image], task_="quality", input_="image")
```

### Co-Instruct

```python
from transformers import AutoModelForCausalLM
import torch

model = AutoModelForCausalLM.from_pretrained(
    "q-future/co-instruct",
    trust_remote_code=True,
    torch_dtype=torch.float16,
    attn_implementation="eager",
    device_map={"": "mps"}  # 或 "cuda:0"
)

# 对话
prompt = "USER: The image: <|image|> {问题} ASSISTANT:"
response = model.chat(prompt, [image], max_new_tokens=100)
```

---

## 📁 相关测试脚本

| 脚本 | 功能 |
|------|------|
| `test_multi_task.py` | 测试 One-Align 25 个评分维度 |
| `test_12_dimensions.py` | 风光摄影 12 维度评分测试 |
| `test_qsit_mini.py` | Q-SiT-mini 评分测试 |
| `compare_models.py` | One-Align vs Q-SiT-mini 排序对比 |
| `test_coinstruct.py` | Co-Instruct 质量分析对话测试 |
| `test_coinstruct_extended.py` | Co-Instruct 扩展能力测试（场景描述、关键字、分类等） |
| `test_generate.py` | One-Align generate() 测试（已确认不可用） |

---

## 📋 关键结论总结

### One-Align

| 特性 | 结论 |
|------|------|
| 评分能力 | ✅ 优秀，25+ 维度可用 |
| 排序稳定性 | ✅ 优秀，区分度高 |
| 文本生成 | ❌ 不可用（generate 有 bug） |
| 分类能力 | ❌ 不可用 |
| 适用场景 | 快速评分、批量筛选 |

### Co-Instruct

| 特性 | 结论 |
|------|------|
| 对话能力 | ✅ 优秀，支持任意提示词 |
| 场景描述 | ✅ 优秀 |
| 关键字生成 | ✅ 优秀 |
| 场景分类 | ✅ 优秀 |
| 情感分析 | ✅ 优秀 |
| 双图对比 | ✅ 优秀 |
| 中文支持 | ✅ 可用 |
| 速度 | ⚠️ 较慢（2-60s/问题） |
| 适用场景 | 详细分析、元数据生成、精选对比 |

### Q-SiT-mini

| 特性 | 结论 |
|------|------|
| 与 One-Align 排序一致性 | ❌ 很低 (Spearman 0.28) |
| 适用场景 | ❌ 不推荐用于风光摄影 |

---

## 🚀 产品开发路线图

基于探索结论，确定两个产品方向：

### 📦 第一阶段：SuperElite GUI（独立应用）

| 项目 | 说明 |
|------|------|
| **核心模型** | One-Align |
| **主要功能** | 批量评分、自动分类、目录整理 |
| **速度目标** | ~1.15s/张 |
| **适用场景** | 拍摄归来后快速筛选数百/数千张照片 |

#### 功能规划

```
┌─────────────────────────────────────────────────────────┐
│  SuperElite GUI                                         │
├─────────────────────────────────────────────────────────┤
│  1. 批量评分                                             │
│     - 选择目录 → One-Align 评分 → 写入 XMP Rating        │
│     - 支持 RAW + JPEG                                   │
│     - 评分阈值可调                                       │
│                                                         │
│  2. 自动分目录                                           │
│     - 根据评分自动分类到子目录                            │
│     - 5★/4★/3★/2★/1★ 或自定义                          │
│                                                         │
│  3. 评分报告                                             │
│     - 生成 CSV 汇总                                      │
│     - 可选：12 维度详细分析                              │
│                                                         │
│  4. 预览界面                                             │
│     - 缩略图 + 评分显示                                  │
│     - 快速浏览结果                                       │
└─────────────────────────────────────────────────────────┘
```

#### 技术选型

| 组件 | 技术 |
|------|------|
| GUI 框架 | PyQt6 / PySide6 |
| 评分引擎 | One-Align (Python) |
| 元数据写入 | ExifTool (CLI) |
| 打包工具 | PyInstaller / py2app |

---

### 🔌 第二阶段：Lightroom Plugin（按需分析）

| 项目 | 说明 |
|------|------|
| **核心模型** | Co-Instruct |
| **主要功能** | 按需分析、关键字生成、场景描述 |
| **速度** | 6-60s/问题（用户可接受，因为是精选照片） |
| **适用场景** | 用户在 Lightroom 中精选照片时，对单张照片进行深度分析 |

#### 功能规划

```
┌─────────────────────────────────────────────────────────┐
│  Lightroom Plugin: SuperElite Analyzer                  │
├─────────────────────────────────────────────────────────┤
│  右键菜单 / 面板功能：                                    │
│                                                         │
│  1. 生成关键字                                           │
│     - Co-Instruct → 10 个关键字 → 写入 XMP Keywords     │
│                                                         │
│  2. 生成描述                                             │
│     - Co-Instruct → 场景描述 → 写入 XMP Caption         │
│                                                         │
│  3. 场景分类                                             │
│     - sunset/aurora/waterfall/mountain... → XMP Label   │
│                                                         │
│  4. 情感分析                                             │
│     - peaceful/dramatic/mysterious... → XMP 自定义字段  │
│                                                         │
│  5. 双图对比                                             │
│     - 选择两张照片 → 分析哪张更好 → 文字报告             │
│                                                         │
│  6. 质量分析报告                                         │
│     - 详细优缺点分析 → 弹窗显示                          │
└─────────────────────────────────────────────────────────┘
```

#### 技术架构

```
┌──────────────────┐     HTTP API      ┌──────────────────┐
│  Lightroom       │ ◄──────────────► │  Python 后端      │
│  (Lua Plugin)    │     JSON 通信     │  (Co-Instruct)   │
└──────────────────┘                   └──────────────────┘
                                              │
                                              ▼
                                       ┌──────────────────┐
                                       │  ExifTool        │
                                       │  (写入 XMP)      │
                                       └──────────────────┘
```

| 组件 | 技术 |
|------|------|
| Lightroom 插件 | Lua + Lightroom SDK |
| 后端服务 | Flask / FastAPI (Python) |
| 分析引擎 | Co-Instruct |
| 通信协议 | HTTP REST API |

---

### 📅 开发优先级

| 阶段 | 产品 | 预计时间 | 状态 |
|------|------|----------|------|
| **Phase 1** | SuperElite GUI | 2-3 周 | 🔜 待开发 |
| **Phase 2** | Lightroom Plugin | 2-3 周 | 📋 规划中 |

### 💡 为什么这样分两步

| 考量 | 说明 |
|------|------|
| **速度** | One-Align 快（1.15s），适合批量；Co-Instruct 慢（6-60s），适合精选 |
| **使用场景** | 批量筛选是第一步，深度分析是精选后的第二步 |
| **用户体验** | GUI 可独立使用；Plugin 集成到工作流 |
| **模型内存** | 两个产品可以分别使用不同模型，不需要同时加载 |

---

## 🔮 后续探索方向（低优先级）

1. **Compare2Score** - 对比评分模型，可能提供更稳定的相对评分
2. **LoRA 微调** - 在自己的数据集上微调 One-Align（需要 GPU）
3. **VQA-Assistant** - 最新对话模型，可能比 Co-Instruct 更强
