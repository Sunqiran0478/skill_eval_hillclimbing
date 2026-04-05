#!/usr/bin/env python3
"""
Reward Model 评测完整闭环
结果对比 → Badcase归因 → Prompt优化 → 再次评测 → 版本对比 → 指标提升
"""

import pandas as pd
import json
import sys
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ============ 配置部分 ============

# 评测Prompt（可版本化管理）
DEFAULT_PROMPT = """你是一位严格的数据准确性审计员。

【你的任务】
依据输入的【待检测的事实对】、【原始参考资料】和【回答内容】，对每一个事实对逐条审计数据准确性，并输出结构化结论。

你必须完成以下步骤：
Step 1. 在【回答内容】中定位该事实对对应的原句/上下文，以理解事实对的含义。
Step 2. 在【原始参考资料】中检索并逐字引用与该事实对最直接相关的证据原文（可多段）。
Step 3. 做一致性核验（必须逐项核对）：认真核对实体、时间、指标和指标数值是否匹配。

所有可能的数据准确性错误类型：
- entity_mismatch: 实体张冠李戴
- value_tampered: 数值篡改
- calculation_error: 计算错误
- fabrication: 无中生有
- no_error: 无错误

【输出要求】
- 只输出JSON，禁止输出任何额外文本
- results长度必须等于待检测的事实对数量
- is_hallucinated: true表示有幻觉（错误），false表示无幻觉（正确）
"""

# Prompt版本历史
PROMPT_VERSIONS = {
    "v1": {
        "prompt": DEFAULT_PROMPT,
        "description": "初始版本"
    }
}

# ============ 核心函数 ============

def load_excel(file_path: str) -> pd.DataFrame:
    """读取Excel文件"""
    df = pd.read_excel(file_path)
    return df


def extract_columns(df: pd.DataFrame) -> dict:
    """提取需要的列"""
    model_col = None
    gt_col = None
    reason_col = None
    sentence_col = None
    query_col = None
    response_col = None
    reference_col = None
    fact_pairs_col = None

    for col in df.columns:
        if col == '模型评测结果0125':
            model_col = col
        elif col == 'Ground_truth评测结果':
            gt_col = col
        elif col == '误判原因分析0113' or col == '误判原因分析original':
            reason_col = col
        elif col == 'sentence':
            sentence_col = col
        elif col == 'query':
            query_col = col
        elif col == 'response_text':
            response_col = col
        elif col == 'reference_text':
            reference_col = col
        elif col == 'fact_pairs_text_优化后final':
            fact_pairs_col = col

    # 模糊匹配备用
    if not model_col:
        for col in df.columns:
            if '模型评测结果' in col:
                model_col = col
                break
    if not gt_col:
        for col in df.columns:
            if 'ground_truth评测结果' in col.lower() or '人工评测结果' in col:
                gt_col = col
                break

    return {
        'model_col': model_col,
        'gt_col': gt_col,
        'reason_col': reason_col,
        'sentence_col': sentence_col,
        'query_col': query_col,
        'response_col': response_col,
        'reference_col': reference_col,
        'fact_pairs_col': fact_pairs_col
    }


def compare_results(df: pd.DataFrame, cols: dict) -> dict:
    """对比模型结果与人工结果"""
    model_col = cols['model_col']
    gt_col = cols['gt_col']

    if not model_col or not gt_col:
        raise ValueError("未找到模型评测结果列或人工评测结果列")

    df[model_col] = pd.to_numeric(df[model_col], errors='coerce')
    df[gt_col] = pd.to_numeric(df[gt_col], errors='coerce')

    valid_df = df.dropna(subset=[model_col, gt_col])

    tp = ((valid_df[model_col] == 1) & (valid_df[gt_col] == 1)).sum()
    fp = ((valid_df[model_col] == 1) & (valid_df[gt_col] == 0)).sum()
    tn = ((valid_df[model_col] == 0) & (valid_df[gt_col] == 0)).sum()
    fn = ((valid_df[model_col] == 0) & (valid_df[gt_col] == 1)).sum()

    total = len(valid_df)

    return {
        'total': total,
        'tp': int(tp),
        'fp': int(fp),
        'tn': int(tn),
        'fn': int(fn)
    }


