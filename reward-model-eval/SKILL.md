---
name: reward-model-eval
description: "Reward Model评测完整闭环（Eval Suite + Hill Climbing）。实现：自动评测→Badcase归因→Prompt优化→版本管理→自动迭代→指标追踪。触发方式：用户说'运行评测闭环'、'hill climbing'、'/reward-eval [文件路径]'。"
argument-hint: "[文件路径]"
disable-model-invocation: true
user-invocable: true
---

# Reward Model 评测完整闭环 (Eval Suite + Hill Climbing)

实现完整的自动化评测闭环：
**自动评测 → Badcase归因 → Prompt优化 → 版本管理 → Hill Climbing迭代 → 指标追踪**

## 和原版的区别

| 维度 | 原版 | Eval Suite + Hill Climbing |
|------|-----|---------------------|
| 评测方式 | 手动运行脚本对比已有结果 | **自动调用LLM评测** |
| Prompt管理 | 单次使用 | **版本管理 + 回滚** |
| 迭代方式 | 手动修改 | **自动Hill Climbing** |
| 效果验证 | 手动对比 | **自动验证指标提升** |

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Eval Suite + Hill Climbing               │
├─────────────────────────────────────────────────────────────┤
│  1. MiniMax API Client                                  │
│     └─ 自动调用MiniMax-M2.5模型                         │
│                                                              │
│  2. Eval Runner                                         │
│     └─ 批量评测数据 → 对比Ground Truth                    │
│                                                              │
│  3. Prompt Manager                                      │
│     └─ 版本管理 → 修改建议 → 回滚                        │
│                                                              │
│  4. Hill Climbing                                     │
│     └─ 自动迭代：评测→分析→修改→验证→继续              │
│                                                              │
│  5. 报告与追踪                                           │
│     └─ 迭代历史 → 指标变化 → 可视化                     │
└─────────────────────────────────────────────────────────────┘
```

## Inputs

1. **Excel文件路径** - 包含以下列的评测集文件：
   - `模型评测结果0125`：（可选，已有模型结果）
   - `Ground_truth评测结果`：人工评测的0/1结果（必需）
   - `query`：（可选）用户问题
   - `response_text`：（必需）回答内容
   - `reference_text`：（必需）参考资料
   - `fact_pairs_text_优化后final`：（必需）事实对

2. **可选参数**：
   - `最大迭代次数`：默认5
   - `每轮评测数`：用于快速测试

## Output

```json
{
  "run_id": "hillclimb_20260405_154200",
  "timestamp": "20260405_154200",
  "total_samples": 857,
  "total_iterations": 3,
  "final_version": "v3",
  "final_metrics": {
    "accuracy": 0.9850,
    "precision": 0.9900,
    "recall": 0.9880,
    "f1": 0.9890,
    "tp": 679,
    "fp": 8,
    "tn": 161,
    "fn": 9
  },
  "baseline_comparison": {
    "baseline_accuracy": 0.9200,
    "final_accuracy": 0.9850,
    "delta": 0.0650
  },
  "iteration_results": [
    {
      "iteration": 1,
      "version": "v1",
      "metrics": {"accuracy": 0.9200}
    },
    {
      "iteration": 2,
      "version": "v2", 
      "metrics": {"accuracy": 0.9600}
    },
    {
      "iteration": 3,
      "version": "v3",
      "metrics": {"accuracy": 0.9850}
    }
  ]
}
```

## 脚本说明

| 脚本 | 功能 |
|------|------|
| `minimax_client.py` | MiniMax API客户端 |
| `eval_runner.py` | 自动评测Runner |
| `prompt_manager.py` | Prompt版本管理 |
| `hillclimbing.py` | **Hill Climbing主脚本** |

## 使用方式

### 命令行运行

```bash
# 完整Hill Climbing（自动迭代）
python scripts/hillclimbing.py /path/to/评测集.xlsx [输出目录] [最大迭代] [每轮评测数]

# 示例（5轮迭代，每轮100条测试）
python scripts/hillclimbing.py /path/to/评测集.xlsx /output/path 5 100

# 快速测试（1轮迭代，50条）
python scripts/hillclimbing.py /path/to/评测集.xlsx /output/path 1 50
```

### 验证报告生成

```bash
# 运行验证并自动生成交付报告
python scripts/validator.py /path/to/评测结果.xlsx full

# 报告输出位置: REPORT_DELIVERY.md
```

### 自动生成报告功能

validator.py 运行后会自动生成 `REPORT_DELIVERY.md`，包含：

1. **版本性能对比** - v1/v2/v3 各版本指标对比
2. **混淆矩阵详情** - TP/TN/FP/FN 详细数据
3. **交付标准判定** - 各指标达标情况
4. **统计显著性分析** - McNemar检验结果
5. **最终交付结论** - 是否准予交付

### Prompt版本管理

```bash
# 列出所有版本
python scripts/prompt_manager.py list

# 获取指定版本
python scripts/prompt_manager.py get v1

# 回滚到指定版本
python scripts/prompt_manager.py rollback v1
```

### CodeBuddy调用

```
/reward-eval /Users/square/Desktop/实习/Reward Model评测集.xlsx
/hill-climb /Users/square/Desktop/评测集.xlsx
```

## 完整迭代示例

```
第1次迭代（v1）: accuracy=0.92
  ↓
分析误判 → 时间对齐问题（3例）→ 生成修改建议
  ↓
应用建议 → 创建v2
  ↓
第2次迭代（v2）: accuracy=0.96 (+4%)
  ↓
分析误判 → 单位换算问题（2例）→ 生成修改建议
  ↓
应用建议 → 创建v3
  ↓
第3次迭代（v3）: accuracy=0.985 (+2.5%)
  ↓
对比baseline: +6.5% ✓
```

## API配置

- **模型**: MiniMax-M2.5
- **API Key**: 环境变量 `MINIMAX_API_KEY` 或代码中配置

## 相关文件

- `prompt_versions/versions.json` - Prompt版本记录
- `prompt_versions/history.json` - 运行历史
- `*_report.json` - 每次运行的报告