#!/usr/bin/env python3
"""
BiliSyncer WebUI 启动脚本
"""

import sys
import os
import socket
import random
import webbrowser
import threading
import time
from pathlib import Path

def find_available_port(start_port=15000, max_port=65535):
    """查找可用端口"""
    for _ in range(100):  # 最多尝试100次
        port = random.randint(start_port, max_port)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return port
            except OSError:
                continue
    
    # 如果随机选择失败，按顺序查找
    for port in range(start_port, max_port + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return port
            except OSError:
                continue
    
    raise RuntimeError("无法找到可用端口")

def open_browser(url, delay=2):
    """延迟打开浏览器"""
    time.sleep(delay)
    webbrowser.open(url)

def main():
    # 检查依赖
    try:
        import flask
        import flask_socketio
    except ImportError as e:
        print(f"缺少依赖: {e}")
        print("请先安装WebUI依赖:")
        print("pip install -r webui_requirements.txt")
        sys.exit(1)
    
    # 设置工作目录
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    # 查找可用端口
    try:
        port = find_available_port()
    except RuntimeError as e:
        print(f"❌ {e}")
        sys.exit(1)
    
    # 启动WebUI
    from webui.app import app, socketio
    
    url = f"http://localhost:{port}"
    
    print("=" * 60)
    print("🎉 BiliSyncer WebUI 启动中...")
    print("📂 工作目录:", script_dir)
    print(f"🌐 访问地址: {url}")
    print(f"🔌 使用端口: {port}")
    print("🔄 支持功能:")
    print("   • 批量下载 B站视频/收藏夹/空间等")
    print("   • 断点续传和任务管理")
    print("   • 批量更新所有任务")
    print("   • 实时日志显示")
    print("=" * 60)
    print("🚀 正在自动打开浏览器...")
    
    # 启动浏览器打开页面（在后台线程中延迟执行）
    browser_thread = threading.Thread(target=open_browser, args=(url,))
    browser_thread.daemon = True
    browser_thread.start()
    
    try:
        socketio.run(app, host='0.0.0.0', port=port, debug=False)
    except KeyboardInterrupt:
        print("\n👋 WebUI已关闭")
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 