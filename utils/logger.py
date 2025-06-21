"""
简化版日志模块
"""

import sys
from datetime import datetime
from typing import Literal, Callable, Optional

LogLevel = Literal["INFO", "WARNING", "ERROR", "DEBUG"]


class Logger:
    """简化版日志器"""
    
    # 全局回调函数，用于WebUI等场景
    _callback: Optional[Callable] = None
    
    @classmethod
    def set_callback(cls, callback: Optional[Callable]):
        """设置日志回调函数"""
        cls._callback = callback
    
    @classmethod
    def _send_to_callback(cls, level: str, message: str, category: Optional[str] = None):
        """发送日志到回调函数"""
        if cls._callback:
            try:
                cls._callback(level, message, category)
            except Exception:
                pass  # 忽略回调错误，避免影响主程序
    
    @staticmethod
    def _format_message(level: LogLevel, message: str) -> str:
        """格式化日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        colors = {
            "INFO": "\033[92m",     # 绿色
            "WARNING": "\033[93m",  # 黄色
            "ERROR": "\033[91m",    # 红色
            "DEBUG": "\033[94m",    # 蓝色
        }
        reset = "\033[0m"
        
        color = colors.get(level, "")
        return f"[{timestamp}] {color}{level}{reset}: {message}"
    
    @classmethod
    def info(cls, message: str):
        """输出信息日志"""
        print(cls._format_message("INFO", message))
        cls._send_to_callback("info", message)
    
    @classmethod
    def warning(cls, message: str):
        """输出警告日志"""
        print(cls._format_message("WARNING", message))
        cls._send_to_callback("warning", message)
    
    @classmethod
    def error(cls, message: str):
        """输出错误日志"""
        print(cls._format_message("ERROR", message), file=sys.stderr)
        cls._send_to_callback("error", message)
    
    @classmethod
    def debug(cls, message: str):
        """输出调试日志"""
        print(cls._format_message("DEBUG", message))
        cls._send_to_callback("debug", message)
    
    @classmethod
    def custom(cls, title: str, badge: str):
        """输出自定义格式的日志"""
        print(f"[{badge}] {title}")
        cls._send_to_callback("custom", title, badge) 