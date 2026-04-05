#!/usr/bin/env python3
"""
Prompt 版本管理器
支持Prompt版本管理和回滚
"""

import os
import json
from typing import Optional, Dict, List
from datetime import datetime
from pathlib import Path


class PromptManager:
    """Prompt版本管理器"""
    
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
    
    def __init__(self, storage_dir: str = None):
        """
        初始化
        
        Args:
            storage_dir: 存储目录，默认当前目录下的prompt_versions
        """
        if storage_dir is None:
            storage_dir = os.path.join(os.getcwd(), 'prompt_versions')
        
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.versions_file = self.storage_dir / 'versions.json'
        self.history_file = self.storage_dir / 'history.json'
        
        # 初始化版本
        self._init_versions()
    
    def _init_versions(self):
        """初始化版本记录"""
        if not self.versions_file.exists():
            initial = {
                'v1': {
                    'prompt': self.DEFAULT_PROMPT,
                    'description': '初始版本',
                    'created_at': datetime.now().isoformat()
                }
            }
            self._save_versions(initial)
        
        if not self.history_file.exists():
            self._save_history({'runs': []})
    
    def _load_versions(self) -> Dict:
        """加载版本记录"""
        with open(self.versions_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _save_versions(self, versions: Dict):
        """保存版本记录"""
        with open(self.versions_file, 'w', encoding='utf-8') as f:
            json.dump(versions, f, ensure_ascii=False, indent=2)
    
    def _load_history(self) -> Dict:
        """加载历史记录"""
        with open(self.history_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _save_history(self, history: Dict):
        """保存历史记录"""
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    
    def get_prompt(self, version: str = 'latest') -> str:
        """
        获取Prompt
        
        Args:
            version: 版本号，如'v1'或'latest'
            
        Returns:
            Prompt文本
        """
        versions = self._load_versions()
        
        if version == 'latest':
            # 获取最新版本
            version = max(versions.keys(), key=lambda x: int(x[1:]))
        
        if version not in versions:
            raise ValueError(f"版本 {version} 不存在")
        
        return versions[version]['prompt']
    
    def set_prompt(self, prompt: str, description: str = '') -> str:
        """
        设置新Prompt并创建新版本
        
        Args:
            prompt: Prompt文本
            description: 描述
            
        Returns:
            新版本号
        """
        versions = self._load_versions()
        
        # 获取下一个版本号
        existing_versions = [int(k[1:]) for k in versions.keys() if k.startswith('v')]
        next_num = max(existing_versions) + 1 if existing_versions else 1
        version = f"v{next_num}"
        
        # 添加新版本
        versions[version] = {
            'prompt': prompt,
            'description': description or f'版本 {next_num}',
            'created_at': datetime.now().isoformat()
        }
        
        self._save_versions(versions)
        
        print(f"已创建新版本: {version}")
        
        return version
    
    def update_prompt(self, version: str, updates: List[Dict]) -> str:
        """
        更新Prompt（应用修改建议）
        
        Args:
            version: 要更新的版本号
            updates: 修改建议列表 [{'type': 'prompt_addition'/'prompt_refinement', 'content': '修改内容'}]
            
        Returns:
            新版本号
        """
        current_prompt = self.get_prompt(version)
        
        # 应用修改
        new_prompt = current_prompt
        for update in updates:
            if update.get('type') == 'prompt_addition':
                # 追加新内容
                new_prompt += f"\n\n【新增规则】\n{update['content']}"
            elif update.get('type') == 'prompt_refinement':
                # 替换内容（简单实现：追加替换说明）
                new_prompt += f"\n\n【规则更新】\n{update['content']}"
        
        # 创建新版本
        description = f"基于{version}的修改"
        new_version = self.set_prompt(new_prompt, description)
        
        return new_version
    
    def rollback(self, target_version: str) -> str:
        """
        回滚到指定版本
        
        Args:
            target_version: 目标版本号
            
        Returns:
            回滚后的版本号
        """
        prompt = self.get_prompt(target_version)
        new_version = self.set_prompt(prompt, f'回滚到{target_version}')
        
        return new_version
    
    def list_versions(self) -> List[Dict]:
        """列出所有版本"""
        versions = self._load_versions()
        
        result = []
        for ver, info in versions.items():
            result.append({
                'version': ver,
                'description': info.get('description', ''),
                'created_at': info.get('created_at', '')
            })
        
        # 按版本号排序
        result.sort(key=lambda x: int(x['version'][1:]))
        
        return result
    
    def record_run(self, run_info: Dict):
        """记录一次运行"""
        history = self._load_history()
        
        if 'runs' not in history:
            history['runs'] = []
        
        history['runs'].append({
            'run_id': run_info.get('run_id'),
            'timestamp': datetime.now().isoformat(),
            'version': run_info.get('version'),
            'metrics': run_info.get('metrics', {}),
            'file': run_info.get('file')
        })
        
        self._save_history(history)
    
    def compare_versions(self, version1: str, version2: str) -> Dict:
        """对比两个版本的Prompt"""
        prompt1 = self.get_prompt(version1)
        prompt2 = self.get_prompt(version2)
        
        return {
            'version1': version1,
            'version2': version2,
            'prompt1': prompt1,
            'prompt2': prompt2,
            'diff': '版本1比版本2长{}字符'.format(len(prompt2) - len(prompt1))
        }


def main():
    import sys
    
    pm = PromptManager()
    
    if len(sys.argv) < 2:
        print("""
用法: python prompt_manager.py <子命令> [参数]

子命令:
  list                      - 列出所有版本
  get [version]             - 获取Prompt
  set <prompt>              - 设置新Prompt
  update <version> <file>   - 应用修改建议文件
  rollback <version>       - 回滚到指定版本

示例:
  python prompt_manager.py list
  python prompt_manager.py get v1
  python prompt_manager.py rollback v1
        """)
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == 'list':
        for v in pm.list_versions():
            print(f"{v['version']}: {v['description']} ({v['created_at']})")
    
    elif cmd == 'get':
        version = sys.argv[2] if len(sys.argv) > 2 else 'latest'
        print(pm.get_prompt(version))
    
    elif cmd == 'set':
        prompt = ' '.join(sys.argv[2:])
        print(pm.set_prompt(prompt))
    
    elif cmd == 'rollback':
        version = sys.argv[2]
        print(pm.rollback(version))
    
    else:
        print(f"未知命令: {cmd}")


if __name__ == '__main__':
    main()