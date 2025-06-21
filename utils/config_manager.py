#!/usr/bin/env python3
"""
配置文件管理模块
"""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

class ConfigManager:
    """配置文件管理器"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir if config_dir is not None else Path(__file__).parent.parent / "config"
        self.config_dir.mkdir(exist_ok=True)
    
    def list_configs(self) -> List[Dict[str, Any]]:
        """列出所有配置文件"""
        configs = []
        
        for config_file in self.config_dir.glob("*.yaml"):
            try:
                config = self.load_config(config_file.stem)
                if config:
                    config['filename'] = config_file.stem
                    configs.append(config)
            except Exception as e:
                print(f"警告: 无法加载配置文件 {config_file}: {e}")
        
        return configs
    
    def load_config(self, name: str) -> Optional[Dict[str, Any]]:
        """加载指定配置文件"""
        config_file = self.config_dir / f"{name}.yaml"
        
        if not config_file.exists():
            return None
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                return config
        except Exception as e:
            print(f"错误: 无法读取配置文件 {config_file}: {e}")
            return None
    
    def save_config(self, name: str, config: Dict[str, Any]) -> bool:
        """保存配置文件"""
        config_file = self.config_dir / f"{name}.yaml"
        
        # 更新时间戳
        config['updated_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if 'created_at' not in config:
            config['created_at'] = config['updated_at']
        
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, 
                         allow_unicode=True, indent=2)
            return True
        except Exception as e:
            print(f"错误: 无法保存配置文件 {config_file}: {e}")
            return False
    
    def delete_config(self, name: str) -> bool:
        """删除配置文件"""
        config_file = self.config_dir / f"{name}.yaml"
        
        if not config_file.exists():
            return False
        
        try:
            config_file.unlink()
            return True
        except Exception as e:
            print(f"错误: 无法删除配置文件 {config_file}: {e}")
            return False
    
    def create_default_config(self) -> Dict[str, Any]:
        """创建默认配置"""
        return {
            'name': '新配置',
            'description': '用户自定义配置',
            'output_dir': '~/Downloads',
            'sessdata': '',
            'vip_strict': False,
            'debug': False,
            'extra_args': []
        }
    
    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """验证配置文件格式"""
        errors = []
        
        required_fields = ['name', 'output_dir']
        for field in required_fields:
            if field not in config:
                errors.append(f"缺少必需字段: {field}")
        
        if 'name' in config and not isinstance(config['name'], str):
            errors.append("name 必须是字符串")
        
        if 'output_dir' in config and not isinstance(config['output_dir'], str):
            errors.append("output_dir 必须是字符串")
        
        if 'vip_strict' in config and not isinstance(config['vip_strict'], bool):
            errors.append("vip_strict 必须是布尔值")
        
        if 'debug' in config and not isinstance(config['debug'], bool):
            errors.append("debug 必须是布尔值")
        
        if 'extra_args' in config and not isinstance(config['extra_args'], list):
            errors.append("extra_args 必须是列表")
        
        return errors
    
    def get_config_for_download(self, name: str) -> Optional[Dict[str, Any]]:
        """获取用于下载的配置参数"""
        config = self.load_config(name)
        if not config:
            return None
        
        return {
            'output_dir': config.get('output_dir', '~/Downloads'),
            'sessdata': config.get('sessdata', ''),
            'vip_strict': config.get('vip_strict', False),
            'debug': config.get('debug', False),
            'extra_args': config.get('extra_args', [])
        }


def get_config_manager() -> ConfigManager:
    """获取配置管理器单例"""
    return ConfigManager() 