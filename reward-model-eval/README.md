# Reward Model 评测完整闭环 (Eval Suite + Hill Climbing)

自动化评测系统：自动评测 → Badcase归因 → Prompt优化 → 版本管理 → Hill Climbing迭代 → 指标追踪

## 功能特性

- **自动评测**: 批量调用 MiniMax API 进行自动化评测
- **Badcase归因**: 智能分析误判原因，生成修改建议
- **Prompt版本管理**: 支持版本记录、回滚和对比
- **Hill Climbing**: 自动迭代优化，持续提升准确率
- **验证交付**: 自动生成 Markdown 交付报告

## 快速开始

```bash
# 克隆仓库
git clone https://github.com/Sunqiran0478/skill_eval_hillclimbing.git
cd skill_eval_hillclimbing

# 安装依赖
pip install -r requirements.txt

# 运行评测
python scripts/hillclimbing.py /path/to/评测集.xlsx

# 运行验证并生成报告
python scripts/validator.py /path/to/评测结果.xlsx full
```

## 目录结构

```
.
├── scripts/
│   ├── hillclimbing.py      # Hill Climbing 主脚本
│   ├── eval.py              # 评测核心逻辑
│   ├── eval_loop.py         # 批量评测循环
│   ├── eval_runner.py       # 评测 Runner
│   ├── minimax_client.py    # MiniMax API 客户端
│   ├── prompt_manager.py    # Prompt 版本管理
│   ├── validator.py         # 效果验证模块
│   └── quick_eval.py        # 快速测试
├── references/
│   ├── 数据格式说明.md
│   └── 评测prompt.md
├── SKILL.md                 # Skill 说明文档
├── REPORT_DELIVERY.md       # 验证交付报告
├── PROMPT_VERSIONS_COMPARISON.md  # Prompt 版本对比
└── eval_visualization.html  # 可视化图表
```

## 性能指标

| 版本 | 准确率 | 精确率 | 召回率 | F1 |
|------|--------|--------|--------|-----|
| v1 | 42.86% | 33.33% | 100% | 50% |
| v2 | 71.43% | 66.67% | 80% | 72.73% |
| v3 | **85.71%** | **83.33%** | **83.33%** | **83.33%** |

## 技术栈

- Python 3.12
- MiniMax API (M2.5模型)
- pandas / numpy / scipy

## License

MIT