#!/usr/bin/env python3
"""
Reward Model 评测结果对比分析脚本
对比模型评测结果与人工评测结果，找出不一致并归纳误判原因
"""

import pandas as pd
import json
import sys
from pathlib import Path


def load_excel(file_path: str) -> pd.DataFrame:
    """读取Excel文件"""
    df = pd.read_excel(file_path)
    return df


def extract_columns(df: pd.DataFrame) -> dict:
    """提取需要的列"""
    # 优先精确匹配
    model_col = None
    gt_col = None
    reason_col = None
    sentence_col = None
    query_col = None

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

    # 如果精确匹配没找到，模糊匹配
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

    if not reason_col:
        for col in df.columns:
            if '误判原因' in col:
                reason_col = col
                break

    return {
        'model_col': model_col,
        'gt_col': gt_col,
        'reason_col': reason_col,
        'sentence_col': sentence_col,
        'query_col': query_col
    }


def compare_results(df: pd.DataFrame, cols: dict) -> dict:
    """对比模型结果与人工结果"""
    model_col = cols['model_col']
    gt_col = cols['gt_col']

    if not model_col or not gt_col:
        raise ValueError("未找到模型评测结果列或人工评测结果列")

    # 转换为数值类型
    df[model_col] = pd.to_numeric(df[model_col], errors='coerce')
    df[gt_col] = pd.to_numeric(df[gt_col], errors='coerce')

    # 过滤空值
    valid_df = df.dropna(subset=[model_col, gt_col])

    # 分类统计
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

    # 找出FP和FN
    df[model_col] = pd.to_numeric(df[model_col], errors='coerce')
    df[gt_col] = pd.to_numeric(df[gt_col], errors='coerce')

    fp_df = df[(df[model_col] == 1) & (df[gt_col] == 0)]
    fn_df = df[(df[model_col] == 0) & (df[gt_col] == 1)]

    # 统计误判原因分布
    reason_distribution = {}
    error_cases = []

    if reason_col:
        # 从已有原因分析中统计
        for _df in [fp_df, fn_df]:
            for _, row in _df.iterrows():
                reason = row.get(reason_col, '未标注')
                if pd.notna(reason):
                    reason_distribution[reason] = reason_distribution.get(reason, 0) + 1

                    # 收集典型案例
                    if len(error_cases) < 5:
                        case = {
                            'query': row.get(query_col, '')[:100] if query_col else '',
                            'sentence': row.get(sentence_col, '')[:100] if sentence_col else '',
                            'model_result': int(row[model_col]),
                            'gt_result': int(row[gt_col]),
                            'reason': str(reason)[:200]
                        }
                        if case['query'] or case['sentence']:
                            error_cases.append(case)

    # 如果没有原因列，分析句子特征
    if not reason_distribution and sentence_col:
        # 简单的关键词分析
        keywords = ['时间', '季度', '年报', '单位', '亿', '万', '精度', '实体', '归属']
        for kw in keywords:
            count = fp_df[sentence_col].str.contains(kw, na=False).sum() + \
                    fn_df[sentence_col].str.contains(kw, na=False).sum()
            if count > 0:
                reason_distribution[kw + '相关问题'] = count

    return {
        'distribution': reason_distribution,
        'fp_count': len(fp_df),
        'fn_count': len(fn_df),
        'cases': error_cases
    }


def generate_recommendations(error_analysis: dict) -> list:
    """生成改进建议"""
    recommendations = []
    dist = error_analysis.get('distribution', {})

    if not dist:
        recommendations.append("建议增加误判原因标注，提高分析精度")
        return recommendations

    # 根据误判类型生成建议
    for reason, count in sorted(dist.items(), key=lambda x: x[1], reverse=True):
        if '时间' in reason:
            recommendations.append(f"建议优化时间对齐逻辑（{count}例），特别是季度与年报的区分")
        elif '单位' in reason or '亿' in reason or '万' in reason:
            recommendations.append(f"建议增加单位换算的校验规则（{count}例）")
        elif '实体' in reason or '归属' in reason:
            recommendations.append(f"建议优化实体归属判断逻辑（{count}例）")
        elif '精度' in reason:
            recommendations.append(f"建议增加数值精度校验（{count}例）")

    return recommendations[:5]


def run_eval(file_path: str, output_format: str = 'json') -> dict:
    """主函数：运行评测对比分析"""
    # 1. 读取数据
    df = load_excel(file_path)

    # 2. 提取列名
    cols = extract_columns(df)

    # 3. 对比结果
    stats = compare_results(df, cols)

    # 4. 计算指标
    metrics = calculate_metrics(stats)

    # 5. 分析误判
    error_analysis = analyze_errors(df, cols)

    # 6. 生成建议
    recommendations = generate_recommendations(error_analysis)

    # 7. 组装报告
    report = {
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
        'recommendations': recommendations
    }

    return report


def main():
    if len(sys.argv) < 2:
        print("用法: python eval.py <excel文件路径> [json/excel]")
        sys.exit(1)

    file_path = sys.argv[1]
    output_format = sys.argv[2] if len(sys.argv) > 2 else 'json'

    try:
        report = run_eval(file_path, output_format)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({'error': str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == '__main__':
    main()