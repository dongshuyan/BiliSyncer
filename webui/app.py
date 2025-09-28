#!/usr/bin/env python3
"""
BiliSyncer WebUI
基于Flask的Web用户界面
"""

import os
import sys
import asyncio
import threading
import signal
import psutil
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


def filter_task_for_json(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """过滤任务数据中不可序列化的字段，用于JSON传输"""
    # 创建副本并移除不可序列化的字段
    filtered_task = task_data.copy()
    filtered_task.pop('thread', None)  # 移除Thread对象
    filtered_task.pop('process', None)  # 移除Process对象
    return filtered_task


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


@app.route('/api/stop_task/<task_id>', methods=['POST'])
def stop_task(task_id):
    """强制停止指定任务"""
    try:
        if task_id not in current_tasks:
            return jsonify({'success': False, 'message': '任务不存在'})
        
        task = current_tasks[task_id]
        
        # 检查任务状态
        if task['status'] in ['completed', 'error', 'stopped']:
            return jsonify({'success': False, 'message': '任务已经结束'})
        
        # 设置停止标志
        task['should_stop'] = True
        task['status'] = 'stopping'
        
        Logger.warning(f"正在停止任务 {task_id}")
        
        # 尝试终止相关进程
        if 'process' in task and task['process']:
            try:
                # 使用psutil强制终止进程及其子进程
                parent = psutil.Process(task['process'].pid)
                children = parent.children(recursive=True)
                
                # 先尝试优雅终止
                for child in children:
                    try:
                        child.terminate()
                    except psutil.NoSuchProcess:
                        pass
                
                parent.terminate()
                
                # 等待一秒，如果还没结束就强制杀死
                try:
                    parent.wait(timeout=1)
                except psutil.TimeoutExpired:
                    parent.kill()
                    for child in children:
                        try:
                            child.kill()
                        except psutil.NoSuchProcess:
                            pass
                
                Logger.info(f"已终止任务 {task_id} 的相关进程")
                
            except Exception as e:
                Logger.warning(f"终止进程时出现问题: {e}")
        
        # 通知前端任务状态更新
        socketio.emit('task_update', filter_task_for_json(task))
        
        return jsonify({'success': True, 'message': '任务停止请求已发送'})
        
    except Exception as e:
        Logger.error(f"停止任务失败: {e}")
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
    save_cover = data.get('save_cover', False)
    debug = data.get('debug', False)
    extra_args_from_config = data.get('extra_args', [])
    
    if not url:
        return jsonify({'success': False, 'message': '请输入下载URL'})
    
    # 判重1：是否已有相同URL正在下载/准备中
    for existing in current_tasks.values():
        try:
            if existing.get('url') == url and existing.get('status') in ['starting', 'running', 'stopping']:
                return jsonify({
                    'success': False,
                    'message': '该URL任务已在进行中',
                    'existing_task_id': existing.get('id'),
                    'status': existing.get('status')
                })
        except Exception:
            pass

    # 判重2：是否为历史任务（通过URL特征快速匹配）
    def _find_existing_task_dir_by_url(target_url: str, base_output_dir: str) -> Optional[Path]:
        try:
            scan_dir = Path(base_output_dir).expanduser()
            if not scan_dir.exists():
                return None
            
            # 从URL中提取关键信息用于快速匹配
            url_lower = target_url.lower()
            
            # 快速检查：只遍历目录名，不读取CSV文件
            for task_dir in scan_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                
                # 快速检查：目录名是否以有效前缀开头
                dir_name = task_dir.name
                valid_prefixes = ['投稿视频-', '番剧-', '收藏夹-', '视频列表-', '视频合集-', 'UP主-', '稍后再看-', '课程-']
                if not any(dir_name.startswith(prefix) for prefix in valid_prefixes):
                    continue
                
                # 快速检查：目录内是否有CSV文件（不读取内容）
                csv_files = list(task_dir.glob("??-??-??-??-??.csv"))
                if not csv_files:
                    continue
                
                # 通过URL特征进行快速匹配
                # 1. 如果是BV号视频，检查目录名是否包含BV号
                if 'bilibili.com/video/bv' in url_lower or 'bilibili.com/video/BV' in url_lower:
                    import re
                    bv_match = re.search(r'BV[a-zA-Z0-9]+', target_url)
                    if bv_match and bv_match.group() in dir_name:
                        return task_dir
                
                # 2. 如果是收藏夹，检查目录名是否包含收藏夹ID
                elif 'space.bilibili.com' in url_lower and 'favlist' in url_lower:
                    import re
                    fid_match = re.search(r'fid=(\d+)', target_url)
                    if fid_match and fid_match.group(1) in dir_name:
                        return task_dir
                
                # 3. 如果是UP主空间，检查目录名是否包含UID
                elif 'space.bilibili.com' in url_lower and '/favlist' not in url_lower:
                    import re
                    uid_match = re.search(r'space\.bilibili\.com/(\d+)', target_url)
                    if uid_match and uid_match.group(1) in dir_name:
                        return task_dir
                
                # 4. 如果是番剧，检查目录名是否包含番剧ID
                elif 'bilibili.com/bangumi' in url_lower:
                    import re
                    ss_match = re.search(r'ss(\d+)', target_url)
                    if ss_match and ss_match.group(1) in dir_name:
                        return task_dir
                
                # 5. 如果是课程，检查目录名是否包含课程ID
                elif 'bilibili.com/cheese' in url_lower:
                    import re
                    ep_match = re.search(r'ep(\d+)', target_url)
                    if ep_match and ep_match.group(1) in dir_name:
                        return task_dir
                
                # 6. 如果是稍后再看，直接匹配
                elif 'watchlater' in url_lower and dir_name.startswith('稍后再看-'):
                    return task_dir
                
        except Exception:
            return None
        return None

    existing_task_dir = _find_existing_task_dir_by_url(url, output_dir)

    task_counter += 1
    task_id = f"task_{task_counter}"
    
    # 准备下载参数
    extra_args = extra_args_from_config.copy() if extra_args_from_config else []
    if vip_strict:
        extra_args.append('--vip-strict')
    if save_cover:
        extra_args.append('--save-cover')
    if debug:
        extra_args.append('--debug')
    
    # 记录任务信息
    current_tasks[task_id] = {
        'id': task_id,
        'url': url,
        'output_dir': output_dir,
        'status': 'starting',
        'start_time': time.time(),
        'progress': 0,
        'progress_detail': {
            'downloaded': 0,
            'total': 0,
            'pending': 0
        },
        'should_stop': False,  # 停止标志
        'process': None,       # 当前进程引用
        'thread': None         # 线程引用
    }
    
    # 在后台线程中执行下载或更新
    def run_download():
        try:
            current_tasks[task_id]['status'] = 'running'
            socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
            
            # 设置Logger回调以捕获所有日志
            Logger.set_callback(create_web_logger_callback(task_id))
            
            # 创建下载器并执行：若发现历史任务目录，则走更新逻辑；否则正常下载
            if existing_task_dir is not None:
                current_tasks[task_id]['type'] = 'update_single'
                downloader = BatchDownloader(
                    output_dir=existing_task_dir.parent,
                    sessdata=cookie if cookie else None,
                    extra_args=extra_args,
                    original_url=None,
                    task_id=task_id,
                    task_control=current_tasks
                )
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(downloader.update_single_task(existing_task_dir))
                loop.close()
            else:
                downloader = BatchDownloader(
                    output_dir=Path(output_dir).expanduser(),
                    sessdata=cookie if cookie else None,
                    extra_args=extra_args,
                    original_url=url,
                    task_id=task_id,  # 传递任务ID以便检查停止标志
                    task_control=current_tasks  # 传递任务控制字典
                )
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(downloader.download_from_url(url))
                loop.close()
            
            # 检查是否被手动停止
            if current_tasks[task_id].get('should_stop', False):
                current_tasks[task_id]['status'] = 'stopped'
                Logger.warning(f"任务 {task_id} 已被手动停止")
            else:
                current_tasks[task_id]['status'] = 'completed'
                current_tasks[task_id]['progress'] = 100
                Logger.custom(f"任务 {task_id} 下载完成", "任务管理")
            
        except Exception as e:
            # 检查是否是因为停止导致的异常
            if current_tasks[task_id].get('should_stop', False):
                current_tasks[task_id]['status'] = 'stopped'
                Logger.warning(f"任务 {task_id} 已被手动停止")
            else:
                current_tasks[task_id]['status'] = 'error'
                current_tasks[task_id]['error'] = str(e)
                Logger.error(f"任务 {task_id} 失败: {e}")
        finally:
            # 清除Logger回调
            Logger.set_callback(None)
            # 清理进程引用
            current_tasks[task_id]['process'] = None
            socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
    
    thread = threading.Thread(target=run_download)
    thread.daemon = True
    current_tasks[task_id]['thread'] = thread  # 保存线程引用
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
    save_cover = data.get('save_cover', False)
    debug = data.get('debug', False)
    extra_args_from_config = data.get('extra_args', [])
    
    task_counter += 1
    task_id = f"update_{task_counter}"
    
    # 准备参数
    extra_args = extra_args_from_config.copy() if extra_args_from_config else []
    if vip_strict:
        extra_args.append('--vip-strict')
    if save_cover:
        extra_args.append('--save-cover')
    if debug:
        extra_args.append('--debug')
    
    # 记录任务信息
    current_tasks[task_id] = {
        'id': task_id,
        'type': 'update_all',
        'output_dir': output_dir,
        'status': 'starting',
        'start_time': time.time(),
        'progress': 0,
        'progress_detail': {
            'downloaded': 0,
            'total': 0,
            'pending': 0
        },
        'should_stop': False,  # 停止标志
        'process': None,       # 当前进程引用
        'thread': None         # 线程引用
    }
    
    # 在后台线程中执行更新
    def run_update():
        try:
            current_tasks[task_id]['status'] = 'running'
            socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
            
            # 设置Logger回调以捕获所有日志
            Logger.set_callback(create_web_logger_callback(task_id))
            
            # 创建下载器并执行批量更新
            downloader = BatchDownloader(
                output_dir=Path(output_dir).expanduser(),
                sessdata=cookie if cookie else None,
                extra_args=extra_args,
                original_url=None,
                task_id=task_id,  # 传递任务ID
                task_control=current_tasks  # 传递任务控制字典
            )
            
            # 在新的事件循环中运行异步任务
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(downloader.update_all_tasks())
            loop.close()
            
            # 检查是否被手动停止
            if current_tasks[task_id].get('should_stop', False):
                current_tasks[task_id]['status'] = 'stopped'
                Logger.warning(f"批量更新任务 {task_id} 已被手动停止")
            else:
                current_tasks[task_id]['status'] = 'completed'
                current_tasks[task_id]['progress'] = 100
                Logger.custom(f"批量更新任务 {task_id} 完成", "任务管理")
            
        except Exception as e:
            # 检查是否是因为停止导致的异常
            if current_tasks[task_id].get('should_stop', False):
                current_tasks[task_id]['status'] = 'stopped'
                Logger.warning(f"批量更新任务 {task_id} 已被手动停止")
            else:
                current_tasks[task_id]['status'] = 'error'
                current_tasks[task_id]['error'] = str(e)
                Logger.error(f"批量更新任务 {task_id} 失败: {e}")
        finally:
            # 清除Logger回调
            Logger.set_callback(None)
            # 清理进程引用
            current_tasks[task_id]['process'] = None
            socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
    
    thread = threading.Thread(target=run_update)
    thread.daemon = True
    current_tasks[task_id]['thread'] = thread  # 保存线程引用
    thread.start()
    
    return jsonify({
        'success': True, 
        'message': '批量更新任务已开始',
        'task_id': task_id
    })


@app.route('/api/update_selected', methods=['POST'])
def start_update_selected():
    """开始选择性更新任务"""
    global task_counter
    
    data = request.get_json() or {}
    task_paths = data.get('task_paths', [])
    cookie = data.get('cookie', '').strip()
    vip_strict = data.get('vip_strict', False)
    save_cover = data.get('save_cover', False)
    debug = data.get('debug', False)
    extra_args_from_config = data.get('extra_args', [])
    
    if not task_paths:
        return jsonify({'success': False, 'message': '请选择要更新的任务'})
    
    task_counter += 1
    task_id = f"update_selected_{task_counter}"
    
    # 准备参数
    extra_args = extra_args_from_config.copy() if extra_args_from_config else []
    if vip_strict:
        extra_args.append('--vip-strict')
    if save_cover:
        extra_args.append('--save-cover')
    if debug:
        extra_args.append('--debug')
    
    # 记录任务信息
    current_tasks[task_id] = {
        'id': task_id,
        'type': 'update_selected',
        'task_paths': task_paths,
        'status': 'starting',
        'start_time': time.time(),
        'progress': 0,
        'progress_detail': {
            'current_task': 0,
            'total_tasks': len(task_paths),
            'current_task_name': '',
            'completed_tasks': []
        },
        'should_stop': False,
        'process': None,
        'thread': None
    }
    
    # 在后台线程中执行更新
    def run_update():
        try:
            current_tasks[task_id]['status'] = 'running'
            socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
            
            # 设置Logger回调以捕获所有日志
            Logger.set_callback(create_web_logger_callback(task_id))
            
            completed_count = 0
            failed_count = 0
            
            for i, task_path in enumerate(task_paths):
                if current_tasks[task_id].get('should_stop', False):
                    Logger.warning(f"选择性更新任务 {task_id} 被手动停止")
                    break
                
                task_name = Path(task_path).name
                current_tasks[task_id]['progress_detail']['current_task'] = i + 1
                current_tasks[task_id]['progress_detail']['current_task_name'] = task_name
                current_tasks[task_id]['progress'] = int((i / len(task_paths)) * 100)
                socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
                
                Logger.info(f"[{i+1}/{len(task_paths)}] 开始更新任务: {task_name}")
                
                try:
                    # 创建下载器并执行单个任务更新
                    downloader = BatchDownloader(
                        output_dir=Path(task_path).parent,  # 使用任务目录的父目录
                        sessdata=cookie if cookie else None,
                        extra_args=extra_args,
                        original_url=None,
                        task_id=task_id,
                        task_control=current_tasks
                    )
                    
                    # 在新的事件循环中运行异步任务
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    await_task = loop.run_until_complete(downloader.update_single_task(Path(task_path)))
                    loop.close()
                    
                    completed_count += 1
                    # 防护性检查：确保progress_detail结构完整
                    if 'progress_detail' not in current_tasks[task_id]:
                        current_tasks[task_id]['progress_detail'] = {
                            'current_task': i + 1,
                            'total_tasks': len(task_paths),
                            'current_task_name': task_name,
                            'completed_tasks': []
                        }
                    elif 'completed_tasks' not in current_tasks[task_id]['progress_detail']:
                        current_tasks[task_id]['progress_detail']['completed_tasks'] = []
                    
                    current_tasks[task_id]['progress_detail']['completed_tasks'].append(task_name)
                    Logger.info(f"✅ 任务更新成功: {task_name}")
                    
                except Exception as e:
                    failed_count += 1
                    Logger.error(f"❌ 任务更新失败 {task_name}: {e}")
                    continue
            
            # 检查是否被手动停止
            if current_tasks[task_id].get('should_stop', False):
                current_tasks[task_id]['status'] = 'stopped'
                Logger.warning(f"选择性更新任务 {task_id} 已被手动停止")
            else:
                current_tasks[task_id]['status'] = 'completed'
                current_tasks[task_id]['progress'] = 100
                Logger.custom(f"选择性更新完成 - 成功: {completed_count}, 失败: {failed_count}, 总计: {len(task_paths)}", "选择性更新")
            
        except Exception as e:
            # 检查是否是因为停止导致的异常
            if current_tasks[task_id].get('should_stop', False):
                current_tasks[task_id]['status'] = 'stopped'
                Logger.warning(f"选择性更新任务 {task_id} 已被手动停止")
            else:
                current_tasks[task_id]['status'] = 'error'
                current_tasks[task_id]['error'] = str(e)
                Logger.error(f"选择性更新任务 {task_id} 失败: {e}")
        finally:
            # 清除Logger回调
            Logger.set_callback(None)
            # 清理进程引用
            current_tasks[task_id]['process'] = None
            socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
    
    thread = threading.Thread(target=run_update)
    thread.daemon = True
    current_tasks[task_id]['thread'] = thread
    thread.start()
    
    return jsonify({
        'success': True, 
        'message': f'选择性更新任务已开始，将更新 {len(task_paths)} 个任务',
        'task_id': task_id
    })


@app.route('/api/delete_all', methods=['POST'])
def start_delete_all():
    """开始批量删除任务的视频文件"""
    global task_counter
    
    data = request.get_json() or {}
    output_dir = data.get('output_dir', '~/Downloads').strip()
    
    task_counter += 1
    task_id = f"delete_{task_counter}"
    
    # 记录任务信息
    current_tasks[task_id] = {
        'id': task_id,
        'type': 'delete_all',
        'output_dir': output_dir,
        'status': 'starting',
        'start_time': time.time(),
        'progress': 0,
        'progress_detail': {
            'deleted': 0,
            'total': 0,
            'current_task': ''
        },
        'should_stop': False,
        'process': None,
        'thread': None
    }
    
    # 在后台线程中执行删除
    def run_delete():
        try:
            current_tasks[task_id]['status'] = 'running'
            socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
            
            # 设置Logger回调以捕获所有日志
            Logger.set_callback(create_web_logger_callback(task_id))
            
            # 创建下载器并执行批量删除
            downloader = BatchDownloader(
                output_dir=Path(output_dir).expanduser(),
                sessdata=None,
                extra_args=[],
                original_url=None,
                task_id=task_id,
                task_control=current_tasks
            )
            
            # 在新的事件循环中运行异步任务
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(downloader.delete_all_tasks())
            loop.close()
            
            # 检查是否被手动停止
            if current_tasks[task_id].get('should_stop', False):
                current_tasks[task_id]['status'] = 'stopped'
                Logger.warning(f"批量删除任务 {task_id} 已被手动停止")
            else:
                current_tasks[task_id]['status'] = 'completed'
                current_tasks[task_id]['progress'] = 100
                Logger.custom(f"批量删除任务 {task_id} 完成", "任务管理")
            
        except Exception as e:
            # 检查是否是因为停止导致的异常
            if current_tasks[task_id].get('should_stop', False):
                current_tasks[task_id]['status'] = 'stopped'
                Logger.warning(f"批量删除任务 {task_id} 已被手动停止")
            else:
                current_tasks[task_id]['status'] = 'error'
                current_tasks[task_id]['error'] = str(e)
                Logger.error(f"批量删除任务 {task_id} 失败: {e}")
        finally:
            # 清除Logger回调
            Logger.set_callback(None)
            # 清理进程引用
            current_tasks[task_id]['process'] = None
            socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
    
    thread = threading.Thread(target=run_delete)
    thread.daemon = True
    current_tasks[task_id]['thread'] = thread
    thread.start()
    
    return jsonify({
        'success': True, 
        'message': '批量删除任务已开始',
        'task_id': task_id
    })


@app.route('/api/delete_selected', methods=['POST'])
def start_delete_selected():
    """开始选择性删除任务的视频文件"""
    global task_counter
    
    data = request.get_json() or {}
    task_paths = data.get('task_paths', [])
    
    if not task_paths:
        return jsonify({'success': False, 'message': '请选择要删除的任务'})
    
    task_counter += 1
    task_id = f"delete_selected_{task_counter}"
    
    # 记录任务信息
    current_tasks[task_id] = {
        'id': task_id,
        'type': 'delete_selected',
        'task_paths': task_paths,
        'status': 'starting',
        'start_time': time.time(),
        'progress': 0,
        'progress_detail': {
            'current_task': 0,
            'total_tasks': len(task_paths),
            'current_task_name': '',
            'completed_tasks': []
        },
        'should_stop': False,
        'process': None,
        'thread': None
    }
    
    # 在后台线程中执行删除
    def run_delete():
        try:
            current_tasks[task_id]['status'] = 'running'
            socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
            
            # 设置Logger回调以捕获所有日志
            Logger.set_callback(create_web_logger_callback(task_id))
            
            completed_count = 0
            failed_count = 0
            
            for i, task_path in enumerate(task_paths):
                if current_tasks[task_id].get('should_stop', False):
                    Logger.warning(f"选择性删除任务 {task_id} 被手动停止")
                    break
                
                task_name = Path(task_path).name
                current_tasks[task_id]['progress_detail']['current_task'] = i + 1
                current_tasks[task_id]['progress_detail']['current_task_name'] = task_name
                current_tasks[task_id]['progress'] = int((i / len(task_paths)) * 100)
                socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
                
                Logger.info(f"[{i+1}/{len(task_paths)}] 开始删除任务: {task_name}")
                
                try:
                    # 创建下载器并执行单个任务删除
                    downloader = BatchDownloader(
                        output_dir=Path(task_path).parent,
                        sessdata=None,
                        extra_args=[],
                        original_url=None,
                        task_id=task_id,
                        task_control=current_tasks
                    )
                    
                    # 在新的事件循环中运行异步任务
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    await_task = loop.run_until_complete(downloader.delete_single_task(Path(task_path)))
                    loop.close()
                    
                    completed_count += 1
                    current_tasks[task_id]['progress_detail']['completed_tasks'].append({
                        'name': task_name,
                        'status': 'success'
                    })
                    Logger.info(f"✅ 删除任务成功: {task_name}")
                    
                except Exception as e:
                    failed_count += 1
                    current_tasks[task_id]['progress_detail']['completed_tasks'].append({
                        'name': task_name,
                        'status': 'error',
                        'error': str(e)
                    })
                    Logger.error(f"❌ 删除任务失败 {task_name}: {e}")
                    continue
            
            # 检查是否被手动停止
            if current_tasks[task_id].get('should_stop', False):
                current_tasks[task_id]['status'] = 'stopped'
                Logger.warning(f"选择性删除任务 {task_id} 已被手动停止")
            else:
                current_tasks[task_id]['status'] = 'completed'
                current_tasks[task_id]['progress'] = 100
                Logger.custom(f"选择性删除任务完成 - 成功: {completed_count}, 失败: {failed_count}", "任务管理")
            
        except Exception as e:
            # 检查是否是因为停止导致的异常
            if current_tasks[task_id].get('should_stop', False):
                current_tasks[task_id]['status'] = 'stopped'
                Logger.warning(f"选择性删除任务 {task_id} 已被手动停止")
            else:
                current_tasks[task_id]['status'] = 'error'
                current_tasks[task_id]['error'] = str(e)
                Logger.error(f"选择性删除任务 {task_id} 失败: {e}")
        finally:
            # 清除Logger回调
            Logger.set_callback(None)
            # 清理进程引用
            current_tasks[task_id]['process'] = None
            socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
    
    thread = threading.Thread(target=run_delete)
    thread.daemon = True
    current_tasks[task_id]['thread'] = thread
    thread.start()
    
    return jsonify({
        'success': True, 
        'message': f'选择性删除任务已开始，将删除 {len(task_paths)} 个任务的视频文件',
        'task_id': task_id
    })


@app.route('/api/tasks')
def get_tasks():
    """获取所有任务状态"""
    # 过滤所有任务的不可序列化字段
    filtered_tasks = [filter_task_for_json(task) for task in current_tasks.values()]
    return jsonify(filtered_tasks)


@app.route('/api/scan_tasks_with_progress', methods=['POST'])
def scan_tasks_with_progress():
    """扫描输出目录中的任务，支持实时进度更新"""
    global task_counter
    
    data = request.get_json() or {}
    output_dir = data.get('output_dir', '~/Downloads')
    
    task_counter += 1
    task_id = f"scan_{task_counter}"
    
    # 记录扫描任务信息
    current_tasks[task_id] = {
        'id': task_id,
        'type': 'scan',
        'output_dir': output_dir,
        'status': 'starting',
        'start_time': time.time(),
        'progress': 0,
        'progress_detail': {
            'current_dir': '',
            'scanned_count': 0,
            'total_dirs': 0,
            'found_tasks': []
        },
        'should_stop': False,
        'process': None,
        'thread': None
    }
    
    def run_scan():
        try:
            current_tasks[task_id]['status'] = 'running'
            socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
            
            # 设置Logger回调
            Logger.set_callback(create_web_logger_callback(task_id))
            
            scan_dir = Path(output_dir).expanduser()
            if not scan_dir.exists():
                raise Exception('目录不存在')
            
            # 创建BatchDownloader实例来使用筛选逻辑
            downloader = BatchDownloader(output_dir=scan_dir)
            
            # 获取所有目录
            all_dirs = [d for d in scan_dir.iterdir() if d.is_dir()]
            total_dirs = len(all_dirs)
            
            current_tasks[task_id]['progress_detail']['total_dirs'] = total_dirs
            socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
            
            Logger.info(f"开始扫描目录: {output_dir}")
            Logger.info(f"发现 {total_dirs} 个子目录")
            
            tasks = []
            
            for i, task_dir in enumerate(all_dirs):
                if current_tasks[task_id].get('should_stop', False):
                    Logger.warning("扫描任务被手动停止")
                    break
                
                # 更新进度
                current_tasks[task_id]['progress_detail']['current_dir'] = task_dir.name
                current_tasks[task_id]['progress_detail']['scanned_count'] = i + 1
                current_tasks[task_id]['progress'] = int(((i + 1) / total_dirs) * 100)
                socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
                
                Logger.info(f"[{i+1}/{total_dirs}] 扫描目录: {task_dir.name}")
                
                try:
                    # 使用新的筛选逻辑，只处理有效的任务目录
                    if downloader._is_valid_task_directory(task_dir):
                        csv_manager = CSVManager(task_dir)
                        original_url = csv_manager.get_original_url()
                        stats = csv_manager.get_download_stats()
                        
                        # 识别任务类型
                        task_type = _identify_task_type(task_dir.name)
                        
                        task_info = {
                            'name': task_dir.name,
                            'path': str(task_dir),
                            'url': original_url,
                            'type': task_type,
                            'total': stats['total'],
                            'downloaded': stats['downloaded'],
                            'pending': stats['pending']
                        }
                        
                        tasks.append(task_info)
                        current_tasks[task_id]['progress_detail']['found_tasks'].append(task_info)
                        
                        Logger.info(f"✅ 发现有效任务: {task_dir.name} ({task_type})")
                        
                        # 实时发送发现的任务
                        socketio.emit('scan_task_found', task_info)
                    else:
                        Logger.debug(f"跳过无效目录: {task_dir.name}")
                        
                except Exception as e:
                    Logger.error(f"扫描目录 {task_dir.name} 时出错: {e}")
                    continue
            
            # 扫描完成
            if current_tasks[task_id].get('should_stop', False):
                current_tasks[task_id]['status'] = 'stopped'
                Logger.warning("扫描任务已停止")
            else:
                current_tasks[task_id]['status'] = 'completed'
                current_tasks[task_id]['progress'] = 100
                Logger.custom(f"扫描完成 - 发现 {len(tasks)} 个有效任务", "任务扫描")
            
            # 发送最终结果
            socketio.emit('scan_completed', {
                'success': True,
                'tasks': tasks,
                'task_id': task_id
            })
            
        except Exception as e:
            current_tasks[task_id]['status'] = 'error'
            current_tasks[task_id]['error'] = str(e)
            Logger.error(f"扫描任务失败: {e}")
            
            socketio.emit('scan_completed', {
                'success': False,
                'message': str(e),
                'task_id': task_id
            })
        finally:
            # 清除Logger回调
            Logger.set_callback(None)
            # 清理进程引用
            current_tasks[task_id]['process'] = None
            socketio.emit('task_update', filter_task_for_json(current_tasks[task_id]))
    
    thread = threading.Thread(target=run_scan)
    thread.daemon = True
    current_tasks[task_id]['thread'] = thread
    thread.start()
    
    return jsonify({
        'success': True,
        'message': '扫描任务已开始',
        'task_id': task_id
    })


@app.route('/api/scan_tasks')
def scan_tasks():
    """扫描输出目录中的任务"""
    output_dir = request.args.get('output_dir', '~/Downloads')
    
    try:
        scan_dir = Path(output_dir).expanduser()
        if not scan_dir.exists():
            return jsonify({'success': False, 'message': '目录不存在'})
        
        # 创建BatchDownloader实例来使用筛选逻辑
        downloader = BatchDownloader(output_dir=scan_dir)
        
        tasks = []
        all_dirs = [d for d in scan_dir.iterdir() if d.is_dir()]
        
        for task_dir in all_dirs:
            # 使用新的筛选逻辑，只处理有效的任务目录
            if downloader._is_valid_task_directory(task_dir):
                csv_manager = CSVManager(task_dir)
                original_url = csv_manager.get_original_url()
                stats = csv_manager.get_download_stats()
                
                # 识别任务类型
                task_type = _identify_task_type(task_dir.name)
                
                tasks.append({
                    'name': task_dir.name,
                    'path': str(task_dir),
                    'url': original_url,
                    'type': task_type,
                    'total': stats['total'],
                    'downloaded': stats['downloaded'],
                    'pending': stats['pending']
                })
        
        return jsonify({'success': True, 'tasks': tasks})
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


def _identify_task_type(dir_name: str) -> str:
    """根据目录名识别任务类型"""
    if dir_name.startswith('投稿视频-'):
        return '投稿视频'
    elif dir_name.startswith('番剧-'):
        return '番剧'
    elif dir_name.startswith('课程-'):
        return '课程'
    elif dir_name.startswith('收藏夹-'):
        return '收藏夹'
    elif dir_name.startswith('视频列表-'):
        return '视频列表'
    elif dir_name.startswith('视频合集-'):
        return '视频合集'
    elif dir_name.startswith('UP主-'):
        return 'UP主'
    elif dir_name.startswith('稍后再看-'):
        return '稍后再看'
    else:
        return '未知'


@socketio.on('connect')
def handle_connect():
    """WebSocket连接处理"""
    emit('connected', {'message': '已连接到BiliSyncer WebUI'})


@socketio.on('get_task_status')
def handle_get_task_status():
    """获取任务状态"""
    # 过滤所有任务的不可序列化字段
    filtered_tasks = [filter_task_for_json(task) for task in current_tasks.values()]
    emit('task_status', filtered_tasks)


if __name__ == '__main__':
    print("启动 BiliSyncer WebUI...")
    print("访问地址: http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False) 