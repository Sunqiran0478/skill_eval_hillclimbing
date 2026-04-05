#!/usr/bin/env python3
"""
Hill Climbing 迭代循环
完整的Eval Suite + Hill Climbing实现
"""

import os
import sys
import json
import pandas as pd
from typing import Optional, Dict, List
from datetime import datetime
from pathlib import Path

from minimax_client import MiniMaxClient, get_client
from eval_runner import EvalRunner
from prompt_manager import PromptManager


class HillClimbingEval:
    """
    Hill Climbing评测循环
    
    完整流程:
    1. 加载评测集
    2. 使用当前Prompt调用LLM评测
    3. 对比结果 vs Ground Truth
    4. 分析Badcase
    5. 生成修改建议
    6. 应用修改 → 创建新版本Prompt
    7. 重新评测 → 验证效果
    8. 如果指标提升 → 保留；否则回滚
    """
    
    def __init__(self, eval_file: str, output_dir: str = None):
        """
        初始化
        
        Args:
            eval_file: 评测集Excel文件路径
            output_dir: 输出目录
        """
        self.eval_file = eval_file
        self.output_dir = output_dir or os.path.dirname(eval_file) or '.'
        
        # 初始化组件
        self.client = get_client()
        self.prompt_manager = PromptManager(self.output_dir)
        
        # 运行记录
        self.run_history = []
        self.current_version = 'v1'
        self.current_metrics = None
    
    def load_data(self) -> pd.DataFrame:
        """加载评测数据"""
        df = pd.read_excel(self.eval_file)
        return df
    
    def eval_with_prompt(self, df: pd.DataFrame, prompt: str, 
                       limit: int = None) -> Dict:
        """
        使用指定Prompt评测
        
        Args:
            df: 评测数据
            prompt: 使用的Prompt
            limit: 评测数量限制
            
        Returns:
            评测结果和指标
        """
        # 创建临时客户端
        temp_client = MiniMaxClient()
        
        # 临时修改system prompt
        original_prompt = self.client.chat.__self__.DEFAULT_SYSTEM_PROMPT if hasattr(self, 'client') else ''
        
        # 使用Runner评测
        self.client.chat.__self__.DEFAULT_SYSTEM_PROMPT = prompt
        
        runner = EvalRunner(self.client)
        results = runner.eval_batch(df, limit=limit, progress=True)
        
        # 恢复原prompt
        if original_prompt:
            self.client.chat.__self__.DEFAULT_SYSTEM_PROMPT = original_prompt
        
        return {
            'results': results,
            'llm_results': [r.get('result') for r in results]
        }
    
    def compare_with_ground_truth(self, llm_results: List[int], 
                                df: pd.DataFrame) -> Dict:
        """
        对比LLM结果与Ground Truth
        
        Args:
            llm_results: LLM评测结果列表
            df: 原始数据（含Ground Truth）
            
        Returns:
            指标和对比结果
        """
        # 找到Ground Truth列
        gt_col = None
        for col in df.columns:
            if 'ground_truth评测结果' in col.lower() or '人工评测结果' in col:
                gt_col = col
                break
        
        if gt_col is None:
            raise ValueError("未找到Ground Truth列")
        
        # 计算指标
        tp = fp = tn = fn = 0
        for i, (_, row) in enumerate(df.iterrows()):
            if i >= len(llm_results):
                break
            
            llm_result = llm_results[i]
            gt_result = row[gt_col]
            
            if llm_result == 1 and gt_result == 1:
                tp += 1
            elif llm_result == 1 and gt_result == 0:
                fp += 1
            elif llm_result == 0 and gt_result == 0:
                tn += 1
            elif llm_result == 0 and gt_result == 1:
                fn += 1
        
        total = tp + fp + tn + fn
        
        accuracy = (tp + tn) / total if total > 0 else 0
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        return {
            'total': total,
            'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn,
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1': f1
        }
    
    def analyze_errors(self, llm_results: List[int], df: pd.DataFrame) -> Dict:
        """分析误判"""
        # 找到Ground Truth列
        gt_col = None
        for col in df.columns:
            if 'ground_truth评测结果' in col.lower() or '人工评测结果' in col:
                gt_col = col
                break
        
        if gt_col is None:
            return {'distribution': {}}
        
        # 分类统计
        error_cases = []
        reason_distribution = {}
        
        for i, (_, row) in enumerate(df.iterrows()):
            if i >= len(llm_results):
                break
            
            llm_result = llm_results[i]
            gt_result = row[gt_col]
            
            if llm_result != gt_result:
                # 误判案例
                sentence = row.get('sentence', '')
                query = row.get('query', '')
                reason = row.get('误判原因分析0113', '未标注')
                
                error_cases.append({
                    'index': i,
                    'query': str(query)[:100],
                    'sentence': str(sentence)[:100],
                    'llm_result': llm_result,
                    'gt_result': gt_result,
                    'reason': str(reason)[:200]
                })
                
                reason_distribution[str(reason)] = reason_distribution.get(str(reason), 0) + 1
        
        return {
            'distribution': reason_distribution,
            'cases': error_cases[:10]
        }
    
    def generate_modifications(self, error_analysis: Dict) -> List[Dict]:
        """生成修改建议"""
        suggestions = []
        dist = error_analysis.get('distribution', {})
        
        for reason, count in dist.items():
            if '时间' in reason:
                suggestions.append({
                    'type': 'prompt_addition',
                    'content': '增加时间对齐规则：指标归属时间需由原回答内容与事实对信息综合判断'
                })
            elif '单位' in reason:
                suggestions.append({
                    'type': 'prompt_addition',
                    'content': '增加单位换算规则：当回答中使用高位数数据时需要校验单位'
                })
            elif '实体' in reason:
                suggestions.append({
                    'type': 'prompt_addition',
                    'content': '增加实体归属规则：严格核对实体、时间、指标的匹配'
                })
        
        return suggestions
    
    def run_iteration(self, max_iterations: int = 5, 
                    limit_per_iter: int = None,
                    early_stop_threshold: float = 0.02) -> Dict:
        """
        运行Hill Climbing迭代
        
        Args:
            max_iterations: 最大迭代次数
            limit_per_iter: 每次迭代评测数量限制（用于快速测试）
            early_stop_threshold: 早停阈值
            
        Returns:
            运行结果报告
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        run_id = f"hillclimb_{timestamp}"
        
        # 加载数据
        print(f"[{run_id}] 加载评测数据...")
        df = self.load_data()
        total_samples = len(df)
        
        # 记录初始版本
        baseline_version = self.current_version
        baseline_metrics = None
        
        iteration_results = []
        
        for iteration in range(1, max_iterations + 1):
            print(f"\n{'='*50}")
            print(f"[{run_id}] 迭代 {iteration}/{max_iterations}")
            print(f"{'='*50}")
            
            # 1. 获取当前Prompt
            current_prompt = self.prompt_manager.get_prompt(self.current_version)
            print(f"使用Prompt版本: {self.current_version}")
            
            # 2. 评测
            print(f"开始LLM评测...")
            eval_results = self.eval_with_prompt(df, current_prompt, limit=limit_per_iter)
            llm_results = eval_results['llm_results']
            
            # 3. 对比Ground Truth
            print(f"对比结果...")
            metrics = self.compare_with_ground_truth(llm_results, df)
            print(f"指标: accuracy={metrics['accuracy']:.4f}, f1={metrics['f1']:.4f}")
            
            # 4. 记录
            self.current_metrics = metrics
            iteration_results.append({
                'iteration': iteration,
                'version': self.current_version,
                'metrics': metrics
            })
            
            # 5. 检查是否满足停止条件
            if iteration == 1:
                baseline_metrics = metrics
                baseline_version = self.current_version
            
            # 如果指标已很好，提前停止
            if metrics['accuracy'] >= 0.99:
                print(f"指标已达标 (accuracy={metrics['accuracy']:.4f})，停止迭代")
                break
            
            # 6. 分析误判
            print(f"分析误判...")
            error_analysis = self.analyze_errors(llm_results, df)
            total_errors = sum(error_analysis.get('distribution', {}).values())
            
            if total_errors == 0:
                print(f"无误判，停止迭代")
                break
            
            print(f"误判分析: {error_analysis.get('distribution', {})}")
            
            # 7. 生成修改建议
            suggestions = self.generate_modifications(error_analysis)
            
            if not suggestions:
                print(f"无有效修改建议，停止迭代")
                break
            
            # 8. 应用修改，创建新版本Prompt
            print(f"应用修改建议...")
            new_version = self.prompt_manager.update_prompt(
                self.current_version, 
                suggestions
            )
            print(f"新版本: {new_version}")
            
            # 记录运行
            self.prompt_manager.record_run({
                'run_id': f"{run_id}_iter{iteration}",
                'version': new_version,
                'metrics': metrics,
                'file': self.eval_file
            })
            
            # 9. 切换到新版本（下一轮使用）
            self.current_version = new_version
            
            # 检查指标变化
            if baseline_metrics:
                delta = metrics['accuracy'] - baseline_metrics['accuracy']
                print(f"指标变化: {delta:+.4f}")
                
                if delta < early_stop_threshold and iteration > 1:
                    print(f"指标无明显提升 ({delta:.4f} < {early_stop_threshold})，停止迭代")
                    break
        
        # 最终结果
        final_metrics = self.current_metrics
        
        # 对比baseline
        comparison = {}
        if baseline_metrics:
            comparison = {
                'baseline_accuracy': baseline_metrics['accuracy'],
                'final_accuracy': final_metrics['accuracy'],
                'delta': final_metrics['accuracy'] - baseline_metrics['accuracy']
            }
        
        result = {
            'run_id': run_id,
            'timestamp': timestamp,
            'eval_file': self.eval_file,
            'total_samples': total_samples,
            'total_iterations': len(iteration_results),
            'final_version': self.current_version,
            'final_metrics': final_metrics,
            'baseline_comparison': comparison,
            'iteration_results': iteration_results
        }
        
        # 保存报告
        report_path = os.path.join(self.output_dir, f'{run_id}_report.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n报告已保存: {report_path}")
        
        return result


def main():
    if len(sys.argv) < 2:
        print("""
Hill Climbing 迭代评测

用法: python hillclimbing.py <评测集文件> [输出目录] [最大迭代次数] [每轮评测数]

示例:
  python hillclimbing.py /path/to/评测集.xlsx /output/path
  python hillclimbing.py /path/to/评测集.xlsx /output/path 5 100
        """)
        sys.exit(1)
    
    eval_file = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None
    max_iterations = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    limit_per_iter = int(sys.argv[4]) if len(sys.argv) > 4 else None
    
    hc = HillClimbingEval(eval_file, output_dir)
    result = hc.run_iteration(max_iterations, limit_per_iter)
    
    print("\n" + "="*50)
    print("最终结果")
    print("="*50)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()