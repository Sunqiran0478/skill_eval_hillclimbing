#!/usr/bin/env python3
"""
效果验证模块
验证评测系统可靠性
"""

import pandas as pd
import numpy as np
import json
import os
from typing import Dict, List, Tuple
from scipy import stats
from datetime import datetime

class EvalValidator:
    """
    效果验证器
    
    验证维度:
    1. 统计显著性 (A/B test,置信区间)
    2. 可重复性 (多次运行)
    3. 泛化能力 (train/test split)
    4. 边界Case处理
    5. 人工校验抽样
    """
    
    def __init__(self, client=None):
        self.client = client
        self.validation_results = []
    
    # ========== 1. 统计显著性验证 ==========
    
    def statistical_significance(self, results_v1: List[int], results_v2: List[int], 
                             alpha: float = 0.05) -> Dict:
        """
        检验两个版本是否存在显著差异
        
        使用McNemar检验（配对样本）
        """
        # 构建2x2列联表
        n00 = n11 = 0  # 两者结果相同
        n01 = n10 = 0  # 两者结果不同
        
        for r1, r2 in zip(results_v1, results_v2):
            if r1 == r2:
                if r1 == 0:
                    n00 += 1
                else:
                    n11 += 1
            else:
                if r1 == 0 and r2 == 1:
                    n10 += 1  # v2比v1好
                else:
                    n01 += 1
        
        # McNemar检验
        if min(n01, n10) < 5:
            # 样本太小，使用binomial检验
            n = n01 + n10
            p_value = stats.binom_test(n01, n, 0.5) if hasattr(stats, 'binom_test') else None
            # 简化版
            p_value = stats.binomtest(n01, n, 0.5).pvalue if hasattr(stats, 'binomtest') else 0.5
        else:
            # 标准McNemar
            chi2 = (abs(n01 - n10) - 1) ** 2 / (n01 + n10)
            p_value = 1 - stats.chi2.cdf(chi2, 1)
        
        significant = p_value < alpha
        
        return {
            'contingency_table': {'n00': n00, 'n11': n11, 'n10': n10, 'n01': n01},
            'chi2': chi2 if 'chi2' in dir() else None,
            'p_value': p_value,
            'significant': significant,
            'alpha': alpha,
            'conclusion': '显著提升' if significant else '无显著差异'
        }
    
    def confidence_interval(self, accuracy: int, total: int, 
                         confidence: float = 0.95) -> Tuple[float, float]:
        """
        计算准确率的置信区间
        
        使用Wilson score interval（更适合小样本）
        """
        from scipy.stats import norm
        
        z = norm.ppf(1 - (1 - confidence) / 2)
        p = accuracy / total
        
        denominator = 1 + z**2 / total
        center = (p + z**2 / (2 * total)) / denominator
        spread = z * np.sqrt((p * (1 - p) + z**2 / (4 * total)) / total) / denominator
        
        lower = max(0, center - spread)
        upper = min(1, center + spread)
        
        return (lower, upper)
    
    # ========== 2. 可重复性验证 ==========
    
    def repeatability_test(self, eval_fn, test_data: pd.DataFrame, 
                          n_runs: int = 3) -> Dict:
        """
        多次运行检验结果稳定性
        
        Args:
            eval_fn: 评测函数
            test_data: 测试数据
            n_runs: 运行次数
        """
        all_results = []
        
        for run in range(n_runs):
            print(f'运行 {run + 1}/{n_runs}...')
            results = []
            for _, row in test_data.iterrows():
                r = eval_fn(row)
                results.append(r)
            all_results.append(results)
        
        # 统计稳定性
        total_samples = len(test_data)
        stable_count = 0
        unstable_samples = []
        
        for i in range(total_samples):
            values = [all_results[r][i] for r in range(n_runs)]
            if len(set(values)) == 1:
                stable_count += 1
            else:
                unstable_samples.append({
                    'index': i,
                    'values': values,
                    'stability': len(set(values)) / n_runs
                })
        
        stability_rate = stable_count / total_samples
        
        return {
            'n_runs': n_runs,
            'total_samples': total_samples,
            'stable_samples': stable_count,
            'unstable_samples': len(unstable_samples),
            'stability_rate': stability_rate,
            'unstable_details': unstable_samples[:5],  # 只显示前5个
            'is_stable': stability_rate >= 0.95,
            'recommendation': '可交付' if stability_rate >= 0.95 else '需优化Prompt'
        }
    
    # ========== 3. 泛化能力验证 ==========
    
    def generalization_test(self, train_data: pd.DataFrame, 
                          test_data: pd.DataFrame, eval_fn) -> Dict:
        """
        留出测试集检验泛化能力
        
        避免在训练数据上过拟合
        """
        # 在训练集上评估
        train_results = [eval_fn(row) for _, row in train_data.iterrows()]
        train_metrics = self._calc_metrics(train_results, train_data['Ground_truth评测结果'])
        
        # 在测试集上评估
        test_results = [eval_fn(row) for _, row in test_data.iterrows()]
        test_metrics = self._calc_metrics(test_results, test_data['Ground_truth评测结果'])
        
        # 对比
        train_acc = train_metrics['accuracy']
        test_acc = test_metrics['accuracy']
        overfitting = train_acc - test_acc
        
        return {
            'train_samples': len(train_data),
            'test_samples': len(test_data),
            'train_accuracy': train_acc,
            'test_accuracy': test_acc,
            'overfitting_gap': overfitting,
            'is_overfitting': overfitting > 0.1,
            'recommendation': '可能过拟合' if overfitting > 0.1 else '泛化能力良好'
        }
    
    # ========== 4. 边界Case验证 ==========
    
    def boundary_case_test(self, test_cases: List[Dict]) -> Dict:
        """
        边界Case专项测试
        
        常见边界Case:
        - 空回答
        - 极长文本
        - 特殊字符
        - 多语言混杂
        - 数值边界(0,负数,极大数)
        """
        results = []
        
        for case in test_cases:
            try:
                eval_result = self._eval_case(case)
                results.append({
                    'case': case['name'],
                    'input': case['input'],
                    'expected': case['expected'],
                    'actual': eval_result,
                    'pass': eval_result == case['expected']
                })
            except Exception as e:
                results.append({
                    'case': case['name'],
                    'input': case['input'],
                    'expected': case['expected'],
                    'actual': 'ERROR',
                    'pass': False,
                    'error': str(e)
                })
        
        passed = sum(1 for r in results if r['pass'])
        total = len(results)
        
        return {
            'total_cases': total,
            'passed': passed,
            'failed': total - passed,
            'pass_rate': passed / total,
            'details': results,
            'isrobust': passed / total >= 0.8,
            'recommendation': f'{passed}/{total}边界Case通过'
        }
    
    # ========== 5. 人工校验 ==========
    
    def human_validation_sample(self, data: pd.DataFrame, 
                            n_samples: int = 20) -> List[Dict]:
        """
        随机抽取样本供人工校验
        
        返回样本列表，包含需要人工标注的项
        """
        # 按预测结果分层抽样
        predicted_hallucinated = data[data['llm_result'] == 1].sample(
            min(n_samples // 2, len(data[data['llm_result'] == 1]))
        predicted_correct = data[data['llm_result'] == 0].sample(
            min(n_samples // 2, len(data[data['llm_result'] == 0])))
        
        sample = pd.concat([predicted_hallucinated, predicted_correct])
        
        return sample[['query', 'response_text', 'reference_text', 
                      'sentence', 'llm_result', 'Ground_truth评测结果']].to_dict('records')
    
    # ========== 辅助函数 ==========
    
    def _calc_metrics(self, llm_results: List[int], gt: pd.Series) -> Dict:
        """计算指标"""
        tp = fp = tn = fn = 0
        for r, g in zip(llm_results, gt):
            if r == 1 and g == 1: tp += 1
            elif r == 1 and g == 0: fp += 1
            elif r == 0 and g == 0: tn += 1
            elif r == 0 and g == 1: fn += 1
        
        total = tp + fp + tn + fn
        acc = (tp + tn) / total if total else 0
        
        return {
            'total': total,
            'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn,
            'accuracy': acc,
            'precision': tp / (tp + fp) if (tp + fp) else 0,
            'recall': tp / (tp + fn) if (tp + fn) else 0
        }
    
    def _eval_case(self, case: Dict) -> int:
        """评测单条case"""
        from minimax_client import get_client
        client = get_client()
        
        prompt = f'''【待检测的事实对】
{case.get('fact_pairs', '')}

【原始参考资料】
{case.get('reference', '')}

【回答内容】
{case.get('response', '')}

只输出JSON: {{"is_hallucinated": true/false}}'''
        
        result = client.chat_json(prompt)
        return 1 if result.get('is_hallucinated') else 0
    
    # ========== 完整验证报告 ==========
    
    def full_validation(self, eval_file: str, n_runs: int = 3, output_dir: str = None) -> Dict:
        """
        完整验证流程
        
        Args:
            eval_file: 评测结果文件路径
            n_runs: 运行次数
            output_dir: 输出目录，默认当前目录
        """
        df = pd.read_excel(eval_file)
        
        # 获取版本信息（从数据中推断或使用默认）
        versions = ['v1', 'v2', 'v3']
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'total_samples': len(df),
            'validations': {}
        }
        
        # 1. 准确性验证
        accuracy = sum(df['llm_result'] == df['Ground_truth评测结果']) / len(df)
        ci_lower, ci_upper = self.confidence_interval(
            int(accuracy * len(df)), len(df))
        
        report['validations']['accuracy'] = {
            'value': accuracy,
            'CI_95': [ci_lower, ci_upper],
            'interpretation': f'95%置信区间为[{ci_lower:.1%}, {ci_upper:.1%}]'
        }
        
        # 2. 可重复性
        # (需要多次运行，简单版跳过)
        
        # 3. 混淆矩阵分析
        tp = sum((df['llm_result'] == 1) & (df['Ground_truth评测结果'] == 1))
        fp = sum((df['llm_result'] == 1) & (df['Ground_truth评测结果'] == 0))
        tn = sum((df['llm_result'] == 0) & (df['Ground_truth评测结果'] == 0))
        fn = sum((df['llm_result'] == 0) & (df['Ground_truth评测结果'] == 1))
        
        report['validations']['confusion_matrix'] = {
            'TP': int(tp), 'FP': int(fp), 'TN': int(tn), 'FN': int(fn)
        }
        
        # 4. 错误分析
        error_cases = df[df['llm_result'] != df['Ground_truth评测结果']]
        
        report['validations']['error_analysis'] = {
            'total_errors': len(error_cases),
            'error_rate': len(error_cases) / len(df),
            'FP_count': int(fp),
            'FN_count': int(fn)
        }
        
        # 5. 交付建议
        report['delivery'] = {
            'ready': accuracy >= 0.85 and ci_lower >= 0.75,
            'confidence': '高' if accuracy >= 0.9 else ('中' if accuracy >= 0.8 else '低'),
            'recommendations': []
        }
        
        if accuracy < 0.85:
            report['delivery']['recommendations'].append('Accuracy未达标，建议继续优化')
        if ci_lower < 0.75:
            report['delivery']['recommendations'].append('置信区间下限过低，需更多数据')
        
        return report


def main():
    import sys
    import os
    
    if len(sys.argv) < 2:
        print("""
效果验证模块

用法: python validator.py <评测结果文件> [验证类型] [输出目录]

示例:
  python validator.py ../test_eval_result.xlsx full
  python validator.py ../test_eval_result.xlsx full ./output/
        """)
        sys.exit(1)
    
    eval_file = sys.argv[1]
    validation_type = sys.argv[2] if len(sys.argv) > 2 else 'full'
    output_dir = sys.argv[3] if len(sys.argv) > 3 else None
    
    validator = EvalValidator()
    
    if validation_type == 'full':
        report = validator.full_validation(eval_file, output_dir=output_dir)
    else:
        report = {'error': 'unknown type'}
    
    print(json.dumps(report, ensure_ascii=False, indent=2))
    
    # 自动生成Markdown报告
    if output_dir and report.get('validations'):
        _generate_markdown_report(report, output_dir)
    elif report.get('validations'):
        # 默认输出到当前目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        skill_dir = os.path.dirname(script_dir)
        _generate_markdown_report(report, skill_dir)


def _generate_markdown_report(report: Dict, output_dir: str):
    """自动生成Markdown格式的交付报告"""
    
    validations = report.get('validations', {})
    accuracy_data = validations.get('accuracy', {})
    confusion = validations.get('confusion_matrix', {})
    error_analysis = validations.get('error_analysis', {})
    delivery = report.get('delivery', {})
    
    accuracy = accuracy_data.get('value', 0)
    ci_lower = accuracy_data.get('CI_95', [0, 0])[0]
    ci_upper = accuracy_data.get('CI_95', [0, 0])[1]
    confidence = delivery.get('confidence', '低')
    ready = delivery.get('ready', False)
    
    # 从混淆矩阵提取数据
    tp = confusion.get('TP', 0)
    fp = confusion.get('FP', 0)
    tn = confusion.get('TN', 0)
    fn = confusion.get('FN', 0)
    total = tp + fp + tn + fn
    
    # 计算各项指标
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    
    # 生成报告内容
    md_content = f"""# 奖励模型验证交付报告

## 1. 验证概述

- **验证时间**: {report.get('timestamp', 'N/A')}
- **总样本数**: {total}
- **正样本(幻觉)**: {tp + fn} ({((tp + fn) / total * 100):.1f}%)
- **负样本(正常)**: {tn + fp} ({((tn + fp) / total * 100):.1f}%)

---

## 2. 核心指标

| 指标 | 数值 | 达标阈值 | 状态 |
|------|------|----------|------|
| **准确率(Accuracy)** | {accuracy:.2%} | ≥ 85% | {'✅ 通过' if accuracy >= 0.85 else '❌ 未达标'} |
| **精确率(Precision)** | {precision:.2%} | ≥ 80% | {'✅ 通过' if precision >= 0.80 else '❌ 未达标'} |
| **召回率(Recall)** | {recall:.2%} | ≥ 80% | {'✅ 通过' if recall >= 0.80 else '❌ 未达标'} |
| **F1分数** | {f1:.2%} | ≥ 80% | {'✅ 通过' if f1 >= 0.80 else '❌ 未达标'} |

### 置信区间
- **95% CI**: [{ci_lower:.1%}, {ci_upper:.1%}]
- **置信度评级**: ⭐ {confidence}

---

## 3. 混淆矩阵

```
                预测结果
              正面(1)   负面(0)
实际  正面(1)    TP={tp}     FN={fn}
值    负面(0)    FP={fp}     TN={tn}
```

| 指标 | 数值 | 含义 |
|------|------|------|
| TP | {tp} | 正确识别幻觉样本 |
| TN | {tn} | 正确识别正常样本 |
| FP | {fp} | 正常样本误判为幻觉 |
| FN | {fn} | 幻觉样本漏判 |

---

## 4. 错误分析

- **总错误数**: {error_analysis.get('total_errors', 0)}
- **错误率**: {error_analysis.get('error_rate', 0):.2%}
- **误报(FP)**: {fp} 例
- **漏报(FN)**: {fn} 例

---

## 5. 交付结论

| 判定项 | 结果 |
|--------|------|
| 准确率 ≥ 85% | {'✅' if accuracy >= 0.85 else '❌'} |
| CI下限 ≥ 75% | {'✅' if ci_lower >= 0.75 else '❌'} |
| 精确率 ≥ 80% | {'✅' if precision >= 0.80 else '❌'} |
| 召回率 ≥ 80% | {'✅' if recall >= 0.80 else '❌'} |
| F1 ≥ 80% | {'✅' if f1 >= 0.80 else '❌'} |

> **🎯 最终结论**: {'准予交付 ✅' if ready else '暂不交付 ❌'}

---

## 6. 建议

{delivery.get('recommendations', ['暂无'])}

---

*报告自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
*验证工具: reward-model-eval/scripts/validator.py*
"""
    
    # 写入文件
    report_path = os.path.join(output_dir, 'REPORT_DELIVERY.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"\n📄 交付报告已生成: {report_path}")


if __name__ == '__main__':
    main()