#!/usr/bin/env python3
"""
MiniMax API 客户端
用于自动化评测
"""

import os
import requests
from typing import Optional

# MiniMax API 配置（第二个Key：可用的）
API_KEY = os.environ.get('MINIMAX_API_KEY', 'sk-api-d6AAsOhBfLy7U6CNcldhq5OnvdwS4PnLNDrB6rrjKVWmiwUObGsIUYb6aZTkJcMkF2wdPr_ODqGOWqLqSlW0mBgQCY0hhUT_cQ8qENA6ljawUWQ46QT8Aw0')
BASE_URL = 'https://api.minimax.chat/v1/text/chatcompletion_v2'
MODEL = 'MiniMax-M2.5'

DEFAULT_SYSTEM_PROMPT = """你是一位严格的数据准确性审计员。

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


class MiniMaxClient:
    """MiniMax API 客户端"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = MODEL):
        self.api_key = api_key or API_KEY
        self.model = model
        self.base_url = BASE_URL
    
    def chat(self, user_content: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT, 
             temperature: float = 0.3, max_tokens: int = 2048) -> str:
        """
        发送聊天请求
        
        Args:
            user_content: 用户输入
            system_prompt: 系统提示
            temperature: 采样温度
            max_tokens: 最大token数
            
        Returns:
            模型回复文本
        """
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_content}
        ]
        
        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
            'stream': False
        }
        
        response = requests.post(
            self.base_url, 
            headers=headers, 
            json=payload, 
            timeout=60
        )
        
        if response.status_code != 200:
            raise Exception(f"API请求失败: {response.status_code} - {response.text}")
        
        result = response.json()
        
        if 'choices' not in result or len(result['choices']) == 0:
            raise Exception(f"API返回格式异常: {result}")
        
        content = result['choices'][0].get('message', {}).get('content', '')
        
        return content
    
    def chat_json(self, user_content: str, system_prompt: str = DEFAULT_SYSTEM_PROMPT, 
                 temperature: float = 0.3) -> dict:
        """
        发送聊天请求并解析JSON响应
        
        Args:
            user_content: 用户输入
            system_prompt: 系统提示
            temperature: 采样温度
            
        Returns:
            解析后的JSON对象
        """
        import json
        import re
        
        content = self.chat(user_content, system_prompt, temperature)
        
        # 尝试提取JSON
        # 1. 尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        
        # 2. 尝试从markdown代码块中提取
        json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*```', content)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # 3. 尝试找最外层的{}
        json_match = re.search(r'\{.+\}', content, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        raise Exception(f"无法解析JSON响应: {content[:200]}")


# 全局客户端实例
_client = None

def get_client() -> MiniMaxClient:
    """获取全局客户端实例"""
    global _client
    if _client is None:
        _client = MiniMaxClient()
    return _client


if __name__ == '__main__':
    # 测试
    client = get_client()
    response = client.chat("请用一句话介绍你自己")
    print("Response:", response)