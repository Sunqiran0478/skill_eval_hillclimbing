#!/usr/bin/env python3
"""
快速评测脚本 - 带重试机制
"""

import pandas as pd
import json
import time
from minimax_client import get_client
import requests

# 加载测试数据
df = pd.read_excel('../test_eval_data.xlsx')
print(f'共{len(df)}条数据')

def eval_row_with_retry(row, max_retries=3):
    """评测单条数据，带重试"""
    prompt = f'''【待检测的事实对】
{row.get('sentence', '')}

【原始参考资料】
{row.get('reference_text', '')}

【回答内容】
{row.get('response_text', '')}

请判断回答中是否存在数据幻觉。
只输出JSON格式: {{"is_hallucinated": true/false}}'''

    for attempt in range(max_retries):
        try:
            client = get_client()
            result = client.chat_json(prompt)
            return 1 if result.get('is_hallucinated', False) else 0
        except Exception as e:
            print(f'  重试 {attempt+1}/{max_retries}: {str(e)[:50]}')
            time.sleep(1)
    return None

def calc_metrics(llm_results, gt_col):
    """计算指标"""
    tp = fp = tn = fn = 0
    for r, gt in zip(llm_results, gt_col):
        if r is None:
            continue
        if r == 1 and gt == 1: tp += 1
        elif r == 1 and gt == 0: fp += 1
        elif r == 0 and gt == 0: tn += 1
        elif r == 0 and gt == 1: fn += 1
    
    total = tp + fp + tn + fn
    acc = (tp + tn) / total if total else 0
    prec = tp / (tp + fp) if (tp + fp) else 0
    rec = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2*prec*rec/(prec+rec) if (prec+rec) else 0
    
    return {'accuracy': round(acc, 4), 'precision': round(prec, 4), 'recall': round(rec, 4), 'f1': round(f1, 4), 
            'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn}

# ========== 评测 ==========
print('\n=== 评测中 ===')
results = []
for i, row in df.iterrows():
    print(f'[{i+1}/{len(df)}]', end=' ')
    r = eval_row_with_retry(row)
    results.append(r)
    gt = row['Ground_truth评测结果']
    print(f'GT={gt}, LLM={r}')
    time.sleep(0.5)  # 避免过快

metrics = calc_metrics(results, df['Ground_truth评测结果'])
print(f'\n最终指标: accuracy={metrics["accuracy"]:.2%}, f1={metrics["f1"]:.2%}')

# 保存结果
df['llm_result'] = results
df.to_excel('../test_eval_result.xlsx', index=False)

# 保存JSON供可视化
viz_data = {
    'versions': [
        {'version': 'v1', 'accuracy': metrics['accuracy'], 'precision': metrics['precision'], 
         'recall': metrics['recall'], 'f1': metrics['f1']}
    ],
    'confusion': {'tp': metrics['tp'], 'fp': metrics['fp'], 'tn': metrics['tn'], 'fn': metrics['fn']},
    'total': len(df)
}

with open('../viz_data.json', 'w') as f:
    json.dump(viz_data, f, ensure_ascii=False)

print(f'\n结果已保存到 viz_data.json')