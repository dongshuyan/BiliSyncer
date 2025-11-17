"""
批量下载器
"""

import asyncio
import subprocess
import sys
import shutil
import glob
from pathlib import Path
from typing import Optional, List, Dict, Any
import re
import time

from utils.types import VideoListData, VideoInfo, DownloadOptions, AId, BvId, CId
from utils.fetcher import Fetcher
from utils.logger import Logger
from utils.csv_manager import CSVManager
from utils.constants import TASK_FOLDER_PREFIXES
from utils.anti_risk_manager import get_anti_risk_manager
from extractors import extract_video_list, extract_video_list_incremental
from api.bilibili import (
    RISK_CONTROL_DETECTED,
    get_ugc_video_list,
    get_bangumi_episode_info,
    get_cheese_episode_info,
)


class BatchDownloader:
    """批量下载器"""
    
    def __init__(self, output_dir: Path, sessdata: Optional[str] = None, extra_args: Optional[List[str]] = None, original_url: Optional[str] = None, task_id: Optional[str] = None, task_control: Optional[Dict] = None):
        """初始化批量下载器"""
        self.output_dir = output_dir
        self.sessdata = sessdata
        self.extra_args = extra_args or []
        self.original_url = original_url
        self.task_id = task_id
        self.task_control = task_control or {}
        self.fetcher = Fetcher(sessdata=sessdata)
        self.csv_manager = None  # 稍后根据任务创建
        self.anti_risk_manager = get_anti_risk_manager()
    
    def _should_stop(self) -> bool:
        """检查是否应该停止任务"""
        if self.task_id and self.task_control:
            return self.task_control.get(self.task_id, {}).get('should_stop', False)
        return False
    
    def _update_progress(self) -> None:
        """更新任务进度"""
        if not self.task_id or not self.task_control or not self.csv_manager:
            return
        
        try:
            # 获取下载统计信息
            stats = self.csv_manager.get_download_stats()
            total = stats['total']
            downloaded = stats['downloaded']
            
            if total > 0:
                progress = int((downloaded / total) * 100)
                
                # 更新任务控制字典中的进度
                if self.task_id in self.task_control:
                    self.task_control[self.task_id]['progress'] = progress
                    self.task_control[self.task_id]['progress_detail'] = {
                        'downloaded': downloaded,
                        'total': total,
                        'pending': stats['pending']
                    }
                    
                    # 如果有WebSocket连接，推送进度更新
                    try:
                        import sys
                        if 'webui.app' in sys.modules:
                            webui_app = sys.modules['webui.app']
                            if hasattr(webui_app, 'socketio') and hasattr(webui_app, 'filter_task_for_json'):
                                webui_app.socketio.emit('task_progress', 
                                    webui_app.filter_task_for_json(self.task_control[self.task_id]))
                    except Exception:
                        # 如果不在WebUI环境中运行或出现错误，忽略WebSocket推送
                        pass
                    
                Logger.debug(f"任务进度更新: {downloaded}/{total} ({progress}%)")
        except Exception as e:
            Logger.error(f"更新进度失败: {e}")
    
    async def download_from_url(self, url: str) -> None:
        """从URL开始批量下载"""
        async with self.fetcher:
            try:
                # 步骤1-4: 解析URL并获取基本信息
                Logger.info("分析URL类型和获取基本信息...")
                video_list = await extract_video_list(self.fetcher, url)
                task_name = video_list["title"]
                Logger.info(f"任务名称: {task_name}")
                
                # 步骤5: 确定"带名称的输出文件夹"
                task_output_dir = self.output_dir / task_name
                task_output_dir.mkdir(parents=True, exist_ok=True)
                self.csv_manager = CSVManager(task_output_dir)
                
                Logger.info(f"任务输出目录: {task_output_dir}")
                
                # 步骤6: 检查是否存在CSV文件
                existing_csv_videos = self.csv_manager.load_video_list()
                videos_to_download = []
                
                if existing_csv_videos:
                    Logger.info("发现现有CSV文件，检查下载状态...")
                    
                    # 步骤6.1: 从CSV获取未完成的下载
                    pending_videos = self.csv_manager.get_pending_videos()
                    
                    if pending_videos:
                        # 步骤6.1.1: 有未完成的下载
                        Logger.info(f"发现 {len(pending_videos)} 个未完成的下载，继续下载任务")
                        videos_to_download = [self._csv_to_video_info(data) for data in pending_videos]
                        
                    else:
                        # 步骤6.1.2: 所有视频都已完成，检查是否有新增视频
                        Logger.info("所有视频已下载完成，检查是否有新增视频...")
                        current_videos = video_list["videos"]
                        
                        # 对比CSV中的视频和当前获取的视频
                        csv_video_urls = {video['video_url'] for video in existing_csv_videos}
                        current_video_urls = {self._get_video_url(video) for video in current_videos}
                        
                        new_video_urls = current_video_urls - csv_video_urls
                        
                        if new_video_urls:
                            Logger.info(f"发现 {len(new_video_urls)} 个新增视频，更新CSV文件")
                            # 更新CSV文件（保持现有下载状态）
                            update_url = self.original_url or url
                            self.csv_manager.update_video_list(current_videos, update_url)
                            # 只下载新增的视频
                            videos_to_download = [v for v in current_videos if self._get_video_url(v) in new_video_urls]
                        else:
                            # 步骤6.1.3: 没有新增视频，任务完成
                            Logger.info("没有发现新增视频，所有任务已完成！")
                            return
                
                else:
                    # 步骤6.2: 没有CSV文件，首次下载
                    Logger.info("首次下载，创建CSV文件...")
                    videos_to_download = video_list["videos"]
                    self.csv_manager.save_video_list(videos_to_download, self.original_url)
                
                if not videos_to_download:
                    Logger.info("没有需要下载的视频")
                    return
                
                # 初始化进度（CSV文件已创建，获取初始进度）
                self._update_progress()
                
                Logger.custom(f"{task_name} ({len(videos_to_download)}个视频)", "批量下载")
                
                # 步骤7: 逐个下载
                await self._download_videos(videos_to_download, url)
                
            except Exception as e:
                Logger.error(f"批量下载失败: {e}")
                raise
    
    async def update_all_tasks(self) -> None:
        """更新所有任务：扫描输出目录下的所有任务并检查更新"""
        try:
            # 检查风控状态
            if self.anti_risk_manager.is_risk_controlled:
                Logger.info("当前处于风控状态，检查风控是否已解除...")
                risk_resolved = await self.anti_risk_manager.check_risk_resolved(self.fetcher)
                if not risk_resolved:
                    Logger.warning("风控未解除，跳过批量更新")
                    return
                else:
                    Logger.info("风控已解除，继续批量更新")
            
            # 扫描所有一级子目录
            all_dirs = [d for d in self.output_dir.iterdir() if d.is_dir()]
            
            if not all_dirs:
                Logger.info("未找到任何目录")
                return
            
            # 筛选符合条件的任务目录
            task_dirs = []
            invalid_dirs = []
            
            for dir_path in all_dirs:
                if self._is_valid_task_directory(dir_path):
                    task_dirs.append(dir_path)
                else:
                    invalid_dirs.append(dir_path)
                    Logger.debug(f"跳过不符合条件的目录: {dir_path.name}")
            
            if invalid_dirs:
                Logger.info(f"跳过 {len(invalid_dirs)} 个不符合条件的目录")
            
            if not task_dirs:
                Logger.info("未找到符合条件的任务目录")
                return
            
            Logger.info(f"发现 {len(task_dirs)} 个任务目录")
            
            # 使用任务队列机制处理风控等待
            await self._process_tasks_with_risk_control(task_dirs)
            
        except Exception as e:
            Logger.error(f"批量更新失败: {e}")
            raise
    
    async def _process_tasks_with_risk_control(self, task_dirs: List[Path]) -> None:
        """使用任务队列机制处理风控等待"""
        pending_tasks = list(task_dirs)  # 待处理任务队列
        completed_tasks = []  # 已完成任务
        error_count = 0
        
        Logger.info(f"开始处理 {len(pending_tasks)} 个任务")
        
        while pending_tasks:
            # 检查是否应该停止
            if self._should_stop():
                Logger.warning("任务被手动停止")
                break
            
            # 检查风控状态
            if self.anti_risk_manager.is_risk_controlled:
                Logger.info("检测到风控状态，等待风控解除...")
                await self._wait_for_risk_control_resolution()
                if self.anti_risk_manager.is_risk_controlled:
                    Logger.warning("风控仍未解除，暂停处理剩余任务")
                    break
            
            # 处理当前任务
            current_task = pending_tasks[0]
            Logger.info(f"处理任务: {current_task.name}")
            
            try:
                await self._update_single_task_directory(current_task)
                completed_tasks.append(current_task)
                pending_tasks.remove(current_task)
                Logger.info(f"✅ 任务完成: {current_task.name}")
                
            except Exception as e:
                error_msg = str(e)
                error_type = type(e).__name__
                
                # 检查是否为风控异常
                if "风控检测" in error_msg:
                    Logger.warning(f"任务 {current_task.name} 遇到风控，暂停处理")
                    # 不移除任务，等待风控解除后重新处理
                    break
                else:
                    error_count += 1
                    Logger.error(f"❌ 任务失败 {current_task.name} ({error_type}): {e}")
                    
                    # 根据错误类型提供建议
                    if "CSV" in error_msg or "encoding" in error_msg.lower():
                        Logger.warning(f"   建议：检查 {current_task.name} 目录下的CSV文件格式和编码")
                    elif "URL" in error_msg or "network" in error_msg.lower():
                        Logger.warning(f"   建议：检查网络连接和原始URL的有效性")
                    elif "permission" in error_msg.lower():
                        Logger.warning(f"   建议：检查 {current_task.name} 目录的读写权限")
                    
                    # 移除失败的任务，避免无限循环
                    pending_tasks.remove(current_task)
                    continue
        
        # 显示完成统计
        total_tasks = len(task_dirs)
        completed_count = len(completed_tasks)
        remaining_count = len(pending_tasks)
        
        Logger.custom(f"批量更新完成 - 成功: {completed_count}, 失败: {error_count}, 剩余: {remaining_count}, 总计: {total_tasks}", "批量更新")
        
        if remaining_count > 0:
            Logger.warning(f"有 {remaining_count} 个任务因风控或其他原因未完成，可稍后重新执行批量更新")
    
    async def _wait_for_risk_control_resolution(self) -> None:
        """等待风控解除（使用指数退避策略）"""
        max_attempts = 6  # 最多尝试6次
        base_delay = 60  # 基础延迟1分钟
        
        for attempt in range(max_attempts):
            Logger.info(f"等待风控解除... (第 {attempt + 1}/{max_attempts} 次尝试)")
            
            # 检查风控是否已解除
            risk_resolved = await self.anti_risk_manager.check_risk_resolved(self.fetcher)
            if risk_resolved:
                Logger.info("风控已解除，继续处理任务")
                return
            
            # 如果不是最后一次尝试，等待指数退避时间
            if attempt < max_attempts - 1:
                delay_time = base_delay * (2 ** attempt)  # 1分钟、2分钟、4分钟、8分钟、16分钟
                Logger.info(f"风控未解除，等待 {delay_time} 秒后进行第 {attempt + 2} 次尝试...")
                await asyncio.sleep(delay_time)
        
        Logger.warning(f"等待风控解除超时（已尝试 {max_attempts} 次），暂停处理")
    
    async def update_single_task(self, task_directory: Path) -> None:
        """定向更新单个任务目录"""
        try:
            # 验证任务目录是否存在
            if not task_directory.exists():
                Logger.error(f"指定的任务目录不存在: {task_directory}")
                return
            
            if not task_directory.is_dir():
                Logger.error(f"指定的路径不是目录: {task_directory}")
                return
            
            # 验证是否为有效的任务目录
            if not self._is_valid_task_directory(task_directory):
                Logger.error(f"指定的目录不是有效的任务目录: {task_directory}")
                Logger.error("有效的任务目录应该：")
                Logger.error("1. 以特定前缀开头（投稿视频-、番剧-、收藏夹-、视频列表-、视频合集-、UP主-、稍后再看-）")
                Logger.error("2. 包含格式为 yy-mm-dd-hh-mm.csv 的CSV文件")
                Logger.error("3. CSV文件包含有效的原始URL")
                return
            
            Logger.info(f"开始更新任务目录: {task_directory.name}")
            
            # 使用共同的更新逻辑
            await self._update_single_task_directory(task_directory)
            Logger.custom(f"✅ 任务更新成功: {task_directory.name}", "定向更新")
            
        except Exception as e:
            error_type = type(e).__name__
            Logger.error(f"❌ 更新任务失败 {task_directory.name} ({error_type}): {e}")
            
            # 根据错误类型提供更具体的建议
            if "CSV" in str(e) or "encoding" in str(e).lower():
                Logger.warning(f"   建议：检查 {task_directory.name} 目录下的CSV文件格式和编码")
            elif "URL" in str(e) or "network" in str(e).lower():
                Logger.warning(f"   建议：检查网络连接和原始URL的有效性")
            elif "permission" in str(e).lower():
                Logger.warning(f"   建议：检查 {task_directory.name} 目录的读写权限")
            
            raise  # 重新抛出异常，让调用者处理
    
    async def delete_all_tasks(self) -> None:
        """删除所有任务的视频文件：扫描输出目录下的所有任务并删除视频文件，保留CSV记录"""
        try:
            # 扫描所有一级子目录
            all_dirs = [d for d in self.output_dir.iterdir() if d.is_dir()]
            
            if not all_dirs:
                Logger.info("未找到任何目录")
                return
            
            # 筛选符合条件的任务目录
            task_dirs = []
            invalid_dirs = []
            
            for dir_path in all_dirs:
                if self._is_valid_task_directory(dir_path):
                    task_dirs.append(dir_path)
                else:
                    invalid_dirs.append(dir_path)
                    Logger.debug(f"跳过不符合条件的目录: {dir_path.name}")
            
            if invalid_dirs:
                Logger.info(f"跳过 {len(invalid_dirs)} 个不符合条件的目录")
            
            if not task_dirs:
                Logger.info("未找到符合条件的任务目录")
                return
            
            Logger.info(f"发现 {len(task_dirs)} 个任务目录")
            
            deleted_count = 0
            error_count = 0
            
            for task_dir in task_dirs:
                Logger.info(f"删除任务目录视频文件: {task_dir.name}")
                
                try:
                    self._delete_single_task_directory(task_dir)
                    deleted_count += 1
                    Logger.info(f"✅ 任务删除成功: {task_dir.name}")
                    
                except Exception as e:
                    error_count += 1
                    error_type = type(e).__name__
                    Logger.error(f"❌ 删除任务失败 {task_dir.name} ({error_type}): {e}")
                    
                    # 根据错误类型提供更具体的建议
                    if "permission" in str(e).lower():
                        Logger.warning(f"   建议：检查 {task_dir.name} 目录的读写权限")
                    elif "not found" in str(e).lower():
                        Logger.warning(f"   建议：检查 {task_dir.name} 目录是否存在")
                    
                    # 继续处理下一个任务，不中断整个批量操作
                    continue
            
            # 显示详细的完成统计
            total_tasks = len(task_dirs)
            Logger.custom(f"批量删除完成 - 成功: {deleted_count}, 失败: {error_count}, 总计: {total_tasks}", "批量删除")
            
            if error_count > 0:
                Logger.warning(f"有 {error_count} 个任务删除失败，请检查上述错误信息")
            
        except Exception as e:
            Logger.error(f"批量删除失败: {e}")
            raise
    
    async def delete_single_task(self, task_directory: Path) -> None:
        """定向删除单个任务目录的视频文件，保留CSV记录"""
        try:
            # 验证任务目录是否存在
            if not task_directory.exists():
                Logger.error(f"指定的任务目录不存在: {task_directory}")
                return
            
            if not task_directory.is_dir():
                Logger.error(f"指定的路径不是目录: {task_directory}")
                return
            
            # 验证是否为有效的任务目录
            if not self._is_valid_task_directory(task_directory):
                Logger.error(f"指定的目录不是有效的任务目录: {task_directory}")
                Logger.error("有效的任务目录应该：")
                Logger.error("1. 以特定前缀开头（投稿视频-、番剧-、收藏夹-、视频列表-、视频合集-、UP主-、稍后再看-）")
                Logger.error("2. 包含格式为 yy-mm-dd-hh-mm.csv 的CSV文件")
                Logger.error("3. CSV文件包含有效的原始URL")
                return
            
            Logger.info(f"开始删除任务目录的视频文件: {task_directory.name}")
            
            # 使用共同的删除逻辑
            self._delete_single_task_directory(task_directory)
            Logger.custom(f"✅ 任务删除成功: {task_directory.name}", "定向删除")
            
        except Exception as e:
            error_type = type(e).__name__
            Logger.error(f"❌ 删除任务失败 {task_directory.name} ({error_type}): {e}")
            
            # 根据错误类型提供更具体的建议
            if "permission" in str(e).lower():
                Logger.warning(f"   建议：检查 {task_directory.name} 目录的读写权限")
            elif "not found" in str(e).lower():
                Logger.warning(f"   建议：检查 {task_directory.name} 目录是否存在")
            
            raise  # 重新抛出异常，让调用者处理
    
    def _delete_single_task_directory(self, task_dir: Path) -> None:
        """删除单个任务目录的视频文件，保留CSV记录的核心逻辑"""
        import re
        
        # 验证任务目录
        if not self._is_valid_task_directory(task_dir):
            raise Exception(f"目录 {task_dir.name} 不是有效的任务目录")
        
        Logger.info(f"正在删除目录 {task_dir.name} 中的视频文件...")
        
        # 找到CSV文件
        csv_pattern = re.compile(r'^\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.csv$')
        csv_files = [f for f in task_dir.iterdir() 
                    if f.is_file() and f.suffix == '.csv' and csv_pattern.match(f.name)]
        
        if not csv_files:
            raise Exception(f"目录 {task_dir.name} 中未找到有效的CSV文件")
        
        csv_file = csv_files[0]  # 使用第一个找到的CSV文件
        Logger.info(f"保护CSV文件: {csv_file.name}")
        
        # 统计需要删除的项目
        items_to_delete = []
        for item in task_dir.iterdir():
            if item.name != csv_file.name:
                items_to_delete.append(item)
        
        if not items_to_delete:
            Logger.info("目录中除CSV文件外没有其他文件，无需删除")
            return
        
        Logger.info(f"准备删除 {len(items_to_delete)} 个项目:")
        
        deleted_items = 0
        deleted_size = 0
        
        # 遍历并删除项目
        for item in items_to_delete:
            Logger.info(f"  - {item.name} ({'文件' if item.is_file() else '目录'})")
            
            try:
                if item.is_file():
                    # 删除文件
                    file_size = item.stat().st_size
                    item.unlink()
                    deleted_items += 1
                    deleted_size += file_size
                    Logger.info(f"✅ 删除文件: {item.name}")
                    
                elif item.is_dir():
                    # 删除目录及其内容
                    dir_size = self._get_directory_size(item)
                    # 使用更强力的删除方法处理只读文件
                    try:
                        shutil.rmtree(item)
                    except OSError:
                        # 如果普通删除失败，尝试修改权限后删除
                        shutil.rmtree(item, onerror=self._remove_readonly)
                    deleted_items += 1
                    deleted_size += dir_size
                    Logger.info(f"✅ 删除目录: {item.name}")
                    
            except Exception as e:
                Logger.error(f"❌ 删除 {item.name} 失败: {e}")
                continue
        
        # 格式化文件大小
        size_str = self._format_file_size(deleted_size)
        Logger.info(f"删除完成: {deleted_items} 个项目，释放空间 {size_str}")
        Logger.info(f"保留CSV文件: {csv_file.name}")
    
    def _get_directory_size(self, directory: Path) -> int:
        """计算目录大小（字节）"""
        total_size = 0
        try:
            for item in directory.rglob('*'):
                if item.is_file():
                    try:
                        total_size += item.stat().st_size
                    except (OSError, IOError):
                        continue
        except Exception:
            pass
        return total_size
    
    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小显示"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        import math
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"
    
    async def _update_single_task_directory(self, task_dir: Path) -> None:
        """更新单个任务目录的核心逻辑"""
        async with self.fetcher:
            # 初始化CSV管理器，直接使用指定的任务目录
            self.csv_manager = CSVManager(task_dir)
            original_url = self.csv_manager.get_original_url()
            
            if not original_url:
                Logger.warning(f"任务目录 {task_dir.name} 中未找到有效的原始URL，将禁用该目录")
                self._disable_task_directory(task_dir, "CSV无URL")
                return
            
            # 验证CSV文件格式
            if not self._validate_csv_format(self.csv_manager):
                Logger.warning(f"任务目录 {task_dir.name} 的CSV文件格式不正确，将禁用该目录")
                self._disable_task_directory(task_dir, "缺少CSV文件")
                return
            
            Logger.info(f"发现任务URL: {original_url}")
            
            # 设置原始URL
            self.original_url = original_url
            
            # 获取现有的视频列表
            existing_videos = self.csv_manager.load_video_list()
            if not existing_videos:
                Logger.warning(f"任务目录 {task_dir.name} 的CSV文件为空，将重新获取视频列表")
                existing_videos = []
            
            # 从URL获取最新的视频列表（使用增量获取优化）
            Logger.info("正在获取最新的视频列表...")
            try:
                # 获取现有视频URL集合用于查重
                existing_urls = self.csv_manager.get_existing_video_urls()
                Logger.debug(f"现有视频URL数量: {len(existing_urls)}")
                
                if existing_urls:
                    # 使用增量提取，支持实时查重
                    Logger.info("使用增量获取模式，支持实时查重")
                    video_list = await extract_video_list_incremental(self.fetcher, original_url, existing_urls)
                else:
                    # 首次获取，使用普通提取
                    Logger.info("首次获取，使用普通提取模式")
                    video_list = await extract_video_list(self.fetcher, original_url)
                
                # 检查是否返回了风控检测指令
                if video_list == RISK_CONTROL_DETECTED:
                    Logger.warning("检测到获取视频列表失败，触发风控检测")
                    is_risk_controlled = await self.anti_risk_manager.check_risk_control(self.fetcher)
                    if is_risk_controlled:
                        Logger.warning("确认受到风控，设置风控状态")
                        self.anti_risk_manager.set_risk_controlled(True)
                        raise Exception("风控检测：获取视频列表失败，可能受到风控")
                    else:
                        Logger.warning("未检测到风控，但获取视频列表失败")
                        raise Exception("获取视频列表失败，非风控原因")
                
                new_videos = video_list["videos"]
            except Exception as e:
                error_msg = str(e).lower()
                Logger.error(f"获取视频列表失败: {e}")
                
                # 检查是否为永久性错误，需要禁用目录
                permanent_errors = ["权限不足", "访问被拒绝", "账号被封", "内容不存在", "已删除"]
                if any(keyword in error_msg for keyword in permanent_errors):
                    Logger.warning(f"检测到永久性错误，将禁用任务目录: {task_dir.name}")
                    self._disable_task_directory(task_dir, "获取失败")
                    return
                
                raise

            # 新增策略：若列表为空或标题已更改，先检测风控再决定是否禁用目录
            try:
                new_title = str(video_list.get("title", "")).strip()
                current_dir_name = task_dir.name
                title_changed = bool(new_title) and (new_title != current_dir_name)
                list_empty = not new_videos or len(new_videos) == 0
                
                if title_changed:
                    # 标题已更改，直接禁用目录
                    Logger.warning(f"检测到标题已更改，将禁用任务目录: {current_dir_name}")
                    self._disable_task_directory(task_dir, "标题已更改")
                    return
                elif list_empty:
                    # 视频列表为空，检测是否受到风控
                    Logger.warning(f"检测到视频列表为空，开始风控检测: {current_dir_name}")
                    
                    # 检测是否受到风控
                    is_risk_controlled = await self.anti_risk_manager.check_risk_control(self.fetcher)
                    
                    if is_risk_controlled:
                        Logger.warning("检测到风控，设置风控状态并抛出异常以触发任务队列等待")
                        self.anti_risk_manager.set_risk_controlled(True)
                        raise Exception("风控检测：视频列表为空，暂停处理等待风控解除")
                    else:
                        # 没有风控，确实是视频列表为空，禁用目录
                        Logger.warning(f"确认视频列表为空（非风控），将禁用任务目录: {current_dir_name}")
                        self._disable_task_directory(task_dir, "视频列表为空")
                        return
                        
            except Exception as e:
                Logger.error(f"处理空列表逻辑时出错: {e}")
                # 若处理流程出错，不影响后续逻辑
                pass
            
            if not new_videos:
                Logger.warning("未获取到任何视频信息")
                return
            
            Logger.info(f"获取到 {len(new_videos)} 个视频")
            
            # 成功获取到视频列表，添加到风控检测的测试URL列表
            try:
                # 根据URL类型确定类型标识
                url_type = "unknown"
                if "space.bilibili.com" in original_url:
                    url_type = "up主"
                elif "favlist" in original_url:
                    url_type = "收藏夹"
                elif "series" in original_url:
                    url_type = "视频合集"
                elif "cheese" in original_url:
                    url_type = "课程"
                elif "bangumi" in original_url:
                    url_type = "番剧"
                
                self.anti_risk_manager.add_successful_url(original_url, url_type)
                Logger.debug(f"已添加成功URL到风控检测列表: {original_url} (类型: {url_type})")
            except Exception as e:
                Logger.error(f"添加成功URL到风控检测列表失败: {e}")
            
            # 检查是否有新增视频
            if existing_videos:
                # 对比CSV中的视频和当前获取的视频
                csv_video_urls = {video['video_url'] for video in existing_videos}
                current_video_urls = {self._get_video_url(video) for video in new_videos}
                
                new_video_urls = current_video_urls - csv_video_urls
                
                if new_video_urls:
                    Logger.info(f"发现 {len(new_video_urls)} 个新增视频，更新CSV文件")
                    # 更新CSV文件（保持现有下载状态）
                    self.csv_manager.update_video_list(new_videos, original_url)
                else:
                    Logger.info("没有发现新增视频")
                
                # 统一处理：无论是否有新增视频，都检查所有待下载视频
                pending_videos = self.csv_manager.get_pending_videos()
                if pending_videos:
                    Logger.info(f"发现 {len(pending_videos)} 个待下载视频，开始下载任务")
                    videos_to_download = [self._csv_to_video_info(data) for data in pending_videos]
                else:
                    Logger.info("所有视频都已下载完成")
                    return
            else:
                # 首次创建CSV文件
                Logger.info("首次创建CSV文件...")
                self.csv_manager.save_video_list(new_videos, original_url)
                videos_to_download = new_videos
            
            # 下载待下载的视频
            if videos_to_download:
                Logger.info(f"开始下载 {len(videos_to_download)} 个视频...")
                await self._download_videos(videos_to_download, original_url)
            else:
                Logger.info("没有需要下载的视频")
    
    def _validate_csv_format(self, csv_manager: CSVManager) -> bool:
        """验证CSV文件格式是否正确"""
        try:
            # 尝试加载视频列表
            videos = csv_manager.load_video_list()
            if videos is None:
                return False
            
            # 检查是否有基本的必需字段
            if not videos:
                Logger.warning("CSV文件为空")
                return True  # 空文件也算有效
            
            required_fields = ['video_url', 'title', 'downloaded']
            first_video = videos[0]
            
            missing_fields = [field for field in required_fields if field not in first_video]
            if missing_fields:
                Logger.error(f"CSV文件缺少必需字段: {missing_fields}")
                return False
            
            # 检查URL格式是否合理
            sample_url = first_video.get('video_url', '')
            if not (sample_url.startswith('http') and 'bilibili.com' in sample_url):
                Logger.error(f"CSV文件中的视频URL格式不正确: {sample_url}")
                return False
            
            Logger.debug("CSV文件格式验证通过")
            return True
            
        except Exception as e:
            Logger.error(f"CSV文件格式验证失败: {e}")
            return False
    
    def _is_valid_task_directory(self, dir_path: Path) -> bool:
        """检查目录是否为有效的任务目录"""
        import re
        
        # 检查目录名是否符合我们的命名格式
        dir_name = dir_path.name
        
        # 支持的命名格式：
        # 1. 投稿视频-BVxxx-标题
        # 2. 番剧-编号-标题  
        # 3. 收藏夹-收藏夹ID-收藏夹名
        # 4. 视频列表-视频列表ID-视频列表名
        # 5. 视频合集-视频合集ID-视频合集名
        # 6. UP主-UP主UID-UP主名
        # 7. 稍后再看-watchlater-稍后再看
        # 8. 课程-课程编号-课程名
        # 检查是否以有效前缀开头
        has_valid_prefix = any(dir_name.startswith(prefix) for prefix in TASK_FOLDER_PREFIXES)
        if not has_valid_prefix:
            return False
        
        # 检查目录内是否包含符合格式的CSV文件
        csv_pattern = re.compile(r'^\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.csv$')
        csv_files = [f for f in dir_path.iterdir() 
                    if f.is_file() and f.suffix == '.csv' and csv_pattern.match(f.name)]
        
        if not csv_files:
            return False
        
        # 进一步验证：检查CSV文件是否包含原始URL
        try:
            csv_manager = CSVManager(dir_path)
            original_url = csv_manager.get_original_url()
            return original_url is not None
        except Exception:
            return False
    
    async def _download_videos(self, videos: list[VideoInfo], original_url: str) -> None:
        """步骤7: 逐个下载视频"""
        for i, video in enumerate(videos, 1):
            try:
                # 检查是否应该停止
                if self._should_stop():
                    Logger.warning(f"收到停止信号，中断下载任务")
                    raise Exception("任务被手动停止")
                
                Logger.info(f"[{i}/{len(videos)}] 开始处理: {video['name']}")
                
                # 检查是否为不可访问的视频
                if video.get('status') == 'unavailable':
                    Logger.warning(f"[{i}/{len(videos)}] 跳过不可访问视频: {video['name']}")
                    # 直接标记为已下载，避免重复尝试
                    video_url = self._get_video_url(video)
                    if self.csv_manager:
                        self.csv_manager.mark_video_downloaded(video_url, folder_size=0)
                    Logger.info(f"[{i}/{len(videos)}] 已标记不可访问视频为已处理: {video['name']}")
                    # 更新进度
                    self._update_progress()
                    continue
                
                # 关键步骤：如果视频状态为pending，先获取详细信息
                if video.get("status") == "pending":
                    await self._fetch_video_details(video)
                
                # 步骤7关键逻辑: 检查视频文件夹是否存在，如果存在就删除重新下载
                await self._cleanup_existing_video_folder(video)
                
                # 调用单视频下载方法
                if not self.csv_manager:
                    Logger.error("CSV管理器未初始化")
                    continue
                
                download_success = await self._download_single_video(video, self.task_id, self.csv_manager.task_dir)
                
                if download_success:
                    # 只有下载成功或应该跳过的情况才标记为已下载
                    video_url = self._get_video_url(video)
                    if self.csv_manager:
                        # 计算文件夹大小
                        folder_size = self._calculate_video_folder_size(video)
                        if folder_size == 0:
                            # 如果大小为0，等待一下再重试（yutto可能在合并音视频）
                            Logger.debug(f"文件夹大小为0，等待2秒后重试...")
                            await asyncio.sleep(2.0)
                            folder_size = self._calculate_video_folder_size(video)
                        
                        self.csv_manager.mark_video_downloaded(video_url, folder_size=folder_size)
                        if folder_size > 0:
                            Logger.info(f"[{i}/{len(videos)}] 下载成功: {video['name']} (大小: {self._format_file_size(folder_size)})")
                        else:
                            Logger.warning(f"[{i}/{len(videos)}] 下载成功但文件夹大小为0: {video['name']}")
                    else:
                        Logger.info(f"[{i}/{len(videos)}] 下载成功: {video['name']}")
                else:
                    Logger.error(f"[{i}/{len(videos)}] 下载失败，不标记为已完成: {video['name']}")
                
                # 更新进度
                self._update_progress()
                
                # 添加视频间延迟，避免请求过于频繁
                if i < len(videos):  # 不是最后一个视频
                    await asyncio.sleep(2.0)  # 延迟2秒
                    
            except Exception as e:
                Logger.error(f"下载视频 {video['name']} 失败: {e}")
                
                # 下载异常时不标记为已处理，让用户修复问题后可以重试
                # 这样配置错误等问题修复后就能重新下载
                Logger.warning(f"[{i}/{len(videos)}] 由于异常未标记为已完成，可修复问题后重试")
                
                # 更新进度（即使失败也要更新进度避免界面卡住）
                self._update_progress()
                
                # 下载失败时也添加短暂延迟，避免连续快速重试
                await asyncio.sleep(1.0)
                continue
        
        # 显示最终统计
        if self.csv_manager:
            stats = self.csv_manager.get_download_stats()
            Logger.custom(f"下载完成 - 成功: {stats['downloaded']}, 总计: {stats['total']}", "批量下载")
    
    def _get_video_url(self, video: VideoInfo) -> str:
        """获取视频URL"""
        if "episode_id" in video:
            # 根据视频路径判断是番剧还是课程
            main_folder = self._extract_main_folder(video)
            if main_folder.startswith("课程-"):
                # 课程视频使用课程URL格式
                return f"https://www.bilibili.com/cheese/play/ep{video['episode_id']}"
            else:
                # 番剧视频使用标准的B站URL格式，与CSV保存格式一致
                return f"https://www.bilibili.com/bangumi/play/ep{video['episode_id']}"
        else:
            # 普通视频使用avid
            return video['avid'].to_url()
    
    async def _fetch_video_details(self, video: VideoInfo) -> None:
        """获取视频的详细信息"""
        avid = video["avid"]
        Logger.info(f"获取视频 {avid} 的详细信息...")
        
        try:
            # 使用正确的异步上下文管理器语法
            async with Fetcher(sessdata=self.sessdata) as fetcher:
                # 判断是否为番剧或课程视频
                episode_id = video.get("episode_id")
                if episode_id:
                    # 获取主文件夹名（保持原来的类型-编号-名称格式）
                    main_folder = self._extract_main_folder(video)
                    
                    # 根据主文件夹类型判断是番剧还是课程
                    if main_folder.startswith("番剧-"):
                        # 番剧视频，使用episode_id获取详细信息
                        Logger.info(f"获取番剧剧集 {episode_id} 的详细信息...")
                        episode_info = await get_bangumi_episode_info(fetcher, episode_id)
                        
                        # 生成番剧视频的文件夹名：视频号-标题
                        video_folder_name = f"{episode_info['avid']}-{episode_info['name']}"
                        
                        # 更新视频信息
                        video.update({
                            "avid": episode_info["avid"],
                            "cid": episode_info["cid"],
                            "title": episode_info["title"],
                            "name": episode_info["name"],
                            "author": episode_info["author"],
                            "duration": episode_info["duration"],
                            "path": Path(main_folder) / video_folder_name,  # 主文件夹/视频号-标题
                            "status": "ready"
                        })
                        
                        Logger.info(f"已获取并保存番剧剧集 {episode_id} 的详细信息: {episode_info['name']}")
                        
                    elif main_folder.startswith("课程-"):
                        # 课程视频，使用episode_id获取详细信息
                        Logger.info(f"获取课程课时 {episode_id} 的详细信息...")
                        episode_info = await get_cheese_episode_info(fetcher, episode_id)
                        
                        # 生成课程视频的文件夹名：视频号-标题
                        video_folder_name = f"{episode_info['avid']}-{episode_info['name']}"
                        
                        # 更新视频信息
                        video.update({
                            "avid": episode_info["avid"],
                            "cid": episode_info["cid"],
                            "title": episode_info["title"],
                            "name": episode_info["name"],
                            "author": episode_info["author"],
                            "duration": episode_info["duration"],
                            "path": Path(main_folder) / video_folder_name,  # 主文件夹/视频号-标题
                            "status": "ready"
                        })
                        
                        Logger.info(f"已获取并保存课程课时 {episode_id} 的详细信息: {episode_info['name']}")
                    
                    # 立即更新CSV文件中的详细信息
                    video_url = self._get_video_url(video)
                    if self.csv_manager:
                        self.csv_manager.update_video_info(video_url, {
                            "title": episode_info["title"],
                            "name": episode_info["name"],
                            "cid": str(episode_info["cid"]),
                            "download_path": str(video["path"]),
                            "status": "ready"
                        })
                else:
                    # 投稿视频，使用原有逻辑获取详细信息
                    detailed_video_data = await get_ugc_video_list(fetcher, avid)
                    
                    # 更新视频信息
                    if detailed_video_data and detailed_video_data.get("videos"):
                        detailed_video = detailed_video_data["videos"][0]
                        
                        # 获取主文件夹名（保持原来的类型-ID-名称格式）
                        main_folder = self._extract_main_folder(video)
                        
                        # 生成单个视频的文件夹名：视频号-标题
                        video_folder_name = f"{avid}-{detailed_video['title']}"
                        
                        # 更新详细信息
                        video.update({
                            "cid": detailed_video["cid"],
                            "title": detailed_video["title"],
                            "name": detailed_video["name"],
                            "path": Path(main_folder) / video_folder_name,  # 主文件夹/视频号-标题
                            "status": "ready"
                        })
                        
                        # 立即更新CSV文件中的详细信息
                        video_url = self._get_video_url(video)
                        if self.csv_manager:
                            self.csv_manager.update_video_info(video_url, {
                                "title": detailed_video["title"],
                                "name": detailed_video["name"],
                                "cid": str(detailed_video["cid"]),
                                "download_path": str(video["path"]),
                                "status": "ready"
                            })
                        
                        Logger.info(f"已获取并保存视频 {avid} 的详细信息")
                    else:
                        raise Exception("无法获取视频详细信息")
                        
        except Exception as e:
            error_msg = str(e)
            Logger.error(f"获取视频 {avid} 详细信息失败: {e}")
            
            # 检查是否为永久性错误
            permanent_errors = ["稿件不可见", "视频不存在", "已删除", "权限不足"]
            if any(keyword in error_msg for keyword in permanent_errors):
                Logger.warning(f"视频 {avid} 不可访问，标记为已处理")
                video["status"] = "unavailable"
                video_url = self._get_video_url(video)
                if self.csv_manager:
                    self.csv_manager.mark_video_downloaded(video_url, folder_size=0)
            else:
                Logger.warning(f"视频 {avid} 获取失败，跳过此次下载")
                raise  # 重新抛出异常，让上层处理
    
    async def _cleanup_existing_video_folder(self, video: VideoInfo) -> None:
        """清理已存在的视频文件夹和文件"""
        if not self.csv_manager:
            return
            
        # 获取最终的视频文件夹名（即视频号-标题格式）
        final_video_folder_name = self._get_final_video_folder_name(video)
        task_dir = self.csv_manager.task_dir
        
        # 完整的视频文件夹路径
        video_folder_path = task_dir / final_video_folder_name
        
        cleaned_items = []
        
        # 1. 检查并删除整个视频文件夹
        if video_folder_path.exists() and video_folder_path.is_dir():
            try:
                shutil.rmtree(video_folder_path, onerror=self._remove_readonly)
                cleaned_items.append(f"文件夹: {final_video_folder_name}")
            except Exception as e:
                Logger.warning(f"删除文件夹时出现警告: {video_folder_path} - {e}")
        
        # 2. 检查并删除可能的视频文件和相关文件（如果直接在根目录）
        # yutto可能创建的文件扩展名
        possible_extensions = ['.mp4', '.flv', '.ass', '.srt', '_audio.m4s', '_video.m4s', '-poster.jpg']
        
        for ext in possible_extensions:
            video_file_path = task_dir / f"{final_video_folder_name}{ext}"
            if video_file_path.exists():
                try:
                    video_file_path.unlink()
                    cleaned_items.append(f"文件: {final_video_folder_name}{ext}")
                except Exception as e:
                    Logger.warning(f"删除文件时出现警告: {video_file_path} - {e}")
        
        # 3. 检查中文字幕文件（可能包含特殊字符）
        for item in task_dir.iterdir():
            if item.name.startswith(final_video_folder_name) and ('中文' in item.name or '自动生成' in item.name):
                try:
                    item.unlink()
                    cleaned_items.append(f"字幕文件: {item.name}")
                except Exception as e:
                    Logger.warning(f"删除字幕文件时出现警告: {item} - {e}")
        
        if cleaned_items:
            Logger.info(f"清理已存在的视频相关内容: {final_video_folder_name}")
            for item in cleaned_items:
                Logger.debug(f"  已删除 {item}")
        else:
            Logger.debug(f"未发现需要清理的内容: {final_video_folder_name}")
    
    def _remove_readonly(self, func, path, exc):
        """处理只读文件删除"""
        import stat
        import os
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass  # 忽略系统文件删除错误
    
    def _sanitize_filename(self, filename: str) -> str:
        """清理文件名中的非法字符"""
        # 移除或替换文件名中的非法字符
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # 处理多个连续的空格，替换为单个空格
        filename = re.sub(r'\s+', ' ', filename)
        
        # 移除首尾空格
        filename = filename.strip()
        
        # 处理可能的空文件名
        if not filename:
            filename = "未命名视频"
        
        # 如果文件名过长，截断但保留扩展名
        if len(filename) > 100:
            filename = filename[:100] + "..."
            
        return filename
    
    async def _download_single_video(self, video, task_id, output_dir, max_retries: int = 5):
        """下载单个视频（支持重试机制）"""
        avid = video["avid"]
        video_url = self._get_video_url(video)
        
        # 检查是否需要停止
        if self._should_stop():
            Logger.info(f"任务 {task_id} 收到停止信号，跳过视频 {avid}")
            return False
        
        # 检查CSV管理器是否可用
        if not self.csv_manager:
            Logger.warning("CSV管理器未初始化，无法检查下载状态")
            return False
        
        # 检查视频是否已下载或不可访问
        pending_videos = self.csv_manager.get_pending_videos()
        if pending_videos is None:
            pending_videos = []
        video_urls_pending = [v['video_url'] for v in pending_videos]
        
        # 添加调试信息
        Logger.debug(f"当前视频URL: {video_url}")
        Logger.debug(f"待下载URL列表: {video_urls_pending[:3]}...")  # 只显示前3个避免太长
        
        if video_url not in video_urls_pending:
            Logger.info(f"视频 {avid} 已下载，跳过")
            return True
        
        # 如果是不可访问的视频，跳过
        if video.get("status") == "unavailable":
            Logger.info(f"视频 {avid} 不可访问，跳过")
            return True
        
        # 检查是否需要停止（下载前再次检查）
        if self._should_stop():
            Logger.info(f"任务 {task_id} 收到停止信号，跳过视频 {avid}")
            return False
        
        # 重试循环
        for attempt in range(max_retries):
            try:
                # 如果是重试，先清理现有文件夹
                if attempt > 0:
                    Logger.info(f"准备第 {attempt + 1}/{max_retries} 次重试下载...")
                    await self._cleanup_existing_video_folder(video)
                    # 重试时添加延迟，避免立即重试
                    await asyncio.sleep(min(2.0 * attempt, 10.0))  # 递增延迟，最大10秒
                
                result = await self._perform_single_download(video, task_id, output_dir)
                
                if result == "success":
                    if attempt > 0:
                        Logger.info(f"视频 {avid} 在第 {attempt + 1} 次尝试后下载成功")
                    return True
                elif result == "should_skip":
                    Logger.info(f"视频 {avid} 无法下载（充电视频/已下架等），标记为已处理")
                    return True
                elif result == "retry":
                    # 可重试的错误
                    if attempt < max_retries - 1:
                        Logger.warning(f"视频 {avid} 下载失败，将进行第 {attempt + 2} 次尝试")
                        continue
                    else:
                        Logger.error(f"视频 {avid} 在 {max_retries} 次尝试后仍然失败，放弃重试")
                        return False
                else:
                    # 不可重试的错误（配置错误等）
                    Logger.error(f"视频 {avid} 下载失败（不可重试的错误）")
                    return False
                    
            except Exception as e:
                if "任务被手动停止" in str(e):
                    Logger.info(f"视频 {avid} 下载被手动停止")
                    return False
                
                Logger.error(f"视频 {avid} 下载异常（第 {attempt + 1} 次尝试）: {e}")
                if attempt < max_retries - 1:
                    Logger.warning(f"将在延迟后进行第 {attempt + 2} 次尝试")
                    await asyncio.sleep(min(2.0 * attempt, 10.0))
                    continue
                else:
                    Logger.error(f"视频 {avid} 在 {max_retries} 次尝试后仍然异常，放弃重试")
                    return False
        
        return False

    async def _perform_single_download(self, video, task_id, output_dir):
        """执行单次下载尝试"""
        avid = video["avid"]
        video_url = self._get_video_url(video)
        
        # 构建yutto命令
        yutto_cmd = ["yutto"]
        
        # 视频URL - 对于课程和番剧，需要使用原始URL而不是avid
        if "episode_id" in video:
            # 使用原始的课程或番剧URL
            actual_video_url = video_url  # 使用CSV中保存的原始URL
        else:
            # 普通视频使用avid URL
            actual_video_url = video['avid'].to_url()
        yutto_cmd.append(actual_video_url)
        
        # 检查是否需要使用批量下载模式(-b参数)
        video_path = video.get('path', Path(f"{avid}"))
        if isinstance(video_path, str):
            video_path = Path(video_path)
        main_folder = self._extract_main_folder(video)
        
        # 课程和多P视频都需要使用批量下载模式
        if main_folder.startswith("课程-") or video.get('is_multi_part', False):
            yutto_cmd.append("-b")
            if main_folder.startswith("课程-"):
                Logger.info(f"检测到课程，使用批量下载模式")
            else:
                total_parts = video.get('total_parts', 1)
                Logger.info(f"检测到多P视频，使用批量下载模式 (共{total_parts}P)")
        
        # 输出目录 - 使用video['path']中设置的最终文件夹名（即视频号-标题格式）
        video_path = video.get('path', Path(f"{avid}"))
        if isinstance(video_path, str):
            video_path = Path(video_path)
        
        # 获取最终的视频文件夹名（即视频号-标题格式）
        final_video_folder_name = video_path.name
        
        # yutto的输出目录设置为任务主目录（使用绝对路径）
        video_output_dir = (output_dir / final_video_folder_name).resolve()
        yutto_cmd.extend(["-d", str(video_output_dir)])
        
        # 如果有SESSDATA，添加-c参数
        if self.sessdata:
            yutto_cmd.extend(["-c", self.sessdata])
        
        # 添加用户额外参数
        yutto_cmd.extend(self.extra_args)
        
        # 收集yutto输出用于智能判断结果
        yutto_output = []
        
        try:
            Logger.debug(f"执行命令: {' '.join(yutto_cmd)}")
            
            # 执行yutto命令，捕获输出并实时转发到Logger
            process = await asyncio.create_subprocess_exec(
                *yutto_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=Path(__file__).parent
            )
            
            # 保存进程引用以便停止控制
            if self.task_id and self.task_control:
                self.task_control[self.task_id]['process'] = process
            
            # 实时读取和转发输出
            if process.stdout:
                while True:
                    # 检查是否应该停止
                    if self._should_stop():
                        Logger.warning("收到停止信号，终止yutto进程")
                        process.terminate()
                        try:
                            await asyncio.wait_for(process.wait(), timeout=3.0)
                        except asyncio.TimeoutError:
                            Logger.warning("进程未在3秒内终止，强制杀死")
                            process.kill()
                        raise Exception("任务被手动停止")
                    
                    try:
                        line = await asyncio.wait_for(process.stdout.readline(), timeout=1.0)
                        if not line:
                            break
                        
                        # 解码输出并发送到Logger
                        output = line.decode('utf-8', errors='ignore').strip()
                        if output:
                            # 收集输出用于后续分析
                            yutto_output.append(output)
                            
                            # 根据输出内容判断日志级别
                            if 'error' in output.lower() or 'failed' in output.lower():
                                Logger.error(f"[yutto] {output}")
                            elif 'warning' in output.lower() or 'warn' in output.lower():
                                Logger.warning(f"[yutto] {output}")
                            elif 'downloading' in output.lower() or 'progress' in output.lower() or '%' in output:
                                Logger.custom(output, "下载进度")
                            else:
                                Logger.info(f"[yutto] {output}")
                    except asyncio.TimeoutError:
                        # 超时继续循环，用于检查停止信号
                        continue
            
            # 等待进程完成
            return_code = await process.wait()
            
            # 分析下载结果并返回结果类型
            download_result = self._analyze_yutto_result(return_code, yutto_output)
            return download_result
                
        except Exception as e:
            Logger.error(f"调用yutto失败: {e}")
            raise
        finally:
            # 清理进程引用
            if self.task_id and self.task_control:
                self.task_control[self.task_id]['process'] = None

    def _analyze_yutto_result(self, return_code: int, output_lines: list) -> str:
        """分析yutto下载结果
        
        Returns:
            "success": 下载成功
            "should_skip": 应该跳过（充电视频等不可下载内容）
            "retry": 可重试的临时错误（网络问题等）
            "failure": 真正的失败（配置错误等）
        """
        # 合并所有输出为一个字符串用于分析
        full_output = "\n".join(output_lines).lower()
        
        # 如果返回码为0，说明下载成功
        if return_code == 0:
            return "success"
        
        # 分析失败原因 - 优先检查配置问题
        # 1. 配置问题（不应标记为成功）- 优先级最高
        config_error_indicators = [
            "启用了严格校验大会员或登录模式，请检查 sessdata 或大会员状态",
            "请检查 sessdata",
            "cookie 无效",
            "登录失败",
            "身份验证失败"
        ]
        
        for indicator in config_error_indicators:
            if indicator in full_output:
                Logger.error(f"检测到配置错误: {indicator}")
                return "failure"
        
        # 2. 应该跳过的情况（标记为成功避免重复尝试）- 优先级较高
        skip_indicators = [
            "尚不支持 dash 格式",  # 充电视频
            "该视频（bvid:",       # 充电视频的另一种表达
            "视频不存在",
            "稿件不可见",
            "已删除",
            "权限不足",
            "需要付费",
            "会员专享",  # 仅当不是配置错误时才跳过
            "充电专享"
        ]
        
        for indicator in skip_indicators:
            if indicator in full_output:
                Logger.info(f"检测到应跳过的失败类型: {indicator}")
                return "should_skip"
        
        # 3. 可重试的临时错误
        retry_error_indicators = [
            "网络错误",
            "连接超时",
            "请求失败",
            "下载失败",
            "separator is not found",  # 网络传输问题
            "chunk exceed the limit",  # 网络传输问题
            "connection reset",
            "timeout",
            "temporary failure",
            "无法访问",
            "无法连接",
            "网络不可达",
            "服务器错误",
            "503 service unavailable",
            "502 bad gateway",
            "504 gateway timeout"
        ]
        
        for indicator in retry_error_indicators:
            if indicator in full_output:
                Logger.warning(f"检测到可重试的错误: {indicator}")
                return "retry"
        
        # 默认情况：未知错误，不标记为成功
        Logger.warning(f"未识别的失败类型，返回码: {return_code}")
        return "failure"
    
    def _extract_main_folder(self, video: VideoInfo) -> str:
        """提取视频所属的主目录名称"""
        raw_path = video.get("path", "")
        if isinstance(raw_path, Path):
            raw_str = raw_path.as_posix()
        else:
            raw_str = str(raw_path or "")
        
        if raw_str:
            parts = [part for part in raw_str.replace("\\", "/").split("/") if part]
            for part in parts:
                if any(part.startswith(prefix) for prefix in TASK_FOLDER_PREFIXES):
                    return part
            if parts:
                return parts[0]
        
        if self.csv_manager:
            return self.csv_manager.task_dir.name
        return ""
    
    def _build_video_path_from_csv(self, stored_path: str) -> Path:
        """根据CSV中的路径字段还原任务内相对路径"""
        if not stored_path:
            if self.csv_manager:
                return Path(self.csv_manager.task_dir.name)
            return Path("未命名任务")
        
        path_obj = Path(stored_path)
        if path_obj.is_absolute():
            parts = [part for part in path_obj.parts if part]
            for idx, part in enumerate(parts):
                if any(part.startswith(prefix) for prefix in TASK_FOLDER_PREFIXES):
                    relative = Path(part)
                    for sub in parts[idx + 1:]:
                        relative /= sub
                    return relative
            if self.csv_manager:
                return Path(self.csv_manager.task_dir.name) / path_obj.name
            return Path(path_obj.name)
        
        return path_obj
    
    def _get_final_video_folder_name(self, video: VideoInfo) -> str:
        """获取最终视频文件夹名称"""
        video_path = video.get('path', Path(f"{video.get('avid', 'video')}"))
        if isinstance(video_path, str):
            video_path = Path(video_path)
        final_name = video_path.name
        if not final_name:
            final_name = str(video.get('avid', 'video'))
        return final_name
    
    def _get_video_folder_path(self, video: VideoInfo) -> Optional[Path]:
        """获取视频对应的目录路径"""
        if not self.csv_manager:
            return None
        final_name = self._get_final_video_folder_name(video)
        return self.csv_manager.task_dir / final_name
    
    def _calculate_video_folder_size(self, video: VideoInfo) -> int:
        """计算视频文件夹大小"""
        folder_path = self._get_video_folder_path(video)
        if not folder_path:
            Logger.warning(f"无法获取视频文件夹路径: {video.get('name', 'unknown')}")
            return 0
        
        if not folder_path.exists():
            Logger.warning(f"视频文件夹不存在: {folder_path} (视频: {video.get('name', 'unknown')})")
            # 尝试列出任务目录下的所有文件夹，帮助调试
            if self.csv_manager and self.csv_manager.task_dir.exists():
                try:
                    all_dirs = [d.name for d in self.csv_manager.task_dir.iterdir() if d.is_dir()]
                    Logger.debug(f"任务目录下的所有文件夹: {all_dirs[:10]}")  # 只显示前10个
                except Exception:
                    pass
            return 0
        
        size = self._get_directory_size(folder_path)
        Logger.debug(f"计算文件夹大小: {folder_path} = {size} 字节")
        return size
    
    
    def _parse_folder_size_value(self, value: str) -> int:
        """解析CSV中的folder_size字符串"""
        return CSVManager.parse_folder_size_value(value)
    
    def _csv_to_video_info(self, csv_data: Dict[str, str]) -> VideoInfo:
        """将CSV数据转换为VideoInfo"""
        video_url = csv_data['video_url']
        video_path = self._build_video_path_from_csv(csv_data.get('download_path', ''))
        folder_size = self._parse_folder_size_value(csv_data.get('folder_size', '0'))
        
        # 处理不同类型的视频
        if 'bangumi/play/ep' in video_url or 'cheese/play/ep' in video_url:
            # 番剧或课程视频，从URL中提取episode_id
            import re
            ep_match = re.search(r'/ep(\d+)', video_url)
            if ep_match:
                episode_id = ep_match.group(1)
            else:
                episode_id = csv_data['avid']  # 备用方案
            
            video_info = {
                'id': 1,
                'name': csv_data['name'],
                'title': csv_data['title'],
                'avid': BvId("BV1"),  # 占位符，下载时会更新
                'cid': CId(csv_data['cid']),
                'path': video_path,
                'pubdate': 0,  # 番剧和课程没有pubdate
                'status': csv_data.get('status', 'pending'),
                'episode_id': episode_id,  # 保存episode_id用于获取详细信息
                'is_multi_part': csv_data.get('is_multi_part', 'False') == 'True',  # 从CSV读取多P标记
                'total_parts': int(csv_data.get('total_parts', '1')),  # 从CSV读取总分P数量
                'folder_size': folder_size
            }
        else:
            # 普通投稿视频
            avid_str = csv_data['avid']
            if avid_str.startswith('BV') or avid_str.startswith('bv'):
                avid = BvId(avid_str)
            else:
                avid = AId(avid_str)
            
            # 处理pubdate字段 - 可能是Unix时间戳或可读格式
            pubdate_str = csv_data.get('pubdate', '0')
            if pubdate_str == '未知' or not pubdate_str:
                pubdate = 0
            elif pubdate_str.isdigit():
                # 如果是纯数字，说明是Unix时间戳
                pubdate = int(pubdate_str)
            else:
                # 如果是日期字符串，尝试解析为Unix时间戳
                try:
                    from datetime import datetime
                    dt = datetime.strptime(pubdate_str, '%Y-%m-%d %H:%M:%S')
                    pubdate = int(dt.timestamp())
                except ValueError:
                    Logger.warning(f"无法解析pubdate: {pubdate_str}")
                    pubdate = 0
            
            video_info = {
                'id': 1,  # 默认id
                'name': csv_data['name'],
                'title': csv_data['title'],
                'avid': avid,
                'cid': CId(csv_data['cid']),
                'path': video_path,
                'pubdate': pubdate,
                'status': csv_data.get('status', 'pending'),
                'is_multi_part': csv_data.get('is_multi_part', 'False') == 'True',  # 从CSV读取多P标记
                'total_parts': int(csv_data.get('total_parts', '1')),  # 从CSV读取总分P数量
                'folder_size': folder_size
            }
        
        return video_info  # type: ignore 
    
    def get_risk_status(self) -> Dict[str, Any]:
        """获取风控状态信息"""
        return self.anti_risk_manager.get_risk_status()
    
    def get_test_urls(self) -> List[Dict[str, Any]]:
        """获取测试URL列表"""
        return self.anti_risk_manager.get_test_urls()
    
    def clear_test_urls(self) -> None:
        """清空测试URL列表"""
        self.anti_risk_manager.clear_test_urls()

    def _disable_task_directory(self, task_dir: Path, reason: str) -> None:
        """通过重命名方式禁用任务目录，使其不再被更新扫描识别"""
        try:
            parent = task_dir.parent
            old_name = task_dir.name
            
            # 根据原因生成简短描述（不超过5个字）
            reason_mapping = {
                "视频列表为空": "空列表",
                "标题已更改": "标题变",
                "目录前缀无效": "前缀错",
                "缺少CSV文件": "无CSV",
                "CSV无URL": "无URL",
                "获取失败": "获取失败",
                "网络错误": "网络错",
                "权限不足": "权限错"
            }
            
            # 获取简短原因描述，如果找不到映射则使用原原因（截取前5个字符）
            short_reason = reason_mapping.get(reason, reason[:5] if len(reason) > 5 else reason)
            
            # 以"无效-原因-"为前缀，打破有效前缀匹配
            base_new_name = f"无效-{short_reason}-{old_name}"
            new_path = parent / base_new_name
            
            # 如存在重名，追加时间后缀
            if new_path.exists():
                ts = time.strftime('%Y%m%d-%H%M%S')
                new_path = parent / f"{base_new_name}-{ts}"
            task_dir.rename(new_path)
            Logger.custom(f"目录已禁用并重命名为: {new_path.name}（原因：{reason}）", "任务禁用")
        except Exception as e:
            Logger.error(f"禁用任务目录失败: {e}")