def calculate_metrics(stats: dict) -> dict:
    """计算评测指标"""
    tp, fp, tn, fn = stats['tp'], stats['fp'], stats['tn'], stats['fn']
    total = stats['total']

    accuracy = (tp + tn) / total if total > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return {
        'accuracy': round(accuracy, 4),
        'precision': round(precision, 4),
        'recall': round(recall, 4),
        'f1': round(f1, 4)
    }


def analyze_errors(df: pd.DataFrame, cols: dict) -> dict:
    """分析误判原因"""
    model_col = cols['model_col']
    gt_col = cols['gt_col']
    reason_col = cols['reason_col']
    sentence_col = cols['sentence_col']
    query_col = cols['query_col']

    df[model_col] = pd.to_numeric(df[model_col], errors='coerce')
    df[gt_col] = pd.to_numeric(df[gt_col], errors='coerce')

    fp_df = df[(df[model_col] == 1) & (df[gt_col] == 0)]
    fn_df = df[(df[model_col] == 0) & (df[gt_col] == 1)]

    reason_distribution = {}
    error_cases = []

    if reason_col:
        for _df in [fp_df, fn_df]:
            for _, row in _df.iterrows():
                reason = row.get(reason_col, '未标注')
                if pd.notna(reason):
                    reason_distribution[reason] = reason_distribution.get(reason, 0) + 1
                    if len(error_cases) < 10:
                        case = {
                            'query': str(row.get(query_col, ''))[:100] if query_col else '',
                            'sentence': str(row.get(sentence_col, ''))[:100] if sentence_col else '',
                            'model_result': int(row[model_col]),
                            'gt_result': int(row[gt_col]),
                            'reason': str(reason)[:200]
                        }
                        if case['query'] or case['sentence']:
                            error_cases.append(case)

    if not reason_distribution and sentence_col:
        keywords = ['时间', '季度', '年报', '单位', '亿', '万', '精度', '实体', '归属', '范围']
        for kw in keywords:
            count = fp_df[sentence_col].str.contains(kw, na=False).sum() + \
                    fn_df[sentence_col].str.contains(kw, na=False).sum()
            if count > 0:
                reason_distribution[kw + '相关问题'] = count

    return {
        'distribution': reason_distribution,
        'fp_count': len(fp_df),
        'fn_count': len(fn_df),
        'cases': error_cases,
        'fp_df': fp_df,
        'fn_df': fn_df
    }


def generate_recommendations(error_analysis: dict) -> list:
    """生成改进建议"""
    recommendations = []
    dist = error_analysis.get('distribution', {})

    if not dist:
        recommendations.append("建议增加误判原因标注，提高分析精度")
        return recommendations

    for reason, count in sorted(dist.items(), key=lambda x: x[1], reverse=True):
        if '时间' in reason:
            recommendations.append(f"建议优化时间对齐逻辑（{count}例），特别是季度与年报的区分")
        elif '单位' in reason or '亿' in reason or '万' in reason:
            recommendations.append(f"建议增加单位换算的校验规则（{count}例）")
        elif '实体' in reason or '归属' in reason:
            recommendations.append(f"建议优化实体归属判断逻辑（{count}例）")
        elif '精度' in reason:
            recommendations.append(f"建议增加数值精度校验（{count}例）")
        elif '范围' in reason:
            recommendations.append(f"建议优化区间数据的处理逻辑（{count}例）")
        elif '指标' in reason:
            recommendations.append(f"建议优化指标名称匹配逻辑（{count}例）")

    return recommendations[:5]


def generate_prompt_suggestions(error_analysis: dict) -> list:
    """根据误判分析生成Prompt修改建议"""
    suggestions = []
    dist = error_analysis.get('distribution', {})

    for reason, _ in dist.items():
        if '时间' in reason:
            suggestions.append({
                'type': 'prompt_addition',
                'content': '增加时间对齐规则：指标归属时间需由原回答内容与事实对信息综合判断，模型应识别回答中隐含或显式的时间口径，并与参考资料进行合理的会计/金融语义对齐（如"2025年Q3季报"对应"截至 2025-09-27季报"）'
            })
        elif '单位' in reason:
            suggestions.append({
                'type': 'prompt_addition',
                'content': '增加单位换算规则：当回答中使用高位数数据时，需要科学严谨地将原始参考资料对应的数据转化为与回答内容统一的单位，两者小数点左侧的数字必须完全一致'
            })
        elif '实体' in reason or '归属' in reason:
            suggestions.append({
                'type': 'prompt_addition',
                'content': '增加实体归属规则：需要严格核对实体、时间、指标的匹配，避免张冠李戴'
            })
        elif '指标' in reason:
            suggestions.append({
                'type': 'prompt_refinement',
                'content': '优化指标名称匹配规则：对于相似指标名称（如"现金及等价物"vs"现金及短期投资"），需要更智能的匹配'
            })

    return suggestions


