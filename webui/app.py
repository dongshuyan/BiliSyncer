#!/usr/bin/env python3
"""
BiliSyncer WebUI
基于Flask的Web用户界面
"""

import os
import sys
import asyncio
import threading
from pathlib import Path
from typing import Dict, Any, Optional

from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import time

# 添加上级目录到Python路径，以便导入现有模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from batch_downloader import BatchDownloader
from utils.logger import Logger
from utils.csv_manager import CSVManager
from utils.config_manager import ConfigManager

app = Flask(__name__)
app.config['SECRET_KEY'] = 'BiliSyncer-webui-secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# 全局变量存储当前任务状态
current_tasks: Dict[str, Dict[str, Any]] = {}
task_counter = 0


def create_web_logger_callback(task_id: Optional[str] = None):
    """创建WebLogger回调函数"""
    def web_logger_callback(level: str, message: str, category: Optional[str] = None):
        """WebLogger回调函数，发送日志到前端"""
        socketio.emit('log_message', {
            'level': level,
            'message': message,
            'category': category,
            'timestamp': time.strftime('%H:%M:%S'),
            'task_id': task_id
        })
    return web_logger_callback


@app.route('/')
def index():
    """主页 - 下载页面"""
    return render_template('index.html')


@app.route('/update')
def update_page():
    """批量更新页面"""
    return render_template('update.html')


@app.route('/tasks')
def tasks_page():
    """任务管理页面"""
    return render_template('tasks.html')


@app.route('/config')
def config_page():
    """配置管理页面"""
    return render_template('config.html')


@app.route('/api/configs', methods=['GET'])
def get_configs():
    """获取所有配置文件"""
    try:
        config_manager = ConfigManager()
        configs = config_manager.list_configs()
        return jsonify({'success': True, 'configs': configs})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/config/<name>', methods=['GET'])
