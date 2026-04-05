#!/usr/bin/env python3
"""
自动评测 Runner
调用LLM自动评测数据
"""

import os
import json
import pandas as pd
from typing import Optional, List, Dict
from datetime import datetime

from minimax_client import MiniMaxClient, get_client


class EvalRunner:
    """自动评测Runner"""
    
    def __init__(self, client: Optional[MiniMaxClient] = None):
        self.client = client or get_client()
        self.results = []
    
    def format_prompt(self, row: pd.Series) -> str:
        """
        格式化评测prompt
        
        需要从row中提取:
        - query: 用户问题
        - response_text: 回答内容
        - reference_text: 参考资料
        - fact_pairs_text: 事实对
        """
        # 尝试获取各字段
        query = row.get('query', '') or row.get('Query', '') or ''
        response = row.get('response_text', '') or row.get('response', '') or row.get('回答内容', '') or ''
        reference = row.get('reference_text', '') or row.get('reference', '') or row.get('参考资料', '') or ''
        fact_pairs = row.get('fact_pairs_text_优化后final', '') or row.get('fact_pairs', '') or row.get('事实对', '') or ''
        
        # 构建输入
        prompt = f"""【待检测的事实对】
{fact_pairs}

【原始参考资料】
{reference}

【回答内容】
{response}

请逐条检测上述事实对，判断每个事实对在回答中是否存在数据幻觉。
只输出JSON格式，格式如下:
{{"results": [{{"fact": "事实对内容", "is_hallucinated": true/false, "reason": "判断原因"}}]}}
"""
        return prompt
    
    def eval_single(self, row: pd.Series) -> Dict:
        """评测单条数据"""
        prompt = self.format_prompt(row)
        
        try:
            result = self.client.chat_json(prompt)
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'result': None
            }
        
        # 解析结果
        results_list = result.get('results', [])
        if not results_list:
            return {'status': 'error', 'error': 'no_results', 'result': None}
        
        # 汇总判断
        has_hallucination = any(r.get('is_hallucinated', False) for r in results_list)
        
        return {
            'status': 'success',
            'result': 1 if has_hallucination else 0,
            'details': results_list
        }
    
    def eval_batch(self, df: pd.DataFrame, limit: Optional[int] = None, 
                 progress: bool = True) -> List[Dict]:
        """
        批量评测
        
        Args:
            df: 评测数据DataFrame
            limit: 评测数量限制（用于测试）
            progress: 是否显示进度
            
        Returns:
            评测结果列表
        """
        if limit:
            df = df.head(limit)
        
        total = len(df)
        results = []
        
        for idx, (_, row) in enumerate(df.iterrows()):
            if progress and (idx + 1) % 10 == 0:
                print(f"评测进度: {idx + 1}/{total}")
            
            result = self.eval_single(row)
            result['index'] = idx
            results.append(result)
        
        return results
    
    def eval_and_save(self, input_file: str, output_file: str = None, 
                   limit: int = None) -> str:
        """
        评测并保存结果
        
        Args:
            input_file: 输入Excel文件
            output_file: 输出文件路径
            limit: 评测数量限制
            
        Returns:
            输出文件路径
        """
        # 读取数据
        df = pd.read_excel(input_file)
        
        # 评测
        results = self.eval_batch(df, limit=limit)
        
        # 保存结果
        if output_file is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = input_file.replace('.xlsx', f'_llm_result_{timestamp}.xlsx')
        
        # 添加结果列
        df['llm_eval_result'] = [r.get('result', None) for r in results]
        df['llm_eval_status'] = [r.get('status', 'error') for r in results]
        
        df.to_excel(output_file, index=False)
        
        print(f"结果已保存: {output_file}")
        
        return output_file


def main():
    import sys
    
    if len(sys.argv) < 2:
        print("""
用法: python eval_runner.py <excel文件> [输出文件] [评测数量限制]

示例:
  python eval_runner.py /path/to/评测集.xlsx /path/to/结果.xlsx
  python eval_runner.py /path/to/评测集.xlsx /path/to/结果.xlsx 50  # 只评测前50条
        """)
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else None
    
    runner = EvalRunner()
    runner.eval_and_save(input_file, output_file, limit)


if __name__ == '__main__':
    main()