# ============ 完整闭环主函数 ============

def run_full_loop(file_path: str, output_dir: str = None) -> dict:
    """
    完整闭环：结果对比 → Badcase归因 → Prompt优化建议 → 评测对比
    """
    if output_dir is None:
        output_dir = os.path.dirname(file_path) or '.'

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    run_id = f"run_{timestamp}"

    # 1. 读取数据
    print(f"[{run_id}] 读取数据...")
    df = load_excel(file_path)
    cols = extract_columns(df)

    # 2. 结果对比
    print(f"[{run_id}] 对比模型结果与人工结果...")
    stats = compare_results(df, cols)
    metrics = calculate_metrics(stats)

    # 3. Badcase归因
    print(f"[{run_id}] 分析误判原因...")
    error_analysis = analyze_errors(df, cols)

    # 4. 生成改进建议
    recommendations = generate_recommendations(error_analysis)
    prompt_suggestions = generate_prompt_suggestions(error_analysis)

    # 5. 汇总报告
    report = {
        'run_id': run_id,
        'timestamp': timestamp,
        'file': file_path,
        'summary': {
            'total_samples': stats['total'],
            'accuracy': metrics['accuracy'],
            'precision': metrics['precision'],
            'recall': metrics['recall'],
            'f1': metrics['f1'],
            'true_positive': stats['tp'],
            'false_positive': stats['fp'],
            'true_negative': stats['tn'],
            'false_negative': stats['fn']
        },
        'error_analysis': {
            '误判类型分布': error_analysis['distribution'],
            '误判总数': error_analysis['fp_count'] + error_analysis['fn_count'],
            '误判案例': error_analysis['cases']
        },
        'recommendations': recommendations,
        'prompt_suggestions': prompt_suggestions
    }

    # 保存报告
    report_path = os.path.join(output_dir, f'eval_report_{run_id}.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[{run_id}] 报告已保存: {report_path}")

    return report


def compare_versions(history_file: str, new_metrics: dict) -> dict:
    """对比版本，输出指标变化"""
    if not os.path.exists(history_file):
        return {'status': 'first_run', 'improvement': new_metrics}

    with open(history_file, 'r', encoding='utf-8') as f:
        history = json.load(f)

    last_run = history['runs'][-1] if history.get('runs') else None
    if not last_run:
        return {'status': 'no_history', 'improvement': new_metrics}

    old_metrics = last_run.get('summary', {})
    comparison = {
        'status': 'compared',
        'previous': old_metrics,
        'current': new_metrics,
        'changes': {
            'accuracy_delta': new_metrics.get('accuracy', 0) - old_metrics.get('accuracy', 0),
            'precision_delta': new_metrics.get('precision', 0) - old_metrics.get('precision', 0),
            'recall_delta': new_metrics.get('recall', 0) - old_metrics.get('recall', 0),
            'f1_delta': new_metrics.get('f1', 0) - old_metrics.get('f1', 0),
            'fp_delta': new_metrics.get('false_positive', 0) - old_metrics.get('false_positive', 0),
            'fn_delta': new_metrics.get('false_negative', 0) - old_metrics.get('false_negative', 0)
        },
        'improved': new_metrics.get('accuracy', 0) >= old_metrics.get('accuracy', 0)
    }

    return comparison


def main():
    if len(sys.argv) < 2:
        print("""
用法: python eval_loop.py <excel文件路径> [输出目录]

完整闭环功能：
  1. 结果对比 - 对比模型评测与人工评测
  2. Badcase归因 - 分析误判类型和原因
  3. Prompt优化建议 - 生成针对性修改建议
  4. 版本对比 - 与历史结果对比指标变化

示例:
  python eval_loop.py /path/to/评测集.xlsx
  python eval_loop.py /path/to/评测集.xlsx /output/path
        """)
        sys.exit(1)

    file_path = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        report = run_full_loop(file_path, output_dir)
        print("\n" + "="*50)
        print("评测报告")
        print("="*50)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == '__main__':
    main()