def get_config(name):
    """获取指定配置文件"""
    try:
        config_manager = ConfigManager()
        config = config_manager.load_config(name)
        if config:
            return jsonify({'success': True, 'config': config})
        else:
            return jsonify({'success': False, 'message': '配置文件不存在'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/config/<name>', methods=['POST'])
def save_config(name):
    """保存配置文件"""
    try:
        data = request.get_json() or {}
        config_manager = ConfigManager()
        
        # 验证配置
        errors = config_manager.validate_config(data)
        if errors:
            return jsonify({'success': False, 'message': '配置验证失败', 'errors': errors})
        
        success = config_manager.save_config(name, data)
        if success:
            return jsonify({'success': True, 'message': '配置保存成功'})
        else:
            return jsonify({'success': False, 'message': '配置保存失败'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/config/<name>', methods=['DELETE'])
def delete_config(name):
    """删除配置文件"""
    try:
        # 禁止删除默认配置
        if name == 'default':
            return jsonify({'success': False, 'message': '默认配置不能删除，只能修改'})
        
        config_manager = ConfigManager()
        success = config_manager.delete_config(name)
        if success:
            return jsonify({'success': True, 'message': '配置删除成功'})
        else:
            return jsonify({'success': False, 'message': '配置文件不存在或删除失败'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/download', methods=['POST'])
def start_download():
    """开始下载任务"""
    global task_counter
    
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    output_dir = data.get('output_dir', '~/Downloads').strip()
    cookie = data.get('cookie', '').strip()
    vip_strict = data.get('vip_strict', False)
    debug = data.get('debug', False)
    extra_args_from_config = data.get('extra_args', [])
    
    if not url:
        return jsonify({'success': False, 'message': '请输入下载URL'})
    
    task_counter += 1
    task_id = f"task_{task_counter}"
    
    # 准备下载参数
    extra_args = extra_args_from_config.copy() if extra_args_from_config else []
    if vip_strict:
        extra_args.append('--vip-strict')
    if debug:
        extra_args.append('--debug')
    
    # 记录任务信息
    current_tasks[task_id] = {
        'id': task_id,
        'url': url,
        'output_dir': output_dir,
        'status': 'starting',
        'start_time': time.time(),
        'progress': 0
    }
    
    # 在后台线程中执行下载
    def run_download():
        try:
            current_tasks[task_id]['status'] = 'running'
            socketio.emit('task_update', current_tasks[task_id])
            
            # 设置Logger回调以捕获所有日志
            Logger.set_callback(create_web_logger_callback(task_id))
            
            # 创建下载器并执行
            downloader = BatchDownloader(
                output_dir=Path(output_dir).expanduser(),
                sessdata=cookie if cookie else None,
                extra_args=extra_args,
                original_url=url
            )
            
            # 在新的事件循环中运行异步任务
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(downloader.download_from_url(url))
            loop.close()
            
            current_tasks[task_id]['status'] = 'completed'
            current_tasks[task_id]['progress'] = 100
            Logger.custom(f"任务 {task_id} 下载完成", "任务管理")
            
        except Exception as e:
            current_tasks[task_id]['status'] = 'error'
            current_tasks[task_id]['error'] = str(e)
            Logger.error(f"任务 {task_id} 失败: {e}")
        finally:
            # 清除Logger回调
            Logger.set_callback(None)
            socketio.emit('task_update', current_tasks[task_id])
    
    thread = threading.Thread(target=run_download)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True, 
        'message': '下载任务已开始',
        'task_id': task_id
    })


@app.route('/api/update_all', methods=['POST'])
def start_update_all():
    """开始批量更新任务"""
    global task_counter
    
    data = request.get_json() or {}
    output_dir = data.get('output_dir', '~/Downloads').strip()
    cookie = data.get('cookie', '').strip()
    vip_strict = data.get('vip_strict', False)
    debug = data.get('debug', False)
    extra_args_from_config = data.get('extra_args', [])
    
    task_counter += 1
    task_id = f"update_{task_counter}"
    
    # 准备参数
    extra_args = extra_args_from_config.copy() if extra_args_from_config else []
    if vip_strict:
        extra_args.append('--vip-strict')
    if debug:
        extra_args.append('--debug')
    
    # 记录任务信息
    current_tasks[task_id] = {
        'id': task_id,
        'type': 'update_all',
        'output_dir': output_dir,
        'status': 'starting',
        'start_time': time.time(),
        'progress': 0
    }
    
    # 在后台线程中执行更新
    def run_update():
        try:
            current_tasks[task_id]['status'] = 'running'
            socketio.emit('task_update', current_tasks[task_id])
            
            # 设置Logger回调以捕获所有日志
            Logger.set_callback(create_web_logger_callback(task_id))
            
            # 创建下载器并执行批量更新
            downloader = BatchDownloader(
                output_dir=Path(output_dir).expanduser(),
                sessdata=cookie if cookie else None,
                extra_args=extra_args,
                original_url=None
            )
            
            # 在新的事件循环中运行异步任务
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(downloader.update_all_tasks())
            loop.close()
            
            current_tasks[task_id]['status'] = 'completed'
            current_tasks[task_id]['progress'] = 100
            Logger.custom(f"批量更新任务 {task_id} 完成", "任务管理")
            
        except Exception as e:
            current_tasks[task_id]['status'] = 'error'
            current_tasks[task_id]['error'] = str(e)
            Logger.error(f"批量更新任务 {task_id} 失败: {e}")
        finally:
            # 清除Logger回调
            Logger.set_callback(None)
            socketio.emit('task_update', current_tasks[task_id])
    
    thread = threading.Thread(target=run_update)
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True, 
        'message': '批量更新任务已开始',
        'task_id': task_id
    })


@app.route('/api/tasks')
def get_tasks():
    """获取所有任务状态"""
    return jsonify(list(current_tasks.values()))


@app.route('/api/scan_tasks')
def scan_tasks():
    """扫描输出目录中的任务"""
    output_dir = request.args.get('output_dir', '~/Downloads')
    
    try:
        scan_dir = Path(output_dir).expanduser()
        if not scan_dir.exists():
            return jsonify({'success': False, 'message': '目录不存在'})
        
        tasks = []
        for task_dir in scan_dir.iterdir():
            if task_dir.is_dir():
                csv_manager = CSVManager(task_dir)
                original_url = csv_manager.get_original_url()
                stats = csv_manager.get_download_stats()
                
                tasks.append({
                    'name': task_dir.name,
                    'path': str(task_dir),
                    'url': original_url,
                    'total': stats['total'],
                    'downloaded': stats['downloaded'],
                    'pending': stats['pending']
                })
        
        return jsonify({'success': True, 'tasks': tasks})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@socketio.on('connect')
def handle_connect():
    """WebSocket连接处理"""
    emit('connected', {'message': '已连接到BiliSyncer WebUI'})


@socketio.on('get_task_status')
def handle_get_task_status():
    """获取任务状态"""
    emit('task_status', list(current_tasks.values()))


if __name__ == '__main__':
    print("启动 BiliSyncer WebUI...")
    print("访问地址: http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False) 